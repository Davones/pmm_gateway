import httpx
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger()


class HTTPClient:
    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

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