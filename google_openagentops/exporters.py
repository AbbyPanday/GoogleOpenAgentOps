"""
Standard OpenTelemetry & OpenInference Export Module.
Generates compliant OTel JSON protobuf wire representations.
"""

from typing import Any, Dict, Optional
from google_openagentops.tracker import tracker
from google_openagentops.context import active_context


def export_openinference(session_id: str) -> Optional[Dict[str, Any]]:
    """Export session trace bundle conforming to OpenInference and OpenTelemetry JSON specification."""
    session = tracker.get_session(session_id)
    if not session:
        return None

    raw_spans = []
    for s in session.spans:
        raw_spans.append({
            "traceId": s.trace_id,
            "spanId": s.span_id,
            "parentSpanId": s.parent_span_id,
            "name": s.name,
            "kind": s.span_kind,
            "startTimeUnixNano": int(s.start_time * 1_000_000_000),
            "endTimeUnixNano": int((s.end_time or s.start_time) * 1_000_000_000),
            "durationMs": s.duration_ms,
            "status": {
                "code": 1 if s.status == "OK" else 2,
                "message": s.error or ""
            },
            "attributes": {
                **s.attributes,
                "openinference.span.kind": s.span_kind,
                "session.id": session_id,
                "agent.name": s.agent_name or "",
                "agent.role": s.agent_role or "",
                "llm.model_name": s.model,
                "thought.value": s.thought or "",
                "llm.token_count.prompt": s.metrics.prompt_tokens,
                "llm.token_count.completion": s.metrics.completion_tokens,
                "llm.token_count.total": s.metrics.total_tokens,
                "llm.cost.total_usd": s.metrics.total_cost_usd,
                "gcp.project_id": active_context.project_id or "",
                "gcp.runtime": active_context.runtime_type
            }
        })

    resource_spans = [{
        "resource": {
            "attributes": [
                {"key": "service.name", "value": {"stringValue": "google-openagentops"}},
                {"key": "telemetry.sdk.name", "value": {"stringValue": "google_openagentops"}},
                {"key": "telemetry.sdk.language", "value": {"stringValue": "python"}},
                {"key": "cloud.provider", "value": {"stringValue": "gcp"}},
                {"key": "cloud.platform", "value": {"stringValue": active_context.runtime_type}},
            ]
        },
        "scopeSpans": [{
            "scope": {"name": "openinference.instrumentation.gemini"},
            "spans": [
                {
                    "traceId": sp["traceId"],
                    "spanId": sp["spanId"],
                    "name": sp["name"],
                    "kind": sp["kind"],
                    "attributes": [
                        {"key": "openinference.span.kind", "value": sp["kind"]},
                        {"key": "llm.model_name", "value": sp["attributes"]["llm.model_name"]},
                        {"key": "thought.value", "value": sp["attributes"]["thought.value"]},
                    ]
                }
                for sp in raw_spans
            ]
        }]
    }]

    return {
        "resource": {
            "attributes": {
                "service.name": "google-openagentops",
                "telemetry.sdk.name": "google_openagentops",
                "telemetry.sdk.language": "python",
                "gcp.project_id": active_context.project_id,
                "gcp.runtime": active_context.runtime_type,
            }
        },
        "session": {
            "sessionId": session.session_id,
            "sessionName": session.session_name,
            "metrics": session.metrics.to_dict(),
            "gcpContext": active_context.to_dict(),
        },
        "spans": raw_spans,
        "stateTransitions": [st.to_dict() for st in session.state_transitions],
        "handoffs": [h.to_dict() for h in session.handoffs],
        "resourceSpans": resource_spans
    }
