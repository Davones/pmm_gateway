#!/usr/bin/env bash
# 启动 OKX PMM 网关 v2 (OpenResty)
# 用法: bash script/start.sh
set -euo pipefail

V2_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OPENRESTY_BIN="${OPENRESTY_BIN:-/usr/local/openresty/nginx/sbin/nginx}"

if [ ! -x "$OPENRESTY_BIN" ]; then
    echo "[start] 找不到 OpenResty: $OPENRESTY_BIN" >&2
    echo "[start] 请先在生产机执行: bash script/install_openresty.sh" >&2
    exit 1
fi

mkdir -p "$V2_DIR/logs/tmp"

# 先校验配置, 失败不启动
if ! "$OPENRESTY_BIN" -p "$V2_DIR" -c conf/nginx.conf -t; then
    echo "[start] nginx 配置校验失败, 未启动" >&2
    exit 1
fi

"$OPENRESTY_BIN" -p "$V2_DIR" -c conf/nginx.conf
echo "[start] OKX PMM Gateway v2 已启动"
echo "[start] prefix=$V2_DIR  监听 8081  pid 见 logs/nginx.pid"
