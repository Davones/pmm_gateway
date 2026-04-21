
import os
import python_library.utils.baseconfig
import python_library.utils.logUtils
import python_library.utils.pandasUtils


class AppConfig(python_library.utils.baseconfig.BaseConfig):
    # define App config here...
    APP_CONFIG_SAMPLE = 'APP_CONFIG_SAMPLE'


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