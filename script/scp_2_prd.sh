
# 配置文件
scp ./conf/prd/* ec2-user@18.179.69.227:/home/ec2-user/Production_Env/okx_pmm_gateway_Prd/conf

# 源代码
scp ./main.py ec2-user@18.179.69.227:/home/ec2-user/Production_Env/okx_pmm_gateway_Prd
scp -r ./gateway ec2-user@18.179.69.227:/home/ec2-user/Production_Env/okx_pmm_gateway_Prd

# 依赖清单 + 环境安装脚本 (首次部署/依赖变更时才需要)
scp ./requirements.txt ec2-user@18.179.69.227:/home/ec2-user/Production_Env/okx_pmm_gateway_Prd
scp ./script/setup_env.sh ec2-user@18.179.69.227:/home/ec2-user/Production_Env/okx_pmm_gateway_Prd/script/

# python_library (打包传输并排除本地 venv/缓存; 不要用 scp -r, 会把 83M 的 venv 一起传过去)
tar czf - --exclude='venv' --exclude='__pycache__' --exclude='.git' ./python_library \
    | ssh ec2-user@18.179.69.227 'tar xzf - -C /home/ec2-user/Production_Env/okx_pmm_gateway_Prd'

# 传完后在生产机执行:
#   cd /home/ec2-user/Production_Env/okx_pmm_gateway_Prd && bash script/setup_env.sh


# scp ec2-user@18.179.69.227:/home/ec2-user/Production_Env/okx_pmm_gateway_Prd/log/01-realtime-all-20250411.log .