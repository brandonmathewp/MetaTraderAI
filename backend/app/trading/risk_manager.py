import logging
from typing import Optional

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(
        self,
        max_position_size_pct: float = 10.0,
        max_portfolio_risk_pct: float = 2.0,
        stop_loss_pct: float = 5.0,
        take_profit_pct: float = 10.0,
        max_drawdown_pct: float = 20.0,
        max_concurrent_positions: int = 5,
        max_leverage: float = 1.0,
    ):
        self.max_position_size_pct = max_position_size_pct
        self.max_portfolio_risk_pct = max_portfolio_risk_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_concurrent_positions = max_concurrent_positions
        self.max_leverage = max_leverage

    def check_can_open_position(
        self,
        equity: float,
        peak_equity: float,
        current_positions: int,
        position_value: float,
    ) -> tuple[bool, Optional[str]]:
        if current_positions >= self.max_concurrent_positions:
            return False, f"Max concurrent positions ({self.max_concurrent_positions}) reached"

        if equity <= 0:
            return False, "Insufficient equity"

        position_pct = (position_value / equity) * 100
        if position_pct > self.max_position_size_pct:
            return False, f"Position size {position_pct:.1f}% exceeds max {self.max_position_size_pct}%"

        if peak_equity > 0:
            drawdown_pct = ((peak_equity - equity) / peak_equity) * 100
            if drawdown_pct >= self.max_drawdown_pct:
                return False, f"Max drawdown {self.max_drawdown_pct}% reached (current: {drawdown_pct:.1f}%)"

        return True, None

    def check_stop_loss_triggered(self, entry_price: float, current_price: float, side: str) -> bool:
        if entry_price <= 0:
            return False
        if side == "BUY":
            loss_pct = ((entry_price - current_price) / entry_price) * 100
        else:
            loss_pct = ((current_price - entry_price) / entry_price) * 100
        return loss_pct >= self.stop_loss_pct

    def check_take_profit_triggered(self, entry_price: float, current_price: float, side: str) -> bool:
        if entry_price <= 0:
            return False
        if side == "BUY":
            profit_pct = ((current_price - entry_price) / entry_price) * 100
        else:
            profit_pct = ((entry_price - current_price) / entry_price) * 100
        return profit_pct >= self.take_profit_pct

    def compute_position_size(self, equity: float, current_price: float) -> float:
        max_value = equity * (self.max_position_size_pct / 100)
        if current_price <= 0:
            return 0.0
        return max_value / current_price

    def compute_stop_price(self, entry_price: float, side: str) -> float:
        if side == "BUY":
            return entry_price * (1 - self.stop_loss_pct / 100)
        return entry_price * (1 + self.stop_loss_pct / 100)

    def compute_take_profit_price(self, entry_price: float, side: str) -> float:
        if side == "BUY":
            return entry_price * (1 + self.take_profit_pct / 100)
        return entry_price * (1 - self.take_profit_pct / 100)

    def to_config_dict(self) -> dict:
        return {
            "max_position_size_pct": self.max_position_size_pct,
            "max_portfolio_risk_pct": self.max_portfolio_risk_pct,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_concurrent_positions": self.max_concurrent_positions,
            "max_leverage": self.max_leverage,
        }