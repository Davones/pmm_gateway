#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX PMM Gateway 压测脚本(并发版)

特性:
  - 令牌桶匀速放行 + 多 worker 并发, 能真实打满目标 QPS(原版串行发, 实际 QPS 被 RTT 卡死)
  - 每个请求默认使用【唯一 rfqId】(在 --rfqid-base 基础上递增), 用于和后端/网关日志精确配对
  - 每次压测结束打印【最慢的 10 个请求及其 rfqId】, 拿着 rfqId 去网关/后端日志里检索即可定位
  - --burst N: 突发模式, 同时发出 N 个请求, 模拟 OKX 突发流量(定位 10s 排队问题用)

定位 10s 延迟的标准流程:
  1. python3 stress_test.py --burst 2000 --csv burst.csv
  2. 从输出拿最慢的 rfqId; 在网关日志 grep "rfqId=xxx"(total/fwd 耗时)
  3. 拿同一批 rfqId 去后端日志 grep "收到请求"行, 对比时间戳:
     - 后端很快收到 -> 后端处理慢(Case A)
     - 后端 10s 后才收到 -> 网关转发段排队(Case B)

用法示例:
  python3 stress_test.py --probe 3                       # 探测
  python3 stress_test.py --qps 500 --duration 30         # 匀速压测 30s
  python3 stress_test.py --burst 2000 --timeout 60       # 突发 2000 并发
  python3 stress_test.py --qps 100 --duration 10 --csv r.csv --rfqid fixed  # 固定 rfqId
"""

import argparse
import asyncio
import csv
import itertools
import statistics
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import httpx

# ---------------- 默认参数 ----------------
GATEWAY_URL = "http://18.179.69.227:8080"
HEADERS = {
    "X-API-KEY": "newworld-api-key-Tm2s#88%sUs6",
    "Content-Type": "application/json",
}
FIRM_ORDER_BODY = {
    "requestType": "1",
    "confidenceCap": 1200,
    "orderId": "1002656950",
    "confidenceRate": 120,
    "takerAddress": "0x9a8d68089aDBe8428f79c244d34276a9f4251070",
    "takerAmount": "6531966352014705584",
    "beneficiaryAddress": "0x99c3b34110B26253c1057e48A641751Df3733B7a",
    "rfqId": 4690317726035214911,
    "chainIndex": "56",
    "confidenceT": 10,
    "makerAsset": "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",
    "expiryDuration": 20,
    "takerAsset": "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c",
}
PRICING_PARAMS = {"chainIndex": "56"}


# ---------------- 工具 ----------------
def percentile(sorted_values: List[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, int(len(sorted_values) * p))
    return sorted_values[idx]


class Pacing:
    """令牌桶式匀速放行: 保证单位时间内恰好发出 qps 个请求"""

    def __init__(self, qps: float):
        self.interval = 1.0 / qps
        self.next_time = time.perf_counter()
        self.lock = asyncio.Lock()

    async def wait(self):
        async with self.lock:
            now = time.perf_counter()
            wait = self.next_time - now
            if wait > 0:
                await asyncio.sleep(wait)
                self.next_time += self.interval
            else:
                self.next_time = now + self.interval


def build_body(
    body: Optional[Dict[str, Any]],
    rfqid_mode: str,
    counter: itertools.count,
    rfqid_base: int,
) -> Optional[Dict[str, Any]]:
    """unique 模式下每次返回一个 rfqId 递增的新 body"""
    if body is None or rfqid_mode == "fixed":
        return body
    b = dict(body)
    b["rfqId"] = rfqid_base + next(counter)
    return b


# ---------------- 请求发送 ----------------
def make_client(concurrency: int, timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        limits=httpx.Limits(
            max_connections=concurrency * 2 + 50,
            max_keepalive_connections=concurrency + 50,
        ),
    )


async def send_one(
    client: httpx.AsyncClient,
    url: str,
    method: str,
    body: Optional[Dict[str, Any]],
    params: Optional[Dict[str, Any]],
) -> Tuple[float, Optional[int], Optional[str]]:
    """返回 (延迟ms, status_code或None, 错误类别或None)"""
    t0 = time.perf_counter()
    try:
        if method == "GET":
            r = await client.get(url, params=params, headers=HEADERS)
        else:
            r = await client.post(url, json=body, headers=HEADERS)
        return (time.perf_counter() - t0) * 1000, r.status_code, None
    except httpx.TimeoutException:
        return (time.perf_counter() - t0) * 1000, None, "timeout"
    except httpx.ConnectError:
        return (time.perf_counter() - t0) * 1000, None, "connect"
    except httpx.ReadError:
        return (time.perf_counter() - t0) * 1000, None, "read"
    except httpx.RemoteProtocolError:
        return (time.perf_counter() - t0) * 1000, None, "protocol"
    except httpx.PoolTimeout:
        return (time.perf_counter() - t0) * 1000, None, "pool-timeout"
    except Exception as e:  # noqa: BLE001
        return (time.perf_counter() - t0) * 1000, None, f"other:{type(e).__name__}"


def fmt_slowest(slowest: List[Tuple], limit: int = 10) -> str:
    """格式化最慢请求清单(rfqId 用于日志检索)"""
    if not slowest:
        return ""
    lines = [f"最慢的 {min(limit, len(slowest))} 个请求(拿 rfqId 去网关/后端日志检索):"]
    lines.append(f"{'rfqId':>21} | {'latency':>9} | {'status':>7} | 错误")
    for lat, rid, err, status in sorted(slowest, key=lambda x: -x[0])[:limit]:
        lines.append(f"{rid:>21} | {lat:>8.1f}ms | {str(status or '-'):>7} | {err or ''}")
    return "\n".join(lines)


# ---------------- 单请求探测(诊断用) ----------------
async def run_probe(n, url, method, body, params, timeout, rfqid_mode, rfqid_base):
    print(f"probe: 依次发 {n} 个请求(单连接复用, rfqId 模式={rfqid_mode})\n")
    counter = itertools.count(0)
    async with make_client(concurrency=8, timeout=timeout) as client:
        for i in range(n):
            b = build_body(body, rfqid_mode, counter, rfqid_base)
            lat, status, err = await send_one(client, url, method, b, params)
            rid = b.get("rfqId") if isinstance(b, dict) else "-"
            if err:
                print(f"[{i+1}] rfqId={rid} 异常 {err}, 耗时 {lat:.1f} ms")
            else:
                print(f"[{i+1}] rfqId={rid} status={status} latency={lat:.1f} ms")
            await asyncio.sleep(0.5)


# ---------------- QPS 压测 ----------------
async def run_qps_test(
    qps, duration, concurrency, url, method, body, params, timeout,
    rfqid_mode, rfqid_base, csv_writer=None,
) -> Dict[str, Any]:
    pacing = Pacing(qps)
    counter = itertools.count(0)
    latencies: List[float] = []
    errors: Counter = Counter()
    statuses: Counter = Counter()
    slowest: List[Tuple] = []  # (lat, rfqid, err, status)
    generated = 0
    inflight = 0
    max_inflight = 0
    deadline = time.perf_counter() + duration

    async with make_client(concurrency=concurrency, timeout=timeout) as client:

        async def worker():
            nonlocal generated, inflight, max_inflight
            while True:
                if time.perf_counter() >= deadline:
                    return
                await pacing.wait()
                if time.perf_counter() >= deadline:
                    return
                b = build_body(body, rfqid_mode, counter, rfqid_base)
                generated += 1
                inflight += 1
                max_inflight = max(max_inflight, inflight)
                lat, status, err = await send_one(client, url, method, b, params)
                inflight -= 1
                rid = str(b.get("rfqId", "")) if isinstance(b, dict) else ""
                if err:
                    errors[err] += 1
                else:
                    latencies.append(lat)
                    statuses[status] += 1
                slowest.append((lat, rid, err, status))
                if csv_writer:
                    csv_writer.writerow(
                        [time.time(), f"{lat:.2f}", err or "", status or "", rid]
                    )

        await asyncio.gather(*[worker() for _ in range(concurrency)])

    start_time = deadline - duration
    actual_duration = time.perf_counter() - start_time
    actual_qps = generated / actual_duration if actual_duration > 0 else 0
    latencies.sort()
    n = len(latencies)

    return {
        "target_qps": int(qps),
        "actual_qps": actual_qps,
        "total": generated,
        "ok": n,
        "errors": sum(errors.values()),
        "error_breakdown": dict(errors),
        "status_breakdown": dict(statuses),
        "max_inflight": max_inflight,
        "avg_latency": statistics.mean(latencies) if latencies else 0,
        "min_latency": min(latencies) if latencies else 0,
        "max_latency": max(latencies) if latencies else 0,
        "p50": percentile(latencies, 0.50),
        "p90": percentile(latencies, 0.90),
        "p99": percentile(latencies, 0.99),
        "p999": percentile(latencies, 0.999),
        "slowest": slowest,
    }


# ---------------- 突发压测(模拟 OKX 突发) ----------------
async def run_burst(n, url, method, body, params, timeout, rfqid_mode, rfqid_base, csv_writer=None):
    print(f"burst: 同时发出 {n} 个请求 ...", flush=True)
    counter = itertools.count(0)
    t_start = time.perf_counter()
    async with make_client(concurrency=n, timeout=timeout) as client:
        bodies = [build_body(body, rfqid_mode, counter, rfqid_base) for _ in range(n)]
        results = await asyncio.gather(
            *[send_one(client, url, method, b, params) for b in bodies]
        )

    latencies: List[float] = []
    errors: Counter = Counter()
    statuses: Counter = Counter()
    slowest: List[Tuple] = []
    for b, (lat, status, err) in zip(bodies, results):
        rid = str(b.get("rfqId", "")) if isinstance(b, dict) else ""
        if err:
            errors[err] += 1
        else:
            latencies.append(lat)
            statuses[status] += 1
        slowest.append((lat, rid, err, status))
        if csv_writer:
            csv_writer.writerow([time.time(), f"{lat:.2f}", err or "", status or "", rid])

    total_duration = (time.perf_counter() - t_start) * 1000
    latencies.sort()
    m = len(latencies)
    r = {
        "total": n,
        "ok": m,
        "errors": sum(errors.values()),
        "error_breakdown": dict(errors),
        "status_breakdown": dict(statuses),
        "wall_ms": total_duration,
        "avg_latency": statistics.mean(latencies) if latencies else 0,
        "min_latency": min(latencies) if latencies else 0,
        "max_latency": max(latencies) if latencies else 0,
        "p50": percentile(latencies, 0.50),
        "p90": percentile(latencies, 0.90),
        "p99": percentile(latencies, 0.99),
        "p999": percentile(latencies, 0.999),
        "slowest": slowest,
    }
    print(f"\n{'='*72}")
    print(f"突发 {n} 请求完成, 全部收尾耗时 {total_duration/1000:.1f}s")
    print(f"成功: {r['ok']} | 失败: {r['errors']} | 失败率: {r['errors']/n*100:.1f}%")
    if r["error_breakdown"]:
        print(f"错误分布: {r['error_breakdown']}")
    if r["status_breakdown"]:
        print(f"状态码分布: {r['status_breakdown']}")
    print(f"延迟(ms): avg={r['avg_latency']:.1f} p50={r['p50']:.1f} p90={r['p90']:.1f} "
          f"p99={r['p99']:.1f} p999={r['p999']:.1f} max={r['max_latency']:.1f}")
    print()
    print(fmt_slowest(slowest))
    return r


def print_result(r: Dict[str, Any]):
    print(f"\n{'='*72}")
    print(f"目标 QPS: {r['target_qps']}  实际 QPS: {r['actual_qps']:.1f}  峰值并发: {r['max_inflight']}")
    print(f"{'='*72}")
    err_rate = r["errors"] / r["total"] * 100 if r["total"] else 0
    print(f"请求数: {r['total']} | 成功: {r['ok']} | 失败: {r['errors']} | 失败率: {err_rate:.2f}%")
    if r["error_breakdown"]:
        print(f"错误分布: {r['error_breakdown']}")
    if r["status_breakdown"]:
        print(f"状态码分布: {r['status_breakdown']}")
    print(
        f"延迟(ms): avg={r['avg_latency']:.1f} min={r['min_latency']:.1f} "
        f"max={r['max_latency']:.1f} p50={r['p50']:.1f} p90={r['p90']:.1f} "
        f"p99={r['p99']:.1f} p999={r['p999']:.1f}"
    )
    print()
    print(fmt_slowest(r.get("slowest", [])))


# ---------------- 入口 ----------------
def parse_args():
    p = argparse.ArgumentParser(description="OKX PMM Gateway 压测(并发版)")
    p.add_argument("--url", default=GATEWAY_URL, help="网关地址")
    p.add_argument(
        "--endpoint",
        default="firm-order",
        choices=["firm-order", "pricing", "health"],
        help="压测的接口",
    )
    p.add_argument("--qps", default="50,100,200,500,1000", help="逗号分隔的 QPS 档位")
    p.add_argument("--duration", type=float, default=30, help="每档压测时长(秒)")
    p.add_argument("--timeout", type=float, default=30, help="压测端单请求超时(秒)")
    p.add_argument(
        "--concurrency",
        type=int,
        default=0,
        help="并发 worker 数, 0=自动(约 qps*0.1, 至少 10)",
    )
    p.add_argument("--burst", type=int, default=0, metavar="N", help="突发模式: 同时发出 N 个请求")
    p.add_argument("--probe", type=int, default=0, metavar="N", help="只发 N 个探测请求逐个打印延迟")
    p.add_argument("--csv", default="", help="逐请求延迟落 CSV 文件(含 rfqId)")
    p.add_argument(
        "--rfqid",
        choices=["unique", "fixed"],
        default="unique",
        help="unique=每请求递增 rfqId(默认, 便于日志配对); fixed=固定 rfqId",
    )
    p.add_argument("--rfqid-base", type=int, default=FIRM_ORDER_BODY["rfqId"], help="unique 模式的 rfqId 起始值")
    return p.parse_args()


async def main():
    args = parse_args()

    if args.endpoint == "firm-order":
        url = f"{args.url}/OKXDEX/rfq/firm-order"
        method, body, params = "POST", FIRM_ORDER_BODY, None
    elif args.endpoint == "pricing":
        url = f"{args.url}/OKXDEX/rfq/pricing"
        method, body, params = "GET", None, PRICING_PARAMS
    else:
        url = f"{args.url}/health"
        method, body, params = "GET", None, None

    print(f"网关: {url}")
    print(f"压测端超时: {args.timeout}s  rfqId 模式: {args.rfqid}")

    if args.probe:
        await run_probe(args.probe, url, method, body, params, args.timeout, args.rfqid, args.rfqid_base)
        return

    csv_writer = None
    csv_file = None
    if args.csv:
        csv_file = open(args.csv, "w", newline="")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(["ts", "latency_ms", "error", "status", "rfq_id"])

    try:
        if args.burst:
            await run_burst(
                args.burst, url, method, body, params, args.timeout,
                args.rfqid, args.rfqid_base, csv_writer,
            )
            return

        qps_levels = [int(x) for x in args.qps.split(",") if x.strip()]
        print(f"QPS 档位: {qps_levels}  每档时长: {args.duration}s")

        results = []
        for qps in qps_levels:
            concurrency = args.concurrency or max(10, int(qps * 0.1))
            print(f"\n>>> 压测 {qps} QPS, {args.duration}s, {concurrency} workers ...", flush=True)
            r = await run_qps_test(
                qps, args.duration, concurrency, url, method, body, params, args.timeout,
                args.rfqid, args.rfqid_base, csv_writer,
            )
            results.append(r)
            print_result(r)

        print(f"\n{'='*72}")
        print("汇总")
        print(f"{'='*72}")
        print(
            f"{'QPS':>7} | {'实际QPS':>8} | {'avg':>8} | {'p50':>8} | {'p99':>8} | "
            f"{'p999':>8} | {'max':>8} | {'失败%':>6}"
        )
        for r in results:
            err_rate = r["errors"] / r["total"] * 100 if r["total"] else 0
            print(
                f"{r['target_qps']:>7} | {r['actual_qps']:>8.1f} | {r['avg_latency']:>8.1f} | "
                f"{r['p50']:>8.1f} | {r['p99']:>8.1f} | {r['p999']:>8.1f} | "
                f"{r['max_latency']:>8.1f} | {err_rate:>5.1f}%"
            )
    finally:
        if csv_file:
            csv_file.close()
            print(f"\n逐请求延迟已写入 {args.csv}")


if __name__ == "__main__":
    asyncio.run(main())
