import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + '../..'))

import asyncio
import faulthandler
import logging
import signal
import uvicorn

from conf.config import utils_config_init, AppConfig
from gateway.server import init_gateway


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    # 压掉 httpx/httpcore 每请求一条的 INFO 日志(高 QPS 下是同步写开销)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def setup_faulthandler():
    # 排障用: 生产进程卡死/空转时, 执行 `kill -USR1 <pid>` 会把全部线程的
    # Python 堆栈打到 stderr(日志文件), 进程不退出。
    faulthandler.enable()
    try:
        faulthandler.register(signal.SIGUSR1, all_threads=True, chain=False)
    except Exception:
        pass


def main():
    setup_logging()
    setup_faulthandler()
    utils_config_init()

    logger = logging.getLogger()

    init_gateway(
        routing_table=AppConfig.OKX_PMM_REQUEST_ROUTING_TABLE,
        backend_map=AppConfig.BACKEND_SERVER_MAP,
    )

    host, port = AppConfig.OKX_PMM_GETWAY_HOSTPORT
    logger.info(f"Starting OKX PMM Gateway on {host}:{port}")

    from gateway.server import app
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
        # 关闭 uvicorn 访问日志: 高 QPS 下每请求多一次同步写日志,
        # 请求级日志已由 gateway/server.py 的 _log_request_timing 统一输出
        access_log=False,
    )


if __name__ == '__main__':
    main()

# curl -v -X GET "http://127.0.0.1:1495/OKXDEX/rfq/pricing?chainIndex=56" -H "X-API-KEY: newworld-api-key-Tm2s#88%sUs6"
# curl -v -X POST "http://127.0.0.1:1495/OKXDEX/rfq/firm-order" -H "X-API-KEY: newworld-api-key-Tm2s#88%sUs6" -H "Content-Type: application/json" -d '{"chainIndex": "56", "takerAsset": "0x55d398326f99059ff775485246999027b3197955", "makerAsset": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "takerAmount": "1000000000000000000", "takerAddress": "0x1234567890abcdef1234567890abcdef12345678", "rfqId": 8234567890123, "expiryDuration": 40, "beneficiaryAddress": "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd", "confidenceT": 5, "confidenceRate": 2000, "confidenceCap": 30000}'
# curl -v -X POST "http://127.0.0.1:1495/OKXDEX/rfq/firm-order" -H "X-API-KEY: newworld-api-key-Tm2s#88%sUs6" -H "Content-Type: application/json" -d '{"chainIndex": "56", "takerAsset": "0x55d398326f99059ff775485246999027b3197955", "makerAsset": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "takerAmount": "1000000000000000000", "takerAddress": "0x1234567890abcdef1234567890abcdef12345678", "rfqId": 8234567890123, "expiryDuration": 40, "beneficiaryAddress": "0x949e4CcD90d661e2c68cB5CEDB9a13c0748bE1f6", "confidenceT": 5, "confidenceRate": 2000, "confidenceCap": 30000}'

# curl -v -X POST "http://127.0.0.1:1495/OKXDEX/rfq/firm-order" -H "X-API-KEY: newworld-api-key-Tm2s#88%sUs6" -H "Content-Type: application/json" -d '{"chainIndex": "56", "takerAsset": "0x55d398326f99059ff775485246999027b3197955", "makerAsset": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "takerAmount": "1000000000000000000", "takerAddress": "0x1234567890abcdef1234567890abcdef12345678", "rfqId": 8234567890123, "expiryDuration": 40, "beneficiaryAddress": "0x949e4CcD90d661e2c68cB5CEDB9a13c0748bE1ff", "confidenceT": 5, "confidenceRate": 2000, "confidenceCap": 30000}'