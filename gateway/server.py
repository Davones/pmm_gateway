import logging
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import JSONResponse

from gateway.router import Router
from gateway.http_client import HTTPClient

logger = logging.getLogger()

app = FastAPI(title="OKX PMM Gateway")

router: Optional[Router] = None


def init_gateway(routing_table, backend_map):
    global router
    router = Router(routing_table=routing_table, backend_map=backend_map)
    logger.info("Gateway initialized")


@app.get("/OKXDEX/rfq/pricing")
async def handle_pricing(request: Request):
    query_params = dict(request.query_params)

    uri = "pricing"
    target_url = router.route(uri, query_params)

    if not target_url:
        raise HTTPException(status_code=500, detail="No backend available for pricing")

    full_url = f"http://{target_url}/OKXDEX/rfq/pricing"

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


@app.post("/OKXDEX/rfq/firm-order")
async def handle_firm_order(request: Request):
    body_data = await request.json()

    uri = "firm-order"
    target_url = router.route(uri, body_data)

    if not target_url:
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