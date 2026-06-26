import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.trading.order_manager import Position
from app.trading.risk_manager import RiskManager

logger = logging.getLogger(__name__)


@dataclass
class Portfolio:
    id: int
    user_id: int
    name: str
    initial_balance: float
    cash_balance: float
    positions: dict[str, Position] = field(default_factory=dict)
    realized_pnl: float = 0.0
    peak_equity: float = 0.0
    risk_manager: RiskManager = field(default_factory=RiskManager)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_commission: float = 0.0
    commission_rate: float = 0.001

    @property
    def equity(self) -> float:
        unrealized = sum(p.unrealized_pnl for p in self.positions.values())
        return self.cash_balance + unrealized

    @property
    def total_pnl(self) -> float:
        unrealized = sum(p.unrealized_pnl for p in self.positions.values())
        return self.realized_pnl + unrealized - self.total_commission

    @property
    def total_pnl_pct(self) -> float:
        if self.initial_balance <= 0:
            return 0.0
        return (self.total_pnl / self.initial_balance) * 100

    @property
    def open_positions_count(self) -> int:
        return sum(1 for p in self.positions.values() if abs(p.quantity) > 0)

    def _tick_peak(self):
        self.peak_equity = max(self.peak_equity, self.equity)

    @property
    def current_drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return ((self.peak_equity - self.equity) / self.peak_equity) * 100

    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def get_or_create_position(self, symbol: str) -> Position:
        if symbol not in self.positions:
            self.positions[symbol] = Position(symbol=symbol)
        return self.positions[symbol]

    def _apply_commission(self, value: float) -> float:
        return value * self.commission_rate

    def can_buy(self, symbol: str, quantity: float, price: float) -> tuple[bool, Optional[str]]:
        cost = quantity * price
        commission = self._apply_commission(cost)
        total = cost + commission

        if total > self.cash_balance:
            return False, f"Insufficient cash: need ${total:.2f}, have ${self.cash_balance:.2f}"

        check, reason = self.risk_manager.check_can_open_position(
            equity=self.equity,
            peak_equity=self.peak_equity,
            current_positions=self.open_positions_count,
            position_value=cost,
        )
        return check, reason

    def can_sell(self, symbol: str, quantity: float) -> tuple[bool, Optional[str]]:
        position = self.get_position(symbol)
        if not position or position.quantity < quantity:
            have = position.quantity if position else 0
            return False, f"Insufficient {symbol}: need {quantity}, have {have}"
        return True, None

    def execute_buy(self, symbol: str, quantity: float, price: float) -> dict:
        cost = quantity * price
        commission = self._apply_commission(cost)
        total = cost + commission

        self.cash_balance -= total
        self.total_commission += commission

        position = self.get_or_create_position(symbol)
        position.add(quantity, price)

        self._tick_peak()

        return {
            "symbol": symbol,
            "side": "BUY",
            "quantity": quantity,
            "price": price,
            "cost": cost,
            "commission": commission,
            "cash_balance": self.cash_balance,
            "equity": self.equity,
            "position": position.to_dict(),
        }

    def execute_sell(self, symbol: str, quantity: float, price: float) -> dict:
        position = self.get_position(symbol)
        if not position:
            raise ValueError(f"No position for {symbol}")

        revenue = quantity * price
        commission = self._apply_commission(revenue)

        position.reduce(quantity, price)
        self.realized_pnl += position.realized_pnl
        position.realized_pnl = 0.0

        self.cash_balance += revenue - commission
        self.total_commission += commission

        if position.quantity <= 0:
            self.positions.pop(symbol, None)

        return {
            "symbol": symbol,
            "side": "SELL",
            "quantity": quantity,
            "price": price,
            "revenue": revenue,
            "commission": commission,
            "realized_pnl": self.realized_pnl,
            "cash_balance": self.cash_balance,
            "equity": self.equity,
            "position": position.to_dict() if position.quantity > 0 else None,
        }

    def update_market_prices(self, prices: dict[str, float]):
        for symbol, price in prices.items():
            if symbol in self.positions:
                self.positions[symbol].update_price(price)

    def check_stop_triggers(self) -> list[tuple[str, str, float]]:
        triggers = []
        for symbol, position in self.positions.items():
            if position.quantity <= 0:
                continue
            if self.risk_manager.check_stop_loss_triggered(position.avg_entry, position.current_price, "BUY"):
                triggers.append((symbol, "STOP_LOSS", position.current_price))
            elif self.risk_manager.check_take_profit_triggered(position.avg_entry, position.current_price, "BUY"):
                triggers.append((symbol, "TAKE_PROFIT", position.current_price))
        return triggers

    def to_summary(self) -> dict:
        self._tick_peak()
        return {
            "id": self.id,
            "name": self.name,
            "initial_balance": self.initial_balance,
            "cash_balance": self.cash_balance,
            "equity": self.equity,
            "realized_pnl": self.realized_pnl,
            "total_pnl": self.total_pnl,
            "total_pnl_pct": self.total_pnl_pct,
            "open_positions": self.open_positions_count,
            "drawdown_pct": self.current_drawdown_pct,
            "total_commission": self.total_commission,
            "peak_equity": self.peak_equity,
        }