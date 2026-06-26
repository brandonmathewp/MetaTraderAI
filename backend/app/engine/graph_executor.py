import asyncio
import logging
from collections import defaultdict, deque
from typing import Optional, Callable, Awaitable

from app.engine.node_types import (
    NodeType, NodeStatus, GraphNodeData, GraphEdgeData,
    NodeResult, ExecutionContext,
)

logger = logging.getLogger(__name__)

NodeHandler = Callable[[GraphNodeData, dict, ExecutionContext], Awaitable[NodeResult]]


class GraphExecutor:
    def __init__(self):
        self._handlers: dict[NodeType, NodeHandler] = {}
        self._execution_log: list[NodeResult] = []
        self._event_callbacks: list[Callable[[dict], Awaitable]] = []

    def register_handler(self, node_type: NodeType, handler: NodeHandler):
        self._handlers[node_type] = handler

    def on_event(self, callback: Callable[[dict], Awaitable]):
        self._event_callbacks.append(callback)

    async def _emit_event(self, event: dict):
        for cb in self._event_callbacks:
            try:
                await cb(event)
            except Exception as e:
                logger.error(f"Event callback error: {e}")

    def _topological_sort(
        self, nodes: dict[str, GraphNodeData], edges: list[GraphEdgeData]
    ) -> list[list[str]]:
        in_degree: dict[str, int] = defaultdict(int)
        adjacency: dict[str, list[str]] = defaultdict(list)

        for node_id in nodes:
            in_degree[node_id] = 0

        for edge in edges:
            src = edge.source_id
            tgt = edge.target_id
            if src in nodes and tgt in nodes and src != tgt:
                adjacency[src].append(tgt)
                in_degree[tgt] += 1

        # Detect cycles via Kahn's algorithm
        queue = deque([nid for nid in nodes if in_degree[nid] == 0])
        visited = set()
        levels: list[list[str]] = []

        while queue:
            level = []
            level_size = len(queue)
            for _ in range(level_size):
                node_id = queue.popleft()
                visited.add(node_id)
                level.append(node_id)
                for neighbor in adjacency[node_id]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)
            if level:
                levels.append(level)

        # Add any unreachable nodes (cycles or disconnected)
        for node_id in nodes:
            if node_id not in visited:
                levels.append([node_id])

        return levels

    async def execute(
        self,
        nodes: dict[str, GraphNodeData],
        edges: list[GraphEdgeData],
        ctx: ExecutionContext,
        initial_input: Optional[dict] = None,
    ) -> dict[str, NodeResult]:
        self._execution_log = []

        # Build adjacency for input aggregation
        incoming: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            incoming[edge.target_id].append(edge.source_id)

        levels = self._topological_sort(nodes, edges)
        results: dict[str, NodeResult] = {}
        node_outputs: dict[str, dict] = {}

        if initial_input:
            # Pass initial input to trigger nodes
            trigger_nodes = [n for n in nodes.values() if n.node_type == NodeType.TRIGGER]
            for t in trigger_nodes:
                node_outputs[t.id] = initial_input

        logger.info(f"Beginning graph execution: {len(levels)} levels, {len(nodes)} nodes")

        for level_num, level in enumerate(levels):
            tasks = []
            for node_id in level:
                node = nodes.get(node_id)
                if not node:
                    continue

                # Collect inputs from all incoming nodes
                aggregated_input: dict = {}
                for src_id in incoming.get(node_id, []):
                    if src_id in node_outputs:
                        aggregated_input[f"from_{src_id}"] = node_outputs[src_id]

                # Add common input data
                aggregated_input["_node"] = {
                    "id": node.id,
                    "type": node.node_type.value,
                    "label": node.label,
                    "config": node.config,
                }
                aggregated_input["_context"] = {
                    "user_id": ctx.user_id,
                    "portfolio_id": ctx.portfolio_id,
                    "strategy_id": ctx.strategy_id,
                }

                handler = self._handlers.get(node.node_type)
                if not handler:
                    result = NodeResult(
                        node_id=node_id,
                        status=NodeStatus.SKIPPED,
                        error=f"No handler for {node.node_type.value}",
                    )
                    results[node_id] = result
                    continue

                tasks.append((node_id, node, handler, aggregated_input))

            # Execute in parallel
            async def run_node(node_id: str, node: GraphNodeData, handler: NodeHandler, inp: dict):
                try:
                    await self._emit_event({
                        "node_id": node_id,
                        "status": "running",
                        "node_label": node.label,
                        "node_type": node.node_type.value,
                    })
                    result = await handler(node, inp, ctx)
                    await self._emit_event(result.to_execution_event())
                    return node_id, result
                except Exception as e:
                    logger.error(f"Node {node_id} ({node.label}) error: {e}", exc_info=True)
                    error_result = NodeResult(
                        node_id=node_id,
                        status=NodeStatus.ERROR,
                        error=str(e),
                    )
                    await self._emit_event(error_result.to_execution_event())
                    return node_id, error_result

            level_results = await asyncio.gather(
                *[run_node(nid, n, h, inp) for nid, n, h, inp in tasks],
                return_exceptions=True,
            )

            for item in level_results:
                if isinstance(item, Exception):
                    logger.error(f"Level execution error: {item}")
                    continue
                node_id, result = item
                results[node_id] = result
                if result.status == NodeStatus.SUCCESS:
                    node_outputs[node_id] = result.data
                self._execution_log.append(result)

        logger.info(f"Graph execution complete: {len(results)} results")
        return results

    def get_execution_log(self) -> list[NodeResult]:
        return self._execution_log.copy()