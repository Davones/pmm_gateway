

import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + '../..'))

import asyncio
from datetime import datetime
import json
import logging
import time

from conf.config import utils_config_init, AppConfig
from python_library.utils.appUtils import AppUtils
from python_library.utils.logUtils import LogUtils


# 配置初始化
utils_config_init()

# 日志句柄
logger = logging.getLogger()




# LogUtils
LogUtils.init_log(log_name='python_library_demo3', console_log='INFO')
logger.debug("debug")
logger.info("info")
logger.warning("warning")
logger.error("error")
logger.critical("critical")



if __name__ == '__main__':

    # AppConfig demo
    print(AppConfig.OKX_PMM_GETWAY_HOSTPORT)
    print(AppConfig.BACKEND_SERVER_MAP)
    print(AppConfig.OKX_PMM_REQUEST_ROUTING_TABLE)
    pass