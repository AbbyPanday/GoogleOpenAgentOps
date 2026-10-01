"""
Convenient decorators and context managers to attach GoogleOpenAgentOps
to any Python agent framework (Google ADK Python, LangChain, CrewAI, AutoGen).
"""

import functools
import inspect
import time
from typing import Any, Callable, Dict, Optional

from google_openagentops.models import SpanKind
from google_openagentops.tracker import tracker


class start_trace:
    """Context manager for tracing an entire multi-agent workflow run."""
    def __init__(self, session_id: str, name: str, attributes: Optional[Dict[str, Any]] = None):
        self.session_id = session_id
        self.name = name
        self.attributes = attributes
        self.trace = None

    def __enter__(self):
        self.trace = tracker.start_trace(self.session_id, self.name, self.attributes)
        return self.trace

    def __exit__(self, exc_type, exc_val, exc_tb):
        status = "ERROR" if exc_val else "OK"
        tracker.end_trace(self.trace.trace_id, status=status, error=str(exc_val) if exc_val else None)


class start_span:
    """Context manager for tracing an individual execution span."""
    def __init__(
        self,
        session_id: str,
        name: str,
        span_kind: str = SpanKind.AGENT.value,
        agent_name: Optional[str] = None,
        agent_role: Optional[str] = None,
        model: str = "gemini-3.8-flash",
        parent_span_id: Optional[str] = None,
        input_data: Any = None,
        attributes: Optional[Dict[str, Any]] = None
    ):
        self.session_id = session_id
        self.name = name
        self.span_kind = span_kind
        self.agent_name = agent_name
        self.agent_role = agent_role
        self.model = model
        self.parent_span_id = parent_span_id
        self.input_data = input_data
        self.attributes = attributes
        self.span = None

    def __enter__(self):
        self.span = tracker.start_span(
            session_id=self.session_id,
            name=self.name,
            span_kind=self.span_kind,
            agent_name=self.agent_name,
            agent_role=self.agent_role,
            model=self.model,
            parent_span_id=self.parent_span_id,
            input_data=self.input_data,
            attributes=self.attributes
        )
        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb):
        tracker.end_span(self.span.span_id, error=exc_val)


def track_agent(name: Optional[str] = None, role: Optional[str] = None, model: str = "gemini-3.8-flash"):
    """Decorator to instrument an agent execution method."""
    def decorator(fn: Callable):
        agent_name = name or fn.__name__

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            session_id = kwargs.get("session_id") or "default-session"
            span = tracker.start_span(
                session_id=session_id,
                name=agent_name,
                span_kind=SpanKind.AGENT.value,
                agent_name=agent_name,
                agent_role=role,
                model=model,
                input_data=kwargs.get("input") or args
            )
            try:
                result = fn(*args, **kwargs)
                thought = None
                if isinstance(result, dict) and "_thought" in result:
                    thought = result["_thought"]
                tracker.end_span(span.span_id, output_data=result, thought=thought)
                return result
            except Exception as e:
                tracker.end_span(span.span_id, error=e)
                raise

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            session_id = kwargs.get("session_id") or "default-session"
            span = tracker.start_span(
                session_id=session_id,
                name=agent_name,
                span_kind=SpanKind.AGENT.value,
                agent_name=agent_name,
                agent_role=role,
                model=model,
                input_data=kwargs.get("input") or args
            )
            try:
                result = await fn(*args, **kwargs)
                thought = None
                if isinstance(result, dict) and "_thought" in result:
                    thought = result["_thought"]
                tracker.end_span(span.span_id, output_data=result, thought=thought)
                return result
            except Exception as e:
                tracker.end_span(span.span_id, error=e)
                raise

        if inspect.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper
    return decorator


def track_tool(name: Optional[str] = None):
    """Decorator to instrument tool execution with robust signature inspection."""
    def decorator(fn: Callable):
        tool_name = name or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            t0 = time.time()
            session_id = kwargs.get("session_id", "default-session")
            span_id = kwargs.get("span_id", "")

            sig = inspect.signature(fn)
            params = sig.parameters
            has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
            call_kwargs = dict(kwargs)
            if not has_var_kw:
                if "session_id" not in params:
                    call_kwargs.pop("session_id", None)
                if "span_id" not in params:
                    call_kwargs.pop("span_id", None)

            try:
                result = fn(*args, **call_kwargs)
                duration_ms = int((time.time() - t0) * 1000)
                tracker.record_tool_call(session_id, span_id, tool_name, params=kwargs or args, result=result, duration_ms=duration_ms)
                return result
            except Exception as e:
                duration_ms = int((time.time() - t0) * 1000)
                tracker.record_tool_call(session_id, span_id, tool_name, params=kwargs or args, result={"error": str(e)}, duration_ms=duration_ms)
                raise
        return wrapper
    return decorator
