# OKX PMM 网关 — 压测与日志分析说明

> 目标读者: 后端(pmm 服务)同学。本文档说明如何从网关层发起压测、如何阅读网关日志、
> 以及如何用 rfqId 与后端日志对账,定位"慢在哪一段"。

---

## 1. 架构与拓扑

```
OKX DEX ──> 网关 v2 (OpenResty/nginx+LuaJIT, 18.179.69.227:8081)
            │  路由规则见 lua/rules.lua (与旧版 conf/prd/config.py 完全一致)
            │  (按请求字段正则匹配, chainIndex=1 → pmmV2, 其他 → pmmV1)
            ├──> pmmV1 = okx_dex_mm  监听 127.0.0.1:1490
            └──> pmmV2 = pmm_maker   监听 127.0.0.1:19099
```

- 网关是**纯转发层**:收到 OKX 的 RFQ 请求 → 按规则路由到后端 → 把后端响应原样透传回去。
- v2 基于 OpenResty:多 worker 事件驱动,天然抗突发(不存在旧版 Python 网关的
  httpcore 连接池 O(n²) 风暴问题——那是 2026-11-10 生产事故的根因)。
- 网关有**并发闸**:全局最多 200 个请求同时转发(跨 worker 精确计数),
  超出的请求**立即快速失败**(firm-order 返回 503,pricing 返回空 levelData),
  不会排队拖死;上游 OKX 超时/失败后会自行重试。
- v1(Python 网关,8080)与 v2(8081)并行运行,便于对比切换。

### 常用运维命令(生产机 v2 目录)

```bash
bash script/start.sh      # 启动(监听 8081)
bash script/stop.sh       # 优雅停止
bash script/restart.sh    # 重启
bash script/reload.sh     # 热重载(改路由规则后用, 不中断流量)
bash script/status.sh     # 查看状态 + 健康检查
curl http://127.0.0.1:8081/debug/counter   # 查看并发闸当前计数(压测后应为 0)
```

## 2. 压测脚本:stress_test.py

依赖:Python 3.8+,`pip install httpx`。在任意能访问网关的机器上运行。

### 三种模式

```bash
# ① 探测: 依次发 N 个请求, 逐个打印延迟(带 rfqId)
python3 stress_test.py --url http://18.179.69.227:8081 --probe 5

# ② 匀速压测: 500 QPS 持续 30 秒(令牌桶匀速放行, 真实打满目标 QPS)
python3 stress_test.py --url http://18.179.69.227:8081 --qps 500 --duration 30 --csv load500.csv

# ③ 突发压测(推荐用于复现后端高并发慢): 同时发出 N 个请求
python3 stress_test.py --url http://18.179.69.227:8081 --burst 2000 --timeout 40 --csv burst2000.csv
```

### 常用参数

| 参数 | 说明 |
|---|---|
| `--endpoint` | `firm-order`(默认)/ `pricing` / `health` |
| `--url` | 网关地址(v2 用 :8081,v1 用 :8080) |
| `--qps` | 逗号分隔的多档 QPS,如 `50,100,200,500` |
| `--duration` | 每档压测时长(秒) |
| `--burst N` | 突发模式:同时发 N 个请求 |
| `--timeout` | 压测端单请求超时(秒) |
| `--csv` | 逐请求结果落盘(ts, latency_ms, error, status, rfq_id) |
| `--rfqid` | `unique`(默认,每请求递增 rfqId,便于日志配对)/ `fixed` |
| `--rfqid-base` | unique 模式的起始 rfqId(默认 4690317726035214911) |

### 输出解读

每轮结束打印:延迟分布(avg/p50/p90/p99/max)、失败分布、状态码分布、
以及**最慢的 10 个请求及其 rfqId** —— 拿这些 rfqId 去网关/后端日志检索即可定位。

### 预期表现(v2 网关)

| 场景 | 预期 |
|---|---|
| 并发 ≤ 200 | 全部正常转发(200) |
| 突发 > 200 | 网关限流:最多 200 个进后端,其余**立即返回 503**(gateway busy) |
| 压测全程 | `curl http://18.179.69.227:8081/health` 应始终保持 200 |
| 匀速 ≤ 200 QPS | 延迟稳定;实际 QPS 上不去 = 后端吞吐瓶颈 |

⚠️ 压测请求是**真实业务请求**,会打到后端真实处理逻辑(rfqId 是递增的压测值,可按需过滤)。
⚠️ `--burst N` 模式下压测端自身把在途连接封顶在 500(压测客户端在更大并发下自身会退化),
突发压力以"打满即补"的方式维持;对网关并发闸(200)的验证不受影响。

## 3. 网关日志格式(v2)

两个日志文件(生产机 v2 目录):

| 文件 | 内容 |
|---|---|
| `logs/access.log` | **每请求 1 行耗时日志**(核心分析数据) |
| `logs/error.log` | SLOW 请求的 WARNING、后端错误的 ERROR、gateway busy 的 WARNING 等 |

### 耗时行格式(access.log,与 v1 同构)

```
2026-11-10 11:21:22.431 [47.243.1.144] firm-order -> 127.0.0.1:1490 rfqId=4690317726035215398 total=4516ms fwd=4220ms (SLOW) status=200
```

| 字段 | 含义 |
|---|---|
| 时间 | 请求**完成**时刻(网关已收到后端响应) |
| [47.243.1.144] | 客户端 IP(真实 OKX 流量;35.73.74.99 是压测机) |
| firm-order / pricing | 接口 |
| 127.0.0.1:1490 | 转发到的后端 |
| rfqId=… | 请求标识(firm-order 唯一;定价请求为 chainIndex=…) |
| total=4516ms | 网关处理总耗时:收到请求 → 返回响应 |
| fwd=4220ms | **转发耗时:网关发往后端 → 收到后端响应(含后端排队+处理+网络)** |
| (SLOW) | total > 1s 自动标记(同时在 error.log 打 WARNING) |
| status=200 | 返回给客户端的 HTTP 状态码 |

### 其他日志行(error.log)

| 日志 | 含义 | 网关动作 |
|---|---|---|
| `gateway busy: 200 concurrent forwards exceeded` | 并发闸满 | firm-order 回 **503**;pricing 回**空 levelData**(200) |
| `backend error after XXXms: status=502 fwd=...` | 转发异常(后端连接失败/读超时) | firm-order 回 **504**;pricing 回空 levelData |
| `No backend for pricing, returning empty levelData` | 路由未命中 | 回空 levelData(200) |
| `No backend available for firm-order` | 路由未命中 | 回 **500** |

### 网关侧耗时口径(重要)

- `total` = 网关处理总耗时;**`receipt_ts` = 日志时间 − total** = 网关把请求发往后端的时刻。
- `fwd` = 后端响应耗时 = (后端收到 → 后端响应) + 网络往返。**fwd ≈ total 说明时间都在等后端**。
- v2 与 v1 的耗时口径一致,两版网关的数据可直接对比。

## 4. 定位"慢在哪一段":rfqId 对账工作流

1. **压测**:`python3 stress_test.py --url http://18.179.69.227:8081 --burst 2000 --csv burst.csv`,取输出的最慢 rfqId;
2. **网关日志**:`grep "rfqId=4690317726035215467" logs/access.log`
   → 拿到 `total` / `fwd` 与 `receipt_ts`(日志时间 − total);
3. **后端日志**:用同一个 rfqId 检索后端"收到请求"的日志行 → 得到后端收到时刻 `T_recv` 与后端响应时刻;
4. **分三段算账**:

```
网关收到 ──[网关内部, µs级]──> 网关发出(receipt_ts)
        ──[网络+后端accept, 正常<10ms]──> 后端收到(T_recv)
        ──[后端处理]──> 后端响应
网关收到响应(fwd 终点)
```

判读:
- **后端收到晚**(T_recv − receipt_ts 大)→ 网络/accept 队列问题(网关侧或后端 web 层);
- **后端收到早、处理慢** → 后端业务逻辑慢(高并发下串行化/全局锁/外部调用),查后端 handler;
- 已知结论(2026-11-10):okx_dex_mm 在 **200 并发**下单请求处理拖到 **4.2 秒**,
  后端存在明显的串行化瓶颈(低并发时单请求仅 6ms)。

## 5. 批量分析工具

### parse_fwd.py — 网关日志转 CSV(v1/v2 通用)

```bash
# v2 网关:
python3 script/parse_fwd.py --log logs/access.log > fwd_report.csv
# v1 网关:
python3 script/parse_fwd.py --log log/supervisord_stdout.log > fwd_report.csv
```

输出每请求一行:`completion_ts, receipt_ts, client_ip, endpoint, target, id, total_ms, fwd_ms, slow, is_stress`。
id 字段用 `="..."` 包裹是防止 Excel 把 19 位 rfqId 当数字丢精度(grep 数字子串不受影响)。

### log_correlate.py — 网关/后端日志按 rfqId 自动配对

```bash
python3 log_correlate.py \
    --gateway-log logs/access.log \
    --backend-log <后端日志路径> \
    --backend-regex '<后端"收到请求"行的正则, 含 (?P<ts>…) 与 (?P<rfqid>…) 命名组>'
```

自动计算 `lag = 后端收到时刻 − 网关发出时刻` 的分布并给出结论提示:
- lag 中位数 < 50ms 且 total 大 → 后端处理慢(Case A);
- lag ≈ total ≈ 大 → 传输段排队(Case B)。

## 6. v2 与 v1 的差异点

| 项 | v1 (Python, 8080) | v2 (OpenResty, 8081) |
|---|---|---|
| 并发闸满 | 等 3 秒拿不到槽位 → 503 | **立即** → 503(快速失败更干脆) |
| 转发超时 | httpx 单请求总超时 5s | 连接 5s + 读间隔 5s(语义略宽, 对 localhost 后端无实质差异) |
| 路由规则 | conf/prd/config.py | lua/rules.lua(内容一致, 改完 `bash script/reload.sh` 热生效) |
| 日志位置 | log/supervisord_stdout.log | logs/access.log + logs/error.log |
| 规则更新 | 重启进程 | 优雅热重载,不中断流量 |
| 性能模型 | 单进程 asyncio(已发生过 O(n²) 风暴事故) | 多 worker 事件驱动,机制上免疫该事故 |

## 7. 历史事故与修复记录(2026-11-10)

- **事故**:v1 网关在突发高并发下数分钟无响应、后端 10 秒后才收到请求。
- **根因**:httpcore 连接池在"排队请求数 >> 连接数"时,每次请求到达/超时都做
  O(排队数×连接数) 全量重分配扫描,突发 2000 并发产生几十亿次同步调用,拖死网关事件循环。
- **v1 修复**:加并发闸(200)+ 池容量对齐,池内永不排队。修复后 burst 2000:927×200 + 1073×503,网关全程健康。
- **v2 重写**:用 OpenResty 从机制上消除该问题(见第 1、6 节),同时保留 v1 全部行为。
- **当前瓶颈**:后端串行化(firm-order ~300 QPS 饱和、pricing ~130 QPS 饱和;
  200 并发下单个请求拖到 ~4.2s)。网关本身 /health 500 QPS 无压力。
