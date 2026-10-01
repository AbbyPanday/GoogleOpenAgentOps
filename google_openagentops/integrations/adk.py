"""
Google ADK (Agent Development Kit) & Multi-Agent Solution Integrations.
Enables linking one or multiple independent ADK agent solutions to the central GoogleOpenAgentOps dashboard.
"""

import functools
import inspect
import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional
import uuid

from google_openagentops.tracker import tracker
from google_openagentops.models import AgentState, SpanKind
from google_openagentops.pricing import calculate_token_cost, estimate_token_count

logger = logging.getLogger("google_openagentops.adk")


class GoogleADKTracker:
    """
    Connects a Google ADK Agent Solution to the GoogleOpenAgentOps central dashboard.
    Supports registering multiple agent solutions with custom solution_id, solution_name,
    and streaming correlated multi-agent execution traces.
    """

    def __init__(
        self,
        solution_id: Optional[str] = None,
        solution_name: str = "GoogleADK-Solution",
        dashboard_url: Optional[str] = None,
        project_id: Optional[str] = None,
        default_model: str = "gemini-3.8-flash"
    ):
        self.solution_id = solution_id or str(uuid.uuid4())[:8]
        self.solution_name = solution_name
        self.default_model = default_model
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT") or "adk-workspace"
        
        # Configure remote telemetry sync if dashboard_url is provided
        if dashboard_url:
            tracker.set_remote_server(dashboard_url)
        elif os.getenv("GOOGLE_OPENAGENTOPS_SERVER_URL"):
            tracker.set_remote_server(os.getenv("GOOGLE_OPENAGENTOPS_SERVER_URL"))

        # Register this ADK solution with central tracker
        self.register_solution()

    def register_solution(self) -> Dict[str, Any]:
        """Broadcast solution registration event to central dashboard."""
        registration_payload = {
            "solution_id": self.solution_id,
            "solution_name": self.solution_name,
            "default_model": self.default_model,
            "project_id": self.project_id,
            "timestamp": int(time.time() * 1000),
            "status": "ONLINE"
        }
        tracker.register_solution(registration_payload)
        return registration_payload

    def start_session(self, user_id: Optional[str] = None, tags: Optional[List[str]] = None) -> str:
        """Start a correlated session scoped to this ADK agent solution."""
        effective_tags = [f"solution:{self.solution_name}", f"sol_id:{self.solution_id}"]
        if tags:
            effective_tags.extend(tags)
        return tracker.start_session(user_id=user_id, tags=effective_tags)

    def end_session(self, session_id: Optional[str] = None, status: str = "SUCCESS"):
        """Close an ADK session and finalize metrics."""
        tracker.end_session(session_id=session_id, status=status)

    def track_agent(
        self,
        agent_name: Optional[str] = None,
        model: Optional[str] = None,
        version: str = "1.0.0"
    ) -> Callable:
        """
        Decorator to instrument an ADK Agent execution loop or step method.
        Tracks AgentState transitions (IDLE -> THINKING -> TOOL_CALLING -> COMPLETED).
        """
        def decorator(func: Callable) -> Callable:
            target_name = agent_name or func.__name__
            assigned_model = model or self.default_model

            if inspect.iscoroutinefunction(func):
                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    session_id = tracker.get_active_session_id() or self.start_session()
                    trace = tracker.start_trace(
                        session_id=session_id,
                        name=f"ADK-Agent:{self.solution_name}:{target_name}",
                        tags=["adk", self.solution_name, target_name]
                    )
                    trace_id = trace.trace_id if hasattr(trace, "trace_id") else trace
                    tracker.update_agent_state(
                        agent_name=target_name,
                        state=AgentState.THINKING,
                        reason=f"ADK Agent {target_name} processing async task",
                        metadata={"solution_id": self.solution_id, "solution_name": self.solution_name, "model": assigned_model}
                    )
                    start_t = time.time()
                    try:
                        result = await func(*args, **kwargs)
                        tracker.update_agent_state(
                            agent_name=target_name,
                            state=AgentState.COMPLETED,
                            reason=f"ADK Agent {target_name} completed task successfully",
                            metadata={"solution_id": self.solution_id}
                        )
                        self._record_llm_metrics(trace_id, assigned_model, args, kwargs, result)
                        return result
                    except Exception as e:
                        tracker.update_agent_state(
                            agent_name=target_name,
                            state=AgentState.FAILED,
                            reason=str(e),
                            metadata={"solution_id": self.solution_id, "error": True}
                        )
                        raise
                    finally:
                        dur_ms = int((time.time() - start_t) * 1000)
                        tracker.end_trace(trace_id=trace_id)
                return async_wrapper
            else:
                @functools.wraps(func)
                def sync_wrapper(*args, **kwargs):
                    session_id = tracker.get_active_session_id() or self.start_session()
                    trace = tracker.start_trace(
                        session_id=session_id,
                        name=f"ADK-Agent:{self.solution_name}:{target_name}",
                        tags=["adk", self.solution_name, target_name]
                    )
                    trace_id = trace.trace_id if hasattr(trace, "trace_id") else trace
                    tracker.update_agent_state(
                        agent_name=target_name,
                        state=AgentState.THINKING,
                        reason=f"ADK Agent {target_name} processing synchronous task",
                        metadata={"solution_id": self.solution_id, "solution_name": self.solution_name, "model": assigned_model}
                    )
                    start_t = time.time()
                    try:
                        result = func(*args, **kwargs)
                        tracker.update_agent_state(
                            agent_name=target_name,
                            state=AgentState.COMPLETED,
                            reason=f"ADK Agent {target_name} task complete",
                            metadata={"solution_id": self.solution_id}
                        )
                        self._record_llm_metrics(trace_id, assigned_model, args, kwargs, result)
                        return result
                    except Exception as e:
                        tracker.update_agent_state(
                            agent_name=target_name,
                            state=AgentState.FAILED,
                            reason=str(e),
                            metadata={"solution_id": self.solution_id, "error": True}
                        )
                        raise
                    finally:
                        dur_ms = int((time.time() - start_t) * 1000)
                        tracker.end_trace(trace_id=trace_id)
                return sync_wrapper
        return decorator

    def track_tool(self, tool_name: Optional[str] = None) -> Callable:
        """Decorator to instrument an ADK Tool invocation."""
        def decorator(func: Callable) -> Callable:
            t_name = tool_name or func.__name__

            if inspect.iscoroutinefunction(func):
                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    span = tracker.start_span(name=f"ADK-Tool:{t_name}", span_kind=SpanKind.TOOL.value)
                    span_id = span.span_id if hasattr(span, "span_id") else span
                    tracker.update_agent_state(
                        agent_name=self.solution_name,
                        state=AgentState.TOOL_CALLING,
                        reason=f"Executing tool {t_name}",
                        metadata={"tool": t_name}
                    )
                    t0 = time.time()
                    try:
                        res = await func(*args, **kwargs)
                        lat = (time.time() - t0) * 1000.0
                        tracker.record_tool_call(tool_name=t_name, duration_ms=lat, is_error=False)
                        tracker.end_span(span_id=span_id, output_payload={"result": str(res)})
                        return res
                    except Exception as e:
                        lat = (time.time() - t0) * 1000.0
                        tracker.record_tool_call(tool_name=t_name, duration_ms=lat, is_error=True, error_message=str(e))
                        tracker.end_span(span_id=span_id, error=str(e))
                        raise
                return async_wrapper
            else:
                @functools.wraps(func)
                def sync_wrapper(*args, **kwargs):
                    span = tracker.start_span(name=f"ADK-Tool:{t_name}", span_kind=SpanKind.TOOL.value)
                    span_id = span.span_id if hasattr(span, "span_id") else span
                    tracker.update_agent_state(
                        agent_name=self.solution_name,
                        state=AgentState.TOOL_CALLING,
                        reason=f"Executing tool {t_name}",
                        metadata={"tool": t_name}
                    )
                    t0 = time.time()
                    try:
                        res = func(*args, **kwargs)
                        lat = (time.time() - t0) * 1000.0
                        tracker.record_tool_call(tool_name=t_name, duration_ms=lat, is_error=False)
                        tracker.end_span(span_id=span_id, output_payload={"result": str(res)})
                        return res
                    except Exception as e:
                        lat = (time.time() - t0) * 1000.0
                        tracker.record_tool_call(tool_name=t_name, duration_ms=lat, is_error=True, error_message=str(e))
                        tracker.end_span(span_id=span_id, error=str(e))
                        raise
                return sync_wrapper
        return decorator

    def record_handoff(self, target_agent: str, context: Optional[Dict[str, Any]] = None):
        """Record an ADK agent-to-agent delegation/handoff."""
        tracker.record_handoff(
            source_agent=self.solution_name,
            target_agent=target_agent,
            context=context or {}
        )

    def _record_llm_metrics(self, trace_id: str, model: str, args: Any, kwargs: Any, result: Any):
        """Calculate and register Gemini 3.x tokens and costs for this step."""
        try:
            prompt_str = f"{args} {kwargs}"
            output_str = str(result)
            p_tokens = estimate_token_count(prompt_str)
            c_tokens = estimate_token_count(output_str)
            tracker.record_llm_call(
                model=model,
                prompt_tokens=p_tokens,
                completion_tokens=c_tokens,
                trace_id=trace_id
            )
        except Exception as e:
            logger.debug(f"Failed to record LLM metrics: {e}")


def track_adk_agent(solution_name: str = "ADK-Agent", model: str = "gemini-3.8-flash") -> GoogleADKTracker:
    """Convenience helper to instantiate an ADK tracker."""
    return GoogleADKTracker(solution_name=solution_name, default_model=model)
