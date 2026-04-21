import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__)) + os.path.sep + '../..'))

import asyncio
import logging
import uvicorn

from conf.config import utils_config_init, AppConfig
from gateway.server import init_gateway


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def main():
    setup_logging()
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
    )


if __name__ == '__main__':
    main()

# curl -v -X GET "http://127.0.0.1:8088/OKXDEX/rfq/pricing?chainIndex=56" -H "X-API-KEY: newworld-api-key-Tm2s#88%sUs6"
# curl -v -X POST "http://127.0.0.1:8088/OKXDEX/rfq/firm-order" -H "X-API-KEY: newworld-api-key-Tm2s#88%sUs6" -H "Content-Type: application/json" -d '{"chainIndex": "1", "takerAsset": "0x55d398326f99059ff775485246999027b3197955", "makerAsset": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "takerAmount": "1000000000000000000", "takerAddress": "0x1234567890abcdef1234567890abcdef12345678", "rfqId": 8234567890123, "expiryDuration": 40, "beneficiaryAddress": "0x949e4CcD90d661e2c68cB5CEDB9a13c0748bE1f1", "confidenceT": 5, "confidenceRate": 2000, "confidenceCap": 30000}'