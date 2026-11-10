#!/usr/bin/env bash
# 部署 OKX PMM 网关 v2 (OpenResty) 到生产机
# 用法: bash script/scp_2_prd.sh
#
# 传完后在生产机执行(首次部署):
#   cd /home/ec2-user/Production_Env/okx_pmm_gateway_v2_Prd
#   bash script/install_openresty.sh    # 仅首次, 安装 OpenResty 运行时
#   bash script/start.sh                # 启动(监听 8081)
#   bash script/status.sh               # 查看状态
set -euo pipefail

HOST="ec2-user@18.179.69.227"
V2_HOME="/home/ec2-user/Production_Env/okx_pmm_gateway_v2_Prd"

ssh "$HOST" "mkdir -p $V2_HOME/{conf,lua,script,docs,logs}"

# 配置与核心代码
scp ./conf/nginx.conf "$HOST:$V2_HOME/conf/"
scp ./lua/rules.lua ./lua/gateway.lua "$HOST:$V2_HOME/lua/"
scp ./script/start.sh ./script/stop.sh ./script/restart.sh ./script/reload.sh \
    ./script/status.sh ./script/install_openresty.sh "$HOST:$V2_HOME/script/"

# 压测与日志分析工具
scp ./stress_test.py "$HOST:$V2_HOME"
scp ./log_correlate.py "$HOST:$V2_HOME"
scp ./script/parse_fwd.py "$HOST:$V2_HOME/script/"
scp -r ./docs "$HOST:$V2_HOME"

echo "部署完成。生产机操作:"
echo "  cd $V2_HOME && bash script/install_openresty.sh   # 仅首次"
echo "  bash script/start.sh                              # 启动, 监听 8081"
echo "  bash script/status.sh                             # 查看状态"
