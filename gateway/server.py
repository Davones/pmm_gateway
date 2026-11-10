import logging
import asyncio
import atexit
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse

from gateway.router import Router
from gateway.http_client import HTTPClient, close_http_client
import atexit

logger = logging.getLogger()

app = FastAPI(title="OKX PMM Gateway")

router: Optional[Router] = None


def get_client_ip(request: Request) -> str:
    # 网关前面可能挂了 ALB/nginx, 优先取转发头里的真实客户端 ip
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    return request.client.host if request.client else "unknown"


def init_gateway(routing_table, backend_map):
    global router
    router = Router(routing_table=routing_table, backend_map=backend_map)
    logger.info("Gateway initialized")
    atexit.register(lambda: asyncio.get_event_loop().run_until_complete(close_http_client()))


@app.get("/OKXDEX/rfq/pricing")
async def handle_pricing(request: Request):
    query_params = dict(request.query_params)
    client_ip = get_client_ip(request)
    logger.info(f"[{client_ip}] GET /OKXDEX/rfq/pricing params={query_params}")

    uri = "pricing"
    target_url = router.route(uri, query_params)

    if not target_url:
        logger.warning(f"[{client_ip}] No backend for pricing, returning empty levelData")
        return JSONResponse(
            content={"code": "0", "msg": "", "data": {"chainIndex": query_params.get("chainIndex", ""), "levelData": []}},
            status_code=200,
        )

    full_url = f"http://{target_url}/OKXDEX/rfq/pricing"

    try:
        async with HTTPClient() as client:
            response = await client.forward_request(
                method="GET",
                url=full_url,
                headers=dict(request.headers),
                params=query_params,
            )

        return JSONResponse(
            content=response.json() if response.headers.get("content-type", "").startswith("application/json") else {},
            status_code=response.status_code,
            headers=dict(response.headers),
        )
    except Exception as e:
        logger.warning(f"[{client_ip}] Pricing backend error: {e}, returning empty levelData")
        return JSONResponse(
            content={"code": "0", "msg": "", "data": {"chainIndex": query_params.get("chainIndex", ""), "levelData": []}},
            status_code=200,
        )


@app.post("/OKXDEX/rfq/firm-order")
async def handle_firm_order(request: Request):
    body_data = await request.json()
    client_ip = get_client_ip(request)
    logger.info(f"[{client_ip}] POST /OKXDEX/rfq/firm-order body={body_data}")

    uri = "firm-order"
    target_url = router.route(uri, body_data)

    if not target_url:
        logger.error(f"[{client_ip}] No backend available for firm-order")
        raise HTTPException(status_code=500, detail="No backend available for firm-order")

    full_url = f"http://{target_url}/OKXDEX/rfq/firm-order"

    async with HTTPClient() as client:
        response = await client.forward_request(
            method="POST",
            url=full_url,
            headers=dict(request.headers),
            json_data=body_data,
        )

    return JSONResponse(
        content=response.json() if response.headers.get("content-type", "").startswith("application/json") else {},
        status_code=response.status_code,
        headers=dict(response.headers),
    )


@app.get("/health")
async def health_check():
    return {"status": "ok"}