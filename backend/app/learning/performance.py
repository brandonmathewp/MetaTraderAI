import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from collections import defaultdict

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.models.models import Trade, Strategy, PerformanceSnapshot, ModelCost

logger = logging.getLogger(__name__)


class PerformanceAnalyzer:
    async def analyze_strategy(self, strategy_id: int, days: int = 7) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=days)

        async with async_session_factory() as db:
            trades_result = await db.execute(
                select(Trade).where(
                    Trade.strategy_id == strategy_id,
                    Trade.created_at >= since,
                ).order_by(Trade.created_at.desc())
            )
            trades = trades_result.scalars().all()

            strategy_result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
            strategy = strategy_result.scalar_one_or_none()

        if not trades:
            return {
                "strategy_id": strategy_id,
                "strategy_name": strategy.name if strategy else "Unknown",
                "total_trades": 0,
                "message": "No trades in this period",
            }

        closed = [t for t in trades if t.outcome_pnl is not None]
        winning = [t for t in closed if t.outcome_pnl > 0]
        losing = [t for t in closed if t.outcome_pnl <= 0]

        total_pnl = sum(t.outcome_pnl or 0 for t in closed)
        win_rate = (len(winning) / len(closed)) * 100 if closed else 0

        avg_win = sum(t.outcome_pnl for t in winning) / len(winning) if winning else 0
        avg_loss = sum(abs(t.outcome_pnl) for t in losing) / len(losing) if losing else 0
        profit_factor = (sum(t.outcome_pnl for t in winning) / sum(abs(t.outcome_pnl) for t in losing)) if losing else float("inf") if winning else 0

        # Sharpe ratio approximation
        daily_pnls = defaultdict(float)
        for t in closed:
            if t.created_at:
                day = t.created_at.date()
                daily_pnls[day] += t.outcome_pnl or 0
        pnl_values = list(daily_pnls.values())
        avg_daily = sum(pnl_values) / len(pnl_values) if pnl_values else 0
        variance = sum((p - avg_daily) ** 2 for p in pnl_values) / len(pnl_values) if pnl_values else 0
        std_dev = variance ** 0.5
        sharpe = (avg_daily / std_dev) if std_dev > 0 else 0

        # Confidence analysis
        confident_trades = [t for t in closed if t.confidence is not None]
        conf_correct = [t for t in confident_trades if (t.confidence >= 0.7 and t.outcome_pnl > 0) or (t.confidence < 0.7 and t.outcome_pnl <= 0)]

        # Model correlation
        model_performance = defaultdict(lambda: {"wins": 0, "losses": 0, "total_pnl": 0.0, "count": 0})
        for t in closed:
            if t.model_prediction:
                try:
                    pred = __import__("json").loads(t.model_prediction)
                    model = pred.get("model", "unknown")
                except Exception:
                    model = "unknown"
                model_performance[model]["count"] += 1
                if t.outcome_pnl > 0:
                    model_performance[model]["wins"] += 1
                else:
                    model_performance[model]["losses"] += 1
                model_performance[model]["total_pnl"] += t.outcome_pnl or 0

        return {
            "strategy_id": strategy_id,
            "strategy_name": strategy.name if strategy else "Unknown",
            "period_days": days,
            "total_trades": len(trades),
            "closed_trades": len(closed),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "total_pnl": round(total_pnl, 4),
            "win_rate": round(win_rate, 1),
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
            "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else "∞",
            "sharpe_ratio": round(sharpe, 3),
            "confidence_accuracy": f"{len(conf_correct)}/{len(confident_trades)}" if confident_trades else "N/A",
            "model_breakdown": {
                model: {
                    "wins": d["wins"],
                    "losses": d["losses"],
                    "win_rate": round((d["wins"] / d["count"] * 100), 1) if d["count"] > 0 else 0,
                    "total_pnl": round(d["total_pnl"], 4),
                }
                for model, d in model_performance.items()
            },
            "daily_pnl": [
                {"date": str(day), "pnl": round(pnl, 4)}
                for day, pnl in sorted(daily_pnls.items())
            ],
        }

    async def save_snapshot(self, strategy_id: int, analysis: dict):
        async with async_session_factory() as db:
            snapshot = PerformanceSnapshot(
                strategy_id=strategy_id,
                win_rate=analysis.get("win_rate"),
                sharpe_ratio=analysis.get("sharpe_ratio"),
                total_trades=analysis.get("total_trades", 0),
                total_pnl=analysis.get("total_pnl", 0),
            )
            db.add(snapshot)
            await db.commit()

    async def get_snapshots(self, strategy_id: int, limit: int = 30) -> list[dict]:
        async with async_session_factory() as db:
            result = await db.execute(
                select(PerformanceSnapshot)
                .where(PerformanceSnapshot.strategy_id == strategy_id)
                .order_by(PerformanceSnapshot.snapshot_date.desc())
                .limit(limit)
            )
            return [
                {
                    "id": s.id,
                    "win_rate": s.win_rate,
                    "sharpe_ratio": s.sharpe_ratio,
                    "total_trades": s.total_trades,
                    "total_pnl": s.total_pnl,
                    "date": s.snapshot_date.isoformat() if s.snapshot_date else None,
                }
                for s in result.scalars().all()
            ]

    async def get_overall_stats(self, user_id: int) -> dict:
        async with async_session_factory() as db:
            from app.models.models import Portfolio

            result = await db.execute(
                select(func.count(Trade.id), func.sum(Trade.outcome_pnl))
                .join(Portfolio, Trade.portfolio_id == Portfolio.id)
                .where(Trade.outcome_pnl is not None, Portfolio.user_id == user_id)
            )
            total, total_pnl = result.one()

            strat_result = await db.execute(
                select(Strategy.id, Strategy.name)
                .where(Strategy.user_id == user_id)
                .limit(50)
            )

            strategies = []
            for s in strat_result.all():
                analysis = await self.analyze_strategy(s.id)
                strategies.append({
                    "id": s.id,
                    "name": s.name,
                    "win_rate": analysis.get("win_rate", 0),
                    "total_pnl": analysis.get("total_pnl", 0),
                })

            return {
                "total_trades": total or 0,
                "total_pnl": round(total_pnl or 0, 4),
                "strategies": strategies,
            }


analyzer = PerformanceAnalyzer()