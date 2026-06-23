import httpx
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger()

_global_client: Optional[httpx.AsyncClient] = None


def get_http_client() -> httpx.AsyncClient:
    global _global_client
    if _global_client is None:
        _global_client = httpx.AsyncClient(
            timeout=5.0,
            limits=httpx.Limits(
                max_connections=500,
                max_keepalive_connections=100,
            ),
        )
    return _global_client


async def close_http_client():
    global _global_client
    if _global_client is not None:
        await _global_client.aclose()
        _global_client = None


class HTTPClient:
    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    async def __aenter__(self):
        self._client = get_http_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def forward_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        if not self._client:
            raise RuntimeError("HTTPClient must be used as async context manager")

        request_headers = self._filter_headers(headers)

        logger.debug(f"Forwarding {method} request to {url}")

        response = await self._client.request(
            method=method,
            url=url,
            headers=request_headers,
            params=params,
            json=json_data,
        )

        return response

    def _filter_headers(self, headers: Optional[Dict[str, str]]) -> Dict[str, str]:
        if not headers:
            return {}

        exclude_keys = {'host', 'content-length'}
        return {k: v for k, v in headers.items() if k.lower() not in exclude_keys}