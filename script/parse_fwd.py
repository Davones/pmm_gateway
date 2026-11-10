#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把网关日志中的耗时行解析成 CSV(供后端对账分析)
兼容 v1 (Python 网关) 与 v2 (OpenResty 网关) 两种日志格式。

输出列: completion_ts, receipt_ts, client_ip, endpoint, target, id, total_ms, fwd_ms, slow, is_stress
  - completion_ts: 网关返回响应时刻(日志时间)
  - receipt_ts:    网关把请求发往后端的时刻(= completion_ts - total_ms)
  - id:            firm-order 为 rfqId, pricing 为 chainIndex
                   字段用 ="..." 包裹, 防止 Excel 把 19 位 rfqId 当数字丢精度(grep 数字子串不受影响)
  - fwd_ms:        网关 -> 后端 -> 网关 的耗时(含后端排队+处理+网络), 核心指标
  - slow:          total > 1s 标记
  - is_stress:     来自压测机(默认 35.73.74.99)的流量标记为 1, 真实 OKX 流量为 0

用法:
  # v2 网关(OpenResty, 耗时行在 access.log)
  python3 script/parse_fwd.py --log logs/access.log > fwd_report.csv
  # v1 网关(Python, 耗时行在 supervisord_stdout.log)
  python3 script/parse_fwd.py --log log/supervisord_stdout.log > fwd_report.csv
"""

import argparse
import re
import sys
from datetime import datetime, timedelta

DEFAULT_LOG = "/home/ec2-user/Production_Env/okx_pmm_gateway_v2_Prd/logs/access.log"
DEFAULT_STRESS_IP = "35.73.74.99"

# v1 行: 2026-11-10 11:21:22,431 - root - WARNING - [ip] firm-order -> addr rfqId=X total=4516ms fwd=4220ms (SLOW)
# v2 行: 2026-11-10 11:21:22.431 [ip] firm-order -> addr rfqId=X total=4516ms fwd=4220ms (SLOW) status=200
TIMING_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[,.](\d{3}).*?"
    r"\[([^\]]+)\] (firm-order|pricing) -> (\S+)"
    r" (\w+)=(\S+)"
    r" total=(\d+)ms fwd=(-|\d+)ms( \(SLOW\))?(?: status=(\d+))?$"
)


def excel_id(v: str) -> str:
    # 防止 Excel 把 19 位 rfqId 当数字丢精度: 用 ="..." 文本形式
    return f'="{v}"' if v else ""


def main():
    ap = argparse.ArgumentParser(description="网关日志耗时行 -> CSV(v1/v2 通用)")
    ap.add_argument("--log", default=DEFAULT_LOG, help="网关日志路径")
    ap.add_argument("--stress-ip", default=DEFAULT_STRESS_IP, help="压测机 IP(标记 is_stress 用)")
    args = ap.parse_args()

    print("completion_ts,receipt_ts,client_ip,endpoint,target,id,total_ms,fwd_ms,slow,is_stress")
    n = 0
    with open(args.log, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = TIMING_RE.match(line)
            if not m:
                continue
            ts_s, ts_ms, ip, ep, target, idt, idv, total_s, fwd_s, slow, status = m.groups()
            try:
                dt = datetime.strptime(ts_s + "." + ts_ms, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                continue
            total = int(total_s)
            receipt = dt - timedelta(milliseconds=total)
            fwd_v = "-" if fwd_s == "-" else fwd_s
            is_stress = 1 if ip == args.stress_ip else 0
            print(
                f"{ts_s}.{ts_ms},{receipt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]},{ip},{ep},{target},"
                f"{excel_id(idv or '')},{total},{fwd_v},{1 if slow else 0},{is_stress}"
            )
            n += 1

    sys.stderr.write(f"rows={n}\n")


if __name__ == "__main__":
    main()
