
# 配置文件
scp ./conf/* ec2-user@18.179.69.227:/home/ec2-user/Development_Env/okx_pmm_gateway/conf

# 源代码
scp ./main.py ec2-user@18.179.69.227:/home/ec2-user/Development_Env/okx_pmm_gateway
scp -r ./gateway ec2-user@18.179.69.227:/home/ec2-user/Development_Env/okx_pmm_gateway

# # python_library
# scp -r ./python_library ec2-user@18.179.69.227:/home/ec2-user/Development_Env/okx_pmm_gateway


# scp ec2-user@18.179.69.227:/home/ec2-user/Development_Env/okx_pmm_gateway/log/01-realtime-all-20250411.log .