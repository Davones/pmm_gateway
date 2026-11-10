#!/usr/bin/env bash
# 停止 OKX PMM 网关 v2(优雅停止: 处理完在途请求后退出)
# 用法: bash script/stop.sh
set -uo pipefail

V2_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OPENRESTY_BIN="${OPENRESTY_BIN:-/usr/local/openresty/nginx/sbin/nginx}"

if [ ! -f "$V2_DIR/logs/nginx.pid" ]; then
    echo "[stop] 未运行(无 pid 文件)"
    exit 0
fi

if "$OPENRESTY_BIN" -p "$V2_DIR" -c conf/nginx.conf -s quit 2>/dev/null; then
    echo "[stop] 已优雅停止(quit)"
else
    # 某些情况下 quit 可能超时, 退回 stop
    "$OPENRESTY_BIN" -p "$V2_DIR" -c conf/nginx.conf -s stop 2>/dev/null
    echo "[stop] 已停止(stop)"
fi
