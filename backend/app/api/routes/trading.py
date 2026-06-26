import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import User, Portfolio as DbPortfolio, Position as DbPosition, Trade
from app.trading.paper_broker import PaperBroker
from app.trading.portfolio import Portfolio
from app.trading.order_manager import OrderSide, OrderType, OrderStatus
from app.trading.risk_manager import RiskManager
from app.market.binance_client import BinanceClient
from app.learning.trade_memory import trade_memory

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trading", tags=["trading"])

# In-memory portfolio cache keyed by (user_id, portfolio_id)
_portfolio_cache: dict[tuple[int, int], Portfolio] = {}
_broker_cache: dict[int, PaperBroker] = {}


def _get_broker(user_id: int) -> PaperBroker:
    if user_id not in _broker_cache:
        _broker_cache[user_id] = PaperBroker()
    return _broker_cache[user_id]


def _db_to_portfolio(p: DbPortfolio, positions: list[dict] | None = None) -> Portfolio:
    portfolio = Portfolio(
        id=p.id,
        user_id=p.user_id,
        name=p.name,
        initial_balance=p.initial_balance,
        cash_balance=p.cash_balance,
    )
    if positions:
        for pos in positions:
            if pos["quantity"] != 0:
                portfolio.positions[pos["symbol"]] = app.trading.order_manager.Position(
                    symbol=pos["symbol"],
                    quantity=pos["quantity"],
                    avg_entry=pos["avg_entry"],
                    current_price=pos.get("current_price", pos["avg_entry"]),
                    unrealized_pnl=pos.get("unrealized_pnl", 0.0),
                )
    _portfolio_cache[(p.user_id, p.id)] = portfolio
    return portfolio


async def _load_or_refresh_portfolio(
    portfolio_id: int, user_id: int, db: AsyncSession
) -> Portfolio:
    key = (user_id, portfolio_id)
    if key in _portfolio_cache:
        portfolio = _portfolio_cache[key]
        result = await db.execute(select(DbPortfolio).where(DbPortfolio.id == portfolio_id))
        db_p = result.scalar_one_or_none()
        if db_p:
            portfolio.cash_balance = db_p.cash_balance
        return portfolio

    result = await db.execute(select(DbPortfolio).where(DbPortfolio.id == portfolio_id))
    db_p = result.scalar_one_or_none()
    if not db_p:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    if db_p.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    pos_result = await db.execute(select(DbPosition).where(DbPosition.portfolio_id == portfolio_id))
    positions = [
        {
            "symbol": p.symbol,
            "quantity": p.quantity,
            "avg_entry": p.avg_entry,
            "current_price": p.current_price,
            "unrealized_pnl": p.unrealized_pnl,
        }
        for p in pos_result.scalars().all()
    ]
    return _db_to_portfolio(db_p, positions)


async def _sync_portfolio_to_db(portfolio: Portfolio, db: AsyncSession):
    result = await db.execute(select(DbPortfolio).where(DbPortfolio.id == portfolio.id))
    db_p = result.scalar_one_or_none()
    if db_p:
        db_p.cash_balance = portfolio.cash_balance

    for symbol, pos in portfolio.positions.items():
        pos_result = await db.execute(
            select(DbPosition).where(
                DbPosition.portfolio_id == portfolio.id,
                DbPosition.symbol == symbol,
            )
        )
        db_pos = pos_result.scalar_one_or_none()
        if pos.quantity <= 0:
            if db_pos:
                await db.delete(db_pos)
            continue
        if db_pos:
            db_pos.quantity = pos.quantity
            db_pos.avg_entry = pos.avg_entry
            db_pos.current_price = pos.current_price
            db_pos.unrealized_pnl = pos.unrealized_pnl
        else:
            db_pos = DbPosition(
                portfolio_id=portfolio.id,
                symbol=symbol,
                quantity=pos.quantity,
                avg_entry=pos.avg_entry,
                current_price=pos.current_price,
                unrealized_pnl=pos.unrealized_pnl,
            )
            db.add(db_pos)


# Schemas
class MarketOrderRequest(BaseModel):
    symbol: str
    side: str
    quantity: float
    portfolio_id: int
    strategy_id: Optional[int] = None
    model_prediction: Optional[str] = None
    confidence: Optional[float] = None


class LimitOrderRequest(BaseModel):
    symbol: str
    side: str
    quantity: float
    limit_price: float
    portfolio_id: int
    strategy_id: Optional[int] = None


class PortfolioCreate(BaseModel):
    name: str
    initial_balance: float = 100000.0


class RiskConfigUpdate(BaseModel):
    max_position_size_pct: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    max_concurrent_positions: Optional[int] = None


# Routes
@router.get("/portfolio")
async def list_portfolios(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DbPortfolio).where(DbPortfolio.user_id == current_user.id)
    )
    portfolios = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "initial_balance": p.initial_balance,
            "cash_balance": p.cash_balance,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in portfolios
    ]


@router.post("/portfolio")
async def create_portfolio(
    data: PortfolioCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    portfolio = DbPortfolio(
        user_id=current_user.id,
        name=data.name,
        initial_balance=data.initial_balance,
        cash_balance=data.initial_balance,
    )
    db.add(portfolio)
    await db.flush()
    return {"id": portfolio.id, "name": portfolio.name, "initial_balance": portfolio.initial_balance, "cash_balance": portfolio.cash_balance}


@router.delete("/portfolio/{portfolio_id}")
async def delete_portfolio(
    portfolio_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DbPortfolio).where(DbPortfolio.id == portfolio_id, DbPortfolio.user_id == current_user.id)
    )
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    key = (current_user.id, portfolio_id)
    _portfolio_cache.pop(key, None)
    await db.delete(p)
    return {"message": "Portfolio deleted"}


@router.get("/portfolio/{portfolio_id}/summary")
async def get_portfolio_summary(
    portfolio_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _load_or_refresh_portfolio(portfolio_id, current_user.id, db)
    return p.to_summary()


@router.get("/portfolio/{portfolio_id}/positions")
async def get_positions(
    portfolio_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    p = await _load_or_refresh_portfolio(portfolio_id, current_user.id, db)
    return [pos.to_dict() for pos in p.positions.values() if abs(pos.quantity) > 0]


@router.get("/portfolio/{portfolio_id}/trades")
async def get_trades(
    portfolio_id: int,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Trade)
        .where(Trade.portfolio_id == portfolio_id)
        .order_by(Trade.created_at.desc())
        .limit(limit)
    )
    trades = result.scalars().all()
    return [
        {
            "id": t.id,
            "symbol": t.symbol,
            "side": t.side,
            "quantity": t.quantity,
            "price": t.price,
            "confidence": t.confidence,
            "outcome_pnl": t.outcome_pnl,
            "status": t.status,
            "model_prediction": t.model_prediction,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "closed_at": t.closed_at.isoformat() if t.closed_at else None,
        }
        for t in trades
    ]


@router.post("/market-order")
async def place_market_order(
    data: MarketOrderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    side = OrderSide.BUY if data.side.upper() == "BUY" else OrderSide.SELL
    broker = _get_broker(current_user.id)
    portfolio = await _load_or_refresh_portfolio(data.portfolio_id, current_user.id, db)

    order = await broker.execute_market_order(
        portfolio=portfolio,
        symbol=data.symbol.upper(),
        side=side,
        quantity=data.quantity,
        strategy_id=data.strategy_id,
        model_prediction=data.model_prediction,
        confidence=data.confidence,
    )

    await _sync_portfolio_to_db(portfolio, db)

    # Log trade in DB
    trade = Trade(
        portfolio_id=portfolio.id,
        strategy_id=data.strategy_id,
        symbol=data.symbol.upper(),
        side=data.side.upper(),
        quantity=order.filled_quantity,
        price=order.filled_price,
        model_prediction=data.model_prediction,
        confidence=data.confidence,
        status=order.status.value,
    )
    db.add(trade)
    await db.flush()

    # Store in ChromaDB for RAG learning
    if order.status == OrderStatus.FILLED:
        try:
            await trade_memory.store_trade(
                trade_id=trade.id,
                user_id=current_user.id,
                symbol=data.symbol.upper(),
                side=data.side.upper(),
                price=order.filled_price,
                quantity=order.filled_quantity,
                outcome_pnl=None,
                confidence=data.confidence,
                model_prediction=data.model_prediction,
            )
        except Exception as e:
            logger.warning(f"Trade memory store failed (non-critical): {e}")

    return {
        "order": broker.order_to_dict(order),
        "portfolio_summary": portfolio.to_summary(),
        "trade_id": trade.id,
    }


@router.post("/limit-order")
async def place_limit_order(
    data: LimitOrderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    side = OrderSide.BUY if data.side.upper() == "BUY" else OrderSide.SELL
    broker = _get_broker(current_user.id)
    portfolio = await _load_or_refresh_portfolio(data.portfolio_id, current_user.id, db)

    order = await broker.execute_limit_order(
        portfolio=portfolio,
        symbol=data.symbol.upper(),
        side=side,
        quantity=data.quantity,
        limit_price=data.limit_price,
        strategy_id=data.strategy_id,
    )

    await _sync_portfolio_to_db(portfolio, db)

    if order.status == OrderStatus.FILLED:
        trade = Trade(
            portfolio_id=portfolio.id,
            strategy_id=data.strategy_id,
            symbol=data.symbol.upper(),
            side=data.side.upper(),
            quantity=order.filled_quantity,
            price=order.filled_price,
            status=order.status.value,
        )
        db.add(trade)
        await db.flush()

    return {
        "order": broker.order_to_dict(order),
        "portfolio_summary": portfolio.to_summary(),
    }


@router.post("/cancel-order/{order_id}")
async def cancel_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
):
    broker = _get_broker(current_user.id)
    order = broker.cancel_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found or already filled")
    return {"order": broker.order_to_dict(order)}


@router.get("/open-orders")
async def get_open_orders(
    portfolio_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
):
    broker = _get_broker(current_user.id)
    orders = broker.get_open_orders(portfolio_id)
    return [broker.order_to_dict(o) for o in orders]


@router.get("/order-history")
async def get_order_history(
    portfolio_id: Optional[int] = None,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    broker = _get_broker(current_user.id)
    orders = broker.get_order_history(portfolio_id, limit)
    return [broker.order_to_dict(o) for o in orders]


@router.get("/risk-config/{portfolio_id}")
async def get_risk_config(
    portfolio_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    portfolio = await _load_or_refresh_portfolio(portfolio_id, current_user.id, db)
    return portfolio.risk_manager.to_config_dict()


@router.put("/risk-config/{portfolio_id}")
async def update_risk_config(
    portfolio_id: int,
    data: RiskConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    portfolio = await _load_or_refresh_portfolio(portfolio_id, current_user.id, db)
    rm = portfolio.risk_manager
    if data.max_position_size_pct is not None:
        rm.max_position_size_pct = data.max_position_size_pct
    if data.stop_loss_pct is not None:
        rm.stop_loss_pct = data.stop_loss_pct
    if data.take_profit_pct is not None:
        rm.take_profit_pct = data.take_profit_pct
    if data.max_drawdown_pct is not None:
        rm.max_drawdown_pct = data.max_drawdown_pct
    if data.max_concurrent_positions is not None:
        rm.max_concurrent_positions = data.max_concurrent_positions
    return rm.to_config_dict()