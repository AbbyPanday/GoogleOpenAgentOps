"""
Core data structures for GoogleOpenAgentOps complying with OpenInference & OpenTelemetry.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional
import time
import uuid


class SpanKind(str, Enum):
    AGENT = "AGENT"
    TOOL = "TOOL"
    CHAIN = "CHAIN"
    LLM = "LLM"
    RETRIEVER = "RETRIEVER"
    EMBEDDING = "EMBEDDING"


class AgentState(str, Enum):
    IDLE = "IDLE"
    INITIALIZING = "INITIALIZING"
    THINKING = "THINKING"
    TOOL_CALLING = "TOOL_CALLING"
    EXECUTING = "EXECUTING"
    WAITING_FEEDBACK = "WAITING_FEEDBACK"
    HANDOFF = "HANDOFF"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class TokenMetrics:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_cost_usd: float = 0.0
    completion_cost_usd: float = 0.0
    total_cost_usd: float = 0.0

    def __getitem__(self, item: str):
        return getattr(self, item)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ToolCallRecord:
    tool_name: str
    tool_call_id: str = field(default_factory=lambda: f"tool-{uuid.uuid4().hex[:8]}")
    params: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    duration_ms: int = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StateTransition:
    transition_id: str
    timestamp: float
    iso_timestamp: str
    agent_name: str
    from_state: str
    to_state: str
    reason: str
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Handoff:
    handoff_id: str
    timestamp: float
    from_agent: str
    to_agent: str
    summary: str
    state_payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Span:
    span_id: str
    trace_id: str
    session_id: str
    name: str
    span_kind: str = SpanKind.AGENT.value
    parent_span_id: Optional[str] = None
    agent_name: Optional[str] = None
    agent_role: Optional[str] = None
    model: str = "gemini-3.8-flash"
    status: str = "RUNNING"  # RUNNING | OK | ERROR
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: int = 0
    input: Any = None
    system_prompt: Optional[str] = None
    output: Any = None
    thought: Optional[str] = None
    error: Optional[str] = None
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    metrics: TokenMetrics = field(default_factory=TokenMetrics)
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["tool_calls"] = [t.to_dict() if hasattr(t, "to_dict") else t for t in self.tool_calls]
        d["metrics"] = self.metrics.to_dict() if hasattr(self.metrics, "to_dict") else self.metrics
        return d


@dataclass
class Trace:
    trace_id: str
    session_id: str
    name: str
    status: str = "RUNNING"
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration_ms: int = 0
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SessionMetrics:
    total_spans: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    avg_latency_ms: int = 0
    agent_runs_count: int = 0
    tool_calls_count: int = 0
    thought_loops_count: int = 0
    error_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Session:
    session_id: str
    session_name: str
    status: str = "ACTIVE"
    current_agent: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    traces: List[Trace] = field(default_factory=list)
    spans: List[Span] = field(default_factory=list)
    state_transitions: List[StateTransition] = field(default_factory=list)
    handoffs: List[Handoff] = field(default_factory=list)
    metrics: SessionMetrics = field(default_factory=SessionMetrics)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "session_name": self.session_name,
            "status": self.status,
            "current_agent": self.current_agent,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "traces": [t.to_dict() for t in self.traces],
            "spans": [s.to_dict() for s in self.spans],
            "state_transitions": [st.to_dict() for st in self.state_transitions],
            "handoffs": [h.to_dict() for h in self.handoffs],
            "metrics": self.metrics.to_dict(),
        }
