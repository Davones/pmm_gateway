#!/usr/bin/env bash
# 查看 OKX PMM 网关 v2 运行状态
# 用法: bash script/status.sh
set -uo pipefail

V2_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8081/health}"

echo "== OKX PMM Gateway v2 状态 =="
if [ -f "$V2_DIR/logs/nginx.pid" ]; then
    PID="$(cat "$V2_DIR/logs/nginx.pid")"
    if kill -0 "$PID" 2>/dev/null; then
        echo "进程: 运行中 (master pid=$PID)"
        ps -o pid,ppid,%cpu,%mem,etime,cmd -p "$PID" | tail -1
    else
        echo "进程: 未运行(pid 文件存在但进程已死)"
    fi
else
    echo "进程: 未运行(无 pid 文件)"
fi

echo -n "健康检查: "
if curl -s -m 3 -o /dev/null -w "%{http_code}" "$HEALTH_URL" | grep -q 200; then
    echo "OK ($HEALTH_URL -> 200)"
else
    echo "失败 ($HEALTH_URL 无响应)"
fi

echo "日志: $V2_DIR/logs/access.log (耗时行)  $V2_DIR/logs/error.log (SLOW/错误)"
