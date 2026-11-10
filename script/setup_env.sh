#!/usr/bin/env bash
# 在【生产/开发机器】上执行, 为网关准备 python 运行环境
#
#   cd /home/ec2-user/Production_Env/okx_pmm_gateway_Prd
#   bash script/setup_env.sh
#
# 做的事情:
#   1. 挑一个 >= 3.8 的 python 解释器
#   2. 在项目目录下建 ./venv 虚拟环境
#   3. 按 requirements.txt 安装依赖
#   4. 建 log 目录, 并做一次导入自检
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
echo "项目目录: ${PROJECT_DIR}"

# ---------- 1. 找 python ----------
PY=""
for c in python3.12 python3.11 python3.10 python3.9 python3.8 python3; do
    command -v "$c" >/dev/null 2>&1 || continue
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 8) else 1)' 2>/dev/null; then
        PY="$c"
        break
    fi
done

if [ -z "${PY}" ]; then
    cat >&2 <<'EOF'
[错误] 没有找到 >= 3.8 的 python (fastapi / pydantic v2 的最低要求)。
先装一个再重跑本脚本:
  Amazon Linux 2 :  sudo amazon-linux-extras install python3.8   # 或 sudo yum install -y python3.11
  Amazon Linux 2023 / RHEL9 : sudo yum install -y python3.11 python3.11-pip
  Ubuntu/Debian  :  sudo apt-get install -y python3 python3-venv python3-pip
EOF
    exit 1
fi
echo "使用解释器: ${PY} ($(${PY} -V 2>&1))"

# ---------- 2. 建 venv ----------
if [ ! -x "./venv/bin/python" ]; then
    echo "创建虚拟环境 ./venv ..."
    if ! "${PY}" -m venv ./venv 2>/dev/null; then
        # 有些发行版没带 ensurepip(python3-venv), 退回 virtualenv
        echo "python -m venv 不可用, 改用 virtualenv ..."
        "${PY}" -m pip install --user -q virtualenv
        "${PY}" -m virtualenv -q ./venv
    fi
else
    echo "已存在 ./venv, 跳过创建"
fi

# ---------- 3. 装依赖 ----------
./venv/bin/python -m pip install -q --upgrade pip setuptools wheel
echo "安装 requirements.txt ..."
./venv/bin/python -m pip install -r requirements.txt

# ---------- 4. 自检 ----------
mkdir -p log
echo "导入自检 ..."
./venv/bin/python - <<'PYCHECK'
import os, sys
sys.path.insert(0, os.getcwd())
import fastapi, uvicorn, httpx, pydantic, colorlog, pandas
from conf.config import AppConfig            # 会连带导入 python_library
from gateway.server import app               # noqa: F401
print("  依赖 OK, 监听地址 =", AppConfig.OKX_PMM_GETWAY_HOSTPORT)
PYCHECK

cat <<EOF

环境准备完成。启动方式:
  直接跑   : ${PROJECT_DIR}/venv/bin/python main.py
  supervisor: ${PROJECT_DIR}/venv/bin/python -m supervisor.supervisord -c conf/supervisord.conf
              (supervisor 需要单独装: ./venv/bin/pip install supervisor)
EOF
