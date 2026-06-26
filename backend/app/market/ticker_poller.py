import asyncio
import logging
from typing import Optional

from app.market.binance_client import BinanceClient

logger = logging.getLogger(__name__)


class TickerPoller:
    def __init__(self, client: BinanceClient):
        self.client = client
        self._running = False
        self._symbols: set[str] = set()
        self._callbacks: dict[str, list] = {}
        self._task: Optional[asyncio.Task] = None

    def add_symbol(self, symbol: str):
        self._symbols.add(symbol)

    def remove_symbol(self, symbol: str):
        self._symbols.discard(symbol)

    def on_ticker(self, symbol: str, callback):
        if symbol not in self._callbacks:
            self._callbacks[symbol] = []
        self._callbacks[symbol].append(callback)

    async def start(self, interval: float = 1.0):
        self._running = True
        self._task = asyncio.create_task(self._poll(interval))

    async def _poll(self, interval: float):
        while self._running:
            try:
                for symbol in list(self._symbols):
                    try:
                        ticker = await self.client.get_ticker_24hr(symbol)
                        if isinstance(ticker, dict):
                            ticker = [ticker]
                        for t in ticker:
                            for cb in self._callbacks.get(t.get("symbol", symbol), []):
                                try:
                                    await cb(t)
                                except Exception as e:
                                    logger.error(f"Ticker callback error: {e}")
                    except Exception as e:
                        logger.error(f"Ticker poll error for {symbol}: {e}")
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Poller error: {e}")
                await asyncio.sleep(interval)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass