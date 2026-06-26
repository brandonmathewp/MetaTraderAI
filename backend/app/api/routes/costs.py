from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, text, and_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import User, ModelCost, DailyBudget, Strategy
from app.learning.cost_tracker import cost_tracker as ct

router = APIRouter(prefix="/api/costs", tags=["costs"])


class BudgetSetRequest(BaseModel):
    model_name: str
    max_usd_per_day: float


class ThrottleConfig(BaseModel):
    enabled: bool = True
    auto_fallback: bool = True


class CostSummary(BaseModel):
    date: str
    models: list[dict]
    overall_cost: float
    overall_calls: int
    budgets: list[dict]


@router.get("/live-summary")
async def get_live_summary(
    current_user: User = Depends(get_current_user),
):
    summary = await ct.get_user_cost_summary(current_user.id)
    return summary


@router.get("/today")
async def get_today_costs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        select(
            ModelCost.openrouter_model_name,
            func.count(ModelCost.id).label("calls"),
            func.sum(ModelCost.request_tokens).label("total_request_tokens"),
            func.sum(ModelCost.response_tokens).label("total_response_tokens"),
            func.sum(ModelCost.usd_cost).label("total_cost"),
        )
        .where(ModelCost.user_id == current_user.id, ModelCost.created_at >= today)
        .group_by(ModelCost.openrouter_model_name)
        .order_by(func.sum(ModelCost.usd_cost).desc())
    )
    rows = result.all()

    models = []
    overall_cost = 0.0
    overall_calls = 0
    for row in rows:
        overall_cost += row.total_cost or 0.0
        overall_calls += row.calls
        models.append({
            "model": row.openrouter_model_name,
            "calls": row.calls,
            "request_tokens": row.total_request_tokens or 0,
            "response_tokens": row.total_response_tokens or 0,
            "cost": round(row.total_cost or 0.0, 6),
        })

    return {"date": today.isoformat(), "models": models, "overall_cost": round(overall_cost, 6), "overall_calls": overall_calls}


@router.get("/by-strategy")
async def get_costs_by_strategy(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    days: int = Query(7, ge=1, le=90),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(
            ModelCost.strategy_id,
            func.sum(ModelCost.usd_cost).label("total_cost"),
            func.count(ModelCost.id).label("calls"),
        )
        .where(ModelCost.user_id == current_user.id, ModelCost.created_at >= since)
        .group_by(ModelCost.strategy_id)
        .order_by(func.sum(ModelCost.usd_cost).desc())
    )
    rows = result.all()

    strategies = []
    for row in rows:
        strategy_name = "Unknown"
        total_c = row.total_cost or 0.0
        if row.strategy_id:
            s_result = await db.execute(select(Strategy.name).where(Strategy.id == row.strategy_id))
            s = s_result.scalar_one_or_none()
            if s:
                strategy_name = s
        strategies.append({
            "strategy_id": row.strategy_id,
            "strategy_name": strategy_name,
            "total_cost": round(total_c, 6),
            "calls": row.calls,
        })

    return {"days": days, "strategies": strategies}


@router.get("/by-strategy-detail/{strategy_id}")
async def get_strategy_cost_detail(
    strategy_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    days: int = Query(7, ge=1, le=90),
):
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == current_user.id))
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    since = datetime.now(timezone.utc) - timedelta(days=days)

    model_result = await db.execute(
        select(
            ModelCost.openrouter_model_name,
            func.count(ModelCost.id).label("calls"),
            func.sum(ModelCost.usd_cost).label("total_cost"),
            func.sum(ModelCost.request_tokens).label("total_req"),
            func.sum(ModelCost.response_tokens).label("total_resp"),
        )
        .where(
            ModelCost.user_id == current_user.id,
            ModelCost.strategy_id == strategy_id,
            ModelCost.created_at >= since,
        )
        .group_by(ModelCost.openrouter_model_name)
        .order_by(func.sum(ModelCost.usd_cost).desc())
    )
    model_rows = model_result.all()

    daily_result = await db.execute(
        select(
            func.date(ModelCost.created_at).label("day"),
            func.sum(ModelCost.usd_cost).label("total_cost"),
        )
        .where(
            ModelCost.user_id == current_user.id,
            ModelCost.strategy_id == strategy_id,
            ModelCost.created_at >= since,
        )
        .group_by(func.date(ModelCost.created_at))
        .order_by(text("day"))
    )

    return {
        "strategy_id": strategy_id,
        "strategy_name": strategy.name,
        "days": days,
        "models": [
            {
                "model": row.openrouter_model_name,
                "calls": row.calls,
                "cost": round(row.total_cost or 0.0, 6),
                "request_tokens": row.total_req or 0,
                "response_tokens": row.total_resp or 0,
            }
            for row in model_rows
        ],
        "daily": [
            {"date": str(row.day), "cost": round(row.total_cost or 0.0, 6)}
            for row in daily_result.all()
        ],
    }


@router.get("/predictive")
async def get_predictive_costs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    days_ahead: int = Query(30, ge=7, le=365),
):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    seven_days_ago = today - timedelta(days=7)
    thirty_days_ago = today - timedelta(days=30)

    # 7-day average
    result_7 = await db.execute(
        select(func.sum(ModelCost.usd_cost))
        .where(ModelCost.user_id == current_user.id, ModelCost.created_at >= seven_days_ago)
    )
    total_7d = result_7.scalar() or 0.0
    daily_avg_7 = total_7d / 7.0

    # 30-day average
    result_30 = await db.execute(
        select(func.sum(ModelCost.usd_cost))
        .where(ModelCost.user_id == current_user.id, ModelCost.created_at >= thirty_days_ago)
    )
    total_30d = result_30.scalar() or 0.0
    daily_avg_30 = total_30d / 30.0

    return {
        "seven_day_total": round(total_7d, 6),
        "seven_day_daily_avg": round(daily_avg_7, 6),
        "thirty_day_total": round(total_30d, 6),
        "thirty_day_daily_avg": round(daily_avg_30, 6),
        "days_projected": days_ahead,
        "projected_7day_rate": round(daily_avg_7 * days_ahead, 6),
        "projected_30day_rate": round(daily_avg_30 * days_ahead, 6),
    }


@router.get("/budgets")
async def get_budgets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        select(DailyBudget).where(DailyBudget.user_id == current_user.id, DailyBudget.date >= today)
    )
    budgets = result.scalars().all()

    return [
        {
            "id": b.id,
            "model_name": b.model_name,
            "max_usd_per_day": b.max_usd_per_day,
            "current_usd_spent": b.current_usd_spent,
            "usage_pct": round((b.current_usd_spent / b.max_usd_per_day * 100), 2) if b.max_usd_per_day > 0 else 0,
        }
        for b in budgets
    ]


@router.post("/budgets")
async def set_budget(
    data: BudgetSetRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        select(DailyBudget).where(
            DailyBudget.user_id == current_user.id,
            DailyBudget.model_name == data.model_name,
            DailyBudget.date >= today,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.max_usd_per_day = data.max_usd_per_day
    else:
        budget = DailyBudget(
            user_id=current_user.id,
            model_name=data.model_name,
            max_usd_per_day=data.max_usd_per_day,
            current_usd_spent=0.0,
            date=today,
        )
        db.add(budget)

    await db.flush()
    return {"model_name": data.model_name, "max_usd_per_day": data.max_usd_per_day}


@router.delete("/budgets/{budget_id}")
async def delete_budget(
    budget_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DailyBudget).where(DailyBudget.id == budget_id, DailyBudget.user_id == current_user.id)
    )
    budget = result.scalar_one_or_none()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    await db.delete(budget)
    return {"message": "Budget deleted"}


@router.get("/check")
async def check_budget_for_model(
    model_name: str = Query(..., description="Model name to check"),
    current_user: User = Depends(get_current_user),
):
    check = await ct.check_budget(current_user.id, model_name)
    return {
        "model": model_name,
        "allowed": check.allowed,
        "remaining": check.remaining,
        "spent": check.spent,
        "budget": check.budget,
        "reason": check.reason,
    }


@router.get("/history")
async def get_cost_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(
            func.date(ModelCost.created_at).label("day"),
            func.sum(ModelCost.usd_cost).label("total_cost"),
            func.count(ModelCost.id).label("calls"),
        )
        .where(ModelCost.user_id == current_user.id, ModelCost.created_at >= since)
        .group_by(func.date(ModelCost.created_at))
        .order_by(text("day"))
    )
    rows = result.all()

    return [
        {"date": str(row.day), "total_cost": round(row.total_cost or 0.0, 6), "calls": row.calls}
        for row in rows
    ]


@router.get("/models")
async def get_model_rates():
    rates = {
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.00, "output": 30.00},
        "claude-3-opus": {"input": 15.00, "output": 75.00},
        "claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
        "claude-3-haiku": {"input": 0.25, "output": 1.25},
        "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
        "gemini-1.5-flash-8b": {"input": 0.0375, "output": 0.15},
        "deepseek-chat": {"input": 0.14, "output": 0.28},
    }
    return {"rates": rates, "unit": "USD per 1M tokens"}


@router.post("/reset-daily")
async def reset_daily_budgets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(DailyBudget).where(DailyBudget.user_id == current_user.id, DailyBudget.date >= today)
    )
    for budget in result.scalars().all():
        budget.current_usd_spent = 0.0
    await db.flush()
    return {"message": "Daily budgets reset"}