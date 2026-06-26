import logging
from typing import Optional, Callable, Awaitable

import pandas as pd

from app.market.binance_client import BinanceClient, kline_to_dict

logger = logging.getLogger(__name__)


def compute_sma(data: pd.Series, period: int) -> pd.Series:
    return data.rolling(window=period).mean()


def compute_ema(data: pd.Series, period: int) -> pd.Series:
    return data.ewm(span=period, adjust=False).mean()


def compute_rsi(data: pd.Series, period: int = 14) -> pd.Series:
    delta = data.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_macd(data: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    ema_fast = compute_ema(data, fast)
    ema_slow = compute_ema(data, slow)
    macd_line = ema_fast - ema_slow
    signal_line = compute_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def compute_bollinger_bands(data: pd.Series, period: int = 20, std_dev: int = 2) -> dict:
    sma = compute_sma(data, period)
    std = data.rolling(window=period).std()
    return {
        "upper": sma + std_dev * std,
        "middle": sma,
        "lower": sma - std_dev * std,
    }


async def get_indicators(client: BinanceClient, symbol: str, interval: str = "1m", limit: int = 500) -> dict:
    klines = await client.get_klines(symbol, interval, limit)
    candles = [kline_to_dict(k) for k in klines]
    df = pd.DataFrame(candles)
    df["close"] = pd.to_numeric(df["close"])
    df["high"] = pd.to_numeric(df["high"])
    df["low"] = pd.to_numeric(df["low"])
    df["volume"] = pd.to_numeric(df["volume"])

    latest = candles[-1] if candles else None

    return {
        "symbol": symbol,
        "interval": interval,
        "latest_price": latest["close"] if latest else None,
        "latest_volume": latest["volume"] if latest else None,
        "sma_20": compute_sma(df["close"], 20).iloc[-1] if len(df) >= 20 else None,
        "sma_50": compute_sma(df["close"], 50).iloc[-1] if len(df) >= 50 else None,
        "sma_200": compute_sma(df["close"], 200).iloc[-1] if len(df) >= 200 else None,
        "ema_12": compute_ema(df["close"], 12).iloc[-1] if len(df) >= 12 else None,
        "ema_26": compute_ema(df["close"], 26).iloc[-1] if len(df) >= 26 else None,
        "rsi_14": compute_rsi(df["close"], 14).iloc[-1] if len(df) >= 14 else None,
        "macd": _get_macd_values(df["close"]) if len(df) >= 26 else None,
        "bollinger": _get_bb_values(df["close"]) if len(df) >= 20 else None,
        "candles": candles[-100:],
    }


def _get_macd_values(close: pd.Series) -> dict:
    macd_data = compute_macd(close)
    return {
        "macd": float(macd_data["macd"].iloc[-1]),
        "signal": float(macd_data["signal"].iloc[-1]),
        "histogram": float(macd_data["histogram"].iloc[-1]),
    }


def _get_bb_values(close: pd.Series) -> dict:
    bb = compute_bollinger_bands(close)
    return {
        "upper": float(bb["upper"].iloc[-1]),
        "middle": float(bb["middle"].iloc[-1]),
        "lower": float(bb["lower"].iloc[-1]),
    }