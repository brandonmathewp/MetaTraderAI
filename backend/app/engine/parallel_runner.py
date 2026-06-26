import asyncio
import logging
from typing import Optional

from app.engine.node_types import (
    NodeType, NodeStatus, GraphNodeData, GraphEdgeData,
    NodeResult, ExecutionContext,
)

logger = logging.getLogger(__name__)


class ParallelRunner:
    def __init__(self, max_parallel: int = 10, timeout_per_node: float = 60.0):
        self.max_parallel = max_parallel
        self.timeout_per_node = timeout_per_node

async def run_parallel(
    self,
    tasks: dict[str, asyncio.Task],
    node_map: dict[str, GraphNodeData],
) -> dict[str, NodeResult]:
    results: dict[str, NodeResult] = {}
    semaphore = asyncio.Semaphore(self.max_parallel)

    async def bounded_task(node_id: str, node: GraphNodeData, coro):
        async with semaphore:
            try:
                return node_id, await asyncio.wait_for(coro, timeout=self.timeout_per_node)
            except asyncio.TimeoutError:
                return node_id, NodeResult(
                    node_id=node_id,
                    status=NodeStatus.ERROR,
                    error=f"Node timed out after {self.timeout_per_node}s",
                )
            except Exception as e:
                return node_id, NodeResult(
                    node_id=node_id,
                    status=NodeStatus.ERROR,
                    error=str(e),
                )

    bound_tasks = []
    for node_id, coro_task in tasks.items():
        node = node_map.get(node_id)
        if node:
            bound_tasks.append(bounded_task(node_id, node, coro_task))

    if bound_tasks:
        gathered = await asyncio.gather(*bound_tasks, return_exceptions=True)
        for item in gathered:
            if isinstance(item, Exception):
                logger.error(f"Parallel task exception: {item}")
                continue
            if item is not None:
                node_id, result = item
                results[node_id] = result

    return results