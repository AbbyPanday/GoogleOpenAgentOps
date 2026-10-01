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
                            trace_id=data.get("trace_id", "trace-1"),
                            session_id=sid,
                            name=data.get("name", "agent"),
                            span_kind=data.get("span_kind", "AGENT"),
                            agent_name=data.get("agent_name"),
                            model=data.get("model", "gemini-3.8-flash"),
                            status=data.get("status", "OK"),
                            duration_ms=data.get("duration_ms", 0),
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
