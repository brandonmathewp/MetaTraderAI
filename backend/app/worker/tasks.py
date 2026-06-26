import logging

from app.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task
def fetch_market_data(symbol: str, interval: str = "1m"):
    logger.info(f"Fetching market data for {symbol} ({interval})")
    return {"symbol": symbol, "interval": interval, "status": "queued"}


@celery_app.task
def execute_model_graph(strategy_id: int, user_id: int):
    logger.info(f"Executing model graph for strategy {strategy_id} (user {user_id})")
    return {"strategy_id": strategy_id, "status": "queued"}


@celery_app.task
def run_auto_improver(strategy_id: int, user_id: int):
    logger.info(f"Running auto-improver for strategy {strategy_id} (user {user_id})")
    return {"strategy_id": strategy_id, "status": "queued"}


@celery_app.task
def compute_performance_snapshot(strategy_id: int):
    logger.info(f"Computing performance snapshot for strategy {strategy_id}")
    return {"strategy_id": strategy_id, "status": "queued"}