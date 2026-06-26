import asyncio
import io
import json
import logging
import sys
import textwrap
import time
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from typing import Optional

from app.market.binance_client import BinanceClient
from app.market.indicators import get_indicators

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30
MAX_OUTPUT_LENGTH = 10000


def _make_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


class ScriptSandbox:
    def __init__(
        self,
        user_id: int,
        portfolio_id: Optional[int] = None,
        strategy_id: Optional[int] = None,
    ):
        self.user_id = user_id
        self.portfolio_id = portfolio_id
        self.strategy_id = strategy_id
        self.output_lines: list[str] = []
        self.errors: list[str] = []
        self.result: dict = {}

    def _log(self, level: str, msg: str):
        ts = _make_timestamp()
        self.output_lines.append(f"[{ts}] [{level}] {msg}")

    def _build_trade_api(self):
        sandbox = self

        class TradeAPI:
            @staticmethod
            async def buy(symbol: str, quantity: float) -> dict:
                if not sandbox.portfolio_id:
                    return {"error": "No portfolio attached"}
                try:
                    from app.trading.paper_broker import PaperBroker
                    from app.trading.portfolio import Portfolio as PortfolioLib
                    from app.trading.order_manager import OrderSide
                    from app.core.database import async_session_factory
                    from app.models.models import Portfolio as DbPortfolio
                    from sqlalchemy import select

                    async with async_session_factory() as db:
                        result = await db.execute(
                            select(DbPortfolio).where(DbPortfolio.id == sandbox.portfolio_id)
                        )
                        db_p = result.scalar_one_or_none()
                        if not db_p:
                            return {"error": "Portfolio not found"}

                        port = PortfolioLib(
                            id=db_p.id,
                            user_id=db_p.user_id,
                            name=db_p.name,
                            initial_balance=db_p.initial_balance,
                            cash_balance=db_p.cash_balance,
                        )

                    broker = PaperBroker()
                    order = await broker.execute_market_order(
                        portfolio=port,
                        symbol=symbol.upper(),
                        side=OrderSide.BUY,
                        quantity=quantity,
                        strategy_id=sandbox.strategy_id,
                    )
                    return {
                        "symbol": symbol,
                        "side": "BUY",
                        "quantity": quantity,
                        "filled_price": order.filled_price,
                        "status": order.status.value,
                    }
                except Exception as e:
                    return {"error": str(e)}

            @staticmethod
            async def sell(symbol: str, quantity: float) -> dict:
                if not sandbox.portfolio_id:
                    return {"error": "No portfolio attached"}
                try:
                    from app.trading.paper_broker import PaperBroker
                    from app.trading.portfolio import Portfolio as PortfolioLib
                    from app.trading.order_manager import OrderSide
                    from app.core.database import async_session_factory
                    from app.models.models import Portfolio as DbPortfolio
                    from sqlalchemy import select

                    async with async_session_factory() as db:
                        result = await db.execute(
                            select(DbPortfolio).where(DbPortfolio.id == sandbox.portfolio_id)
                        )
                        db_p = result.scalar_one_or_none()
                        if not db_p:
                            return {"error": "Portfolio not found"}

                        port = PortfolioLib(
                            id=db_p.id,
                            user_id=db_p.user_id,
                            name=db_p.name,
                            initial_balance=db_p.initial_balance,
                            cash_balance=db_p.cash_balance,
                        )

                    broker = PaperBroker()
                    order = await broker.execute_market_order(
                        portfolio=port,
                        symbol=symbol.upper(),
                        side=OrderSide.SELL,
                        quantity=quantity,
                        strategy_id=sandbox.strategy_id,
                    )
                    return {
                        "symbol": symbol,
                        "side": "SELL",
                        "quantity": quantity,
                        "filled_price": order.filled_price,
                        "status": order.status.value,
                    }
                except Exception as e:
                    return {"error": str(e)}

            @staticmethod
            async def set_stop_loss(symbol: str, price: float) -> dict:
                return {"symbol": symbol, "stop_loss": price, "status": "set"}

            @staticmethod
            async def set_take_profit(symbol: str, price: float) -> dict:
                return {"symbol": symbol, "take_profit": price, "status": "set"}

        return TradeAPI()

    def _build_market_api(self):
        sandbox = self

        class MarketAPI:
            @staticmethod
            async def get_price(symbol: str) -> float:
                client = BinanceClient()
                try:
                    data = await client.get_price(symbol.upper())
                    if isinstance(data, dict):
                        return float(data.get("price", 0))
                    if isinstance(data, list) and len(data) > 0:
                        return float(data[0].get("price", 0))
                    return 0.0
                finally:
                    await client.close()

            @staticmethod
            async def get_indicator(symbol: str, indicator: str, period: int = 14) -> float:
                client = BinanceClient()
                try:
                    data = await get_indicators(client, symbol.upper(), "1m", 500)
                    if indicator == "RSI":
                        return data.get("rsi_14", 0) or 0
                    elif indicator == "SMA":
                        key = f"sma_{period}"
                        return data.get(key, 0) or 0
                    elif indicator == "EMA":
                        key = f"ema_{period}"
                        return data.get(key, 0) or 0
                    return 0
                finally:
                    await client.close()

            @staticmethod
            async def get_klines(symbol: str, interval: str = "1m", limit: int = 100) -> list:
                client = BinanceClient()
                try:
                    klines = await client.get_klines(symbol.upper(), interval, limit)
                    return [
                        {
                            "open": float(k[1]),
                            "high": float(k[2]),
                            "low": float(k[3]),
                            "close": float(k[4]),
                            "volume": float(k[5]),
                            "time": k[0],
                        }
                        for k in klines
                    ]
                finally:
                    await client.close()

            @staticmethod
            async def get_orderbook(symbol: str, depth: int = 20) -> dict:
                client = BinanceClient()
                try:
                    data = await client.get_order_book(symbol.upper(), depth)
                    return {
                        "bids": [[float(b[0]), float(b[1])] for b in data.get("bids", [])[:10]],
                        "asks": [[float(a[0]), float(a[1])] for a in data.get("asks", [])[:10]],
                    }
                finally:
                    await client.close()

        return MarketAPI()

    def _build_portfolio_api(self):
        sandbox = self

        class PortfolioAPI:
            @staticmethod
            async def get_balance() -> float:
                return await self._get_portfolio_attr("cash_balance")

            @staticmethod
            async def get_positions() -> dict:
                return await self._get_portfolio_attr("positions", as_dict=True)

            @staticmethod
            async def get_pnl() -> float:
                return await self._get_portfolio_attr("total_pnl")

            @staticmethod
            async def get_equity() -> float:
                return await self._get_portfolio_attr("equity")

            @staticmethod
            async def _get_portfolio_attr(attr: str, as_dict: bool = False):
                if not sandbox.portfolio_id:
                    return 0.0 if not as_dict else {}
                try:
                    from app.core.database import async_session_factory
                    from app.models.models import Portfolio as DbPortfolio
                    from sqlalchemy import select

                    async with async_session_factory() as db:
                        result = await db.execute(
                            select(DbPortfolio).where(DbPortfolio.id == sandbox.portfolio_id)
                        )
                        db_p = result.scalar_one_or_none()
                        if not db_p:
                            return 0.0 if not as_dict else {}
                        if as_dict:
                            from app.trading.portfolio import Portfolio as PortfolioLib
                            port = PortfolioLib(
                                id=db_p.id,
                                user_id=db_p.user_id,
                                name=db_p.name,
                                initial_balance=db_p.initial_balance,
                                cash_balance=db_p.cash_balance,
                            )
                            return {s: p.to_dict() for s, p in port.positions.items()}
                        return getattr(db_p, attr, 0.0)
                except Exception:
                    return 0.0 if not as_dict else {}

        return PortfolioAPI()

    def _build_model_api(self):
        sandbox = self

        class ModelAPI:
            @staticmethod
            async def predict(name: str, prompt: str, context: dict = None) -> dict:
                try:
                    from app.core.openrouter import get_openrouter
                    openrouter = get_openrouter()
                    messages = [
                        {"role": "system", "content": "You are a trading analyst. Output JSON: {\"action\": \"BUY|SELL|HOLD\", \"confidence\": 0.0-1.0, \"reasoning\": \"...\"}"},
                        {"role": "user", "content": f"{prompt}\n\nContext: {json.dumps(context or {})}"},
                    ]
                    response = await openrouter.chat_completion_tracked(
                        user_id=sandbox.user_id,
                        model=name,
                        messages=messages,
                        temperature=0.7,
                        max_tokens=512,
                        strategy_id=sandbox.strategy_id,
                        node_label=f"Script: {sandbox.user_id}",
                        enforce_budget=True,
                        auto_fallback=True,
                    )
                    content = openrouter.extract_content(response)
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return {"raw": content}
                except Exception as e:
                    return {"error": str(e)}

        return ModelAPI()

    async def execute(self, code: str, input_data: dict = None) -> dict:
        self.output_lines = []
        self.errors = []

        # Capture stdout/stderr
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        # Build the full script wrapper
        indented_code = textwrap.indent(code, '    ')
        wrapped_code = f"""
import asyncio

async def __sandbox_run():
{indented_code}

try:
    result = asyncio.get_event_loop().run_until_complete(__sandbox_run())
except RuntimeError:
    result = asyncio.run(__sandbox_run())
"""

        safe_builtins = {
            "print": lambda *a, **kw: print(*a, **kw, file=stdout_buf),
            "len": len,
            "range": range,
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            "list": list,
            "dict": dict,
            "sum": sum,
            "min": min,
            "max": max,
            "abs": abs,
            "round": round,
            "sorted": sorted,
            "enumerate": enumerate,
            "zip": zip,
            "isinstance": isinstance,
            "type": type,
            "True": True,
            "False": False,
            "None": None,
            "Exception": Exception,
        }

        # Build the global namespace with API objects
        safe_globals = {
            "__builtins__": safe_builtins,
            "market": self._build_market_api(),
            "trade": self._build_trade_api(),
            "portfolio": self._build_portfolio_api(),
            "model": self._build_model_api(),
            "ctx": input_data or {},
            "import": _blocked_import,
        }

        safe_locals = {}
        start_time = time.time()

        try:
            with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                exec(wrapped_code, safe_globals, safe_locals)
        except Exception as e:
            self.errors.append(f"Execution error: {e}")
            self._log("ERROR", str(e))

        elapsed = (time.time() - start_time) * 1000
        self._log("INFO", f"Completed in {elapsed:.0f}ms")

        stdout_content = stdout_buf.getvalue()
        stderr_content = stderr_buf.getvalue()

        if stdout_content.strip():
            for line in stdout_content.strip().split("\n"):
                self._log("OUT", line)

        if stderr_content.strip():
            for line in stderr_content.strip().split("\n"):
                self._log("ERR", line)

        result = safe_locals.get("result", {})
        if isinstance(result, (dict, list, str, int, float, bool)):
            pass
        else:
            result = {"raw": str(result)[:500]}

        return {
            "output": "\n".join(self.output_lines[-200:]),
            "errors": self.errors,
            "result": result,
            "elapsed_ms": round(elapsed, 0),
            "success": len(self.errors) == 0,
        }


def _blocked_import(*args, **kwargs):
    raise ImportError("import statements are not allowed in sandbox scripts")


sandbox_factory = ScriptSandbox