import json
import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.models.models import (
    Strategy, GraphNode, GraphEdge, AutoImproverMutation,
    Trade, Portfolio,
)
from app.learning.performance import analyzer
from app.learning.cost_tracker import cost_tracker

logger = logging.getLogger(__name__)

MODEL_OPTIONS = [
    "gpt-4o", "gpt-4o-mini", "gpt-4-turbo",
    "claude-3-opus", "claude-3.5-sonnet", "claude-3-haiku",
    "gemini-2.0-flash", "deepseek-chat",
]


class AutoImprover:
    def __init__(
        self,
        improvement_threshold: float = -0.02,
        min_trades_for_mutation: int = 5,
        max_mutations_per_cycle: int = 3,
        auto_apply: bool = False,
        aggressiveness: str = "moderate",
    ):
        self.improvement_threshold = improvement_threshold
        self.min_trades_for_mutation = min_trades_for_mutation
        self.max_mutations_per_cycle = max_mutations_per_cycle
        self.auto_apply = auto_apply
        self.aggressiveness = aggressiveness

    async def run_improvement_cycle(
        self,
        strategy_id: int,
        user_id: int,
    ) -> list[dict]:
        analysis = await analyzer.analyze_strategy(strategy_id, days=7)

        if analysis.get("total_trades", 0) < self.min_trades_for_mutation:
            logger.info(f"Strategy {strategy_id}: not enough trades ({analysis['total_trades']}) for mutation")
            return []

        async with async_session_factory() as db:
            s_result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
            strategy = s_result.scalar_one_or_none()
            if not strategy or not strategy.graph_json:
                return []

            nodes_result = await db.execute(
                select(GraphNode).where(GraphNode.strategy_id == strategy_id)
            )
            nodes = nodes_result.scalars().all()

            edges_result = await db.execute(
                select(GraphEdge).where(GraphEdge.strategy_id == strategy_id)
            )
            edges = edges_result.scalars().all()

            llm_nodes = [n for n in nodes if n.node_type in ("llmModel", "council")]
            action_nodes = [n for n in nodes if n.node_type == "action"]

            if not llm_nodes:
                return []

            mutations = []
            model_breakdown = analysis.get("model_breakdown", {})

            # Determine if we need improvement
            needs_improvement = (
                analysis.get("profit_factor", 0) < 1.0
                or analysis.get("win_rate", 0) < 45
            )

            if not needs_improvement and self.aggressiveness == "conservative":
                return []

            mutation_fns = []

            # 1. Model swap for underperforming models
            if model_breakdown:
                for llm_node in llm_nodes:
                    node_config = {}
                    if llm_node.node_config_json:
                        try:
                            node_config = json.loads(llm_node.node_config_json)
                        except json.JSONDecodeError:
                            pass
                    current_model = node_config.get("model_name", "gpt-4o")
                    node_perf = model_breakdown.get(current_model, {})
                    if node_perf.get("win_rate", 100) < 50:
                        mutation_fns.append(
                            lambda n=llm_node, cfg=node_config, old=current_model: self._mutate_model_swap(n, cfg, old)
                        )

            # 2. Temperature tweak
            if random.random() < 0.4:
                for llm_node in llm_nodes:
                    node_config = json.loads(llm_node.node_config_json) if llm_node.node_config_json else {}
                    mutation_fns.append(
                        lambda n=llm_node, cfg=node_config: self._mutate_temperature(n, cfg)
                    )

            # 3. Prompt optimization
            if random.random() < 0.3:
                for llm_node in llm_nodes:
                    node_config = json.loads(llm_node.node_config_json) if llm_node.node_config_json else {}
                    old_prompt = node_config.get("system_prompt", "")
                    if old_prompt:
                        new_prompt = self._optimize_prompt(old_prompt, analysis)
                        if new_prompt != old_prompt:
                            node_config["system_prompt"] = new_prompt
                            mutation_fns.append(
                                lambda n=llm_node, cfg=node_config: ("prompt_optimize", cfg)
                            )

            # 4. Threshold adjustment for action nodes
            if random.random() < 0.25:
                for action_node in action_nodes:
                    node_config = json.loads(action_node.node_config_json) if action_node.node_config_json else {}
                    mutation_fns.append(
                        lambda n=action_node, cfg=node_config: self._mutate_threshold(n, cfg, analysis)
                    )

            # 5. Node rewire (shuffle council voters or change merge strategy)
            if random.random() < 0.15 and len(llm_nodes) >= 2:
                mutation_fns.append(
                    lambda: self._mutate_rewire(strategy_id, db)
                )

            # Execute mutations
            random.shuffle(mutation_fns)
            mutation_count = 0

            for fn in mutation_fns[:self.max_mutations_per_cycle]:
                try:
                    result = await fn() if asyncio.iscoroutinefunction(fn) else fn()
                    if result:
                        mutation_count += 1

                        # Handle different result formats
                        if isinstance(result, tuple) and len(result) == 2:
                            mutation_type, new_config = result
                            node = llm_nodes[0] if llm_nodes else None
                            if node:
                                node.node_config_json = json.dumps(new_config)
                                mutation = AutoImproverMutation(
                                    strategy_id=strategy_id,
                                    old_graph_json=json.dumps({"nodes": len(nodes), "edges": len(edges)}),
                                    new_graph_json=json.dumps({
                                        "mutation_type": mutation_type,
                                        "node_id": node.id,
                                        "new_config": new_config,
                                    }),
                                    reason=f"Auto-improver: {mutation_type}",
                                    applied=self.auto_apply,
                                    performance_before=json.dumps({
                                        "win_rate": analysis.get("win_rate"),
                                        "profit_factor": analysis.get("profit_factor"),
                                    }),
                                )
                                db.add(mutation)
                                mutations.append({
                                    "type": mutation_type,
                                    "node_id": node.id,
                                    "auto_applied": self.auto_apply,
                                })

                except Exception as e:
                    logger.error(f"Mutation failed: {e}")

            if mutations:
                await db.commit()
                logger.info(f"Strategy {strategy_id}: applied {len(mutations)} mutations")

            return mutations

    def _mutate_model_swap(self, node: GraphNode, config: dict, current_model: str) -> Optional[tuple]:
        cheaper = [m for m in MODEL_OPTIONS if m != current_model]
            if not cheaper:
                new_model = random.choice([m for m in MODEL_OPTIONS if m != current_model])
            else:
                new_model = random.choice(cheaper)

        config["model_name"] = new_model
        logger.info(f"Model swap: {current_model} -> {new_model}")
        return ("model_swap", config)

    def _mutate_temperature(self, node: GraphNode, config: dict) -> Optional[tuple]:
        current = config.get("temperature", 0.7)
        delta = random.uniform(-0.2, 0.2)
        new_temp = round(max(0.0, min(2.0, current + delta)), 2)
        if abs(new_temp - current) < 0.05:
            return None
        config["temperature"] = new_temp
        logger.info(f"Temperature tweak: {current} -> {new_temp}")
        return ("temperature_tweak", config)

    def _mutate_threshold(self, node: GraphNode, config: dict, analysis: dict) -> Optional[tuple]:
        current = config.get("confidence_threshold", 0.7)
        win_rate = analysis.get("win_rate", 50)
        if win_rate < 45:
            new_threshold = round(min(1.0, current + 0.05), 2)
        else:
            new_threshold = round(max(0.3, current - 0.05), 2)
        if abs(new_threshold - current) < 0.01:
            return None
        config["confidence_threshold"] = new_threshold
        logger.info(f"Threshold adjust: {current} -> {new_threshold}")
        return ("threshold_adjust", config)

    async def _mutate_rewire(self, strategy_id: int, db: AsyncSession):
        nodes_result = await db.execute(
            select(GraphNode).where(GraphNode.strategy_id == strategy_id)
        )
        nodes = nodes_result.scalars().all()
        merge_nodes = [n for n in nodes if n.node_type == "merge"]
        if not merge_nodes:
            return None
        merge_node = random.choice(merge_nodes)
        config = json.loads(merge_node.node_config_json) if merge_node.node_config_json else {}
        strategies = ["concatenate", "best_confidence", "weighted"]
        current = config.get("merge_strategy", "concatenate")
        new_strat = random.choice([s for s in strategies if s != current])
        config["merge_strategy"] = new_strat
        merge_node.node_config_json = json.dumps(config)
        logger.info(f"Node rewire: merge strategy {current} -> {new_strat}")
        return None

    def _optimize_prompt(self, prompt: str, analysis: dict) -> str:
        improvements = []
        win_rate = analysis.get("win_rate", 50)
        if win_rate < 40:
            improvements.append(
                "Be more conservative. Only recommend BUY when multiple indicators agree. "
                "Reduce false positives."
            )
        elif win_rate > 60:
            improvements.append(
                "Increase position sizes when confidence is high."
            )

        if analysis.get("losing_trades", 0) > analysis.get("winning_trades", 0):
            improvements.append(
                "Consider stop-loss at -3%. Exit trades faster when they move against you."
            )

        if not improvements:
            return prompt

        suffix = "\n\n[IMPROVEMENT INSTRUCTIONS]\n" + "\n".join(improvements)

        if "[IMPROVEMENT INSTRUCTIONS]" in prompt:
            parts = prompt.split("[IMPROVEMENT INSTRUCTIONS]")
            return parts[0] + suffix

        return prompt + suffix

    async def should_circuit_break(self, strategy_id: int) -> tuple[bool, Optional[str]]:
        analysis = await analyzer.analyze_strategy(strategy_id, days=7)
        total_pnl = analysis.get("total_pnl", 0)
        if total_pnl < self.improvement_threshold * 10000:
            return True, f"P&L too negative: ${total_pnl:.2f}"

        win_rate = analysis.get("win_rate", 50)
        if win_rate < 20 and analysis.get("total_trades", 0) > 10:
            return True, f"Win rate critically low: {win_rate}%"

        return False, None

    async def get_mutation_history(self, strategy_id: int, limit: int = 20) -> list[dict]:
        async with async_session_factory() as db:
            result = await db.execute(
                select(AutoImproverMutation)
                .where(AutoImproverMutation.strategy_id == strategy_id)
                .order_by(AutoImproverMutation.created_at.desc())
                .limit(limit)
            )
            return [
                {
                    "id": m.id,
                    "reason": m.reason,
                    "applied": m.applied,
                    "performance_before": m.performance_before,
                    "performance_after": m.performance_after,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in result.scalars().all()
            ]


import asyncio


improver = AutoImprover()