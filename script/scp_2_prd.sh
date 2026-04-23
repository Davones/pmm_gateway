
# 配置文件
scp ./conf/prd/* ec2-user@18.179.69.227:/home/ec2-user/Production_Env/okx_pmm_gateway_Prd/conf

# 源代码
scp ./main.py ec2-user@18.179.69.227:/home/ec2-user/Production_Env/okx_pmm_gateway_Prd
scp -r ./gateway ec2-user@18.179.69.227:/home/ec2-user/Production_Env/okx_pmm_gateway_Prd

# # python_library
# scp -r ./python_library ec2-user@18.179.69.227:/home/ec2-user/Production_Env/okx_pmm_gateway_Prd


# scp ec2-user@18.179.69.227:/home/ec2-user/Production_Env/okx_pmm_gateway_Prd/log/01-realtime-all-20250411.log .