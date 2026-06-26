import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Callable

from app.engine.node_types import (
    NodeType, NodeStatus, GraphNodeData, GraphEdgeData,
    NodeResult, ExecutionContext,
)
from app.engine.graph_executor import GraphExecutor
from app.engine.council import CouncilRunner
from app.market.binance_client import BinanceClient
from app.market.indicators import get_indicators
from app.core.openrouter import get_openrouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.models.models import Portfolio as DbPortfolio
from app.trading.paper_broker import PaperBroker
from app.trading.order_manager import OrderSide, OrderStatus
from app.trading.portfolio import Portfolio as PortfolioLib
from app.learning.context_builder import context_builder as rag_builder
from app.learning.trade_memory import trade_memory

logger = logging.getLogger(__name__)


@dataclass
class StrategyRunState:
    strategy_id: int
    user_id: int
    portfolio_id: Optional[int]
    is_running: bool = False
    task: Optional[asyncio.Task] = None
    last_run: Optional[datetime] = None
    run_count: int = 0
    total_cost: float = 0.0


class StrategyScheduler:
    def __init__(self):
        self._strategies: dict[int, StrategyRunState] = {}
        self._executor = GraphExecutor()
        self._council = CouncilRunner()
        self._setup_handlers()
        self._running = False

    async def _get_user_key(self, user_id: int, service: str) -> str:
        try:
            from app.core.credentials import credential_service
            from app.core.config import get_settings
            settings = get_settings()
            env_key = settings.OPENROUTER_API_KEY if service == "openrouter" else settings.BINANCE_API_KEY
            return await credential_service.get_effective_key(user_id, service, env_key) or ""
        except Exception:
            return ""

    async def _get_user_secret(self, user_id: int, service: str) -> str:
        try:
            from app.core.credentials import credential_service
            from app.core.config import get_settings
            settings = get_settings()
            env_secret = settings.BINANCE_API_SECRET
            return await credential_service.get_effective_secret(user_id, service, env_secret) or ""
        except Exception:
            return ""

    def _setup_handlers(self):
        self._executor.register_handler(NodeType.TRIGGER, self._handle_trigger)
        self._executor.register_handler(NodeType.MARKET_DATA, self._handle_market_data)
        self._executor.register_handler(NodeType.LLM_MODEL, self._handle_llm_model)
        self._executor.register_handler(NodeType.COUNCIL, self._handle_council)
        self._executor.register_handler(NodeType.FILTER, self._handle_filter)
        self._executor.register_handler(NodeType.MERGE, self._handle_merge)
        self._executor.register_handler(NodeType.ACTION, self._handle_action)
        self._executor.register_handler(NodeType.SCRIPT, self._handle_script)

    def set_executor_on_event(self, callback):
        self._executor.on_event(callback)

    async def _handle_trigger(self, node: GraphNodeData, inp: dict, ctx: ExecutionContext) -> NodeResult:
        return NodeResult(
            node_id=node.id,
            status=NodeStatus.SUCCESS,
            data={"triggered": True, "timestamp": datetime.now(timezone.utc).isoformat()},
        )

    async def _handle_market_data(self, node: GraphNodeData, inp: dict, ctx: ExecutionContext) -> NodeResult:
        symbol = node.symbol or "BTCUSDT"
        interval = node.interval
        client = BinanceClient()
        try:
            indicators = await get_indicators(client, symbol, interval)
            return NodeResult(
                node_id=node.id,
                status=NodeStatus.SUCCESS,
                data=indicators,
            )
        except Exception as e:
            return NodeResult(node_id=node.id, status=NodeStatus.ERROR, error=str(e))
        finally:
            await client.close()

    async def _handle_llm_model(self, node: GraphNodeData, inp: dict, ctx: ExecutionContext) -> NodeResult:
        model_name = node.model_name or "gpt-4o"
        system_prompt = node.system_prompt or "You are a trading analyst. Output JSON: {\"action\": \"BUY|SELL|HOLD\", \"confidence\": 0.0-1.0, \"reasoning\": \"...\"}"

        # Build context from incurrent inputs
        context_parts = []
        for key, value in inp.items():
            if key.startswith("from_") and isinstance(value, dict):
                context_parts.append(json.dumps(value, indent=2))
            elif key.startswith("from_"):
                context_parts.append(str(value))

        context_text = "\n\n".join(context_parts) if context_parts else "No market data available."

        # Inject RAG memory context
        try:
            rag_context = await rag_builder.build_rag_context(
                user_id=ctx.user_id,
                symbol=node.symbol,
                current_context={"market_data": context_text[:1000]},
            )
            if rag_context:
                context_text = rag_context + "\n\n---\n\n" + context_text
        except Exception as e:
            logger.debug(f"RAG context injection failed (non-critical): {e}")

        try:
            openrouter = get_openrouter()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context_text},
            ]
            response = await openrouter.chat_completion_tracked(
                user_id=ctx.user_id,
                model=model_name,
                messages=messages,
                temperature=node.temperature,
                max_tokens=node.max_tokens,
                strategy_id=ctx.strategy_id,
                node_label=node.label,
                enforce_budget=True,
                auto_fallback=True,
            )
            content = openrouter.extract_content(response)
            cost = openrouter.extract_cost(response)
            tokens = openrouter.extract_tokens(response)

            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                parsed = {"raw": content}

            return NodeResult(
                node_id=node.id,
                status=NodeStatus.SUCCESS,
                data={"prediction": parsed, "model": model_name, "raw_content": content[:500]},
                cost_usd=cost,
                tokens_used=tokens.get("total_tokens", 0),
            )
        except Exception as e:
            return NodeResult(node_id=node.id, status=NodeStatus.ERROR, error=str(e))

    async def _handle_council(self, node: GraphNodeData, inp: dict, ctx: ExecutionContext) -> NodeResult:
        return await self._council.run_council(node, inp, ctx)

    async def _handle_filter(self, node: GraphNodeData, inp: dict, ctx: ExecutionContext) -> NodeResult:
        condition = node.condition or "true"
        items = []
        for key, value in inp.items():
            if key.startswith("from_") and isinstance(value, dict):
                items.append(value)

        filtered = items  # Default: pass through (safety: no eval)
        safe_locals = {"items": items, "data": items}
        try:
            result = eval(condition, {"__builtins__": {}}, safe_locals)
            if isinstance(result, list):
                filtered = result
            elif result and isinstance(items, list):
                filtered = items
        except Exception as e:
            logger.warning(f"Filter condition eval failed: {e}")

        return NodeResult(
            node_id=node.id,
            status=NodeStatus.SUCCESS,
            data={"filtered": filtered, "condition": condition, "count": len(filtered)},
        )

    async def _handle_merge(self, node: GraphNodeData, inp: dict, ctx: ExecutionContext) -> NodeResult:
        strategy = node.merge_strategy
        merged = {}
        all_items = []

        for key, value in inp.items():
            if key.startswith("from_"):
                if isinstance(value, dict):
                    if strategy == "weighted" and "confidence" in value:
                        merged[key] = value
                    elif strategy == "best_confidence":
                        all_items.append(value)
                    else:
                        merged[key] = value

        if strategy == "best_confidence" and all_items:
            best = max(all_items, key=lambda x: x.get("prediction", {}).get("confidence", 0) if isinstance(x.get("prediction"), dict) else 0)
            merged = best

        return NodeResult(node_id=node.id, status=NodeStatus.SUCCESS, data={"merged": merged, "strategy": strategy})

    async def _handle_action(self, node: GraphNodeData, inp: dict, ctx: ExecutionContext) -> NodeResult:
        if not ctx.portfolio_id:
            return NodeResult(node_id=node.id, status=NodeStatus.SKIPPED, error="No portfolio attached")

        threshold = node.confidence_threshold
        decisions = []

        for key, value in inp.items():
            if key.startswith("from_") and isinstance(value, dict):
                prediction = value.get("prediction", value)
                if isinstance(prediction, dict):
                    decisions.append(prediction)

        last_decision = {}
        if decisions:
            last_decision = decisions[-1]

        action = last_decision.get("action", "HOLD")
        confidence = last_decision.get("confidence", 0.0)

        if action in ("BUY", "SELL") and confidence >= threshold and ctx.portfolio_id:
            async with async_session_factory() as db:
                result = await db.execute(select(DbPortfolio).where(DbPortfolio.id == ctx.portfolio_id))
                db_p = result.scalar_one_or_none()

                if db_p:
                    port = PortfolioLib(
                        id=db_p.id,
                        user_id=db_p.user_id,
                        name=db_p.name,
                        initial_balance=db_p.initial_balance,
                        cash_balance=db_p.cash_balance,
                    )

                    symbol = node.symbol or "BTCUSDT"
                    client = BinanceClient(api_key=await self._get_user_key(ctx.user_id, "binance"),
                                          api_secret=await self._get_user_secret(ctx.user_id, "binance"))
                    try:
                        ticker_data = await client.get_ticker_24hr(symbol)
                        current_price = float(ticker_data.get("price", 0))
                    except Exception:
                        current_price = 0
                    finally:
                        await client.close()
                    size = port.risk_manager.compute_position_size(port.equity, current_price) or 0.001
                    side = OrderSide.BUY if action == "BUY" else OrderSide.SELL
                    broker = PaperBroker()
                    order = await broker.execute_market_order(
                        portfolio=port, symbol=symbol, side=side, quantity=size,
                        strategy_id=ctx.strategy_id,
                        model_prediction=json.dumps(last_decision),
                        confidence=confidence,
                    )

                    # Store trade in memory for RAG
                    if order.status == OrderStatus.FILLED:
                        try:
                            await trade_memory.store_trade(
                                trade_id=order.id,
                                user_id=ctx.user_id,
                                symbol=symbol,
                                side=side.value,
                                price=order.filled_price,
                                quantity=order.filled_quantity,
                                outcome_pnl=None,
                                confidence=confidence,
                                model_prediction=json.dumps(last_decision),
                            )
                        except Exception as e:
                            logger.debug(f"Trade memory storage failed (non-critical): {e}")

                    return NodeResult(
                        node_id=node.id,
                        status=NodeStatus.SUCCESS,
                        data={
                            "action": action,
                            "confidence": confidence,
                            "order_status": order.status.value,
                            "filled_price": order.filled_price,
                            "quantity": order.filled_quantity,
                            "reasoning": last_decision.get("reasoning", ""),
                        },
                    )

        return NodeResult(
            node_id=node.id,
            status=NodeStatus.SUCCESS,
            data={"action": "HOLD", "reason": f"Confidence {confidence:.2f} below threshold {threshold}"}
            if action != "HOLD" else {"action": "HOLD", "reason": "Model recommended no action"},
        )

    async def _handle_script(self, node: GraphNodeData, inp: dict, ctx: ExecutionContext) -> NodeResult:
        script = node.config.get("script_code", "")
        if not script:
            return NodeResult(node_id=node.id, status=NodeStatus.SKIPPED, error="No script code")

        try:
            safe_builtins = {"print": print, "len": len, "range": range, "int": int, "float": float, "str": str, "bool": bool, "list": list, "dict": dict, "sum": sum, "min": min, "max": max}
            safe_globals = {"__builtins__": safe_builtins, "input_data": inp}
            safe_locals = {}
            exec(script, safe_globals, safe_locals)
            result_data = safe_locals.get("result", {})
            return NodeResult(node_id=node.id, status=NodeStatus.SUCCESS, data={"result": result_data})
        except Exception as e:
            return NodeResult(node_id=node.id, status=NodeStatus.ERROR, error=f"Script error: {e}")

    async def execute_strategy(
        self,
        strategy_id: int,
        user_id: int,
        portfolio_id: Optional[int],
        db_nodes: list[dict],
        db_edges: list[dict],
    ) -> dict[str, NodeResult]:
        nodes: dict[str, GraphNodeData] = {}
        for n in db_nodes:
            config = {}
            if n.get("node_config_json"):
                try:
                    config = json.loads(n["node_config_json"])
                except json.JSONDecodeError:
                    pass
            nodes[str(n["id"])] = GraphNodeData(
                id=str(n["id"]),
                node_type=NodeType(n["node_type"]),
                label=n.get("label", n["node_type"]),
                config=config,
            )

        edges: list[GraphEdgeData] = []
        for e in db_edges:
            edges.append(GraphEdgeData(
                id=str(e["id"]),
                source_id=str(e["source_node_id"]),
                target_id=str(e["target_node_id"]),
                source_handle=e.get("source_handle", "output"),
                target_handle=e.get("target_handle", "input"),
            ))

        ctx = ExecutionContext(
            user_id=user_id,
            portfolio_id=portfolio_id,
            strategy_id=strategy_id,
        )

        initial = {
            "trigger_time": datetime.now(timezone.utc).isoformat(),
            "strategy_id": strategy_id,
        }

        return await self._executor.execute(nodes, edges, ctx, initial_input=initial)

    async def start_strategy(
        self,
        strategy_id: int,
        user_id: int,
        portfolio_id: Optional[int],
        db_nodes: list[dict],
        db_edges: list[dict],
        interval_seconds: int = 300,
    ) -> StrategyRunState:
        if strategy_id in self._strategies and self._strategies[strategy_id].is_running:
            return self._strategies[strategy_id]

        state = StrategyRunState(
            strategy_id=strategy_id,
            user_id=user_id,
            portfolio_id=portfolio_id,
            is_running=True,
        )
        self._strategies[strategy_id] = state

        async def run_loop():
            while self._strategies.get(strategy_id, state).is_running:
                try:
                    state.last_run = datetime.now(timezone.utc)
                    results = await self.execute_strategy(
                        strategy_id, user_id, portfolio_id, db_nodes, db_edges,
                    )
                    state.run_count += 1
                    state.total_cost += sum(r.cost_usd for r in results.values())
                    logger.info(f"Strategy {strategy_id} run #{state.run_count} complete: {len(results)} nodes, ${state.total_cost:.4f} total cost")
                except Exception as e:
                    logger.error(f"Strategy {strategy_id} execution error: {e}", exc_info=True)
                await asyncio.sleep(interval_seconds)

        state.task = asyncio.create_task(run_loop())
        return state

    async def stop_strategy(self, strategy_id: int):
        state = self._strategies.get(strategy_id)
        if state and state.is_running:
            state.is_running = False
            if state.task:
                state.task.cancel()
                try:
                    await state.task
                except asyncio.CancelledError:
                    pass
            return True
        return False

    def get_strategy_state(self, strategy_id: int) -> Optional[dict]:
        state = self._strategies.get(strategy_id)
        if state:
            return {
                "strategy_id": state.strategy_id,
                "is_running": state.is_running,
                "last_run": state.last_run.isoformat() if state.last_run else None,
                "run_count": state.run_count,
                "total_cost": state.total_cost,
            }
        return None

    def get_all_running(self) -> list[dict]:
        return [
            {
                "strategy_id": sid,
                "is_running": s.is_running,
                "last_run": s.last_run.isoformat() if s.last_run else None,
                "run_count": s.run_count,
                "total_cost": s.total_cost,
            }
            for sid, s in self._strategies.items()
        ]


# Global singleton
scheduler = StrategyScheduler()