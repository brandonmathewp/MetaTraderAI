import asyncio
import json
import logging
from typing import Optional, Callable, Awaitable

import websockets
from websockets.asyncio.client import ClientConnection

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class BinanceWebSocket:
    def __init__(self):
        self._ws: Optional[ClientConnection] = None
        self._running = False
        self._subscriptions: dict[str, list[Callable[[dict], Awaitable]]] = {}
        self._tasks: list[asyncio.Task] = []

    async def connect(self, streams: list[str]):
        url = f"{settings.BINANCE_WS_BASE}/stream?streams={'/'.join(streams)}"
        self._ws = await websockets.connect(url)
        self._running = True
        logger.info(f"Connected to Binance WebSocket: {streams}")

    async def listen(self):
        while self._running and self._ws:
            try:
                message = await self._ws.recv()
                data = json.loads(message)
                stream = data.get("stream", "")
                stream_data = data.get("data", {})

                if stream in self._subscriptions:
                    for callback in self._subscriptions[stream]:
                        self._tasks.append(asyncio.create_task(callback(stream_data)))

                # Clean up completed tasks
                self._tasks = [t for t in self._tasks if not t.done()]
            except websockets.ConnectionClosed:
                logger.warning("WebSocket connection closed, reconnecting...")
                break
            except Exception as e:
                logger.error(f"WebSocket error: {e}")

    def subscribe(self, stream: str, callback: Callable[[dict], Awaitable]):
        if stream not in self._subscriptions:
            self._subscriptions[stream] = []
        self._subscriptions[stream].append(callback)

    def unsubscribe(self, stream: str, callback: Callable[[dict], Awaitable]):
        if stream in self._subscriptions and callback in self._subscriptions[stream]:
            self._subscriptions[stream].remove(callback)

    async def close(self):
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._ws:
            await self._ws.close()
        logger.info("WebSocket closed")


binance_ws: Optional[BinanceWebSocket] = None


def get_binance_ws() -> BinanceWebSocket:
    global binance_ws
    if binance_ws is None:
        binance_ws = BinanceWebSocket()
    return binance_ws