from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
import json

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import User, Strategy, GraphNode, GraphEdge
from app.engine.strategy_scheduler import scheduler
from app.engine.node_types import NODE_TYPE_LABELS, NODE_TYPE_COLORS
from pydantic import BaseModel

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class StrategyCreate(BaseModel):
    name: str
    description: str | None = None
    graph_json: str | None = None


class StrategyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    graph_json: str | None = None
    is_active: bool | None = None


class NodeCreate(BaseModel):
    node_type: str
    label: str
    node_config_json: str | None = None
    position_x: float = 0
    position_y: float = 0


class EdgeCreate(BaseModel):
    source_node_id: int
    target_node_id: int
    source_handle: str = "output"
    target_handle: str = "input"


@router.get("")
async def list_strategies(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Strategy).where(Strategy.user_id == current_user.id).order_by(Strategy.updated_at.desc())
    )
    strategies = result.scalars().all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "graph_json": s.graph_json,
            "is_active": s.is_active,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s in strategies
    ]


@router.post("")
async def create_strategy(
    data: StrategyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    strategy = Strategy(user_id=current_user.id, name=data.name, description=data.description, graph_json=data.graph_json)
    db.add(strategy)
    await db.flush()
    return {"id": strategy.id, "name": strategy.name, "is_active": strategy.is_active}


@router.get("/{strategy_id}")
async def get_strategy(
    strategy_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == current_user.id)
    )
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return {
        "id": strategy.id,
        "name": strategy.name,
        "description": strategy.description,
        "graph_json": strategy.graph_json,
        "is_active": strategy.is_active,
        "created_at": strategy.created_at.isoformat() if strategy.created_at else None,
        "updated_at": strategy.updated_at.isoformat() if strategy.updated_at else None,
    }


@router.put("/{strategy_id}")
async def update_strategy(
    strategy_id: int,
    data: StrategyUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == current_user.id)
    )
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    if data.name is not None:
        strategy.name = data.name
    if data.description is not None:
        strategy.description = data.description
    if data.graph_json is not None:
        strategy.graph_json = data.graph_json
    if data.is_active is not None:
        strategy.is_active = data.is_active

    await db.flush()
    return {"id": strategy.id, "name": strategy.name, "is_active": strategy.is_active}


@router.delete("/{strategy_id}")
async def delete_strategy(
    strategy_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == current_user.id)
    )
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    await db.delete(strategy)
    return {"message": "Strategy deleted"}


@router.get("/{strategy_id}/nodes")
async def list_nodes(
    strategy_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GraphNode)
        .join(Strategy)
        .where(GraphNode.strategy_id == strategy_id, Strategy.user_id == current_user.id)
    )
    nodes = result.scalars().all()
    return [
        {
            "id": n.id,
            "node_type": n.node_type,
            "label": n.label,
            "node_config_json": n.node_config_json,
            "position_x": n.position_x,
            "position_y": n.position_y,
        }
        for n in nodes
    ]


@router.post("/{strategy_id}/nodes")
async def create_node(
    strategy_id: int,
    data: NodeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == current_user.id)
    )
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    node = GraphNode(
        strategy_id=strategy_id,
        node_type=data.node_type,
        label=data.label,
        node_config_json=data.node_config_json,
        position_x=data.position_x,
        position_y=data.position_y,
    )
    db.add(node)
    await db.flush()
    return {
        "id": node.id,
        "node_type": node.node_type,
        "label": node.label,
        "position_x": node.position_x,
        "position_y": node.position_y,
    }


@router.put("/{strategy_id}/nodes/{node_id}")
async def update_node(
    strategy_id: int,
    node_id: int,
    data: NodeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GraphNode)
        .join(Strategy)
        .where(GraphNode.id == node_id, GraphNode.strategy_id == strategy_id, Strategy.user_id == current_user.id)
    )
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    node.node_type = data.node_type
    node.label = data.label
    node.node_config_json = data.node_config_json
    node.position_x = data.position_x
    node.position_y = data.position_y
    await db.flush()
    return {"id": node.id, "label": node.label}


@router.delete("/{strategy_id}/nodes/{node_id}")
async def delete_node(
    strategy_id: int,
    node_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GraphNode)
        .join(Strategy)
        .where(GraphNode.id == node_id, GraphNode.strategy_id == strategy_id, Strategy.user_id == current_user.id)
    )
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    await db.delete(node)
    return {"message": "Node deleted"}


@router.get("/{strategy_id}/edges")
async def list_edges(
    strategy_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GraphEdge)
        .join(Strategy)
        .where(GraphEdge.strategy_id == strategy_id, Strategy.user_id == current_user.id)
    )
    edges = result.scalars().all()
    return [
        {
            "id": e.id,
            "source_node_id": e.source_node_id,
            "target_node_id": e.target_node_id,
            "source_handle": e.source_handle,
            "target_handle": e.target_handle,
        }
        for e in edges
    ]


@router.post("/{strategy_id}/edges")
async def create_edge(
    strategy_id: int,
    data: EdgeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == current_user.id)
    )
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    edge = GraphEdge(
        strategy_id=strategy_id,
        source_node_id=data.source_node_id,
        target_node_id=data.target_node_id,
        source_handle=data.source_handle,
        target_handle=data.target_handle,
    )
    db.add(edge)
    await db.flush()
    return {
        "id": edge.id,
        "source_node_id": edge.source_node_id,
        "target_node_id": edge.target_node_id,
    }


@router.delete("/{strategy_id}/edges/{edge_id}")
async def delete_edge(
    strategy_id: int,
    edge_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(GraphEdge)
        .join(Strategy)
        .where(GraphEdge.id == edge_id, GraphEdge.strategy_id == strategy_id, Strategy.user_id == current_user.id)
    )
    edge = result.scalar_one_or_none()
    if not edge:
        raise HTTPException(status_code=404, detail="Edge not found")
    await db.delete(edge)
    return {"message": "Edge deleted"}


class ExecuteRequest(BaseModel):
    portfolio_id: int | None = None


# Execution endpoints
@router.post("/{strategy_id}/execute")
async def execute_strategy(
    strategy_id: int,
    data: ExecuteRequest = ExecuteRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == current_user.id))
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    nodes_result = await db.execute(select(GraphNode).where(GraphNode.strategy_id == strategy_id))
    db_nodes = [
        {
            "id": n.id, "node_type": n.node_type, "label": n.label,
            "node_config_json": n.node_config_json,
            "position_x": n.position_x, "position_y": n.position_y,
        }
        for n in nodes_result.scalars().all()
    ]

    edges_result = await db.execute(select(GraphEdge).where(GraphEdge.strategy_id == strategy_id))
    db_edges = [
        {
            "id": e.id, "source_node_id": e.source_node_id,
            "target_node_id": e.target_node_id,
            "source_handle": e.source_handle, "target_handle": e.target_handle,
        }
        for e in edges_result.scalars().all()
    ]

    results = await scheduler.execute_strategy(
        strategy_id=strategy_id,
        user_id=current_user.id,
        portfolio_id=data.portfolio_id,
        db_nodes=db_nodes,
        db_edges=db_edges,
    )

    return {
        "strategy_id": strategy_id,
        "nodes_executed": len(results),
        "results": {
            node_id: {
                "status": r.status.value,
                "data": r.data,
                "error": r.error,
                "cost_usd": r.cost_usd,
                "tokens_used": r.tokens_used,
            }
            for node_id, r in results.items()
        },
        "total_cost": sum(r.cost_usd for r in results.values()),
        "total_tokens": sum(r.tokens_used for r in results.values()),
    }


@router.post("/{strategy_id}/execute/stream")
async def execute_strategy_stream(
    strategy_id: int,
    data: ExecuteRequest = ExecuteRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == current_user.id))
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    nodes_result = await db.execute(select(GraphNode).where(GraphNode.strategy_id == strategy_id))
    db_nodes = [
        {
            "id": n.id, "node_type": n.node_type, "label": n.label,
            "node_config_json": n.node_config_json,
            "position_x": n.position_x, "position_y": n.position_y,
        }
        for n in nodes_result.scalars().all()
    ]

    edges_result = await db.execute(select(GraphEdge).where(GraphEdge.strategy_id == strategy_id))
    db_edges = [
        {
            "id": e.id, "source_node_id": e.source_node_id,
            "target_node_id": e.target_node_id,
            "source_handle": e.source_handle, "target_handle": e.target_handle,
        }
        for e in edges_result.scalars().all()
    ]

    events_queue: asyncio.Queue = asyncio.Queue()

    async def on_event(event: dict):
        await events_queue.put(event)

    scheduler.set_executor_on_event(on_event)

    async def event_stream():
        import asyncio as aio
        exec_task = aio.create_task(scheduler.execute_strategy(
            strategy_id=strategy_id,
            user_id=current_user.id,
            portfolio_id=data.portfolio_id,
            db_nodes=db_nodes,
            db_edges=db_edges,
        ))

        while not exec_task.done() or not events_queue.empty():
            try:
                event = await aio.wait_for(events_queue.get(), timeout=60.0)
                yield f"data: {json.dumps(event)}\n\n"
            except aio.TimeoutError:
                break

        final = await exec_task
        yield f"data: {json.dumps({'type': 'complete', 'total_cost': sum(r.cost_usd for r in final.values())})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{strategy_id}/start")
async def start_strategy(
    strategy_id: int,
    data: ExecuteRequest = ExecuteRequest(),
    interval_seconds: int = Query(300, ge=30, le=86400),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == current_user.id))
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    # Activate in DB
    strategy.is_active = True

    nodes_result = await db.execute(select(GraphNode).where(GraphNode.strategy_id == strategy_id))
    db_nodes = [
        {
            "id": n.id, "node_type": n.node_type, "label": n.label,
            "node_config_json": n.node_config_json,
        }
        for n in nodes_result.scalars().all()
    ]

    edges_result = await db.execute(select(GraphEdge).where(GraphEdge.strategy_id == strategy_id))
    db_edges = [
        {
            "id": e.id, "source_node_id": e.source_node_id,
            "target_node_id": e.target_node_id,
            "source_handle": e.source_handle, "target_handle": e.target_handle,
        }
        for e in edges_result.scalars().all()
    ]

    state = await scheduler.start_strategy(
        strategy_id=strategy_id,
        user_id=current_user.id,
        portfolio_id=data.portfolio_id,
        db_nodes=db_nodes,
        db_edges=db_edges,
        interval_seconds=interval_seconds,
    )

    await db.flush()
    return {
        "strategy_id": strategy_id,
        "is_running": state.is_running,
        "interval_seconds": interval_seconds,
    }


@router.post("/{strategy_id}/stop")
async def stop_strategy(
    strategy_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == current_user.id))
    strategy = result.scalar_one_or_none()
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")

    stopped = await scheduler.stop_strategy(strategy_id)
    strategy.is_active = False
    await db.flush()

    return {"strategy_id": strategy_id, "stopped": stopped}


@router.get("/{strategy_id}/status")
async def get_strategy_status(
    strategy_id: int,
    current_user: User = Depends(get_current_user),
):
    return scheduler.get_strategy_state(strategy_id) or {"strategy_id": strategy_id, "is_running": False, "run_count": 0, "total_cost": 0.0}


@router.get("/running")
async def list_running_strategies(current_user: User = Depends(get_current_user)):
    return scheduler.get_all_running()


@router.get("/node-types")
async def get_node_types():
    return [
        {"type": t.value, "label": NODE_TYPE_LABELS[t], "color": NODE_TYPE_COLORS[t]}
        for t in NODE_TYPE_LABELS
    ]


@router.post("/{strategy_id}/clone")
async def clone_strategy(
    strategy_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == current_user.id))
    original = result.scalar_one_or_none()
    if not original:
        raise HTTPException(status_code=404, detail="Strategy not found")

    clone = Strategy(
        user_id=current_user.id,
        name=f"{original.name} (clone)",
        description=original.description,
        graph_json=original.graph_json,
        is_active=False,
    )
    db.add(clone)
    await db.flush()

    nodes_result = await db.execute(select(GraphNode).where(GraphNode.strategy_id == strategy_id))
    old_to_new = {}
    for n in nodes_result.scalars().all():
        new_node = GraphNode(
            strategy_id=clone.id,
            node_type=n.node_type,
            label=n.label,
            node_config_json=n.node_config_json,
            position_x=n.position_x,
            position_y=n.position_y,
        )
        db.add(new_node)
        await db.flush()
        old_to_new[n.id] = new_node.id

    edges_result = await db.execute(select(GraphEdge).where(GraphEdge.strategy_id == strategy_id))
    for e in edges_result.scalars().all():
        new_edge = GraphEdge(
            strategy_id=clone.id,
            source_node_id=old_to_new.get(e.source_node_id, e.source_node_id),
            target_node_id=old_to_new.get(e.target_node_id, e.target_node_id),
            source_handle=e.source_handle,
            target_handle=e.target_handle,
        )
        db.add(new_edge)

    await db.flush()
    return {"id": clone.id, "name": clone.name}