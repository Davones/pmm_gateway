#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网关日志 <-> 后端日志 关联分析脚本

用途: 定位 "网关收到请求后 10s 后端才收到" 的瓶颈在哪一段。

原理:
  新版网关每请求输出一行耗时日志(含 rfqId / total / fwd):
    [ip] firm-order -> 127.0.0.1:1490 rfqId=4690317726035214911 total=10123ms fwd=10098ms (SLOW)
  后端在收到请求时也输出一行(需要含 rfqId 和日志时间戳)。

  按 rfqId 配对后计算:
    lag = 后端收到时间 - 网关 handler 开始时间(网关日志时间 - total)

判读(核心):
  lag 中位数 < 50ms 且 total 大       -> 慢在后端处理 (Case A): 后端很快收到, 处理了 10s。查后端 handler 内部
                                        (同步 DB/RPC/链上调用/全局锁/线程池太小)
  lag ≈ total ≈ 10s(此时 fwd 也大)    -> 慢在网关->后端传输段 (Case B): 网关连接池等待 或 后端 accept 队列堆积
                                        再配合: 网关日志里 504/PoolTimeout 多不多; 生产机上
                                        `ss -ltn | grep -E '1490|19099'` 看 Recv-Q 是否长期 > 0
  lag 大但 fwd 小                     -> 数据异常: 检查两台日志的时间戳格式/时区

用法(在生产机上, 两个日志在同一台机器):
  python3 log_correlate.py \
      --gateway-log log/supervisord_stdout.log \
      --backend-log <后端日志路径> \
      --backend-regex '<后端"收到请求"行的正则, 需含 (?P<ts>...) 和 (?P<rfqid>...) 命名组>'

后端正则示例(按后端实际日志格式调整):
  时间戳+任意内容+rfqId: '(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:[.,]\d+)?).*?rfqId[=:\s]+(?P<rfqid>\d+)'
  rfqId 在行首:           '(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:[.,]\d+)?)\s+.*?\b(?P<rfqid>\d{16,})\b'
"""

import argparse
import re
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# ---------------- 默认正则 ----------------
GATEWAY_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[.,]\d+).*?"
    r"\[(?P<ip>[^\]]+)\] (?P<endpoint>firm-order|pricing) -> (?P<target>\S+)"
    r"(?: (?P<id_field>rfqId|chainIndex)=(?P<id_val>\S+))?"
    r" total=(?P<total>\d+)ms fwd=(?P<fwd>\d+)ms"
)

BACKEND_RE_DEFAULT = (
    r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:[.,]\d+)?).*?rfqId[=:\s]+(?P<rfqid>\d+)"
)

TS_FORMATS = [
    "%Y-%m-%d %H:%M:%S,%f",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
]


def parse_ts(s: str) -> Optional[datetime]:
    for fmt in TS_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


# ---------------- 日志解析 ----------------
def parse_gateway_log(path: str) -> List[Dict]:
    """返回 [{ts, endpoint, target, id, total_ms, fwd_ms, raw}]"""
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = GATEWAY_RE.match(line)
            if not m:
                continue
            ts = parse_ts(m.group("ts"))
            if ts is None:
                continue
            rows.append(
                {
                    "ts": ts,
                    "endpoint": m.group("endpoint"),
                    "target": m.group("target"),
                    "id": m.group("id_val") if m.group("id_field") else None,
                    "id_field": m.group("id_field") or "",
                    "total_ms": int(m.group("total")),
                    "fwd_ms": int(m.group("fwd")),
                    "raw": line.strip(),
                }
            )
    return rows


def parse_backend_log(path: str, regex: re.Pattern) -> Dict[str, datetime]:
    """返回 {rfqId: 最早一条"收到请求"时间}"""
    found: Dict[str, datetime] = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = regex.search(line)
            if not m:
                continue
            ts = parse_ts(m.group("ts"))
            rfqid = m.group("rfqid")
            if ts is None or not rfqid:
                continue
            if rfqid not in found or ts < found[rfqid]:
                found[rfqid] = ts
    return found


# ---------------- 配对与分析 ----------------
def analyze(gateway_rows: List[Dict], backend_rows: Dict[str, datetime]):
    matched = 0
    unmatched = 0
    lags_ms: List[float] = []
    slow_detail: List[Tuple] = []

    for g in gateway_rows:
        if g["endpoint"] != "firm-order" or g["id_field"] != "rfqId":
            continue
        bid = g["id"]
        if bid is None or bid not in backend_rows:
            unmatched += 1
            continue

        matched += 1
        # 网关耗时行的日志时间 = 请求结束时; handler 开始 = 日志时间 - total
        handler_start = g["ts"] - timedelta(milliseconds=g["total_ms"])
        backend_recv = backend_rows[bid]
        lag_ms = (backend_recv - handler_start).total_seconds() * 1000
        lags_ms.append(lag_ms)

        if lag_ms > 100 or g["total_ms"] > 1000:
            slow_detail.append((lag_ms, g))

    if not lags_ms:
        print("没有配对成功任何请求, 请检查:")
        print("  1. 后端日志正则是否匹配到行(先单独 grep 验证)")
        print("  2. 后端日志里 rfqId 的写法(是 rfqId 还是 rfq_id?)")
        print("  3. 两边的日志时间戳格式是否被正确解析")
        return

    lags_ms.sort()
    n = len(lags_ms)
    print(f"配对成功: {matched}  网关有记录但后端日志找不到: {unmatched}")
    print(f"\nlag = 后端收到时刻 - 网关收到时刻(handler 开始)  [负值 = 时钟偏差, 正常应接近 0~几十 ms]")
    print(f"  min={lags_ms[0]:.0f}ms  p50={lags_ms[int(n*0.5)]:.0f}ms  p90={lags_ms[int(n*0.9)]:.0f}ms  "
          f"p99={lags_ms[int(n*0.99)]:.0f}ms  max={lags_ms[-1]:.0f}ms")

    # 网关 total/fwd 分布(配对上的请求)
    totals = sorted(g["total_ms"] for g in gateway_rows if g["endpoint"] == "firm-order" and g["id"] in backend_rows)
    fwds = sorted(g["fwd_ms"] for g in gateway_rows if g["endpoint"] == "firm-order" and g["id"] in backend_rows)
    if totals:
        m = len(totals)
        print(f"\n网关 total: p50={totals[int(m*0.5)]}ms p99={totals[int(m*0.99)]}ms max={totals[-1]}ms")
        print(f"网关 fwd  : p50={fwds[int(m*0.5)]}ms p99={fwds[int(m*0.99)]}ms max={fwds[-1]}ms")

    print(f"\n{'-'*80}")
    print("结论提示:")
    if statistics.median(lags_ms) < 50:
        print("  -> lag 中位数很小: 后端几乎立刻收到请求, 慢在后端【处理段】(Case A)")
        print("     查后端 handler: 同步 DB/Redis/RPC/链上调用? 全局锁? 单 worker? 线程池太小?")
    else:
        print("  -> lag 很大: 请求在网关转发到后端的【传输段】排队 (Case B)")
        print("     查: ① 网关日志 504/PoolTimeout 频率; ② 生产机 `ss -ltn | grep -E '1490|19099'` 的 Recv-Q")
        print("        ③ 后端 web 层 accept 队列/自身前置队列")

    if slow_detail:
        print(f"\n{'='*80}")
        print(f"慢请求明细 (lag>100ms 或 total>1s), 共 {len(slow_detail)} 条, 最多列 20 条:")
        print(f"{'lag(ms)':>10} | {'total':>6} | {'fwd':>6} | 网关日志行")
        for lag_ms, g in sorted(slow_detail, reverse=True)[:20]:
            print(f"{lag_ms:>10.0f} | {g['total_ms']:>6} | {g['fwd_ms']:>6} | {g['raw'][:150]}")


# ---------------- 入口 ----------------
def main():
    ap = argparse.ArgumentParser(description="网关/后端日志按 rfqId 关联分析")
    ap.add_argument("--gateway-log", required=True, help="网关日志(含新版耗时行)")
    ap.add_argument("--backend-log", required=True, help='后端日志(含"收到请求"行, 带 rfqId)')
    ap.add_argument("--backend-regex", default=BACKEND_RE_DEFAULT, help="后端行正则, 需含 (?P<ts>...) 与 (?P<rfqid>...)")
    args = ap.parse_args()

    try:
        backend_re = re.compile(args.backend_regex)
    except re.error as e:
        print(f"后端正则无效: {e}")
        return

    gateway_rows = parse_gateway_log(args.gateway_log)
    backend_rows = parse_backend_log(args.backend_log, backend_re)
    print(f"网关耗时行: {len(gateway_rows)}  后端收到请求行(去重后 rfqId 数): {len(backend_rows)}")
    if not gateway_rows:
        print("网关日志没有匹配到耗时行 — 确认日志里有 'total=...ms fwd=...ms' 格式的新版行")
        return
    if not backend_rows:
        print("后端日志没有匹配到任何行 — 用 --backend-regex 调整正则, 或先 grep 后端日志里的一条样例")
        return

    analyze(gateway_rows, backend_rows)


if __name__ == "__main__":
    main()
