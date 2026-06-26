from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import User, Strategy, AutoImproverMutation
from app.learning.trade_memory import trade_memory
from app.learning.performance import analyzer
from app.learning.auto_improver import improver
from app.learning.context_builder import context_builder

router = APIRouter(prefix="/api/learning", tags=["learning"])


class MemorySearchRequest(BaseModel):
    symbol: str | None = None
    top_k: int = 5
    only_successful: bool = False
    query_text: str | None = None


class ImproverConfig(BaseModel):
    auto_apply: bool = False
    aggressiveness: str = "moderate"
    improvement_threshold: float = -0.02
    min_trades: int = 5


@router.get("/memory/stats")
async def get_memory_stats(current_user: User = Depends(get_current_user)):
    return await trade_memory.get_stats(current_user.id)


@router.post("/memory/search")
async def search_memory(
    data: MemorySearchRequest,
    current_user: User = Depends(get_current_user),
):
    results = await trade_memory.query_similar(
        user_id=current_user.id,
        symbol=data.symbol,
        context_text=data.query_text,
        top_k=data.top_k,
        only_successful=data.only_successful,
    )
    return {"results": results, "count": len(results)}


@router.delete("/memory")
async def clear_memory(current_user: User = Depends(get_current_user)):
    await trade_memory.clear_all(current_user.id)
    return {"message": "Memory cleared"}


@router.get("/memory/context")
async def get_rag_context(
    symbol: str = Query(None),
    current_user: User = Depends(get_current_user),
):
    rag = await context_builder.build_rag_context(
        user_id=current_user.id,
        symbol=symbol,
    )
    return {"context": rag, "has_content": bool(rag)}


@router.get("/performance/strategy/{strategy_id}")
async def get_strategy_performance(
    strategy_id: int,
    days: int = Query(7, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    s_result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == current_user.id)
    )
    if not s_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Strategy not found")
    result = await analyzer.analyze_strategy(strategy_id, days)
    await analyzer.save_snapshot(strategy_id, result)
    return result


@router.get("/performance/overall")
async def get_overall_performance(current_user: User = Depends(get_current_user)):
    return await analyzer.get_overall_stats(current_user.id)


@router.get("/performance/snapshots/{strategy_id}")
async def get_snapshots(
    strategy_id: int,
    limit: int = Query(30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    s_result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == current_user.id)
    )
    if not s_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Strategy not found")
    return await analyzer.get_snapshots(strategy_id, limit)


@router.post("/improver/run/{strategy_id}")
async def run_improver(
    strategy_id: int,
    config: ImproverConfig = ImproverConfig(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    s_result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == current_user.id)
    )
    strategy = s_result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    should_break, reason = await improver.should_circuit_break(strategy_id)
    if should_break:
        return {"mutations": [], "circuit_broken": True, "reason": reason}

    before = await analyzer.analyze_strategy(strategy_id, days=7)
    improver.auto_apply = config.auto_apply
    improver.aggressiveness = config.aggressiveness
    mutations = await improver.run_improvement_cycle(strategy_id, current_user.id)

    return {
        "mutations": mutations,
        "auto_applied": config.auto_apply,
        "performance_before": {
            "win_rate": before.get("win_rate"),
            "profit_factor": before.get("profit_factor"),
            "total_pnl": before.get("total_pnl"),
        },
        "circuit_broken": False,
    }


@router.get("/improver/history/{strategy_id}")
async def get_improver_history(
    strategy_id: int,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    s_result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == current_user.id)
    )
    if not s_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Strategy not found")
    return await improver.get_mutation_history(strategy_id, limit)


@router.post("/improver/revert/{mutation_id}")
async def revert_mutation(
    mutation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AutoImproverMutation).join(Strategy).where(
            AutoImproverMutation.id == mutation_id,
            Strategy.user_id == current_user.id,
        )
    )
    mutation = result.scalar_one_or_none()
    if not mutation:
        raise HTTPException(status_code=404, detail="Mutation not found")
    mutation.applied = False
    return {"message": "Mutation reverted", "mutation_id": mutation_id}