"""
GoogleOpenAgentOps: Google Cloud Native & Self-Hosted Observability SDK for AI Agents.
Auto-adapts to Google Cloud Console, Cloud Trace, Cloud Monitoring, Cloud Logging,
Application Default Credentials (ADC), and active Google Gemini 3.x production models.
"""

from google_openagentops.context import (
    GCPEnvironmentContext,
    auto_discover_gcp_context,
    detect_gcp_project_id,
    detect_gcp_runtime,
    detect_api_keys,
    active_context
)
from google_openagentops.models import (
    SpanKind,
    AgentState,
    Span,
    Trace,
    Session,
    Handoff,
    StateTransition,
    TokenMetrics,
    ToolCallRecord,
    ReplayEvent,
    CiCdEvent
)
from google_openagentops.pricing import (
    MODEL_PRICING,
    calculate_token_cost,
    estimate_token_count
)
from google_openagentops.tracker import GoogleOpenAgentOpsTracker, tracker
from google_openagentops.decorators import (
    session,
    agent,
    operation,
    tool,
    workflow,
    guardrail,
    session_scope,
    track_agent,
    track_tool,
    start_trace,
    start_span
)
from google_openagentops.integrations.adk import (
    GoogleADKTracker,
    track_adk_agent
)
from google_openagentops.deploy import (
    deploy_to_cloud_run,
    get_ssh_setup_command
)
from google_openagentops.gcp import (
    configure_gcp_observability,
    GCPCloudTraceExporter,
    GCPCloudMonitoringExporter,
    GCPCloudLoggingHandler
)
from google_openagentops.exporters import export_openinference
from google_openagentops.server import launch_dashboard
from google_openagentops.jev import evaluate_task, route_model, JevDecisionEngine


def init(
    project_id: str = None,
    api_key: str = None,
    auto_gcp_observability: bool = True,
    session_id: str = None,
    metadata: dict = None,
    print_banner: bool = False
):
    """
    Primary entrypoint to initialize GoogleOpenAgentOps.
    - Auto-adapts to Google Cloud Console runtime (Cloud Run, GKE, Vertex AI, GCE).
    - Resolves active Gemini API keys (GEMINI_API_KEY, GOOGLE_API_KEY).
    - Configures Cloud Trace, Monitoring, and Logging.
    """
    import os
    if api_key:
        os.environ["GEMINI_API_KEY"] = api_key.strip()
        os.environ["GOOGLE_API_KEY"] = api_key.strip()

    ctx = auto_discover_gcp_context(explicit_project=project_id, print_banner=print_banner)
    sess = tracker.get_or_create_session(session_id, metadata)

    if auto_gcp_observability and (ctx.project_id or ctx.is_gcp):
        configure_gcp_observability(project_id=ctx.project_id)

    return sess


__version__ = "1.0.0"
__all__ = [
    "init",
    "GoogleOpenAgentOpsTracker",
    "tracker",
    "active_context",
    "GCPEnvironmentContext",
    "auto_discover_gcp_context",
    "detect_gcp_project_id",
    "detect_gcp_runtime",
    "detect_api_keys",
    "SpanKind",
    "AgentState",
    "Span",
    "Trace",
    "Session",
    "Handoff",
    "StateTransition",
    "TokenMetrics",
    "ToolCallRecord",
    "ReplayEvent",
    "CiCdEvent",
    "MODEL_PRICING",
    "calculate_token_cost",
    "estimate_token_count",
    "session",
    "agent",
    "operation",
    "tool",
    "workflow",
    "guardrail",
    "session_scope",
    "track_agent",
    "track_tool",
    "start_trace",
    "start_span",
    "GoogleADKTracker",
    "track_adk_agent",
    "deploy_to_cloud_run",
    "get_ssh_setup_command",
    "configure_gcp_observability",
    "GCPCloudTraceExporter",
    "GCPCloudMonitoringExporter",
    "GCPCloudLoggingHandler",
    "export_openinference",
    "launch_dashboard",
    "evaluate_task",
    "route_model",
    "JevDecisionEngine",
]
