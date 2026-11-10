import asyncio
import httpx
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger()

_client: Optional[httpx.AsyncClient] = None
_forward_semaphore: Optional[asyncio.Semaphore] = None

# ---- 并发闸配置(生产事故修复, 2026-11-10) ----
# 根因: httpcore 连接池在"排队请求数 >> 连接数"时, 每次请求到达/超时都会执行
# O(排队数 × 连接数) 的全量重分配扫描(_assign_requests_to_connections),
# 突发流量下退化成几十亿次同步调用, 把网关事件循环拖死数分钟
# (症状: 高 CPU 空转、/health 打不通、后端 10s+ 才收到请求)。
# 修复: 网关层限制并发转发, 并发上限 == httpx 连接池容量, 让池内永远不排队。
# 超过上限的请求最多等 FORWARD_WAIT_TIMEOUT 秒, 拿不到槽位直接快速失败
# (做市网关快速失败优于长时间拖死; 上游 OKX 会自行重试)。
MAX_CONCURRENT_FORWARD = 200
FORWARD_WAIT_TIMEOUT = 3.0

# 转发的请求头中需要剔除的 hop-by-hop / 由 httpx 自己管理的头
_EXCLUDE_REQUEST_HEADERS = {
    'host', 'content-length', 'connection', 'keep-alive',
    'transfer-encoding', 'te', 'upgrade', 'proxy-authorization', 'proxy-connection',
}

# 透传响应时由框架自己计算的头
_EXCLUDE_RESPONSE_HEADERS = {'content-length', 'content-encoding', 'transfer-encoding'}


class ForwardBusyError(Exception):
    """网关过载: 并发闸满, 快速失败"""


def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=5.0,
            limits=httpx.Limits(
                max_connections=MAX_CONCURRENT_FORWARD,
                max_keepalive_connections=MAX_CONCURRENT_FORWARD,
            ),
        )
    return _client


def _get_semaphore() -> asyncio.Semaphore:
    global _forward_semaphore
    if _forward_semaphore is None:
        _forward_semaphore = asyncio.Semaphore(MAX_CONCURRENT_FORWARD)
    return _forward_semaphore


async def close_http_client():
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def filter_request_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    if not headers:
        return {}
    return {k: v for k, v in headers.items() if k.lower() not in _EXCLUDE_REQUEST_HEADERS}


def filter_response_headers(headers: Optional[Dict[str, str]]) -> Dict[str, str]:
    if not headers:
        return {}
    return {k: v for k, v in headers.items() if k.lower() not in _EXCLUDE_RESPONSE_HEADERS}


async def forward_request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
) -> httpx.Response:
    semaphore = _get_semaphore()
    try:
        # asyncio.Semaphore.acquire 在 3.9+ 是取消安全的(取消时把槽位转给下一个等待者)
        await asyncio.wait_for(semaphore.acquire(), timeout=FORWARD_WAIT_TIMEOUT)
    except (asyncio.TimeoutError, TimeoutError):
        raise ForwardBusyError(
            f"gateway overloaded: {MAX_CONCURRENT_FORWARD} concurrent forwards "
            f"for over {FORWARD_WAIT_TIMEOUT}s"
        ) from None

    try:
        client = get_http_client()
        logger.debug(f"Forwarding {method} request to {url}")
        return await client.request(
            method=method,
            url=url,
            headers=filter_request_headers(headers),
            params=params,
            json=json_data,
        )
    finally:
        semaphore.release()
