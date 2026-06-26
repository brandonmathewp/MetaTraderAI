import asyncio
import logging

from app.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task
def fetch_market_data(symbol: str, interval: str = "1m"):
    async def _run():
        from app.market.binance_client import BinanceClient
        from app.market.indicators import get_indicators
        client = BinanceClient()
        try:
            indicators = await get_indicators(client, symbol, interval)
            logger.info(f"Fetched market data for {symbol} ({interval}): {list(indicators.keys())}")
            return {"symbol": symbol, "interval": interval, "status": "completed", "indicators": indicators}
        except Exception as e:
            logger.error(f"Market data fetch failed for {symbol}: {e}")
            return {"symbol": symbol, "interval": interval, "status": "error", "error": str(e)}
        finally:
            await client.close()
    return asyncio.run(_run())


@celery_app.task
def execute_model_graph(strategy_id: int, user_id: int, portfolio_id: int | None = None):
    async def _run():
        from sqlalchemy import select
        from app.core.database import async_session_factory
        from app.models.models import Strategy, GraphNode, GraphEdge
        from app.engine.strategy_scheduler import scheduler

        async with async_session_factory() as db:
            s_result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
            strategy = s_result.scalar_one_or_none()
            if not strategy:
                return {"strategy_id": strategy_id, "status": "error", "error": "Strategy not found"}

            nodes_result = await db.execute(
                select(GraphNode).where(GraphNode.strategy_id == strategy_id)
            )
            db_nodes = [
                {
                    "id": n.id, "node_type": n.node_type, "label": n.label,
                    "node_config_json": n.node_config_json,
                }
                for n in nodes_result.scalars().all()
            ]

            edges_result = await db.execute(
                select(GraphEdge).where(GraphEdge.strategy_id == strategy_id)
            )
            db_edges = [
                {
                    "id": e.id, "source_node_id": e.source_node_id,
                    "target_node_id": e.target_node_id,
                    "source_handle": e.source_handle, "target_handle": e.target_handle,
                }
                for e in edges_result.scalars().all()
            ]

        try:
            results = await scheduler.execute_strategy(
                strategy_id, user_id, portfolio_id, db_nodes, db_edges,
            )
            logger.info(f"Strategy {strategy_id} executed: {len(results)} nodes")
            return {
                "strategy_id": strategy_id,
                "status": "completed",
                "nodes_executed": len(results),
                "total_cost": sum(r.cost_usd for r in results.values()),
            }
        except Exception as e:
            logger.error(f"Strategy {strategy_id} execution failed: {e}")
            return {"strategy_id": strategy_id, "status": "error", "error": str(e)}
    return asyncio.run(_run())


@celery_app.task
def run_auto_improver(strategy_id: int, user_id: int):
    async def _run():
        from app.learning.auto_improver import improver
        try:
            mutations = await improver.run_improvement_cycle(strategy_id, user_id)
            logger.info(f"Auto-improver ran for strategy {strategy_id}: {len(mutations)} mutations")
            return {
                "strategy_id": strategy_id,
                "status": "completed",
                "mutations_applied": len(mutations),
                "mutations": mutations,
            }
        except Exception as e:
            logger.error(f"Auto-improver failed for strategy {strategy_id}: {e}")
            return {"strategy_id": strategy_id, "status": "error", "error": str(e)}
    return asyncio.run(_run())


@celery_app.task
def compute_performance_snapshot(strategy_id: int, days: int = 7):
    async def _run():
        from app.learning.performance import analyzer
        try:
            result = await analyzer.analyze_strategy(strategy_id, days=days)
            await analyzer.save_snapshot(strategy_id, result)
            logger.info(f"Performance snapshot computed for strategy {strategy_id}")
            return {
                "strategy_id": strategy_id,
                "status": "completed",
                "win_rate": result.get("win_rate"),
                "profit_factor": result.get("profit_factor"),
                "total_trades": result.get("total_trades"),
                "total_pnl": result.get("total_pnl"),
            }
        except Exception as e:
            logger.error(f"Performance snapshot failed for strategy {strategy_id}: {e}")
            return {"strategy_id": strategy_id, "status": "error", "error": str(e)}
    return asyncio.run(_run())