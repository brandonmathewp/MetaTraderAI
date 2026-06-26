from app.models.models import (
    User,
    ApiKey,
    Portfolio,
    Position,
    Trade,
    Strategy,
    GraphNode,
    GraphEdge,
    ModelCost,
    DailyBudget,
    CustomScript,
    PerformanceSnapshot,
    AutoImproverMutation,
)
from app.core.database import Base

target_metadata = Base.metadata