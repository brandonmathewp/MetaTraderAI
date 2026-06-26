import hashlib
import hmac
import time
from typing import Optional

import httpx
from urllib.parse import urlencode

from app.core.config import get_settings

settings = get_settings()


class BinanceClient:
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = settings.BINANCE_API_BASE
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _sign_params(self, params: dict) -> str:
        query = urlencode(params)
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def _request(self, method: str, path: str, signed: bool = False, **kwargs) -> dict:
        client = await self._get_client()
        headers = {"X-MBX-APIKEY": self.api_key} if self.api_key else {}

        if signed and self.api_secret:
            params = kwargs.get("params", {})
            params["timestamp"] = int(time.time() * 1000)
            params["signature"] = self._sign_params(params)
            kwargs["params"] = params

        url = f"{self.base_url}{path}"
        response = await client.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
        return response.json()

    async def get_exchange_info(self) -> dict:
        return await self._request("GET", "/api/v3/exchangeInfo")

    async def get_symbol_info(self, symbol: str) -> dict:
        info = await self._request("GET", "/api/v3/exchangeInfo", params={"symbol": symbol})
        return info["symbols"][0] if info.get("symbols") else {}

    async def get_klines(
        self,
        symbol: str,
        interval: str = "1m",
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> list:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return await self._request("GET", "/api/v3/klines", params=params)

    async def get_ticker_24hr(self, symbol: Optional[str] = None) -> list | dict:
        params = {}
        if symbol:
            params["symbol"] = symbol
        return await self._request("GET", "/api/v3/ticker/24hr", params=params)

    async def get_price(self, symbol: Optional[str] = None) -> list | dict:
        params = {}
        if symbol:
            params["symbol"] = symbol
        return await self._request("GET", "/api/v3/ticker/price", params=params)

    async def get_order_book(self, symbol: str, limit: int = 100) -> dict:
        return await self._request("GET", "/api/v3/depth", params={"symbol": symbol, "limit": limit})

    async def get_account(self) -> dict:
        return await self._request("GET", "/api/v3/account", signed=True)

    def get_websocket_url(self, streams: list[str]) -> str:
        stream_str = "/".join(streams)
        return f"{settings.BINANCE_WS_BASE}/stream?streams={stream_str}"


def kline_to_dict(kline: list) -> dict:
    return {
        "open_time": kline[0],
        "open": float(kline[1]),
        "high": float(kline[2]),
        "low": float(kline[3]),
        "close": float(kline[4]),
        "volume": float(kline[5]),
        "close_time": kline[6],
        "quote_volume": float(kline[7]),
        "trades": kline[8],
        "taker_buy_base": float(kline[9]),
        "taker_buy_quote": float(kline[10]),
    }