import logging
import time
import asyncio
import atexit
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse

from gateway.router import Router
from gateway.http_client import (
    forward_request,
    close_http_client,
    filter_response_headers,
    ForwardBusyError,
)

logger = logging.getLogger()

app = FastAPI(title="OKX PMM Gateway")

router: Optional[Router] = None

# 超过该耗时(ms)的请求打 WARN, 用于定位慢请求
SLOW_REQUEST_THRESHOLD_MS = 1000


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


def _log_request_timing(
    client_ip: str, endpoint: str, target: str, total_ms: float, fwd_ms: float, req_id: Optional[str] = None
):
    """统一的请求耗时日志: 1 行/请求, 慢请求升级为 WARNING

    total_ms: 网关处理总耗时(收到请求 -> 返回响应)
    fwd_ms:   转发到后端的耗时(诊断时区分: 慢在网关转发段还是后端处理段)
    req_id:   请求标识(rfqId/chainIndex), 用于和后端"收到请求"日志精确配对
    """
    id_part = f" {req_id}" if req_id else ""
    line = f"[{client_ip}] {endpoint} -> {target}{id_part} total={total_ms:.0f}ms fwd={fwd_ms:.0f}ms"
    if total_ms > SLOW_REQUEST_THRESHOLD_MS:
        logger.warning(f"{line} (SLOW)")
    else:
        logger.info(line)


def _proxy_response(response) -> Response:
    """透传后端响应字节, 避免 JSON 解析后再序列化的双重开销"""
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=filter_response_headers(dict(response.headers)),
    )


def _empty_pricing_response(query_params: Dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        content={"code": "0", "msg": "", "data": {"chainIndex": query_params.get("chainIndex", ""), "levelData": []}},
        status_code=200,
    )


@app.get("/OKXDEX/rfq/pricing")
async def handle_pricing(request: Request):
    t0 = time.perf_counter()
    query_params = dict(request.query_params)
    client_ip = get_client_ip(request)
    logger.debug(f"[{client_ip}] GET /OKXDEX/rfq/pricing params={query_params}")

    target_url = router.route("pricing", query_params)
    if not target_url:
        logger.warning(f"[{client_ip}] No backend for pricing, returning empty levelData")
        return _empty_pricing_response(query_params)

    full_url = f"http://{target_url}/OKXDEX/rfq/pricing"

    try:
        t1 = time.perf_counter()
        response = await forward_request(
            method="GET",
            url=full_url,
            headers=dict(request.headers),
            params=query_params,
        )
        fwd_ms = (time.perf_counter() - t1) * 1000
        total_ms = (time.perf_counter() - t0) * 1000
        _log_request_timing(
            client_ip, "pricing", target_url, total_ms, fwd_ms,
            req_id=f"chainIndex={query_params.get('chainIndex', '?')}",
        )
        return _proxy_response(response)
    except Exception as e:
        total_ms = (time.perf_counter() - t0) * 1000
        logger.warning(
            f"[{client_ip}] Pricing backend error after {total_ms:.0f}ms: "
            f"{type(e).__name__}: {e}, returning empty levelData"
        )
        return _empty_pricing_response(query_params)


@app.post("/OKXDEX/rfq/firm-order")
async def handle_firm_order(request: Request):
    t0 = time.perf_counter()
    body_data = await request.json()
    client_ip = get_client_ip(request)
    logger.debug(f"[{client_ip}] POST /OKXDEX/rfq/firm-order body={body_data}")

    target_url = router.route("firm-order", body_data)
    if not target_url:
        logger.error(f"[{client_ip}] No backend available for firm-order")
        raise HTTPException(status_code=500, detail="No backend available for firm-order")

    full_url = f"http://{target_url}/OKXDEX/rfq/firm-order"

    try:
        t1 = time.perf_counter()
        response = await forward_request(
            method="POST",
            url=full_url,
            headers=dict(request.headers),
            json_data=body_data,
        )
    except ForwardBusyError as e:
        total_ms = (time.perf_counter() - t0) * 1000
        rfq_id = body_data.get("rfqId", "?")
        logger.warning(f"[{client_ip}] firm-order rfqId={rfq_id} gateway busy after {total_ms:.0f}ms: {e}")
        raise HTTPException(status_code=503, detail="gateway busy") from e
    except Exception as e:
        total_ms = (time.perf_counter() - t0) * 1000
        rfq_id = body_data.get("rfqId", "?")
        logger.error(
            f"[{client_ip}] firm-order rfqId={rfq_id} backend error after {total_ms:.0f}ms: "
            f"{type(e).__name__}: {e}"
        )
        raise HTTPException(status_code=504, detail=f"backend error: {e}") from e

    fwd_ms = (time.perf_counter() - t1) * 1000
    total_ms = (time.perf_counter() - t0) * 1000
    _log_request_timing(
        client_ip, "firm-order", target_url, total_ms, fwd_ms,
        req_id=f"rfqId={body_data.get('rfqId', '?')}",
    )
    return _proxy_response(response)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
