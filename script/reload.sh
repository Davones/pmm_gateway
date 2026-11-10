#!/usr/bin/env bash
# 热重载 OKX PMM 网关 v2(修改 conf/nginx.conf 或 lua/rules.lua 后使用, 不中断流量)
# 用法: bash script/reload.sh
set -euo pipefail

V2_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OPENRESTY_BIN="${OPENRESTY_BIN:-/usr/local/openresty/nginx/sbin/nginx}"

if [ ! -f "$V2_DIR/logs/nginx.pid" ]; then
    echo "[reload] 网关未运行, 请先 bash script/start.sh" >&2
    exit 1
fi

if "$OPENRESTY_BIN" -p "$V2_DIR" -c conf/nginx.conf -t; then
    "$OPENRESTY_BIN" -p "$V2_DIR" -c conf/nginx.conf -s reload
    echo "[reload] 已热重载, 在途连接不受影响"
else
    echo "[reload] 配置校验失败, 保持旧配置运行(未重载)" >&2
    exit 1
fi
