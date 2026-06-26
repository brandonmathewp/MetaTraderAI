import json
import logging
from typing import Optional

from app.core.openrouter import get_openrouter
from app.engine.node_types import NodeStatus, GraphNodeData, NodeResult, ExecutionContext

logger = logging.getLogger(__name__)


class CouncilRunner:
    def __init__(self):
        self.openrouter = get_openrouter()

    async def run_council(
        self,
        node: GraphNodeData,
        aggregated_input: dict,
        ctx: ExecutionContext,
    ) -> NodeResult:
        voter_models = node.config.get("voter_models", [])
        presiding_model = node.config.get("presiding_model", node.config.get("model_name", "gpt-4o"))
        question = node.config.get("question", "Analyze the market data and decide: BUY, SELL, or HOLD?")

        if not voter_models:
            return NodeResult(
                node_id=node.id,
                status=NodeStatus.ERROR,
                error="No voter models configured for council",
            )

        context_text = self._build_context(aggregated_input)

        import asyncio

        async def run_voter(model_name: str, idx: int) -> Optional[dict]:
            try:
                messages = [
                    {
                        "role": "system",
                        "content": f"You are a trading analyst (Voter #{idx + 1}). Answer with a JSON: {{\"action\": \"BUY|SELL|HOLD\", \"confidence\": 0.0-1.0, \"reasoning\": \"...\"}}",
                    },
                    {"role": "user", "content": f"{context_text}\n\n{question}"},
                ]
                response = await self.openrouter.chat_completion_tracked(
                    user_id=ctx.user_id,
                    model=model_name,
                    messages=messages,
                    temperature=node.temperature,
                    max_tokens=node.max_tokens,
                    strategy_id=ctx.strategy_id,
                    node_label=f"{node.label} (Voter #{idx + 1})",
                    enforce_budget=True,
                    auto_fallback=True,
                )
                content = self.openrouter.extract_content(response)
                cost = self.openrouter.extract_cost(response)
                tokens = self.openrouter.extract_tokens(response)
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    parsed = {"action": "HOLD", "confidence": 0.5, "reasoning": content}
                return {"model": model_name, "vote": parsed, "cost": cost, "tokens": tokens}
            except Exception as e:
                logger.error(f"Council voter {model_name} error: {e}")
                return {"model": model_name, "vote": {"action": "HOLD", "confidence": 0.0, "reasoning": str(e)}, "cost": 0.0, "tokens": {}}

        voter_tasks = [run_voter(model, i) for i, model in enumerate(voter_models)]
        voter_responses = await asyncio.gather(*voter_tasks)

        total_cost = 0.0
        total_tokens = 0
        voter_results = []
        for vr in voter_responses:
            if vr:
                voter_results.append(vr)
                total_cost += vr.get("cost", 0.0)
                total_tokens += vr.get("tokens", {}).get("total_tokens", 0)

        votes_text = json.dumps([{"voter": vr["model"], "vote": vr["vote"]} for vr in voter_results], indent=2)

        try:
            messages = [
                {
                    "role": "system",
                    "content": "You are the presiding judge of a trading council. Review the voters' opinions and produce a final JSON: {\"action\": \"BUY|SELL|HOLD\", \"confidence\": 0.0-1.0, \"reasoning\": \"...\", \"vote_breakdown\": {\"BUY\": N, \"SELL\": N, \"HOLD\": N}}",
                },
                {"role": "user", "content": f"Market context:\n{context_text}\n\nVoter opinions:\n{votes_text}\n\nMake your final judgment."},
            ]
            response = await self.openrouter.chat_completion_tracked(
                user_id=ctx.user_id,
                model=presiding_model,
                messages=messages,
                temperature=0.5,
                max_tokens=node.max_tokens,
                strategy_id=ctx.strategy_id,
                node_label=f"{node.label} (Judge)",
                enforce_budget=True,
                auto_fallback=True,
            )
            content = self.openrouter.extract_content(response)
            cost = self.openrouter.extract_cost(response)
            total_cost += cost
            tokens = self.openrouter.extract_tokens(response)
            total_tokens += tokens.get("total_tokens", 0)

            try:
                final = json.loads(content)
            except json.JSONDecodeError:
                final = {"action": "HOLD", "confidence": 0.5, "reasoning": content}

        except Exception as e:
            final = {"action": "HOLD", "confidence": 0.0, "reasoning": f"Judge error: {str(e)}"}

        return NodeResult(
            node_id=node.id,
            status=NodeStatus.SUCCESS,
            data={
                "council_decision": final,
                "voter_results": [
                    {"model": vr["model"], "action": vr["vote"].get("action"), "confidence": vr["vote"].get("confidence")}
                    for vr in voter_results
                ],
                "voter_count": len(voter_results),
            },
            cost_usd=total_cost,
            tokens_used=total_tokens,
        )

    @staticmethod
    def _build_context(input_data: dict) -> str:
        parts = []
        for key, value in input_data.items():
            if key.startswith("from_"):
                if isinstance(value, dict):
                    parts.append(json.dumps(value, indent=2))
                else:
                    parts.append(str(value))
        return "\n\n".join(parts) if parts else "No additional context available."