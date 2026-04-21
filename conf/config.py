
import os
from typing import List

import python_library.utils.baseconfig
import python_library.utils.logUtils
import python_library.utils.pandasUtils

class MatchRule:
    field: str  # 请求的字段
    regex: str  # 该字段的正则匹配规则

    def __init__(self, field: str, regex: str):
        self.field = field
        self.regex = regex

class RoutingRule:
    uri: str    # 请求的uri
    conditions: List[MatchRule]
    target: str

    def __init__(self, uri: str, conditions: List[MatchRule], target: str):
        self.uri = uri
        self.conditions = conditions
        self.target = target


class AppConfig(python_library.utils.baseconfig.BaseConfig):
    # define App config here...
    # okx网关监听的本地地址
    OKX_PMM_GETWAY_HOSTPORT = ("172.31.24.73", 8088)
    BACKEND_SERVER_MAP = {
        "pmmV2": "127.0.0.1:1495",
        "pmmV1": "127.0.0.1:8080",
    }
    OKX_PMM_REQUEST_ROUTING_TABLE = [
        # pricing
        RoutingRule(uri='pricing', conditions=[MatchRule(field='chainIndex', regex='1')], target="pmmV2"), # 针对 "pricing接口" 的路由规则: 如果 "chainIndex" 字段正则匹配 '1' 成功; 则将请求路由到 pmmV2
        RoutingRule(uri='pricing', conditions=[], target="pmmV1"), # 针对 "pricing接口" 的路由规则: 无需任何条件, 默认路由到 pmmV1 中去 (如果上面的条件均不匹配, 那么就会走这个路由)

        # firm-order
        RoutingRule(uri='firm-order', conditions=[MatchRule(field='chainIndex', regex='1')], target="pmmV2"), # 针对 "firm-order接口" 的路由规则: 如果 "chainIndex" 字段正则匹配 '1' 成功; 则将请求路由到 pmmV2
        RoutingRule(uri='firm-order', conditions=[MatchRule(field='chainIndex', regex='56'), MatchRule(field='beneficiaryAddress', regex='0x949e4CcD90d661e2c68cB5CEDB9a13c0748bE1f6')], target="pmmV2"), # 针对 "firm-order接口" 的路由规则, 如果: 1. "chainIndex" 字段正则匹配 '56' 成功; 2. "beneficiaryAddress" 字段正则匹配 "..." 成功; 则将请求路由到 pmmV2
        RoutingRule(uri='firm-order', conditions=[], target="pmmV1"), # 针对 "firm-order接口" 的路由规则: 无需任何条件, 默认路由到 pmmV1 中去 (如果上面的条件均不匹配, 那么就会走这个路由)
    ]


def utils_config_init():
    # 基础配置 - 项目根路径
    python_library.utils.logUtils.BaseConfig.APP_ROOT_PATH = os.path.abspath(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + '..')

    # 日志utils
    python_library.utils.logUtils.LogConfig.LOG_LEVEL = "DEBUG"

    # # pandas 库配置
    # python_library.utils.pandasUtils.PandasUtils.pandas_config_init()

    # # 交易所配置
    # python_library.pyApi.api_cex.exchange_config.ExchangeConfig.BINANCE_APIKEY = '(BINANCE_APIKEY)'
    # python_library.pyApi.api_cex.exchange_config.ExchangeConfig.BINANCE_SECRET = '(BINANCE_SECRET)'

    # # mysql配置
    # python_library.utils.mysqlUtils.MysqlConfig.MYSQL_HOST = '(MYSQL_HOST)'
    # python_library.utils.mysqlUtils.MysqlConfig.MYSQL_PASSWORD = '(MYSQL_PASSWORD)'

    # # tushare配置
    # python_library.pyApi.api_stock.stock_config.StockApiConfig.TUSHARE_TOKEN = '(TUSHARE_TOKEN)'

    # # redis配置
    # python_library.pyCli.redisClient.RedisConfig.REDIS_PASSWD = "(REDIS_PASSWD)"

    # # cache配置
    # python_library.utils.cacheUtils.GlobalCacheConfig.GLOBAL_CACHE_REDIS_KEY = "(GLOBAL_CACHE_REDIS_KEY)"

utils_config_init()