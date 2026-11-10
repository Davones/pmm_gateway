#!/usr/bin/env bash
# 安装 OpenResty(生产机只需执行一次; 需要 sudo 权限)
# 用法: bash script/install_openresty.sh
# 支持: Amazon Linux 2 / CentOS (yum), Ubuntu / Debian (apt)
set -euo pipefail

NGINX_BIN=/usr/local/openresty/nginx/sbin/nginx

if [ -x "$NGINX_BIN" ]; then
    "$NGINX_BIN" -v
    echo "OpenResty 已安装, 跳过"
    exit 0
fi

if command -v yum >/dev/null 2>&1; then
    echo "检测到 yum (Amazon Linux / CentOS) ..."
    sudo yum install -y yum-utils
    sudo yum-config-manager --add-repo https://openresty.org/package/amazon/openresty.repo
    sudo yum install -y openresty
elif command -v apt-get >/dev/null 2>&1; then
    echo "检测到 apt (Ubuntu / Debian) ..."
    sudo apt-get update
    sudo apt-get install -y --no-install-recommends wget gnupg ca-certificates lsb-release
    wget -qO - https://openresty.org/package/pubkey.gpg | sudo apt-key add -
    echo "deb http://openresty.org/package/ubuntu $(lsb_release -sc) main" \
        | sudo tee /etc/apt/sources.list.d/openresty.list
    sudo apt-get update
    sudo apt-get install -y openresty
else
    echo "不支持的系统, 请手动安装: https://openresty.org/cn/installation.html" >&2
    exit 1
fi

"$NGINX_BIN" -v
echo "安装完成, 可执行: bash script/start.sh"
