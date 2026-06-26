import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: dict[int, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = []
            self._connections[user_id].append(websocket)
        logger.info(f"User {user_id} connected (total: {len(self._connections.get(user_id, []))})")

    async def disconnect(self, user_id: int, websocket: WebSocket):
        async with self._lock:
            if user_id in self._connections:
                self._connections[user_id].remove(websocket)
                if not self._connections[user_id]:
                    del self._connections[user_id]
        logger.info(f"User {user_id} disconnected")

    async def send_to_user(self, user_id: int, data: dict[str, Any]):
        async with self._lock:
            connections = self._connections.get(user_id, []).copy()

        dead: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                if user_id in self._connections:
                    for ws in dead:
                        if ws in self._connections[user_id]:
                            self._connections[user_id].remove(ws)

    async def broadcast(self, data: dict[str, Any]):
        async with self._lock:
            all_connections = [
                (uid, ws) for uid, conns in self._connections.items() for ws in conns
            ]

        dead: list[tuple[int, WebSocket]] = []
        for uid, ws in all_connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append((uid, ws))

        if dead:
            async with self._lock:
                for uid, ws in dead:
                    if uid in self._connections and ws in self._connections[uid]:
                        self._connections[uid].remove(ws)

    async def broadcast_market_data(self, symbol: str, data: dict[str, Any]):
        await self.broadcast({"type": "market_update", "symbol": symbol, "data": data})

    async def send_trade_update(self, user_id: int, trade: dict[str, Any]):
        await self.send_to_user(user_id, {"type": "trade_update", "trade": trade})

    async def send_cost_update(self, user_id: int, costs: dict[str, Any]):
        await self.send_to_user(user_id, {"type": "cost_update", "costs": costs})

    async def send_graph_execution(self, user_id: int, node_id: int, status: str, data: dict = None):
        await self.send_to_user(user_id, {
            "type": "graph_execution",
            "node_id": node_id,
            "status": status,
            "data": data or {},
        })


manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket, user_id: int):
    await manager.connect(user_id, websocket)
    try:
        while True:
            message = await websocket.receive_text()
            try:
                data = json.loads(message)
                msg_type = data.get("type", "")

                if msg_type == "subscribe_ticker":
                    symbol = data.get("symbol", "")
                    if symbol:
                        from app.market.websocket import get_binance_ws
                        ws_manager = get_binance_ws()

                        async def ticker_callback(ticker_data):
                            await manager.send_to_user(user_id, {
                                "type": "ticker",
                                "symbol": symbol,
                                "data": {
                                    "price": float(ticker_data.get("lastPrice", 0)),
                                    "price_change_pct": float(ticker_data.get("priceChangePercent", 0)),
                                    "volume": float(ticker_data.get("volume", 0)),
                                    "high": float(ticker_data.get("highPrice", 0)),
                                    "low": float(ticker_data.get("lowPrice", 0)),
                                },
                            })

                        ws_manager.subscribe(f"{symbol.lower()}@ticker", ticker_callback)

                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

            except json.JSONDecodeError:
                pass
            except Exception as e:
                logger.error(f"WebSocket message error: {e}")

    except WebSocketDisconnect:
        await manager.disconnect(user_id, websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await manager.disconnect(user_id, websocket)