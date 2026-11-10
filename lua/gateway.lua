-- ============================================================
-- OKX PMM 网关 v2 核心逻辑: 路由 / 并发闸 / 耗时日志
-- 行为与 v1 (Python 版) 对齐, 差异点见 docs/gateway_stress_test_and_log_analysis.md
-- ============================================================

local rules = require("rules")

-- 与 v1 并发闸一致的参数
local MAX_CONCURRENT_FORWARD = 200   -- 全局并发转发上限
local SLOW_THRESHOLD_MS = 1000       -- total 超过该值打 (SLOW) 标记

local _M = {}

-- ---------------- 并发闸(shared dict 全局计数, 跨 worker 生效) ----------------
-- v1 是"等 3 秒拿不到槽位再失败", v2 简化为"立即失败":
-- 做市网关快速失败优于排队, 上游 OKX 会自行重试。

local function try_acquire()
    local dict = ngx.shared.gw_active
    local n, err = dict:incr("active", 1, 0)
    if not n then
        ngx.log(ngx.ERR, "limit dict error: ", err)
        return true   -- 计数不可用时放行, 避免误伤
    end
    if n > MAX_CONCURRENT_FORWARD then
        dict:incr("active", -1, 0)   -- 回滚
        return false
    end
    return true
end

local function release()
    local dict = ngx.shared.gw_active
    dict:incr("active", -1, 0)
end

-- ---------------- 工具 ----------------
local function get_client_ip()
    local xff = ngx.var.http_x_forwarded_for
    if xff and xff ~= "" then
        local first = string.match(xff, "^%s*([^,]+)")
        if first then
            return first
        end
    end
    local real = ngx.var.http_x_real_ip
    if real and real ~= "" then
        return real
    end
    return ngx.var.remote_addr
end

-- 从原始 JSON body 文本中提取字段。
-- 故意不用 cjson 解析: 19 位 rfqId 超过 LuaJIT double 的 2^53 精度, 会丢精度;
-- body 原样透传给后端, 不重新编码。
local function extract_field(body, field, is_string)
    if is_string then
        return body:match('"' .. field .. '"%s*:%s*"([^"]*)"')
    end
    return body:match('"' .. field .. '"%s*:%s*(-?%d+)')
end

-- 条件匹配: 全部满足才算命中(AND); 字段缺失直接不命中。
-- ngx.re.match 是前缀锚定(与旧版 re.match 语义一致), "io" = 忽略大小写 + 编译缓存。
local function match_conditions(conditions, fields)
    if not conditions or #conditions == 0 then
        return true
    end
    for _, cond in ipairs(conditions) do
        local field, pattern = cond[1], cond[2]
        local value = fields[field]
        if value == nil then
            return false
        end
        if not ngx.re.match(value, pattern, "io") then
            return false
        end
    end
    return true
end

local function route(uri, fields)
    for _, rule in ipairs(rules.ROUTING_TABLE) do
        if rule.uri == uri and match_conditions(rule.conditions, fields) then
            return rules.BACKEND_MAP[rule.target]
        end
    end
    return nil
end

-- 设置转发与日志所需的 nginx 变量(access -> balancer 通过变量传递, ngx.ctx 跨阶段不可见)
-- 注意: ngx.ctx 在 error_page 内部跳转后不复存在(会丢 release),
-- 所以"已获取/已释放"标志用 ngx.var 传递(变量可跨内部跳转存活)

local function set_vars(endpoint, backend, id_field, id_value)
    ngx.var.gw_endpoint = endpoint
    ngx.var.gw_backend = backend and (backend.host .. ":" .. backend.port) or "-"
    ngx.var.gw_id_field = id_field
    ngx.var.gw_id = id_value or "?"
    if backend then
        ngx.var.gw_backend_host = backend.host
        ngx.var.gw_backend_port = backend.port
    end
end

local function mark_acquired()
    ngx.var.gw_acquired = "1"
end

-- ---------------- pricing ----------------
function _M.access_pricing()
    local fields = { chainIndex = ngx.var.arg_chainIndex }
    local backend = route("pricing", fields)
    set_vars("pricing", backend, "chainIndex", fields.chainIndex)

    if not backend then
        ngx.log(ngx.WARN, "[", get_client_ip(), "] No backend for pricing, returning empty levelData")
        return _M.empty_pricing_response()
    end

    if not try_acquire() then
        ngx.log(ngx.WARN, "[", get_client_ip(), "] pricing gateway busy, returning empty levelData")
        return _M.empty_pricing_response()
    end
    mark_acquired()
end

function _M.empty_pricing_response()
    ngx.status = ngx.HTTP_OK
    ngx.header.content_type = "application/json"
    ngx.say('{"code":"0","msg":"","data":{"chainIndex":"' .. (ngx.var.arg_chainIndex or "")
        .. '","levelData":[]}}')
    return ngx.exit(ngx.HTTP_OK)
end

-- ---------------- firm-order ----------------
function _M.access_firm_order()
    ngx.req.read_body()
    local body = ngx.req.get_body_data() or ""
    local fields = {
        chainIndex = extract_field(body, "chainIndex", true),
        beneficiaryAddress = extract_field(body, "beneficiaryAddress", true),
        rfqId = extract_field(body, "rfqId", false),
    }
    local backend = route("firm-order", fields)
    set_vars("firm-order", backend, "rfqId", fields.rfqId)

    if not backend then
        ngx.log(ngx.ERR, "[", get_client_ip(), "] No backend available for firm-order")
        ngx.header.content_type = "application/json"
        ngx.say('{"detail":"No backend available for firm-order"}')
        return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
    end

    if not try_acquire() then
        ngx.log(ngx.WARN, "[", get_client_ip(), "] firm-order rfqId=", fields.rfqId or "?",
            " gateway busy: ", MAX_CONCURRENT_FORWARD, " concurrent forwards exceeded")
        ngx.status = ngx.HTTP_SERVICE_UNAVAILABLE
        ngx.header.content_type = "application/json"
        ngx.say('{"detail":"gateway busy"}')
        return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
    end
    mark_acquired()
end

-- ---------------- balancer(动态后端选择) ----------------
function _M.balance()
    local balancer = require("ngx.balancer")   -- 独立模块, 必须显式 require
    local host = ngx.var.gw_backend_host
    local port = tonumber(ngx.var.gw_backend_port)
    if not host or not port then
        ngx.log(ngx.ERR, "balancer: no backend selected")
        return ngx.exit(ngx.HTTP_INTERNAL_SERVER_ERROR)
    end
    local ok, err = balancer.set_current_peer(host, port)
    if not ok then
        ngx.log(ngx.ERR, "balancer: set_current_peer failed: ", err)
        return ngx.exit(ngx.HTTP_SERVICE_UNAVAILABLE)
    end
end

-- ---------------- 耗时日志(log 阶段, 每请求执行一次) ----------------
function _M.log_request()
    -- 幂等释放: 主 location 与 fallback location 只会有一个执行 log 阶段,
    -- 但加 guard 防止未来 nginx 版本行为变化导致双释放。
    -- 注意用 ngx.var 而非 ngx.ctx: ctx 在 error_page 内部跳转后不复存在
    if ngx.var.gw_acquired == "1" and ngx.var.gw_released ~= "1" then
        ngx.var.gw_released = "1"
        release()
    end

    local total_s = tonumber(ngx.var.request_time) or 0
    local total_ms = string.format("%.0f", total_s * 1000)

    local fwd_s = ngx.var.upstream_response_time
    local fwd_ms = "-ms"
    if fwd_s and fwd_s ~= "-" then
        fwd_ms = string.format("%.0fms", tonumber(fwd_s) * 1000)
    end

    ngx.var.gw_total_ms = total_ms .. "ms"
    ngx.var.gw_fwd_ms = fwd_ms
    if total_s * 1000 > SLOW_THRESHOLD_MS then
        ngx.var.gw_slow = " (SLOW)"
    else
        ngx.var.gw_slow = ""
    end
    ngx.var.gw_ts = string.format("%s.%03d", os.date("%Y-%m-%d %H:%M:%S"),
        math.floor(ngx.now() * 1000) % 1000)
    ngx.var.gw_client_ip = get_client_ip()

    local endpoint = ngx.var.gw_endpoint or "-"
    local id_field = ngx.var.gw_id_field or "id"
    local id_value = ngx.var.gw_id or "?"

    if ngx.var.gw_slow ~= "" then
        ngx.log(ngx.WARN, "[", get_client_ip(), "] ", endpoint, " -> ",
            ngx.var.gw_backend or "-", " ", id_field, "=", id_value,
            " total=", total_ms, "ms fwd=", fwd_ms, " (SLOW)")
    end

    local status = ngx.status
    if status and status >= 500 then
        ngx.log(ngx.ERR, "[", get_client_ip(), "] ", endpoint, " ", id_field, "=", id_value,
            " backend error after ", total_ms, "ms: status=", status, " fwd=", fwd_ms)
    end
end

return _M
