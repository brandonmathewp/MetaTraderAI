from enum import Enum
from typing import Optional

# Re-export these args to avoid pydantic import issues
from dataclasses import dataclass, field
import json


class NodeType(str, Enum):
    TRIGGER = "trigger"
    MARKET_DATA = "marketData"
    LLM_MODEL = "llmModel"
    COUNCIL = "council"
    FILTER = "filter"
    MERGE = "merge"
    ACTION = "action"
    SCRIPT = "script"


class NodeStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"


NODE_TYPE_LABELS = {
    NodeType.TRIGGER: "Trigger",
    NodeType.MARKET_DATA: "Market Data",
    NodeType.LLM_MODEL: "LLM Model",
    NodeType.COUNCIL: "Council",
    NodeType.FILTER: "Filter",
    NodeType.MERGE: "Merge",
    NodeType.ACTION: "Action",
    NodeType.SCRIPT: "Script",
}

NODE_TYPE_COLORS = {
    NodeType.TRIGGER: "#3b82f6",
    NodeType.MARKET_DATA: "#22c55e",
    NodeType.LLM_MODEL: "#a855f7",
    NodeType.COUNCIL: "#f59e0b",
    NodeType.FILTER: "#06b6d4",
    NodeType.MERGE: "#ec4899",
    NodeType.ACTION: "#ef4444",
    NodeType.SCRIPT: "#64748b",
}


@dataclass
class GraphNodeData:
    id: str
    node_type: NodeType
    label: str
    config: dict = field(default_factory=dict)

    @property
    def model_name(self) -> Optional[str]:
        return self.config.get("model_name")

    @property
    def system_prompt(self) -> Optional[str]:
        return self.config.get("system_prompt")

    @property
    def temperature(self) -> float:
        return float(self.config.get("temperature", 0.7))

    @property
    def max_tokens(self) -> int:
        return int(self.config.get("max_tokens", 1024))

    @property
    def symbol(self) -> Optional[str]:
        return self.config.get("symbol")

    @property
    def interval(self) -> str:
        return self.config.get("interval", "1m")

    @property
    def indicators(self) -> list[str]:
        return self.config.get("indicators", [])

    @property
    def condition(self) -> Optional[str]:
        return self.config.get("condition")

    @property
    def confidence_threshold(self) -> float:
        return float(self.config.get("confidence_threshold", 0.7))

    @property
    def voters_count(self) -> int:
        return int(self.config.get("voters_count", 3))

    @property
    def cron_expression(self) -> Optional[str]:
        return self.config.get("cron_expression")

    @property
    def merge_strategy(self) -> str:
        return self.config.get("merge_strategy", "concatenate")


@dataclass
class GraphEdgeData:
    id: str
    source_id: str
    target_id: str
    source_handle: str = "output"
    target_handle: str = "input"


@dataclass
class NodeResult:
    node_id: str
    status: NodeStatus
    data: dict = field(default_factory=dict)
    error: Optional[str] = None
    cost_usd: float = 0.0
    tokens_used: int = 0

    def to_execution_event(self) -> dict:
        return {
            "node_id": self.node_id,
            "status": self.status.value,
            "data_preview": str(self.data)[:200] if self.data else None,
            "error": self.error,
            "cost_usd": self.cost_usd,
        }


@dataclass
class ExecutionContext:
    user_id: int
    portfolio_id: Optional[int] = None
    strategy_id: Optional[int] = None
    run_simulation: bool = True