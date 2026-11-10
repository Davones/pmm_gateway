#!/usr/bin/env bash
# 重启 OKX PMM 网关 v2
# 用法: bash script/restart.sh
set -uo pipefail

V2_DIR="$(cd "$(dirname "$0")/.." && pwd)"

bash "$V2_DIR/script/stop.sh" || true
sleep 1
bash "$V2_DIR/script/start.sh"
