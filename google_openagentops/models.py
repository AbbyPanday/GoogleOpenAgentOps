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
    GUARDRAIL = "GUARDRAIL"
    WORKFLOW = "WORKFLOW"
    OPERATION = "OPERATION"
    DEPLOYMENT = "DEPLOYMENT"


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
class ReplayEvent:
    event_id: str
    session_id: str
    timestamp: float
    iso_timestamp: str
    event_type: str  # "AGENT_START" | "THOUGHT" | "TOOL_CALL" | "TOOL_RESULT" | "HANDOFF" | "STATE_TRANSITION" | "GUARDRAIL" | "ERROR" | "AGENT_FINISH"
    agent_name: Optional[str] = None
    span_id: Optional[str] = None
    title: str = ""
    description: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CiCdEvent:
    event_id: str
    timestamp: float
    iso_timestamp: str
    pipeline_name: str
    run_id: str
    commit_sha: str
    branch: str
    status: str  # "SUCCESS" | "FAILURE" | "RUNNING"
    duration_ms: int = 0
    environment: str = "production"
    provider: str = "github-actions"  # "github-actions" | "cloud-build" | "gitlab-ci"
    details: Dict[str, Any] = field(default_factory=dict)

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
    replay_events: List[ReplayEvent] = field(default_factory=list)
    metrics: SessionMetrics = field(default_factory=SessionMetrics)

    def build_replay_events(self) -> List[Dict[str, Any]]:
        """Construct chronological replay sequence combining spans, thoughts, tool calls, and transitions."""
        events: List[Dict[str, Any]] = []

        # 1. State transitions
        for st in self.state_transitions:
            events.append({
                "event_id": f"evt-st-{st.transition_id}",
                "timestamp": st.timestamp,
                "iso_timestamp": st.iso_timestamp,
                "event_type": "STATE_TRANSITION",
                "agent_name": st.agent_name,
                "title": f"State: {st.from_state} → {st.to_state}",
                "description": st.reason,
                "payload": st.to_dict()
            })

        # 2. Handoffs
        for h in self.handoffs:
            events.append({
                "event_id": f"evt-ho-{h.handoff_id}",
                "timestamp": h.timestamp,
                "iso_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(h.timestamp)),
                "event_type": "HANDOFF",
                "agent_name": h.to_agent,
                "title": f"Handoff: {h.from_agent} → {h.to_agent}",
                "description": h.summary,
                "payload": h.to_dict()
            })

        # 3. Spans, tool calls, thoughts
        for s in self.spans:
            # Start
            events.append({
                "event_id": f"evt-start-{s.span_id}",
                "timestamp": s.start_time,
                "iso_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(s.start_time)),
                "event_type": f"{s.span_kind}_START",
                "agent_name": s.agent_name or s.name,
                "span_id": s.span_id,
                "title": f"Started {s.name} ({s.span_kind})",
                "description": f"Model: {s.model}",
                "payload": {"input": s.input, "model": s.model, "attributes": s.attributes}
            })

            # Thought
            if s.thought:
                events.append({
                    "event_id": f"evt-th-{s.span_id}",
                    "timestamp": s.start_time + 0.05,
                    "iso_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(s.start_time + 0.05)),
                    "event_type": "THOUGHT",
                    "agent_name": s.agent_name or s.name,
                    "span_id": s.span_id,
                    "title": f"Reasoning Loop ({s.agent_name or s.name})",
                    "description": s.thought[:140] + ("..." if len(s.thought) > 140 else ""),
                    "payload": {"thought": s.thought}
                })

            # Tool calls
            for tc in s.tool_calls:
                tc_dict = tc.to_dict() if hasattr(tc, "to_dict") else tc
                events.append({
                    "event_id": f"evt-tc-{tc_dict.get('tool_call_id', uuid.uuid4().hex[:6])}",
                    "timestamp": tc_dict.get("timestamp", s.start_time + 0.1),
                    "iso_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(tc_dict.get("timestamp", s.start_time + 0.1))),
                    "event_type": "TOOL_CALL",
                    "agent_name": s.agent_name or s.name,
                    "span_id": s.span_id,
                    "title": f"Tool: {tc_dict.get('tool_name')}",
                    "description": f"Duration: {tc_dict.get('duration_ms', 0)}ms",
                    "payload": tc_dict
                })

            # Finish
            if s.end_time:
                events.append({
                    "event_id": f"evt-end-{s.span_id}",
                    "timestamp": s.end_time,
                    "iso_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(s.end_time)),
                    "event_type": f"{s.span_kind}_FINISH",
                    "agent_name": s.agent_name or s.name,
                    "span_id": s.span_id,
                    "title": f"Completed {s.name} [{s.status}]",
                    "description": f"Duration: {s.duration_ms}ms • Cost: ${s.metrics.total_cost_usd:.6f}",
                    "payload": {"output": s.output, "error": s.error, "metrics": s.metrics.to_dict()}
                })

        # Explicit custom replay events
        for re in self.replay_events:
            events.append(re.to_dict() if hasattr(re, "to_dict") else re)

        # Sort chronologically
        events.sort(key=lambda x: x.get("timestamp", 0.0))
        return events

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
            "replay_events": [re.to_dict() if hasattr(re, "to_dict") else re for re in self.replay_events],
            "metrics": self.metrics.to_dict(),
        }
