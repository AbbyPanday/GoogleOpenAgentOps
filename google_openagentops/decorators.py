"""
GoogleOpenAgentOps Decorator & Context Manager Suite.
Offers 100% AgentOps parity + Google ADK & OpenInference native compliance.

Decorators:
- @session: Wraps top-level workflow executions, manages session lifecycle.
- @agent: Instruments an agent class or method with role, model, thoughts, and spans.
- @operation: Instruments fine-grained operational logic and data transforms.
- @tool: Instruments tool execution with parameter capture and execution timings.
- @workflow: Instruments orchestrator workflows and multi-agent loops.
- @guardrail: Instruments safety checks, input/output validation, and policy compliance.

Context Managers:
- start_trace: Traces multi-agent runs.
- start_span: Granular span scope.
- session_scope: Explicit with-block session management.
"""

import functools
import inspect
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Union

import contextvars

from google_openagentops.models import SpanKind, AgentState
from google_openagentops.tracker import tracker

_current_session_id = contextvars.ContextVar("current_session_id", default=None)
_current_trace_id = contextvars.ContextVar("current_trace_id", default=None)
_current_span_id = contextvars.ContextVar("current_span_id", default=None)


class ExecutionContext:
    @staticmethod
    def get_session_id() -> Optional[str]:
        return _current_session_id.get() or tracker.active_session_id

    @staticmethod
    def set_session(session_id: str):
        _current_session_id.set(session_id)
        tracker.active_session_id = session_id

    @staticmethod
    def get_trace_id() -> Optional[str]:
        return _current_trace_id.get()

    @staticmethod
    def set_trace(trace_id: str):
        _current_trace_id.set(trace_id)

    @staticmethod
    def get_span_id() -> Optional[str]:
        return _current_span_id.get()

    @staticmethod
    def set_span(span_id: str):
        _current_span_id.set(span_id)

    @staticmethod
    def clear_span():
        _current_span_id.set(None)

    @staticmethod
    def clear():
        _current_session_id.set(None)
        _current_trace_id.set(None)
        _current_span_id.set(None)


active_context = ExecutionContext()


class session_scope:
    """Context manager for managing an explicit Session lifecycle."""
    def __init__(self, session_id: Optional[str] = None, session_name: Optional[str] = None, tags: Optional[Dict[str, Any]] = None):
        self.session_id = session_id or f"sess-{uuid.uuid4().hex[:8]}"
        self.session_name = session_name or f"Session-{self.session_id[-4:]}"
        self.tags = tags or {}
        self.session = None

    def __enter__(self):
        self.session = tracker.start_session(
            session_id=self.session_id,
            session_name=self.session_name,
            metadata=self.tags
        )
        active_context.set_session(self.session_id)
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        status = "FAILED" if exc_val else "COMPLETED"
        tracker.end_session(self.session_id, status=status)
        active_context.clear()


class start_trace:
    """Context manager for tracing an entire multi-agent workflow run."""
    def __init__(self, session_id: Optional[str] = None, name: str = "main_trace", attributes: Optional[Dict[str, Any]] = None):
        self.session_id = session_id or active_context.get_session_id() or "default-session"
        self.name = name
        self.attributes = attributes
        self.trace = None

    def __enter__(self):
        self.trace = tracker.start_trace(self.session_id, self.name, self.attributes)
        active_context.set_trace(self.trace.trace_id)
        return self.trace

    def __exit__(self, exc_type, exc_val, exc_tb):
        status = "ERROR" if exc_val else "OK"
        tracker.end_trace(self.trace.trace_id, status=status, error=str(exc_val) if exc_val else None)


class start_span:
    """Context manager for tracing an individual execution span."""
    def __init__(
        self,
        session_id: Optional[str] = None,
        name: str = "execution_span",
        span_kind: str = SpanKind.AGENT.value,
        agent_name: Optional[str] = None,
        agent_role: Optional[str] = None,
        model: str = "gemini-3.8-flash",
        parent_span_id: Optional[str] = None,
        input_data: Any = None,
        attributes: Optional[Dict[str, Any]] = None
    ):
        self.session_id = session_id or active_context.get_session_id() or "default-session"
        self.name = name
        self.span_kind = span_kind
        self.agent_name = agent_name
        self.agent_role = agent_role
        self.model = model
        self.parent_span_id = parent_span_id or active_context.get_span_id()
        self.input_data = input_data
        self.attributes = attributes or {}
        self.span = None
        self._prev_span = None

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
        self._prev_span = active_context.get_span_id()
        active_context.set_span(self.span.span_id)
        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb):
        error = exc_val if exc_val else None
        tracker.end_span(self.span.span_id, error=error)
        if self._prev_span:
            active_context.set_span(self._prev_span)
        else:
            active_context.clear_span()


def session(
    _func: Optional[Callable] = None,
    *,
    session_id: Optional[str] = None,
    session_name: Optional[str] = None,
    tags: Optional[Dict[str, Any]] = None
):
    """
    Session-level decorator (AgentOps @session parity).
    Automatically initializes a session context before function execution and closes it upon completion.
    """
    def decorator(fn: Callable):
        s_name = session_name or fn.__name__

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            sid = session_id or kwargs.get("session_id") or f"sess-{uuid.uuid4().hex[:8]}"
            with session_scope(session_id=sid, session_name=s_name, tags=tags):
                return fn(*args, **kwargs)

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            sid = session_id or kwargs.get("session_id") or f"sess-{uuid.uuid4().hex[:8]}"
            with session_scope(session_id=sid, session_name=s_name, tags=tags):
                return await fn(*args, **kwargs)

        if inspect.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper

    if _func is None:
        return decorator
    return decorator(_func)


def agent(
    _func: Optional[Union[Callable, type]] = None,
    *,
    name: Optional[str] = None,
    role: Optional[str] = None,
    model: str = "gemini-3.8-flash"
):
    """
    Agent-level decorator (AgentOps @agent parity).
    Can decorate an agent class or an agent run/execute method.
    """
    def decorator(target: Union[Callable, type]):
        if inspect.isclass(target):
            orig_init = target.__init__
            agent_label = name or target.__name__

            @functools.wraps(orig_init)
            def wrapped_init(self, *args, **kwargs):
                self._agent_name = agent_label
                self._agent_role = role or getattr(self, "role", "Autonomous Agent")
                self._agent_model = model
                orig_init(self, *args, **kwargs)

            target.__init__ = wrapped_init

            for method_name in ["run", "execute", "invoke", "call", "__call__"]:
                if hasattr(target, method_name):
                    orig_method = getattr(target, method_name)
                    if callable(orig_method):
                        setattr(target, method_name, _instrument_agent_method(orig_method, agent_label, role, model))
            return target
        else:
            agent_label = name or target.__name__
            return _instrument_agent_method(target, agent_label, role, model)

    if _func is None:
        return decorator
    return decorator(_func)


def _instrument_agent_method(fn: Callable, agent_name: str, role: Optional[str], model: str):
    """Internal helper to wrap agent execution methods (sync and async)."""
    @functools.wraps(fn)
    def sync_wrapper(*args, **kwargs):
        session_id = kwargs.get("session_id") or active_context.get_session_id() or "default-session"
        parent_span_id = active_context.get_span_id()
        span = tracker.start_span(
            session_id=session_id,
            name=agent_name,
            span_kind=SpanKind.AGENT.value,
            agent_name=agent_name,
            agent_role=role,
            model=model,
            parent_span_id=parent_span_id,
            input_data=kwargs.get("input") or (args[1:] if len(args) > 1 and hasattr(args[0], "__class__") else args)
        )
        prev_span = active_context.get_span_id()
        active_context.set_span(span.span_id)
        tracker.record_state_transition(
            session_id=session_id,
            agent_name=agent_name,
            from_state=AgentState.IDLE.value,
            to_state=AgentState.THINKING.value,
            reason=f"Invoking {agent_name}"
        )
        try:
            result = fn(*args, **kwargs)
            thought = None
            if isinstance(result, dict) and "_thought" in result:
                thought = result["_thought"]
            tracker.end_span(span.span_id, output_data=result, thought=thought)
            tracker.record_state_transition(
                session_id=session_id,
                agent_name=agent_name,
                from_state=AgentState.THINKING.value,
                to_state=AgentState.COMPLETED.value,
                reason=f"Finished {agent_name}"
            )
            return result
        except Exception as e:
            tracker.end_span(span.span_id, error=e)
            tracker.record_state_transition(
                session_id=session_id,
                agent_name=agent_name,
                from_state=AgentState.THINKING.value,
                to_state=AgentState.FAILED.value,
                reason=str(e)
            )
            raise
        finally:
            if prev_span:
                active_context.set_span(prev_span)
            else:
                active_context.clear_span()

    @functools.wraps(fn)
    async def async_wrapper(*args, **kwargs):
        session_id = kwargs.get("session_id") or active_context.get_session_id() or "default-session"
        parent_span_id = active_context.get_span_id()
        span = tracker.start_span(
            session_id=session_id,
            name=agent_name,
            span_kind=SpanKind.AGENT.value,
            agent_name=agent_name,
            agent_role=role,
            model=model,
            parent_span_id=parent_span_id,
            input_data=kwargs.get("input") or (args[1:] if len(args) > 1 and hasattr(args[0], "__class__") else args)
        )
        prev_span = active_context.get_span_id()
        active_context.set_span(span.span_id)
        tracker.record_state_transition(
            session_id=session_id,
            agent_name=agent_name,
            from_state=AgentState.IDLE.value,
            to_state=AgentState.THINKING.value,
            reason=f"Invoking {agent_name}"
        )
        try:
            result = await fn(*args, **kwargs)
            thought = None
            if isinstance(result, dict) and "_thought" in result:
                thought = result["_thought"]
            tracker.end_span(span.span_id, output_data=result, thought=thought)
            tracker.record_state_transition(
                session_id=session_id,
                agent_name=agent_name,
                from_state=AgentState.THINKING.value,
                to_state=AgentState.COMPLETED.value,
                reason=f"Finished {agent_name}"
            )
            return result
        except Exception as e:
            tracker.end_span(span.span_id, error=e)
            tracker.record_state_transition(
                session_id=session_id,
                agent_name=agent_name,
                from_state=AgentState.THINKING.value,
                to_state=AgentState.FAILED.value,
                reason=str(e)
            )
            raise
        finally:
            if prev_span:
                active_context.set_span(prev_span)
            else:
                active_context.clear_span()

    if inspect.iscoroutinefunction(fn):
        return async_wrapper
    return sync_wrapper


def operation(
    _func: Optional[Callable] = None,
    *,
    name: Optional[str] = None
):
    """
    Operation/Task-level decorator (AgentOps @operation parity).
    Captures intermediate task execution units as OpenInference CHAIN/OPERATION spans.
    """
    def decorator(fn: Callable):
        op_name = name or fn.__name__

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            session_id = kwargs.get("session_id") or active_context.get_session_id() or "default-session"
            parent_span_id = active_context.get_span_id()
            span = tracker.start_span(
                session_id=session_id,
                name=op_name,
                span_kind=SpanKind.OPERATION.value,
                parent_span_id=parent_span_id,
                input_data=kwargs.get("input") or args
            )
            prev_span = active_context.get_span_id()
            active_context.set_span(span.span_id)
            try:
                res = fn(*args, **kwargs)
                tracker.end_span(span.span_id, output_data=res)
                return res
            except Exception as e:
                tracker.end_span(span.span_id, error=e)
                raise
            finally:
                if prev_span:
                    active_context.set_span(prev_span)
                else:
                    active_context.clear_span()

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            session_id = kwargs.get("session_id") or active_context.get_session_id() or "default-session"
            parent_span_id = active_context.get_span_id()
            span = tracker.start_span(
                session_id=session_id,
                name=op_name,
                span_kind=SpanKind.OPERATION.value,
                parent_span_id=parent_span_id,
                input_data=kwargs.get("input") or args
            )
            prev_span = active_context.get_span_id()
            active_context.set_span(span.span_id)
            try:
                res = await fn(*args, **kwargs)
                tracker.end_span(span.span_id, output_data=res)
                return res
            except Exception as e:
                tracker.end_span(span.span_id, error=e)
                raise
            finally:
                if prev_span:
                    active_context.set_span(prev_span)
                else:
                    active_context.clear_span()

        if inspect.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper

    if _func is None:
        return decorator
    return decorator(_func)


def tool(
    _func: Optional[Callable] = None,
    *,
    name: Optional[str] = None
):
    """
    Tool decorator (AgentOps @tool parity).
    Instruments tool execution with signature safety, execution duration, and tool call record logging.
    """
    def decorator(fn: Callable):
        tool_name = name or fn.__name__

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            t0 = time.time()
            session_id = kwargs.get("session_id") or active_context.get_session_id() or "default-session"
            span_id = kwargs.get("span_id") or active_context.get_span_id() or ""

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
                tracker.record_tool_call(
                    session_id=session_id,
                    span_id=span_id,
                    tool_name=tool_name,
                    params=kwargs or args,
                    result=result,
                    duration_ms=duration_ms
                )
                return result
            except Exception as e:
                duration_ms = int((time.time() - t0) * 1000)
                tracker.record_tool_call(
                    session_id=session_id,
                    span_id=span_id,
                    tool_name=tool_name,
                    params=kwargs or args,
                    result={"error": str(e)},
                    duration_ms=duration_ms
                )
                raise

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            t0 = time.time()
            session_id = kwargs.get("session_id") or active_context.get_session_id() or "default-session"
            span_id = kwargs.get("span_id") or active_context.get_span_id() or ""

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
                result = await fn(*args, **call_kwargs)
                duration_ms = int((time.time() - t0) * 1000)
                tracker.record_tool_call(
                    session_id=session_id,
                    span_id=span_id,
                    tool_name=tool_name,
                    params=kwargs or args,
                    result=result,
                    duration_ms=duration_ms
                )
                return result
            except Exception as e:
                duration_ms = int((time.time() - t0) * 1000)
                tracker.record_tool_call(
                    session_id=session_id,
                    span_id=span_id,
                    tool_name=tool_name,
                    params=kwargs or args,
                    result={"error": str(e)},
                    duration_ms=duration_ms
                )
                raise

        if inspect.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper

    if _func is None:
        return decorator
    return decorator(_func)


def workflow(
    _func: Optional[Callable] = None,
    *,
    name: Optional[str] = None
):
    """
    Workflow decorator (AgentOps @workflow parity).
    Wraps orchestrator multi-agent pipelines and tracks overall workflow spans.
    """
    def decorator(fn: Callable):
        wf_name = name or fn.__name__

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            session_id = kwargs.get("session_id") or active_context.get_session_id() or "default-session"
            span = tracker.start_span(
                session_id=session_id,
                name=wf_name,
                span_kind=SpanKind.WORKFLOW.value,
                input_data=kwargs.get("input") or args
            )
            prev_span = active_context.get_span_id()
            active_context.set_span(span.span_id)
            try:
                res = fn(*args, **kwargs)
                tracker.end_span(span.span_id, output_data=res)
                return res
            except Exception as e:
                tracker.end_span(span.span_id, error=e)
                raise
            finally:
                if prev_span:
                    active_context.set_span(prev_span)
                else:
                    active_context.clear_span()

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            session_id = kwargs.get("session_id") or active_context.get_session_id() or "default-session"
            span = tracker.start_span(
                session_id=session_id,
                name=wf_name,
                span_kind=SpanKind.WORKFLOW.value,
                input_data=kwargs.get("input") or args
            )
            prev_span = active_context.get_span_id()
            active_context.set_span(span.span_id)
            try:
                res = await fn(*args, **kwargs)
                tracker.end_span(span.span_id, output_data=res)
                return res
            except Exception as e:
                tracker.end_span(span.span_id, error=e)
                raise
            finally:
                if prev_span:
                    active_context.set_span(prev_span)
                else:
                    active_context.clear_span()

        if inspect.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper

    if _func is None:
        return decorator
    return decorator(_func)


def guardrail(
    _func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    score_threshold: Optional[float] = None
):
    """
    Guardrail decorator for automated safety & validation checks.
    Evaluates function outputs, recording a guardrail span and replay event.
    """
    def decorator(fn: Callable):
        g_name = name or fn.__name__

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            session_id = kwargs.get("session_id") or active_context.get_session_id() or "default-session"
            res = fn(*args, **kwargs)
            passed = True
            reason = "Validation check satisfied"
            score = 1.0

            if isinstance(res, bool):
                passed = res
                score = 1.0 if res else 0.0
                reason = "Boolean validation passed" if res else "Boolean validation failed"
            elif isinstance(res, (int, float)) and score_threshold is not None:
                score = float(res)
                passed = score >= score_threshold
                reason = f"Score {score:.2f} >= threshold {score_threshold:.2f}" if passed else f"Score {score:.2f} below threshold {score_threshold:.2f}"
            elif isinstance(res, dict):
                passed = res.get("passed", True)
                score = res.get("score", 1.0)
                reason = res.get("reason", "Dict validation check")

            tracker.record_guardrail(
                session_id=session_id,
                name=g_name,
                passed=passed,
                input_data=kwargs or args,
                output_data=res,
                score=score,
                reason=reason
            )
            return res

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            session_id = kwargs.get("session_id") or active_context.get_session_id() or "default-session"
            res = await fn(*args, **kwargs)
            passed = True
            reason = "Validation check satisfied"
            score = 1.0

            if isinstance(res, bool):
                passed = res
                score = 1.0 if res else 0.0
                reason = "Boolean validation passed" if res else "Boolean validation failed"
            elif isinstance(res, (int, float)) and score_threshold is not None:
                score = float(res)
                passed = score >= score_threshold
                reason = f"Score {score:.2f} >= threshold {score_threshold:.2f}" if passed else f"Score {score:.2f} below threshold {score_threshold:.2f}"
            elif isinstance(res, dict):
                passed = res.get("passed", True)
                score = res.get("score", 1.0)
                reason = res.get("reason", "Dict validation check")

            tracker.record_guardrail(
                session_id=session_id,
                name=g_name,
                passed=passed,
                input_data=kwargs or args,
                output_data=res,
                score=score,
                reason=reason
            )
            return res

        if inspect.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper

    if _func is None:
        return decorator
    return decorator(_func)


# Backward compatibility aliases
track_agent = agent
track_tool = tool
