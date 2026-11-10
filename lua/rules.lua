-- ============================================================
-- 路由表: 与旧版 conf/prd/config.py 完全一致
-- 修改规则后执行 bash script/reload.sh 生效(优雅热重载, 不中断流量)
-- ============================================================

local _M = {}

-- 后端地址映射(对应旧版 BACKEND_SERVER_MAP)
_M.BACKEND_MAP = {
    pmmV2 = { host = "127.0.0.1", port = 19099 },
    pmmV1 = { host = "127.0.0.1", port = 1490 },
}

-- 路由表(对应旧版 OKX_PMM_REQUEST_ROUTING_TABLE)
-- 每条规则: uri + conditions({{字段, 正则}, ...}, AND 关系, 全部满足才命中) + target
-- 规则按顺序匹配, 首个命中的生效; conditions 为空 = 兜底规则
-- 正则语义: 前缀锚定 + 忽略大小写, 与旧版 re.match(re.IGNORECASE) 一致
_M.ROUTING_TABLE = {
    -- pricing
    { uri = "pricing",    conditions = { { "chainIndex", "1" } }, target = "pmmV2" },
    { uri = "pricing",    conditions = {},                        target = "pmmV1" },

    -- firm-order
    { uri = "firm-order", conditions = { { "chainIndex", "1" } }, target = "pmmV2" },
    -- 历史规则(保留注释, 与旧配置一致):
    -- { uri = "firm-order", conditions = { { "beneficiaryAddress", "0x.*[Ff]{2}$" } }, target = "pmmV1" },
    -- { uri = "firm-order", conditions = { { "chainIndex", "1" }, { "beneficiaryAddress", "0x.*[Ff]{2}$" } }, target = "pmmV2" },
    { uri = "firm-order", conditions = {},                        target = "pmmV1" },
}

return _M
