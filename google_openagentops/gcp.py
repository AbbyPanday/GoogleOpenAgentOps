"""
Google Cloud Platform (GCP) Native Observability Module for GoogleOpenAgentOps.
Provides first-class integration with:
- Google Cloud Trace (Cloud Trace v2 API / OpenTelemetry GCP Exporter)
- Google Cloud Monitoring (Cloud Monitoring v3 API / Custom Metrics)
- Google Cloud Logging (Structured JSON Logging with Trace Context linking)
- Google Cloud Console deep-link navigation
"""

import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional
import uuid

from google_openagentops.models import Span, Trace, Session
from google_openagentops.tracker import tracker
from google_openagentops.context import active_context, detect_gcp_project_id


def format_gcp_trace_id(raw_trace_id: str) -> str:
    """Format an OpenAgentOps trace ID into a 32-character hex string for Google Cloud Trace."""
    clean = "".join(c for c in raw_trace_id if c in "0123456789abcdefABCDEF")
    if len(clean) >= 32:
        return clean[:32].lower()
    padded = (clean + uuid.uuid4().hex)[:32].lower()
    return padded


def format_gcp_span_id(raw_span_id: str) -> str:
    """Format an OpenAgentOps span ID into a 16-character hex string for Google Cloud Trace."""
    clean = "".join(c for c in raw_span_id if c in "0123456789abcdefABCDEF")
    if len(clean) >= 16:
        return clean[:16].lower()
    padded = (clean + uuid.uuid4().hex)[:16].lower()
    return padded


get_gcp_project_id = detect_gcp_project_id


class GCPCloudTraceExporter:
    """
    Exports agent execution spans to Google Cloud Trace v2.
    Conforms to projects/{project_id}/traces/{trace_id}/spans/{span_id} schema.
    """

    def __init__(self, project_id: Optional[str] = None):
        self.project_id = detect_gcp_project_id(project_id) or active_context.project_id or "default-gcp-project"
        self._client = None
        self._init_client()

    def _init_client(self):
        try:
            from google.cloud import trace_v2
            self._client = trace_v2.TraceServiceClient()
        except Exception:
            self._client = None

    @property
    def has_native_sdk(self) -> bool:
        return self._client is not None

    def build_trace_spans(self, session_id: str) -> List[Dict[str, Any]]:
        """Construct Google Cloud Trace v2 span payloads from session spans."""
        session = tracker.get_session(session_id)
        if not session:
            return []

        gcp_spans = []
        for s in session.spans:
            hex_trace = format_gcp_trace_id(s.trace_id)
            hex_span = format_gcp_span_id(s.span_id)
            parent_hex = format_gcp_span_id(s.parent_span_id) if s.parent_span_id else None

            start_s = int(s.start_time)
            start_nano = int((s.start_time - start_s) * 1_000_000_000)
            end_time = s.end_time or s.start_time
            end_s = int(end_time)
            end_nano = int((end_time - end_s) * 1_000_000_000)

            attributes = {
                "/agentops/agent_name": {"string_value": {"value": s.agent_name or s.name}},
                "/agentops/agent_role": {"string_value": {"value": s.agent_role or ""}},
                "/agentops/model": {"string_value": {"value": s.model}},
                "/agentops/span_kind": {"string_value": {"value": s.span_kind}},
                "/agentops/tokens/prompt": {"int_value": s.metrics.prompt_tokens},
                "/agentops/tokens/completion": {"int_value": s.metrics.completion_tokens},
                "/agentops/tokens/total": {"int_value": s.metrics.total_tokens},
                "/agentops/cost_usd": {"string_value": {"value": f"{s.metrics.total_cost_usd:.6f}"}},
            }

            if s.thought:
                attributes["/agentops/thought"] = {"string_value": {"value": s.thought[:1024]}}
            if s.error:
                attributes["/agentops/error"] = {"string_value": {"value": str(s.error)[:1024]}}

            span_dict = {
                "name": f"projects/{self.project_id}/traces/{hex_trace}/spans/{hex_span}",
                "span_id": hex_span,
                "parent_span_id": parent_hex,
                "display_name": {"value": f"{s.name} ({s.span_kind})", "truncated_byte_count": 0},
                "start_time": {"seconds": start_s, "nanos": start_nano},
                "end_time": {"seconds": end_s, "nanos": end_nano},
                "attributes": {"attribute_map": attributes},
                "status": {"code": 0 if s.status == "OK" else 2, "message": s.error or "OK"}
            }
            gcp_spans.append(span_dict)
        return gcp_spans

    def export_session(self, session_id: str) -> Dict[str, Any]:
        """Export session spans to Cloud Trace."""
        spans = self.build_trace_spans(session_id)
        if not spans:
            return {"exported": 0, "status": "NO_SPANS"}

        if self._client:
            try:
                from google.cloud import trace_v2
                batch_spans = []
                for s in spans:
                    span_obj = trace_v2.Span(
                        name=s["name"],
                        span_id=s["span_id"],
                        parent_span_id=s.get("parent_span_id"),
                        display_name=trace_v2.TruncatableString(value=s["display_name"]["value"]),
                        status=trace_v2.Status(code=s["status"]["code"], message=s["status"]["message"])
                    )
                    batch_spans.append(span_obj)

                self._client.batch_write_spans(
                    name=f"projects/{self.project_id}",
                    spans=batch_spans
                )
                return {"exported": len(spans), "status": "PUBLISHED_VIA_SDK", "project": self.project_id}
            except Exception as e:
                return {"exported": len(spans), "status": "SDK_ERROR", "error": str(e), "spans": spans}

        return {"exported": len(spans), "status": "FORMATTED_GCP_TRACE", "project": self.project_id, "spans": spans}


class GCPCloudMonitoringExporter:
    """
    Exports agent metrics directly into Google Cloud Monitoring (Stackdriver).
    Custom metric descriptors:
    - custom.googleapis.com/agentops/tokens
    - custom.googleapis.com/agentops/cost_usd
    - custom.googleapis.com/agentops/latency_ms
    - custom.googleapis.com/agentops/agent_runs
    """

    def __init__(self, project_id: Optional[str] = None):
        self.project_id = detect_gcp_project_id(project_id) or active_context.project_id or "default-gcp-project"
        self._client = None
        self._init_client()

    def _init_client(self):
        try:
            from google.cloud import monitoring_v3
            self._client = monitoring_v3.MetricServiceClient()
        except Exception:
            self._client = None

    @property
    def has_native_sdk(self) -> bool:
        return self._client is not None

    def build_time_series(self, session_id: str) -> List[Dict[str, Any]]:
        """Build Google Cloud Monitoring TimeSeries descriptors for session metrics."""
        session = tracker.get_session(session_id)
        if not session:
            return []

        now_s = int(time.time())
        m = session.metrics
        time_series = [
            {
                "metric": {
                    "type": "custom.googleapis.com/agentops/tokens",
                    "labels": {"session_id": session_id, "project": self.project_id}
                },
                "resource": {
                    "type": "global",
                    "labels": {"project_id": self.project_id}
                },
                "points": [{
                    "interval": {"end_time": {"seconds": now_s}},
                    "value": {"int64_value": m.total_tokens}
                }]
            },
            {
                "metric": {
                    "type": "custom.googleapis.com/agentops/cost_usd",
                    "labels": {"session_id": session_id, "project": self.project_id}
                },
                "resource": {
                    "type": "global",
                    "labels": {"project_id": self.project_id}
                },
                "points": [{
                    "interval": {"end_time": {"seconds": now_s}},
                    "value": {"double_value": float(m.total_cost_usd)}
                }]
            },
            {
                "metric": {
                    "type": "custom.googleapis.com/agentops/latency_ms",
                    "labels": {"session_id": session_id, "project": self.project_id}
                },
                "resource": {
                    "type": "global",
                    "labels": {"project_id": self.project_id}
                },
                "points": [{
                    "interval": {"end_time": {"seconds": now_s}},
                    "value": {"int64_value": m.avg_latency_ms}
                }]
            },
            {
                "metric": {
                    "type": "custom.googleapis.com/agentops/agent_runs",
                    "labels": {"session_id": session_id, "project": self.project_id}
                },
                "resource": {
                    "type": "global",
                    "labels": {"project_id": self.project_id}
                },
                "points": [{
                    "interval": {"end_time": {"seconds": now_s}},
                    "value": {"int64_value": m.agent_runs_count}
                }]
            }
        ]
        return time_series

    def export_metrics(self, session_id: str) -> Dict[str, Any]:
        """Send TimeSeries data points to Google Cloud Monitoring."""
        series = self.build_time_series(session_id)
        if not series:
            return {"exported": 0, "status": "NO_METRICS"}

        if self._client:
            try:
                from google.cloud import monitoring_v3
                gcp_series = []
                for s in series:
                    point = monitoring_v3.Point()
                    point.interval.end_time.seconds = s["points"][0]["interval"]["end_time"]["seconds"]
                    if "int64_value" in s["points"][0]["value"]:
                        point.value.int64_value = s["points"][0]["value"]["int64_value"]
                    else:
                        point.value.double_value = s["points"][0]["value"]["double_value"]

                    ts = monitoring_v3.TimeSeries()
                    ts.metric.type = s["metric"]["type"]
                    for k, v in s["metric"]["labels"].items():
                        ts.metric.labels[k] = v
                    ts.resource.type = s["resource"]["type"]
                    for k, v in s["resource"]["labels"].items():
                        ts.resource.labels[k] = v
                    ts.points.append(point)
                    gcp_series.append(ts)

                self._client.create_time_series(
                    name=f"projects/{self.project_id}",
                    time_series=gcp_series
                )
                return {"exported": len(gcp_series), "status": "PUBLISHED_VIA_SDK", "project": self.project_id}
            except Exception as e:
                return {"exported": len(series), "status": "SDK_ERROR", "error": str(e), "time_series": series}

        return {"exported": len(series), "status": "FORMATTED_GCP_MONITORING", "project": self.project_id, "time_series": series}


class GCPCloudLoggingHandler(logging.Handler):
    """
    Google Cloud Logging Structured JSON Handler.
    Emits log records formatted with:
    - logging.googleapis.com/trace
    - logging.googleapis.com/spanId
    - logging.googleapis.com/trace_sampled
    Enables one-click 'View Trace' navigation directly in Google Cloud Console.
    """

    def __init__(self, project_id: Optional[str] = None, stream=None):
        super().__init__()
        self.project_id = detect_gcp_project_id(project_id) or active_context.project_id or "default-gcp-project"
        self.stream = stream or sys.stdout

    def format_gcp_payload(self, record: logging.LogRecord) -> Dict[str, Any]:
        severity_map = {
            logging.DEBUG: "DEBUG",
            logging.INFO: "INFO",
            logging.WARNING: "WARNING",
            logging.ERROR: "ERROR",
            logging.CRITICAL: "CRITICAL",
        }
        severity = severity_map.get(record.levelno, "DEFAULT")

        trace_id = getattr(record, "trace_id", None)
        span_id = getattr(record, "span_id", None)

        payload: Dict[str, Any] = {
            "message": record.getMessage(),
            "severity": severity,
            "component": "google_openagentops",
            "timestamp": {"seconds": int(record.created), "nanos": int((record.created - int(record.created)) * 1_000_000_000)},
        }

        if trace_id:
            hex_trace = format_gcp_trace_id(trace_id)
            payload["logging.googleapis.com/trace"] = f"projects/{self.project_id}/traces/{hex_trace}"
            payload["logging.googleapis.com/trace_sampled"] = True

        if span_id:
            payload["logging.googleapis.com/spanId"] = format_gcp_span_id(span_id)

        for attr in ("agent_name", "agent_role", "model", "thought", "cost_usd", "total_tokens", "action"):
            if hasattr(record, attr):
                payload[attr] = getattr(record, attr)

        return payload

    def emit(self, record: logging.LogRecord):
        try:
            payload = self.format_gcp_payload(record)
            msg = json.dumps(payload)
            self.stream.write(msg + "\n")
            self.stream.flush()
        except Exception:
            self.handleError(record)


class GCPObservability:
    """Manages active GCP Cloud Trace, Cloud Monitoring, and Cloud Logging bindings."""

    def __init__(self, project_id: Optional[str] = None):
        self.project_id = detect_gcp_project_id(project_id) or active_context.project_id or "default-gcp-project"
        self.trace_exporter = GCPCloudTraceExporter(self.project_id)
        self.monitoring_exporter = GCPCloudMonitoringExporter(self.project_id)
        self.logger = logging.getLogger("google_openagentops.gcp")
        self._handler = GCPCloudLoggingHandler(self.project_id)
        self.logger.addHandler(self._handler)
        self.logger.setLevel(logging.INFO)
        self._attached = False

    def attach_to_tracker(self):
        """Subscribe to GoogleOpenAgentOps telemetry stream for continuous GCP synchronization."""
        if self._attached:
            return

        def _telemetry_listener(event: Dict[str, Any]):
            ev_type = event.get("type")
            data = event.get("data", {})
            session_id = data.get("sessionId")

            if ev_type == "SPAN_ENDED":
                rec = logging.LogRecord(
                    name="google_openagentops.gcp",
                    level=logging.INFO,
                    pathname="",
                    lineno=0,
                    msg=f"Span completed: {data.get('name')}",
                    args=(),
                    exc_info=None
                )
                rec.trace_id = data.get("traceId")
                rec.span_id = data.get("spanId")
                rec.agent_name = data.get("name")
                rec.cost_usd = data.get("costUsd")
                rec.total_tokens = data.get("totalTokens")
                self._handler.emit(rec)

            elif ev_type in ("TRACE_ENDED", "SESSION_CREATED"):
                if session_id:
                    self.trace_exporter.export_session(session_id)
                    self.monitoring_exporter.export_metrics(session_id)

        tracker.add_subscriber(_telemetry_listener)
        self._attached = True
        return self


_gcp_instance: Optional[GCPObservability] = None


def configure_gcp_observability(
    project_id: Optional[str] = None,
    sync_traces: bool = True,
    sync_metrics: bool = True,
    sync_logs: bool = True
) -> GCPObservability:
    """One-line configuration to bind GoogleOpenAgentOps with Google Cloud Platform."""
    global _gcp_instance
    _gcp_instance = GCPObservability(project_id)
    _gcp_instance.attach_to_tracker()
    return _gcp_instance
