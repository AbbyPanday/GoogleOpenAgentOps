"""
Zero-dependency embedded OpenAgentOps HTTP & SSE Observability Server.
Streams real-time state machine changes, traces, token costs, and GCP console deep links.
Supports receiving telemetry from remote Google ADK agent solutions.
"""

from http.server import SimpleHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
import json
import os
import time
import queue
import threading
from typing import Optional
from urllib.parse import urlparse

from google_openagentops.tracker import tracker
from google_openagentops.exporters import export_openinference
from google_openagentops.context import active_context

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")

_sse_subscribers = []
_sse_lock = threading.Lock()


def broadcast_event(event_dict: dict):
    """Broadcast an event payload to all connected SSE clients."""
    with _sse_lock:
        dead = []
        for q in _sse_subscribers:
            try:
                q.put_nowait(event_dict)
            except Exception:
                dead.append(q)
        for d in dead:
            if d in _sse_subscribers:
                _sse_subscribers.remove(d)



class GoogleOpenAgentOpsHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def log_message(self, format, *args):
        pass  # Suppress noisy standard HTTP logs

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len) if content_len > 0 else b"{}"

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}

        # Broadcast telemetry to connected SSE streaming clients
        if payload:
            broadcast_event(payload)

        if path in ("/api/agentops/telemetry", "/api/agentops/events"):
            event_type = payload.get("type", "REMOTE_EVENT")
            data = payload.get("data", {})

            if event_type == "SOLUTION_REGISTERED":
                sol = data.get("solution", {})
                if sol:
                    tracker.register_solution(sol)
            elif event_type == "SESSION_CREATED":
                sid = data.get("sessionId")
                if sid:
                    tracker.get_or_create_session(sid, data.get("gcpContext"))
            elif event_type == "STATE_TRANSITION":
                sid = data.get("sessionId")
                trans = data.get("transition", {})
                if sid and trans:
                    tracker.record_state_transition(
                        session_id=sid,
                        agent_name=trans.get("agent_name", "agent"),
                        from_state=trans.get("from_state", "IDLE"),
                        to_state=trans.get("to_state", "COMPLETED"),
                        reason=trans.get("reason", "")
                    )
            elif event_type == "HANDOFF":
                sid = data.get("sessionId")
                h = data.get("handoff", {})
                if sid and h:
                    tracker.record_handoff(
                        session_id=sid,
                        from_agent=h.get("from_agent", ""),
                        to_agent=h.get("to_agent", ""),
                        summary=h.get("summary", "")
                    )
            elif event_type == "LLM_CALL":
                sid = data.get("sessionId")
                m = data.get("metrics", {})
                if sid and m:
                    sess = tracker.get_or_create_session(sid)
                    sess.metrics.total_tokens += m.get("total_tokens", 0)
                    sess.metrics.total_cost_usd += m.get("total_cost_usd", 0.0)
            elif event_type in ("SPAN_STARTED", "SPAN_ENDED"):
                sid = data.get("session_id") or data.get("sessionId")
                if sid:
                    sess = tracker.get_or_create_session(sid)
                    span_id = data.get("span_id") or data.get("spanId")
                    existing = next((s for s in sess.spans if (s.span_id if hasattr(s, "span_id") else s.get("span_id")) == span_id), None)
                    if existing:
                        if hasattr(existing, "status"):
                            existing.status = data.get("status", existing.status)
                            existing.duration_ms = data.get("duration_ms", existing.duration_ms)
                            existing.output = data.get("output", existing.output)
                            if data.get("thought"):
                                existing.thought = data.get("thought")
                            if data.get("metrics"):
                                m = data["metrics"]
                                existing.metrics.prompt_tokens = m.get("prompt_tokens", existing.metrics.prompt_tokens)
                                existing.metrics.completion_tokens = m.get("completion_tokens", existing.metrics.completion_tokens)
                                existing.metrics.total_tokens = m.get("total_tokens", existing.metrics.total_tokens)
                                existing.metrics.total_cost_usd = m.get("total_cost_usd", existing.metrics.total_cost_usd)
                    else:
                        from google_openagentops.models import Span, TokenMetrics
                        m_data = data.get("metrics", {})
                        m_obj = TokenMetrics(
                            prompt_tokens=m_data.get("prompt_tokens", 0),
                            completion_tokens=m_data.get("completion_tokens", 0),
                            total_tokens=m_data.get("total_tokens", 0),
                            total_cost_usd=m_data.get("total_cost_usd", 0.0)
                        )
                        new_span = Span(
                            span_id=span_id or "span-1",
                            trace_id=data.get("trace_id") or data.get("traceId", "trace-1"),
                            session_id=sid,
                            name=data.get("name", "agent"),
                            span_kind=data.get("span_kind") or data.get("spanKind", "AGENT"),
                            agent_name=data.get("agent_name") or data.get("agentName"),
                            model=data.get("model", "gemini-3.8-flash"),
                            status=data.get("status", "OK"),
                            duration_ms=data.get("duration_ms") if data.get("duration_ms") is not None else data.get("durationMs", 0),
                            input=data.get("input"),
                            output=data.get("output"),
                            thought=data.get("thought"),
                            metrics=m_obj
                        )
                        sess.spans.append(new_span)
                        sess.metrics.total_tokens += m_obj.total_tokens
                        sess.metrics.total_cost_usd += m_obj.total_cost_usd
                        sess.metrics.total_spans += 1
            elif event_type == "THOUGHT_RECORDED":
                sid = data.get("session_id") or data.get("sessionId")
                span_id = data.get("span_id") or data.get("spanId")
                thought = data.get("thought")
                if sid and span_id:
                    sess = tracker.get_or_create_session(sid)
                    for s in sess.spans:
                        curr_id = s.span_id if hasattr(s, "span_id") else s.get("span_id")
                        if curr_id == span_id:
                            if hasattr(s, "thought"):
                                s.thought = thought
                            else:
                                s["thought"] = thought
                            break
            elif event_type == "TOOL_CALLED":
                sid = data.get("sessionId") or data.get("session_id")
                span_id = data.get("spanId") or data.get("span_id")
                tool_data = data.get("tool", {})
                if sid and span_id and tool_data:
                    sess = tracker.get_or_create_session(sid)
                    for s in sess.spans:
                        curr_id = s.span_id if hasattr(s, "span_id") else s.get("span_id")
                        if curr_id == span_id:
                            from google_openagentops.models import ToolCallRecord
                            tc = ToolCallRecord(
                                tool_name=tool_data.get("tool_name", "tool"),
                                tool_call_id=tool_data.get("tool_call_id", "tool-1"),
                                params=tool_data.get("params", {}),
                                result=tool_data.get("result"),
                                duration_ms=tool_data.get("duration_ms", 0)
                            )
                            if hasattr(s, "tool_calls"):
                                s.tool_calls.append(tc)
                            break
            elif event_type == "GUARDRAIL":
                sid = data.get("sessionId") or data.get("session_id")
                if sid:
                    tracker.record_guardrail(
                        session_id=sid,
                        name=data.get("name", "guardrail"),
                        passed=data.get("passed", True),
                        input_data=data.get("input"),
                        output_data=data.get("output"),
                        agent_name=data.get("agent_name"),
                        score=data.get("score"),
                        reason=data.get("reason")
                    )
            elif event_type == "CICD_EVENT":
                ev = data.get("event", {})
                tracker.record_cicd_event(
                    pipeline_name=ev.get("pipeline_name", "pipeline"),
                    run_id=ev.get("run_id", "run-1"),
                    commit_sha=ev.get("commit_sha", "HEAD"),
                    branch=ev.get("branch", "main"),
                    status=ev.get("status", "SUCCESS"),
                    duration_ms=ev.get("duration_ms", 0),
                    environment=ev.get("environment", "production"),
                    provider=ev.get("provider", "github-actions"),
                    details=ev.get("details", {})
                )

            # Broadcast to SSE subscribers without re-forwarding
            payload_out = {
                "type": event_type,
                "timestamp": int(time.time() * 1000),
                "data": data
            }
            with tracker._telemetry_lock:
                for sub in list(tracker.subscribers):
                    try:
                        sub(payload_out)
                    except Exception:
                        pass

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"status": "ok", "ingested": true}')
            return

        if path in ("/api/agentops/cicd", "/api/cicd"):
            ev = tracker.record_cicd_event(
                pipeline_name=payload.get("pipeline_name", "CI/CD Pipeline"),
                run_id=payload.get("run_id", "run-1"),
                commit_sha=payload.get("commit_sha", "HEAD"),
                branch=payload.get("branch", "main"),
                status=payload.get("status", "SUCCESS"),
                duration_ms=payload.get("duration_ms", 0),
                environment=payload.get("environment", "production"),
                provider=payload.get("provider", "github-actions"),
                details=payload.get("details", {})
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "event": ev.to_dict()}).encode("utf-8"))
            return

        if path == "/api/agentops/register":
            tracker.register_solution(payload)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(b'{"status": "ok", "registered": true}')
            return

        self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b'{"error": "Endpoint not found"}')

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/api/agentops/stream", "/stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            q = queue.Queue(maxsize=200)
            with _sse_lock:
                _sse_subscribers.append(q)
            try:
                init_msg = json.dumps({"type": "SYSTEM", "timestamp": int(time.time() * 1000), "data": {"status": "STREAM_CONNECTED"}})
                self.wfile.write(f"data: {init_msg}\n\n".encode("utf-8"))
                self.wfile.flush()
                while True:
                    try:
                        msg = q.get(timeout=2.0)
                        self.wfile.write(f"data: {json.dumps(msg)}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
            except (ConnectionResetError, BrokenPipeError, Exception):
                pass
            finally:
                with _sse_lock:
                    if q in _sse_subscribers:
                        _sse_subscribers.remove(q)
            return

        if path in ("/api/agentops/metrics", "/api/metrics"):
            metrics = tracker.get_aggregated_metrics()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(metrics).encode("utf-8"))
            return

        if path in ("/api/agentops/cicd", "/api/cicd"):
            events = tracker.get_cicd_events()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"events": events, "count": len(events)}).encode("utf-8"))
            return

        if path == "/api/agentops/context":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(active_context.to_dict()).encode("utf-8"))
            return

        if path == "/api/agentops/solutions":
            solutions = tracker.get_solutions()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"solutions": solutions, "count": len(solutions)}).encode("utf-8"))
            return

        if path == "/api/agentops/sessions":
            sessions = tracker.get_all_sessions()
            solutions = tracker.get_solutions()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "sessions": sessions,
                "solutions": solutions,
                "gcpContext": active_context.to_dict()
            }).encode("utf-8"))
            return

        if "/replay" in path and ("/session/" in path or "/sessions/" in path):
            parts = path.split("/replay")[0].split("/")
            session_id = parts[-1]
            replay = tracker.get_session_replay(session_id)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"sessionId": session_id, "events": replay, "count": len(replay)}).encode("utf-8"))
            return

        if path.startswith("/api/agentops/session/"):
            session_id = path.split("/api/agentops/session/")[1].strip("/")
            sess = tracker.get_session(session_id)
            if not sess:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Session not found"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"session": sess.to_dict(), "gcpContext": active_context.to_dict()}).encode("utf-8"))
            return

        if path.startswith("/api/agentops/export/"):
            session_id = path.split("/api/agentops/export/")[1].strip("/")
            export_data = export_openinference(session_id)
            if not export_data:
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Session not found for export"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Disposition", f'attachment; filename="google-openagentops-trace-{session_id}.json"')
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(export_data, indent=2).encode("utf-8"))
            return

        if path == "/api/agentops/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            q = queue.Queue()
            def listener(payload):
                q.put(payload)

            tracker.add_subscriber(listener)
            try:
                # Send initial greeting
                self.wfile.write(b'data: {"type": "CONNECTED", "msg": "GoogleOpenAgentOps Stream Active"}\n\n')
                self.wfile.flush()
                while True:
                    try:
                        item = q.get(timeout=25.0)
                        msg = f"data: {json.dumps(item)}\n\n"
                        self.wfile.write(msg.encode("utf-8"))
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
            except (ConnectionResetError, BrokenPipeError):
                pass
            finally:
                tracker.remove_subscriber(listener)
            return

        if path == "/" or not path:
            self.path = "/index.html"
        return super().do_GET()


# Uses built-in multi-threaded HTTP server so SSE streams do not block REST requests


def launch_dashboard(port: int = 8000, host: str = "localhost", blocking: bool = False) -> ThreadingHTTPServer:
    """Launch the embedded GoogleOpenAgentOps dashboard server."""
    server = ThreadingHTTPServer((host, port), GoogleOpenAgentOpsHandler)
    url = f"http://{host}:{port}"
    print(f"\n[*] GoogleOpenAgentOps Observability Dashboard running at {url}")
    print(f"   GCP Runtime: {active_context.runtime_type} | Project: {active_context.project_id or 'Local'}")
    if active_context.console_trace_url:
        print(f"   Google Cloud Trace Console: {active_context.console_trace_url}")
    print("   Open in your browser to view Agent State Machine, OTel Waterfall & Token Economics.\n")

    if blocking:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.server_close()
            print("Server stopped.")
    else:
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
    return server
