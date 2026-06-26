from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.market.binance_client import BinanceClient
from app.market.indicators import get_indicators
from app.models.models import User, Portfolio

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/symbols")
async def get_symbols():
    client = BinanceClient()
    try:
        info = await client.get_exchange_info()
        symbols = [
            {
                "symbol": s["symbol"],
                "base_asset": s.get("baseAsset", ""),
                "quote_asset": s.get("quoteAsset", ""),
                "status": s.get("status", ""),
            }
            for s in info.get("symbols", [])
            if s.get("status") == "TRADING" and s.get("quoteAsset") == "USDT"
        ]
        return {"symbols": symbols}
    finally:
        await client.close()


@router.get("/price")
async def get_price(
    symbol: str = Query(..., description="Trading pair, e.g. BTCUSDT"),
):
    client = BinanceClient()
    try:
        data = await client.get_price(symbol)
        if isinstance(data, list):
            matching = [d for d in data if d.get("symbol") == symbol]
            if matching:
                return {"symbol": symbol, "price": float(matching[0]["price"])}
        if isinstance(data, dict):
            return {"symbol": data.get("symbol", symbol), "price": float(data.get("price", 0))}
        raise HTTPException(status_code=404, detail="Symbol not found")
    finally:
        await client.close()


@router.get("/klines")
async def get_klines_endpoint(
    symbol: str = Query(..., description="Trading pair"),
    interval: str = Query("1m", description="Kline interval"),
    limit: int = Query(500, ge=1, le=1000),
):
    client = BinanceClient()
    try:
        klines = await client.get_klines(symbol, interval, limit)
        return {
            "symbol": symbol,
            "interval": interval,
            "klines": [
                {
                    "open_time": k[0],
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "close_time": k[6],
                }
                for k in klines
            ],
        }
    finally:
        await client.close()


@router.get("/indicators")
async def get_indicators_endpoint(
    symbol: str = Query(..., description="Trading pair"),
    interval: str = Query("1m", description="Kline interval"),
    limit: int = Query(500, ge=1, le=1000),
):
    client = BinanceClient()
    try:
        return await get_indicators(client, symbol, interval, limit)
    finally:
        await client.close()


@router.get("/ticker24hr")
async def get_ticker_24hr_endpoint(symbol: str = Query(None)):
    client = BinanceClient()
    try:
        return await client.get_ticker_24hr(symbol)
    finally:
        await client.close()


@router.get("/orderbook")
async def get_order_book_endpoint(
    symbol: str = Query(..., description="Trading pair"),
    limit: int = Query(100, ge=1, le=5000),
):
    client = BinanceClient()
    try:
        data = await client.get_order_book(symbol, limit)
        return {
            "symbol": symbol,
            "bids": [[float(b[0]), float(b[1])] for b in data.get("bids", [])[:20]],
            "asks": [[float(a[0]), float(a[1])] for a in data.get("asks", [])[:20]],
        }
    finally:
        await client.close()