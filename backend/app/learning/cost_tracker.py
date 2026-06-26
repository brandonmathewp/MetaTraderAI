import logging
from datetime import datetime, timezone
from typing import Optional, NamedTuple

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.models.models import ModelCost, DailyBudget, Strategy

logger = logging.getLogger(__name__)


class BudgetCheck(NamedTuple):
    allowed: bool
    remaining: float
    spent: float
    budget: float
    reason: Optional[str] = None


class CostTracker:
    def __init__(self):
        self._budget_cache: dict[str, float] = {}
        self._daily_resets: set[str] = set()

    async def log_model_call(
        self,
        user_id: int,
        model_name: str,
        request_tokens: int,
        response_tokens: int,
        usd_cost: float,
        strategy_id: Optional[int] = None,
        model_node_label: Optional[str] = None,
    ) -> int:
        async with async_session_factory() as db:
            cost_entry = ModelCost(
                user_id=user_id,
                strategy_id=strategy_id,
                model_node_label=model_node_label,
                openrouter_model_name=model_name,
                request_tokens=request_tokens,
                response_tokens=response_tokens,
                usd_cost=usd_cost,
            )
            db.add(cost_entry)
            await db.flush()
            await db.commit()

            # Update daily budget spent
            today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

            budget_result = await db.execute(
                select(DailyBudget).where(
                    DailyBudget.user_id == user_id,
                    DailyBudget.model_name == model_name,
                    DailyBudget.date >= today,
                )
            )
            budget = budget_result.scalar_one_or_none()

            if budget:
                budget.current_usd_spent += usd_cost
            else:
                budget = DailyBudget(
                    user_id=user_id,
                    model_name=model_name,
                    max_usd_per_day=5.0,
                    current_usd_spent=usd_cost,
                    date=today,
                )
                db.add(budget)

            await db.commit()

            # Push to WebSocket
            await self._notify_cost_update(user_id, cost_entry.id, usd_cost, model_name)

            return cost_entry.id

    async def check_budget(
        self,
        user_id: int,
        model_name: str,
        estimated_cost: float = 0.0,
    ) -> BudgetCheck:
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        async with async_session_factory() as db:
            budget_result = await db.execute(
                select(DailyBudget).where(
                    DailyBudget.user_id == user_id,
                    DailyBudget.model_name == model_name,
                    DailyBudget.date >= today,
                )
            )
            budget = budget_result.scalar_one_or_none()

            if not budget:
                return BudgetCheck(
                    allowed=True,
                    remaining=float("inf"),
                    spent=0.0,
                    budget=float("inf"),
                    reason="No budget configured — unlimited",
                )

            if budget.current_usd_spent >= budget.max_usd_per_day:
                return BudgetCheck(
                    allowed=False,
                    remaining=0.0,
                    spent=budget.current_usd_spent,
                    budget=budget.max_usd_per_day,
                    reason=f"Daily budget exhausted: ${budget.current_usd_spent:.4f} / ${budget.max_usd_per_day:.2f}",
                )

            if estimated_cost > 0:
                remaining = budget.max_usd_per_day - budget.current_usd_spent
                if estimated_cost > remaining:
                    return BudgetCheck(
                        allowed=False,
                        remaining=remaining,
                        spent=budget.current_usd_spent,
                        budget=budget.max_usd_per_day,
                        reason=f"Estimated cost ${estimated_cost:.4f} exceeds remaining ${remaining:.4f}",
                    )

            return BudgetCheck(
                allowed=True,
                remaining=budget.max_usd_per_day - budget.current_usd_spent,
                spent=budget.current_usd_spent,
                budget=budget.max_usd_per_day,
            )

    async def get_cheaper_fallback(self, model_name: str) -> Optional[str]:
        fallbacks = {
            "gpt-4o": "gpt-4o-mini",
            "gpt-4-turbo": "gpt-4o-mini",
            "claude-3-opus": "claude-3-sonnet",
            "claude-3.5-sonnet": "claude-3-haiku",
            "gemini-2.0-flash": "gemini-1.5-flash-8b",
        }
        return fallbacks.get(model_name)

    async def get_model_cost_estimate(self, model_name: str, prompt_tokens: int) -> float:
        rates = {
            "gpt-4o": (2.50, 10.00),
            "gpt-4o-mini": (0.15, 0.60),
            "gpt-4-turbo": (10.00, 30.00),
            "claude-3-opus": (15.00, 75.00),
            "claude-3.5-sonnet": (3.00, 15.00),
            "claude-3-haiku": (0.25, 1.25),
            "gemini-2.0-flash": (0.10, 0.40),
            "gemini-1.5-flash-8b": (0.0375, 0.15),
            "deepseek-chat": (0.14, 0.28),
        }
        input_rate, output_rate = rates.get(model_name, (1.0, 5.0))
        estimated_output = prompt_tokens * 0.5
        cost = (prompt_tokens * input_rate / 1_000_000) + (estimated_output * output_rate / 1_000_000)
        return round(cost, 6)

    async def get_user_cost_summary(self, user_id: int, days: int = 1) -> dict:
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        since = today

        async with async_session_factory() as db:
            # Today's totals
            result = await db.execute(
                select(
                    ModelCost.openrouter_model_name,
                    func.count(ModelCost.id).label("calls"),
                    func.sum(ModelCost.request_tokens).label("total_req"),
                    func.sum(ModelCost.response_tokens).label("total_resp"),
                    func.sum(ModelCost.usd_cost).label("total_cost"),
                )
                .where(ModelCost.user_id == user_id, ModelCost.created_at >= since)
                .group_by(ModelCost.openrouter_model_name)
                .order_by(func.sum(ModelCost.usd_cost).desc())
            )
            rows = result.all()

            models = []
            overall = 0.0
            overall_calls = 0
            for row in rows:
                cost = row.total_cost or 0.0
                overall += cost
                overall_calls += row.calls
                models.append({
                    "model": row.openrouter_model_name,
                    "calls": row.calls,
                    "request_tokens": row.total_req or 0,
                    "response_tokens": row.total_resp or 0,
                    "cost": round(cost, 6),
                })

            # Budgets
            budget_result = await db.execute(
                select(DailyBudget).where(DailyBudget.user_id == user_id, DailyBudget.date >= today)
            )
            budgets = [
                {
                    "id": b.id,
                    "model_name": b.model_name,
                    "max_usd_per_day": b.max_usd_per_day,
                    "current_usd_spent": b.current_usd_spent,
                    "usage_pct": round((b.current_usd_spent / b.max_usd_per_day * 100), 2) if b.max_usd_per_day > 0 else 0,
                }
                for b in budget_result.scalars().all()
            ]

            return {
                "today": {
                    "models": models,
                    "overall_cost": round(overall, 6),
                    "overall_calls": overall_calls,
                },
                "budgets": budgets,
            }

    async def _notify_cost_update(self, user_id: int, cost_id: int, usd_cost: float, model_name: str):
        try:
            from app.api.websocket import manager
            await manager.send_cost_update(user_id, {
                "cost_id": cost_id,
                "usd_cost": usd_cost,
                "model_name": model_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as e:
            logger.debug(f"Cost WS push failed (non-critical): {e}")


cost_tracker = CostTracker()