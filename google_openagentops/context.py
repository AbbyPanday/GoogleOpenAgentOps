"""
Google Cloud Platform (GCP) Auto-Adaptation Engine.
Automatically detects and adapts to:
- GCP Runtime Environments (Cloud Run, GKE, Compute Engine, Cloud Functions, Vertex AI, Local)
- Google Cloud Project ID & Project Number
- Active Google / Gemini API Keys (GEMINI_API_KEY, GOOGLE_API_KEY)
- GCP Region / Zone & Service Account Credentials
- Google Cloud Console Deep Links (Cloud Trace, Cloud Monitoring, Cloud Logging)
"""

import json
import logging
import os
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("google_openagentops.context")


@dataclass
class GCPEnvironmentContext:
    """Encapsulates the detected Google Cloud Platform environment state."""
    is_gcp: bool = False
    runtime_type: str = "Local / Non-GCP"  # Cloud Run | GKE | GCE | Cloud Functions | Vertex AI | Local
    project_id: Optional[str] = None
    project_number: Optional[str] = None
    region: Optional[str] = None
    zone: Optional[str] = None
    service_account: Optional[str] = None
    api_key_configured: bool = False
    api_key_source: Optional[str] = None  # GEMINI_API_KEY | GOOGLE_API_KEY | Custom
    console_trace_url: Optional[str] = None
    console_monitoring_url: Optional[str] = None
    console_logging_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_gcp": self.is_gcp,
            "runtime_type": self.runtime_type,
            "project_id": self.project_id,
            "project_number": self.project_number,
            "region": self.region,
            "zone": self.zone,
            "service_account": self.service_account,
            "api_key_configured": self.api_key_configured,
            "api_key_source": self.api_key_source,
            "console_trace_url": self.console_trace_url,
            "console_monitoring_url": self.console_monitoring_url,
            "console_logging_url": self.console_logging_url,
            "metadata": self.metadata,
        }

    def print_diagnostic_banner(self):
        """Prints a friendly console diagnostic banner showing auto-adapted GCP context."""
        print("\n" + "=" * 70)
        print("  GoogleOpenAgentOps - Google Cloud Environment Context")
        print("=" * 70)
        print(f"  * Runtime Environment  : {self.runtime_type}")
        print(f"  * Google Cloud Project : {self.project_id or 'Not Configured (Running in Local Mode)'}")
        if self.region or self.zone:
            print(f"  * Region / Zone        : {self.region or self.zone}")
        if self.service_account:
            print(f"  * Service Account      : {self.service_account}")
        print(f"  * Gemini API Key       : {'[CONFIGURED via ' + str(self.api_key_source) + ']' if self.api_key_configured else '[NOT DETECTED]'}")
        if self.console_trace_url:
            print(f"  * Cloud Trace Console  : {self.console_trace_url}")
        if self.console_logging_url:
            print(f"  * Cloud Logging Console: {self.console_logging_url}")
        print("=" * 70 + "\n")


_METADATA_PROBED = False
_METADATA_AVAILABLE = False


def _is_metadata_available() -> bool:
    global _METADATA_PROBED, _METADATA_AVAILABLE
    if _METADATA_PROBED:
        return _METADATA_AVAILABLE
    _METADATA_PROBED = True
    import socket
    host = os.getenv("GCE_METADATA_HOST", "169.254.169.254")
    try:
        s = socket.create_connection((host, 80), timeout=0.04)
        s.close()
        _METADATA_AVAILABLE = True
    except Exception:
        _METADATA_AVAILABLE = False
    return _METADATA_AVAILABLE


def _query_metadata_server(path: str, timeout_seconds: float = 0.25) -> Optional[str]:
    """Safely query GCP Compute Metadata Server with cached reachability check."""
    if not _is_metadata_available():
        return None
    host = os.getenv("GCE_METADATA_HOST", "169.254.169.254")
    url = f"http://{host}/computeMetadata/v1/{path.lstrip('/')}"
    req = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            if resp.status == 200:
                val = resp.read().decode("utf-8").strip()
                return val if val else None
    except Exception:
        pass
    return None


def detect_gcp_runtime() -> str:
    """Detect the specific Google Cloud runtime environment."""
    if os.getenv("K_SERVICE") and os.getenv("K_REVISION"):
        return "Google Cloud Run"
    if os.getenv("FUNCTION_TARGET") or os.getenv("FUNCTION_SIGNATURE_TYPE"):
        return "Google Cloud Functions"
    if os.getenv("KUBERNETES_SERVICE_HOST"):
        return "Google Kubernetes Engine (GKE)"
    if os.getenv("AIP_PROJECT_NUMBER") or os.getenv("VERTEX_AI_EXPERIMENT"):
        return "Google Cloud Vertex AI"
    if os.getenv("GAE_INSTANCE") or os.getenv("GAE_SERVICE"):
        return "Google App Engine"

    # Fast check of metadata server
    host_type = _query_metadata_server("instance/machine-type")
    if host_type:
        return "Google Compute Engine (GCE)"

    return "Local / Workstation"


def detect_gcp_project_id(explicit_project: Optional[str] = None) -> Optional[str]:
    """
    Resolve Google Cloud Project ID with automatic priority cascading:
    1. Explicit parameter
    2. Environment variables: GOOGLE_CLOUD_PROJECT, GCP_PROJECT, GCLOUD_PROJECT, PROJECT_ID
    3. Google Compute Metadata Server (for Cloud Run / GKE / GCE)
    4. Google Auth Application Default Credentials (ADC)
    """
    if explicit_project:
        return explicit_project.strip()

    for env_var in ("GOOGLE_CLOUD_PROJECT", "GCP_PROJECT", "GCLOUD_PROJECT", "PROJECT_ID"):
        val = os.getenv(env_var)
        if val and val.strip():
            return val.strip()

    # Query metadata server
    meta_proj = _query_metadata_server("project/project-id")
    if meta_proj:
        return meta_proj

    # Check google.auth if installed
    try:
        import google.auth
        _, proj = google.auth.default()
        if proj:
            return proj
    except Exception:
        pass

    return None


def detect_api_keys() -> Tuple[bool, Optional[str]]:
    """
    Detect Google Gemini API keys in the environment.
    Supports GEMINI_API_KEY, GOOGLE_API_KEY, and syncs them across the runtime.
    """
    gemini_key = os.getenv("GEMINI_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY")

    if gemini_key and gemini_key.strip():
        if not google_key:
            os.environ["GOOGLE_API_KEY"] = gemini_key.strip()
        return True, "GEMINI_API_KEY"

    if google_key and google_key.strip():
        if not gemini_key:
            os.environ["GEMINI_API_KEY"] = google_key.strip()
        return True, "GOOGLE_API_KEY"

    return False, None


def auto_discover_gcp_context(
    explicit_project: Optional[str] = None,
    print_banner: bool = False
) -> GCPEnvironmentContext:
    """
    Auto-discovers and builds the complete Google Cloud Platform environment context.
    Adapts seamlessly between local workstation development and Google Cloud deployment.
    """
    runtime = detect_gcp_runtime()
    is_gcp = runtime != "Local / Workstation"
    project_id = detect_gcp_project_id(explicit_project)
    has_key, key_src = detect_api_keys()

    zone = os.getenv("GOOGLE_CLOUD_ZONE") or os.getenv("CLOUD_RUN_ZONE")
    region = os.getenv("GOOGLE_CLOUD_REGION") or os.getenv("CLOUD_RUN_REGION")
    project_number = os.getenv("AIP_PROJECT_NUMBER")
    service_account = None

    if is_gcp:
        if not zone:
            zone_raw = _query_metadata_server("instance/zone")
            if zone_raw:
                zone = zone_raw.split("/")[-1]
        if not project_number:
            project_number = _query_metadata_server("project/numeric-project-id")
        service_account = _query_metadata_server("instance/service-accounts/default/email")

    if zone and not region:
        parts = zone.split("-")
        if len(parts) >= 2:
            region = "-".join(parts[:-1])

    trace_url = None
    monitoring_url = None
    logging_url = None

    if project_id:
        trace_url = f"https://console.cloud.google.com/traces/traces?project={project_id}"
        monitoring_url = f"https://console.cloud.google.com/monitoring/metrics-explorer?project={project_id}"
        logging_url = f"https://console.cloud.google.com/logs/query;query=component%3D%22google_openagentops%22?project={project_id}"

    ctx = GCPEnvironmentContext(
        is_gcp=is_gcp,
        runtime_type=runtime,
        project_id=project_id,
        project_number=project_number,
        region=region,
        zone=zone,
        service_account=service_account,
        api_key_configured=has_key,
        api_key_source=key_src,
        console_trace_url=trace_url,
        console_monitoring_url=monitoring_url,
        console_logging_url=logging_url,
        metadata={
            "python_version": sys.version.split()[0],
            "pid": os.getpid(),
        }
    )

    if print_banner:
        ctx.print_diagnostic_banner()

    return ctx


active_context: GCPEnvironmentContext = auto_discover_gcp_context()
