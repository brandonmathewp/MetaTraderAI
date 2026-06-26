import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import chromadb
from chromadb.utils import embedding_functions

from app.core.config import get_settings
from app.core.database import async_session_factory
from app.models.models import Trade

logger = logging.getLogger(__name__)
settings = get_settings()


class TradeMemory:
    def __init__(self):
        self._client: Optional[chromadb.PersistentClient] = None
        self._collection = None
        self._ef = embedding_functions.DefaultEmbeddingFunction()

    @property
    def client(self) -> chromadb.PersistentClient:
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=settings.CHROMA_PERSIST_DIR,
                settings=chromadb.Settings(anonymized_telemetry=False),
            )
        return self._client

    @property
    def collection(self):
        if self._collection is None:
            try:
                self._collection = self.client.get_collection(
                    name="trade_memories",
                    embedding_function=self._ef,
                )
            except Exception:
                self._collection = self.client.create_collection(
                    name="trade_memories",
                    embedding_function=self._ef,
                    metadata={"description": "Trade memory for RAG"},
                )
        return self._collection

    def _build_trade_text(self, trade: dict) -> str:
        parts = [
            f"Symbol: {trade.get('symbol', 'unknown')}",
            f"Side: {trade.get('side', 'unknown')}",
            f"Price: ${trade.get('price', 0):.2f}",
            f"Quantity: {trade.get('quantity', 0)}",
            f"Confidence: {trade.get('confidence', 0):.2f}",
            f"Outcome PnL: ${trade.get('outcome_pnl', 0):.2f}",
            f"Status: {trade.get('status', 'unknown')}",
            f"Prediction: {str(trade.get('model_prediction', ''))[:200]}",
        ]
        if trade.get("indicators"):
            ind = trade["indicators"]
            parts.append(f"RSI: {ind.get('rsi', 'N/A')}")
            parts.append(f"MACD: {ind.get('macd', 'N/A')}")
            parts.append(f"SMA20: {ind.get('sma20', 'N/A')}")
        return "\n".join(parts)

    async def store_trade(
        self,
        trade_id: int,
        user_id: int,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        outcome_pnl: Optional[float],
        confidence: Optional[float],
        model_prediction: Optional[str],
        indicators: Optional[dict] = None,
    ):
        try:
            trade_data = {
                "symbol": symbol,
                "side": side,
                "price": price,
                "quantity": quantity,
                "outcome_pnl": outcome_pnl,
                "confidence": confidence,
                "model_prediction": model_prediction,
                "indicators": indicators,
                "status": "stored",
            }
            text = self._build_trade_text(trade_data)
            doc_id = f"trade_{trade_id}"
            metadata = {
                "user_id": user_id,
                "symbol": symbol,
                "side": side,
                "outcome_pnl": str(outcome_pnl or 0),
                "confidence": str(confidence or 0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            self.collection.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[metadata],
            )
            logger.info(f"Trade {trade_id} stored in memory ({symbol} {side})")
        except Exception as e:
            logger.error(f"Failed to store trade memory: {e}")

    async def query_similar(
        self,
        user_id: int,
        symbol: Optional[str] = None,
        context_text: Optional[str] = None,
        top_k: int = 5,
        only_successful: bool = False,
    ) -> list[dict]:
        try:
            where_filter = {"user_id": user_id}
            if symbol:
                where_filter["symbol"] = symbol

            query_text = context_text or "trade analysis"
            results = self.collection.query(
                query_texts=[query_text],
                n_results=min(top_k * 3, 50),
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )

            memories = []
            if results.get("documents") and results["documents"][0]:
                for i, doc in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                    distance = results["distances"][0][i] if results.get("distances") else 1.0

                    outcome = float(meta.get("outcome_pnl", 0))
                    if only_successful and outcome <= 0:
                        continue

                    memories.append({
                        "document": doc,
                        "metadata": meta,
                        "relevance": round(1.0 - min(distance, 1.0), 3),
                    })

            return memories[:top_k]
        except Exception as e:
            logger.error(f"Memory query failed: {e}")
            return []

    async def delete_trade(self, trade_id: int):
        try:
            self.collection.delete(ids=[f"trade_{trade_id}"])
        except Exception as e:
            logger.error(f"Failed to delete memory {trade_id}: {e}")

    async def clear_all(self, user_id: Optional[int] = None):
        try:
            if user_id is not None:
                results = self.collection.get(
                    where={"user_id": user_id},
                    include=[],
                )
                if results.get("ids"):
                    self.collection.delete(ids=results["ids"])
            else:
                self.client.delete_collection("trade_memories")
                self._collection = None
        except Exception as e:
            logger.error(f"Failed to clear memories: {e}")

    async def get_stats(self, user_id: Optional[int] = None) -> dict:
        try:
            where = {"user_id": user_id} if user_id else None
            results = self.collection.get(where=where, include=["metadatas"])
            total = len(results.get("ids", []))

            outcomes = []
            for meta in (results.get("metadatas") or []):
                try:
                    outcomes.append(float(meta.get("outcome_pnl", 0)))
                except (ValueError, TypeError):
                    pass

            return {
                "total_memories": total,
                "winning_trades": sum(1 for o in outcomes if o > 0),
                "losing_trades": sum(1 for o in outcomes if o < 0),
                "total_pnl": sum(outcomes),
                "avg_pnl": (sum(outcomes) / len(outcomes)) if outcomes else 0,
            }
        except Exception as e:
            logger.error(f"Memory stats failed: {e}")
            return {"total_memories": 0, "winning_trades": 0, "losing_trades": 0, "total_pnl": 0, "avg_pnl": 0}


trade_memory = TradeMemory()