import json
import logging
from typing import Optional

from app.learning.trade_memory import trade_memory
from app.learning.cost_tracker import cost_tracker

logger = logging.getLogger(__name__)


class ContextBuilder:
    def __init__(self):
        self.memory = trade_memory

    async def build_rag_context(
        self,
        user_id: int,
        symbol: Optional[str] = None,
        current_context: Optional[dict] = None,
        top_k: int = 5,
        include_successful: bool = True,
        include_failures: bool = True,
    ) -> str:
        context_parts = []

        if include_successful:
            successful = await self.memory.query_similar(
                user_id=user_id,
                symbol=symbol,
                context_text=json.dumps(current_context) if current_context else None,
                top_k=max(top_k // 2, 1),
                only_successful=True,
            )
            if successful:
                memories_text = "\n\n".join(
                    f"[SUCCESS #{i+1}] (relevance: {m['relevance']})\n{m['document']}"
                    for i, m in enumerate(successful)
                )
                context_parts.append(f"Past successful trades:\n{memories_text}")

        if include_failures:
            all_memories = await self.memory.query_similar(
                user_id=user_id,
                symbol=symbol,
                context_text=json.dumps(current_context) if current_context else None,
                top_k=top_k,
                only_successful=False,
            )
            failures = [m for m in all_memories if float(m.get("metadata", {}).get("outcome_pnl", 0)) <= 0]
            if failures:
                failures_text = "\n\n".join(
                    f"[FAILURE #{i+1}] (relevance: {m['relevance']})\n{m['document']}"
                    for i, m in enumerate(failures[:max(top_k // 2, 1)])
                )
                context_parts.append(f"Past trades to learn from:\n{failures_text}")

        if not context_parts:
            return ""

        return (
            "=== TRADE MEMORY (RAG) ===\n"
            "The following are similar past trades and their outcomes. "
            "Use this to inform your decision.\n\n"
            + "\n\n---\n\n".join(context_parts)
            + "\n\n=== END MEMORY ==="
        )

    async def build_system_prompt_with_memory(
        self,
        user_id: int,
        base_prompt: str,
        symbol: Optional[str] = None,
        extra_context: Optional[dict] = None,
    ) -> str:
        rag = await self.build_rag_context(
            user_id=user_id,
            symbol=symbol,
            current_context=extra_context,
        )

        if rag:
            return base_prompt + "\n\n" + rag

        return base_prompt


context_builder = ContextBuilder()