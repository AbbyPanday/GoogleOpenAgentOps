import atexit
"""
Thread-safe Telemetry Tracker Engine with Re-entrant RLock.
Stitches multi-turn sessions, agent state transitions, recursive thought loops,
multi-solution Google ADK registration, and SSE broadcasting.
"""

from datetime import datetime, timezone
import json
import logging
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import urllib.request
import uuid

from google_openagentops.models import (
    AgentState,
    Handoff,
    Session,
    Span,
    SpanKind,
    StateTransition,
    TokenMetrics,
    ToolCallRecord,
    Trace
)
from google_openagentops.pricing import calculate_token_cost, estimate_token_count
from google_openagentops.context import active_context

logger = logging.getLogger("google_openagentops.tracker")


class GoogleOpenAgentOpsTracker:
    _instance: Optional["GoogleOpenAgentOpsTracker"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(GoogleOpenAgentOpsTracker, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, max_sessions: int = 100):
        if self._initialized:
            return
        self.max_sessions = max_sessions
        self.sessions: Dict[str, Session] = {}
        self.active_traces: Dict[str, Trace] = {}
        self.solutions: Dict[str, Dict[str, Any]] = {}
        self.active_session_id: Optional[str] = None
        self.remote_server_url: Optional[str] = os.getenv("GOOGLE_OPENAGENTOPS_SERVER_URL")
        self.subscribers: List[Callable[[Dict[str, Any]], None]] = []
        self._telemetry_lock = threading.RLock()
        self._pending_threads: List[threading.Thread] = []
        self._initialized = True

    def set_remote_server(self, url: str):
        """Configure remote dashboard URL for telemetry forwarding."""
        if url:
            self.remote_server_url = url.rstrip("/")

    def register_solution(self, payload: Dict[str, Any]):
        """Register an independent ADK Agent Solution to the central tracker."""
        sol_id = payload.get("solution_id") or str(uuid.uuid4())[:8]
        with self._telemetry_lock:
            payload["last_seen"] = int(time.time() * 1000)
            self.solutions[sol_id] = payload
        self._emit_telemetry("SOLUTION_REGISTERED", {"solution": payload})

    def get_solutions(self) -> List[Dict[str, Any]]:
        """Return all registered ADK agent solutions."""
        with self._telemetry_lock:
            return list(self.solutions.values())

    def start_session(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create and activate a new session, returning session ID."""
        meta = metadata or {}
        if user_id:
            meta["user_id"] = user_id
        if tags:
            meta["tags"] = tags
        sess = self.get_or_create_session(session_id, meta)
        with self._telemetry_lock:
            self.active_session_id = sess.session_id
        return sess.session_id

    def get_active_session_id(self) -> str:
        """Retrieve currently active session ID or initialize one."""
        with self._telemetry_lock:
            if not self.active_session_id or self.active_session_id not in self.sessions:
                sess = self.get_or_create_session()
                self.active_session_id = sess.session_id
            return self.active_session_id

    def end_session(self, session_id: Optional[str] = None, status: str = "SUCCESS"):
        """Finalize and close an observability session."""
        target_id = session_id or self.active_session_id
        if not target_id:
            return
        sess = self.get_session(target_id)
        if sess:
            sess.metadata["session_status"] = status
            sess.metadata["ended_at"] = time.time()
            self._emit_telemetry("SESSION_ENDED", {
                "sessionId": target_id,
                "status": status,
                "metrics": sess.metrics.to_dict()
            })

    def get_or_create_session(self, session_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Session:
        with self._telemetry_lock:
            if not session_id:
                session_id = f"googleagentops-sess-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"

            if session_id not in self.sessions:
                meta = metadata or {}
                meta["gcp_runtime"] = active_context.runtime_type
                meta["gcp_project"] = active_context.project_id
                session = Session(
                    session_id=session_id,
                    session_name=meta.get("session_name", f"Agent Session {session_id[-6:]}"),
                    metadata=meta
                )
                self.sessions[session_id] = session
                self.active_session_id = session_id
                self._prune_sessions()
                self._emit_telemetry("SESSION_CREATED", {"sessionId": session_id, "gcpContext": active_context.to_dict()})

            sess = self.sessions[session_id]
            if metadata:
                sess.metadata.update(metadata)
            return sess

    def get_session(self, session_id: str) -> Optional[Session]:
        return self.sessions.get(session_id)

    def get_all_sessions(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in reversed(list(self.sessions.values()))]

    def _prune_sessions(self):
        if len(self.sessions) > self.max_sessions:
            oldest = list(self.sessions.keys())[:len(self.sessions) - self.max_sessions]
            for sid in oldest:
                del self.sessions[sid]

    def start_trace(self, session_id: Optional[str] = None, name: str = "agent-trace", attributes: Optional[Dict[str, Any]] = None, tags: Optional[List[str]] = None) -> Trace:
        effective_sid = session_id or self.get_active_session_id()
        session = self.get_or_create_session(effective_sid, attributes)
        trace_id = f"trace-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
        attrs = attributes or {}
        if tags:
            attrs["tags"] = tags
        trace = Trace(
            trace_id=trace_id,
            session_id=session.session_id,
            name=name,
            attributes=attrs
        )
        session.traces.append(trace)
        self.active_traces[trace_id] = trace
        self._emit_telemetry("TRACE_STARTED", {"sessionId": session.session_id, "traceId": trace_id, "name": name, "attributes": attrs})
        return trace

    def end_trace(self, trace_id: Any, status: str = "OK", error: Optional[str] = None) -> Optional[Trace]:
        tid = getattr(trace_id, "trace_id", trace_id)
        trace = self.active_traces.get(tid)
        if not trace:
            return None
        trace.end_time = time.time()
        trace.duration_ms = int((trace.end_time - trace.start_time) * 1000)
        trace.status = status
        if error:
            trace.attributes["error"] = str(error)
        if tid in self.active_traces: del self.active_traces[tid]
        self._emit_telemetry("TRACE_ENDED", {"sessionId": trace.session_id, "traceId": trace_id, "durationMs": trace.duration_ms, "status": status})
        return trace

    def start_span(
        self,
        session_id: Optional[str] = None,
        name: str = "agent-span",
        span_kind: str = SpanKind.AGENT.value,
        agent_name: Optional[str] = None,
        agent_role: Optional[str] = None,
        model: str = "gemini-3.8-flash",
        parent_span_id: Optional[str] = None,
        input_data: Any = None,
        system_prompt: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ) -> Span:
        effective_sid = session_id or self.get_active_session_id()
        session = self.get_or_create_session(effective_sid)
        active_trace_id = session.traces[-1].trace_id if session.traces else f"trace-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"
        span_id = f"span-{int(time.time()*1000)}-{uuid.uuid4().hex[:6]}"

        span = Span(
            span_id=span_id,
            trace_id=active_trace_id,
            session_id=session.session_id,
            name=name,
            span_kind=span_kind,
            parent_span_id=parent_span_id,
            agent_name=agent_name or name,
            agent_role=agent_role,
            model=model,
            input=input_data,
            system_prompt=system_prompt,
            attributes=attributes or {}
        )
        session.spans.append(span)

        if span_kind == SpanKind.AGENT.value:
            self.record_state_transition(
                session.session_id,
                agent_name or name,
                AgentState.IDLE.value,
                AgentState.INITIALIZING.value,
                reason=f"Starting {name}"
            )

        self._emit_telemetry("SPAN_STARTED", {
            "sessionId": session.session_id,
            "spanId": span.span_id,
            "traceId": span.trace_id,
            "name": name,
            "agentName": span.agent_name,
            "model": model,
            "spanKind": span_kind
        })
        return span

    def end_span(
        self,
        span_id: str,
        output_data: Any = None,
        thought: Optional[str] = None,
        error: Optional[Any] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        output_payload: Optional[Dict[str, Any]] = None
    ) -> Optional[Span]:
        effective_output = output_data if output_data is not None else output_payload
        with self._telemetry_lock:
            for session in self.sessions.values():
                for span in session.spans:
                    if span.span_id == span_id:
                        span.end_time = time.time()
                        span.duration_ms = max(1, int((span.end_time - span.start_time) * 1000))
                        span.output = effective_output
                        if thought:
                            span.thought = thought
                        if error:
                            span.status = "ERROR"
                            span.error = str(error)
                        else:
                            span.status = "OK"

                        p_tok = prompt_tokens if prompt_tokens is not None else estimate_token_count(span.input or span.system_prompt)
                        c_tok = completion_tokens if completion_tokens is not None else estimate_token_count(effective_output or thought)
                        metrics = calculate_token_cost(span.model, p_tok, c_tok)
                        span.metrics = metrics

                        # Aggregate into session metrics
                        session.metrics.total_spans += 1
                        session.metrics.total_prompt_tokens += metrics.prompt_tokens
                        session.metrics.total_completion_tokens += metrics.completion_tokens
                        session.metrics.total_tokens += metrics.total_tokens
                        session.metrics.total_cost_usd += metrics.total_cost_usd
                        if error:
                            session.metrics.error_count += 1
                        if span.span_kind == SpanKind.AGENT.value:
                            session.metrics.agent_runs_count += 1

                        total_dur = sum(s.duration_ms for s in session.spans)
                        session.metrics.avg_latency_ms = int(total_dur / max(1, len(session.spans)))

                        if span.span_kind == SpanKind.AGENT.value:
                            final_state = AgentState.FAILED.value if error else AgentState.COMPLETED.value
                            self.record_state_transition(
                                session.session_id,
                                span.agent_name or span.name,
                                AgentState.INITIALIZING.value,
                                final_state,
                                reason=f"Finished in {span.duration_ms}ms"
                            )

                        self._emit_telemetry("SPAN_ENDED", {
                            "sessionId": session.session_id,
                            "spanId": span.span_id,
                            "traceId": span.trace_id,
                            "name": span.name,
                            "agentName": span.agent_name,
                            "model": span.model,
                            "durationMs": span.duration_ms,
                            "status": span.status,
                            "costUsd": span.metrics.total_cost_usd,
                            "totalTokens": span.metrics.total_tokens,
                            "metrics": span.metrics.to_dict()
                        })
                        return span
        return None

    def update_agent_state(
        self,
        agent_name: str,
        state: Any,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None
    ):
        """Update and record agent state transition."""
        effective_sid = session_id or self.get_active_session_id()
        state_val = getattr(state, "value", str(state))
        self.record_state_transition(
            session_id=effective_sid,
            agent_name=agent_name,
            from_state=AgentState.IDLE.value,
            to_state=state_val,
            reason=reason or f"State changed to {state_val}",
            extra=metadata
        )

    def record_thought(self, session_id: str, span_id: str, thought_text: str):
        session = self.get_session(session_id)
        if not session:
            return
        for span in session.spans:
            if span.span_id == span_id:
                span.thought = (span.thought + "\n" + thought_text) if span.thought else thought_text
                session.metrics.thought_loops_count += 1
                self.record_state_transition(
                    session_id,
                    span.agent_name or span.name,
                    AgentState.INITIALIZING.value,
                    AgentState.THINKING.value,
                    reason="Chain of thought reasoning",
                    extra={"thought_snippet": thought_text[:200]}
                )
                self._emit_telemetry("THOUGHT_RECORDED", {"sessionId": session_id, "spanId": span_id, "thought": thought_text})
                break

    def record_tool_call(
        self,
        *args,
        **kwargs
    ) -> ToolCallRecord:
        """
        Record tool invocation supporting both positional and keyword invocation signatures:
        (session_id, span_id, tool_name, params, result, duration_ms) OR
        (tool_name=..., duration_ms=..., is_error=..., error_message=..., ...)
        """
        if len(args) >= 3:
            session_id = args[0]
            span_id = args[1]
            tool_name = args[2]
            params = args[3] if len(args) > 3 else kwargs.get("params", {})
            result = args[4] if len(args) > 4 else kwargs.get("result", {})
            duration_ms = args[5] if len(args) > 5 else kwargs.get("duration_ms", 0)
        else:
            session_id = kwargs.get("session_id") or self.get_active_session_id()
            span_id = kwargs.get("span_id", "")
            tool_name = kwargs.get("tool_name", "unnamed_tool")
            params = kwargs.get("params", {})
            is_error = kwargs.get("is_error", False)
            err_msg = kwargs.get("error_message")
            result = {"error": err_msg} if is_error else kwargs.get("result", "OK")
            duration_ms = int(kwargs.get("duration_ms", 0))

        record = ToolCallRecord(tool_name=tool_name, params=params, result=result, duration_ms=duration_ms)
        session = self.get_session(session_id)
        if session:
            session.metrics.tool_calls_count += 1
            for span in session.spans:
                if span.span_id == span_id or not span_id:
                    span.tool_calls.append(record)
                    self.record_state_transition(
                        session_id,
                        span.agent_name or span.name,
                        AgentState.THINKING.value,
                        AgentState.TOOL_CALLING.value,
                        reason=f"Invoked tool {tool_name}"
                    )
                    break
        self._emit_telemetry("TOOL_CALLED", {"sessionId": session_id, "spanId": span_id, "tool": record.to_dict()})
        return record

    def record_llm_call(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> TokenMetrics:
        """Register token counts and compute cost for an LLM call."""
        sid = session_id or self.get_active_session_id()
        metrics = calculate_token_cost(model, prompt_tokens, completion_tokens)
        session = self.get_session(sid)
        if session:
            session.metrics.total_prompt_tokens += prompt_tokens
            session.metrics.total_completion_tokens += completion_tokens
            session.metrics.total_tokens += metrics.total_tokens
            session.metrics.total_cost_usd += metrics.total_cost_usd

        self._emit_telemetry("LLM_CALL", {
            "sessionId": sid,
            "traceId": trace_id,
            "model": model,
            "metrics": metrics.to_dict()
        })
        return metrics

    def record_state_transition(
        self,
        session_id: str,
        agent_name: str,
        from_state: str,
        to_state: str,
        reason: str,
        extra: Optional[Dict[str, Any]] = None
    ) -> StateTransition:
        now = time.time()
        iso = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        st = StateTransition(
            transition_id=f"trans-{int(now*1000)}-{uuid.uuid4().hex[:6]}",
            timestamp=now,
            iso_timestamp=iso,
            agent_name=agent_name,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            extra=extra or {}
        )
        session = self.get_session(session_id)
        if session:
            session.state_transitions.append(st)
        self._emit_telemetry("STATE_TRANSITION", {"sessionId": session_id, "transition": st.to_dict()})
        return st

    def record_handoff(
        self,
        *args,
        **kwargs
    ) -> Handoff:
        """Record agent-to-agent delegation supporting both positional and keyword invocations."""
        now = time.time()
        if len(args) >= 3:
            session_id = args[0]
            from_agent = args[1]
            to_agent = args[2]
            summary = args[3] if len(args) > 3 else kwargs.get("summary", "")
            state_payload = args[4] if len(args) > 4 else kwargs.get("state_payload", {})
        else:
            session_id = kwargs.get("session_id") or self.get_active_session_id()
            from_agent = kwargs.get("from_agent") or kwargs.get("source_agent", "Agent-A")
            to_agent = kwargs.get("to_agent") or kwargs.get("target_agent", "Agent-B")
            summary = kwargs.get("summary", "Agent Handoff")
            state_payload = kwargs.get("state_payload") or kwargs.get("context", {})

        handoff = Handoff(
            handoff_id=f"handoff-{int(now*1000)}-{uuid.uuid4().hex[:6]}",
            timestamp=now,
            from_agent=from_agent,
            to_agent=to_agent,
            summary=summary,
            state_payload=state_payload or {}
        )
        session = self.get_or_create_session(session_id)
        session.handoffs.append(handoff)
        session.current_agent = to_agent
        self.record_state_transition(
            session_id,
            from_agent,
            AgentState.COMPLETED.value,
            AgentState.HANDOFF.value,
            reason=f"Handoff to {to_agent}: {summary}"
        )
        self._emit_telemetry("HANDOFF", {"sessionId": session_id, "handoff": handoff.to_dict()})
        return handoff

    def add_subscriber(self, callback: Callable[[Dict[str, Any]], None]):
        with self._telemetry_lock:
            if callback not in self.subscribers:
                self.subscribers.append(callback)

    def remove_subscriber(self, callback: Callable[[Dict[str, Any]], None]):
        with self._telemetry_lock:
            if callback in self.subscribers:
                self.subscribers.remove(callback)

    def _emit_telemetry(self, event_type: str, data: Dict[str, Any]):
        payload = {
            "type": event_type,
            "timestamp": int(time.time() * 1000),
            "data": data
        }
        with self._telemetry_lock:
            for sub in list(self.subscribers):
                try:
                    sub(payload)
                except Exception:
                    pass

        # If remote server URL is configured, forward asynchronously via HTTP
        if self.remote_server_url:
            self._forward_remote_telemetry(payload)

    def _forward_remote_telemetry(self, payload: Dict[str, Any]):
        def worker():
            try:
                target_url = f"{self.remote_server_url}/api/agentops/telemetry"
                req_data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    target_url,
                    data=req_data,
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    pass
            except Exception:
                pass

        t = threading.Thread(target=worker, daemon=False)
        t.start()
        with self._telemetry_lock:
            self._pending_threads.append(t)
            if len(self._pending_threads) > 50:
                self._pending_threads = [th for th in self._pending_threads if th.is_alive()]

    def flush(self, timeout: float = 2.0):
        """Wait for all pending remote telemetry network requests to complete."""
        with self._telemetry_lock:
            threads = list(self._pending_threads)
        for t in threads:
            if t.is_alive():
                t.join(timeout=timeout)


tracker = GoogleOpenAgentOpsTracker()
OpenAgentOpsTracker = GoogleOpenAgentOpsTracker

atexit.register(lambda: tracker.flush())
