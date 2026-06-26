import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.trading.order_manager import (
    Order, OrderSide, OrderType, OrderStatus, Position,
)
from app.trading.portfolio import Portfolio
from app.market.binance_client import BinanceClient

logger = logging.getLogger(__name__)


class PaperBroker:
    def __init__(self, slippage_pct: float = 0.05, latency_ms: int = 0):
        self.slippage_pct = slippage_pct
        self.latency_ms = latency_ms
        self._order_counter = 0
        self._orders: dict[int, Order] = {}
        self._order_history: list[Order] = []

    def _next_order_id(self) -> int:
        self._order_counter += 1
        return self._order_counter

    def _apply_slippage(self, price: float, side: OrderSide) -> float:
        if side == OrderSide.BUY:
            return price * (1 + self.slippage_pct / 100)
        return price * (1 - self.slippage_pct / 100)

    async def get_current_price(self, symbol: str) -> float:
        client = BinanceClient()
        try:
            data = await client.get_price(symbol)
            if isinstance(data, dict):
                return float(data.get("price", 0))
            if isinstance(data, list) and len(data) > 0:
                return float(data[0].get("price", 0))
        except Exception as e:
            logger.error(f"Failed to fetch price for {symbol}: {e}")
        finally:
            await client.close()
        return 0.0

    def place_order(
        self,
        portfolio: Portfolio,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        strategy_id: Optional[int] = None,
        model_prediction: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> Order:
        order_id = self._next_order_id()

        order = Order(
            id=order_id,
            portfolio_id=portfolio.id,
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            model_prediction=model_prediction,
            confidence=confidence,
        )

        self._orders[order_id] = order
        logger.info(f"Order placed: {order.side} {order.quantity} {order.symbol} @ {order_type}")

        return order

    async def execute_market_order(
        self,
        portfolio: Portfolio,
        symbol: str,
        side: OrderSide,
        quantity: float,
        current_price: Optional[float] = None,
        strategy_id: Optional[int] = None,
        model_prediction: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> Order:
        if current_price is None:
            current_price = await self.get_current_price(symbol)

        if current_price <= 0:
            order = Order(
                id=self._next_order_id(),
                portfolio_id=portfolio.id,
                strategy_id=strategy_id,
                symbol=symbol,
                side=side,
                order_type=OrderType.MARKET,
                quantity=quantity,
                status=OrderStatus.REJECTED,
                reject_reason=f"Could not fetch price for {symbol}",
            )
            self._order_history.append(order)
            return order

        fill_price = self._apply_slippage(current_price, side)

        order = self.place_order(
            portfolio=portfolio,
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            price=fill_price,
            strategy_id=strategy_id,
            model_prediction=model_prediction,
            confidence=confidence,
        )

        try:
            if side == OrderSide.BUY:
                can, reason = portfolio.can_buy(symbol, quantity, fill_price)
                if not can:
                    order.status = OrderStatus.REJECTED
                    order.reject_reason = reason
                    self._order_history.append(order)
                    return order
                result = portfolio.execute_buy(symbol, quantity, fill_price)
            else:
                can, reason = portfolio.can_sell(symbol, quantity)
                if not can:
                    order.status = OrderStatus.REJECTED
                    order.reject_reason = reason
                    self._order_history.append(order)
                    return order
                result = portfolio.execute_sell(symbol, quantity, fill_price)

            order.filled_quantity = quantity
            order.filled_price = fill_price
            order.status = OrderStatus.FILLED
            order.filled_at = datetime.now(timezone.utc)
            self._order_history.append(order)
            logger.info(f"Order filled: {side} {quantity} {symbol} @ ${fill_price:.4f}")

        except Exception as e:
            order.status = OrderStatus.REJECTED
            order.reject_reason = str(e)
            self._order_history.append(order)
            logger.error(f"Order execution failed: {e}")

        return order

    async def execute_limit_order(
        self,
        portfolio: Portfolio,
        symbol: str,
        side: OrderSide,
        quantity: float,
        limit_price: float,
        strategy_id: Optional[int] = None,
    ) -> Order:
        current_price = await self.get_current_price(symbol)

        order = self.place_order(
            portfolio=portfolio,
            symbol=symbol,
            side=side,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            price=limit_price,
            strategy_id=strategy_id,
        )

        should_fill = (
            (side == OrderSide.BUY and current_price <= limit_price)
            or (side == OrderSide.SELL and current_price >= limit_price)
        )

        if not should_fill:
            order.status = OrderStatus.PENDING
            return order

        return await self._fill_order(portfolio, order, current_price)

    async def _fill_order(self, portfolio: Portfolio, order: Order, current_price: float) -> Order:
        fill_price = self._apply_slippage(current_price, order.side)
        try:
            if order.side == OrderSide.BUY:
                can, reason = portfolio.can_buy(order.symbol, order.quantity, fill_price)
                if not can:
                    order.status = OrderStatus.REJECTED
                    order.reject_reason = reason
                    self._order_history.append(order)
                    return order
                portfolio.execute_buy(order.symbol, order.quantity, fill_price)
            else:
                can, reason = portfolio.can_sell(order.symbol, order.quantity)
                if not can:
                    order.status = OrderStatus.REJECTED
                    order.reject_reason = reason
                    self._order_history.append(order)
                    return order
                portfolio.execute_sell(order.symbol, order.quantity, fill_price)

            order.filled_quantity = order.quantity
            order.filled_price = fill_price
            order.status = OrderStatus.FILLED
            order.filled_at = datetime.now(timezone.utc)
            self._order_history.append(order)
        except Exception as e:
            order.status = OrderStatus.REJECTED
            order.reject_reason = str(e)
            self._order_history.append(order)

        return order

    def cancel_order(self, order_id: int) -> Optional[Order]:
        order = self._orders.get(order_id)
        if order and order.is_open:
            order.status = OrderStatus.CANCELLED
            order.cancelled_at = datetime.now(timezone.utc)
            self._order_history.append(order)
            del self._orders[order_id]
            logger.info(f"Order cancelled: {order_id}")
            return order
        return None

    def get_open_orders(self, portfolio_id: Optional[int] = None) -> list[Order]:
        orders = [o for o in self._orders.values() if o.is_open]
        if portfolio_id is not None:
            orders = [o for o in orders if o.portfolio_id == portfolio_id]
        return orders

    def get_order(self, order_id: int) -> Optional[Order]:
        return self._orders.get(order_id)

    def get_order_history(self, portfolio_id: Optional[int] = None, limit: int = 50) -> list[Order]:
        orders = self._order_history[:]
        if portfolio_id is not None:
            orders = [o for o in orders if o.portfolio_id == portfolio_id]
        return sorted(orders, key=lambda o: o.created_at, reverse=True)[:limit]

    def order_to_dict(self, order: Order) -> dict:
        return {
            "id": order.id,
            "portfolio_id": order.portfolio_id,
            "strategy_id": order.strategy_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "order_type": order.order_type.value,
            "quantity": order.quantity,
            "price": order.price,
            "stop_price": order.stop_price,
            "filled_quantity": order.filled_quantity,
            "filled_price": order.filled_price,
            "status": order.status.value,
            "model_prediction": order.model_prediction,
            "confidence": order.confidence,
            "reject_reason": order.reject_reason,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "filled_at": order.filled_at.isoformat() if order.filled_at else None,
            "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
        }