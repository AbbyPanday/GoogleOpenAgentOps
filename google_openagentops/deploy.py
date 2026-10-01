"""
One-Click Google Cloud Run Auto-Deployer & GCP Environment Provisioner.
Automatically detects project credentials, builds and deploys GoogleOpenAgentOps to Cloud Run,
configures compute runtime parameters, and displays live Cloud Run dashboard URL.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from typing import Any, Dict, Optional

logger = logging.getLogger("google_openagentops.deploy")


def check_gcloud_installed() -> bool:
    """Verify that gcloud CLI is available on system PATH."""
    return shutil.which("gcloud") is not None or shutil.which("gcloud.cmd") is not None


def get_active_gcp_project() -> Optional[str]:
    """Retrieve currently active gcloud project."""
    cmd = ["gcloud", "config", "get-value", "project"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        proj = res.stdout.strip()
        return proj if proj and "(unset)" not in proj else None
    except Exception:
        return None


def ensure_gcp_apis_enabled(project_id: str):
    """Enable Cloud Run, Cloud Build, Cloud Trace, Logging, and Monitoring APIs."""
    print("[*] Enabling required Google Cloud APIs (Cloud Run, Cloud Build, Cloud Trace, Monitoring, Logging)...")
    apis = [
        "run.googleapis.com",
        "cloudbuild.googleapis.com",
        "cloudtrace.googleapis.com",
        "monitoring.googleapis.com",
        "logging.googleapis.com"
    ]
    cmd = ["gcloud", "services", "enable", *apis, "--project", project_id]
    try:
        subprocess.run(cmd, check=True)
        print("   [+] Google Cloud APIs successfully enabled.")
    except Exception as e:
        print(f"   [!] Note: API enable command returned: {e}. Continuing deployment...")


def deploy_to_cloud_run(
    project_id: Optional[str] = None,
    region: str = "us-central1",
    service_name: str = "google-openagentops-dashboard",
    port: int = 8000,
    cpu: str = "1",
    memory: str = "512Mi",
    allow_unauthenticated: bool = True,
    open_browser: bool = True
) -> Dict[str, Any]:
    """
    Automated Deployment of GoogleOpenAgentOps Dashboard to Google Cloud Run.
    Configures compute runtime specifications (CPU, RAM, Concurrency) and yields live HTTPS URL.
    """
    print("=" * 72)
    print(" GoogleOpenAgentOps - Automated Google Cloud Run Deployer")
    print("=" * 72)

    if not check_gcloud_installed():
        print("[!] ERROR: 'gcloud' CLI was not found on your system PATH.")
        print("    Please install the Google Cloud SDK: https://cloud.google.com/sdk/docs/install")
        print("    Or run the deployment script directly in Google Cloud Shell or via SSH.")
        return {"status": "ERROR", "message": "gcloud CLI not installed"}

    target_project = project_id or get_active_gcp_project() or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
    if not target_project:
        print("[!] No active GCP Project specified or configured.")
        print("    Run 'gcloud config set project <PROJECT_ID>' or pass --project <PROJECT_ID>")
        return {"status": "ERROR", "message": "No GCP project configured"}

    print(f"[*] Target GCP Project: {target_project}")
    print(f"[*] Deployment Region:  {region}")
    print(f"[*] Service Name:       {service_name}")
    print(f"[*] Compute Runtime:    {cpu} vCPU, {memory} Memory, Container Port {port}")

    # 1. Enable APIs
    ensure_gcp_apis_enabled(target_project)

    # 2. Source root
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # 3. Create Dockerfile if not exists
    dockerfile_path = os.path.join(repo_root, "Dockerfile")
    if not os.path.exists(dockerfile_path):
        print("[*] Generating production Dockerfile for Cloud Run...")
        lines = [
            "FROM python:3.11-slim",
            "WORKDIR /app",
            "COPY pyproject.toml setup.py README.md LICENSE ./",
            "COPY google_openagentops/ ./google_openagentops/",
            "COPY GoogleOpenAgentOps/ ./GoogleOpenAgentOps/",
            "RUN pip install --no-cache-dir .",
            f"ENV PORT={port}",
            "ENV PYTHONUNBUFFERED=1",
            f"EXPOSE {port}",
            f'CMD ["google-openagentops", "server", "--port", "{port}", "--host", "0.0.0.0"]'
        ]
        with open(dockerfile_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    # 4. Deploy to Cloud Run using gcloud run deploy
    print(f"[*] Deploying container to Cloud Run ({service_name})...")
    deploy_cmd = [
        "gcloud", "run", "deploy", service_name,
        "--source", repo_root,
        "--project", target_project,
        "--region", region,
        "--port", str(port),
        "--cpu", cpu,
        "--memory", memory,
        "--set-env-vars", f"GOOGLE_CLOUD_PROJECT={target_project},PORT={port}"
    ]
    if allow_unauthenticated:
        deploy_cmd.append("--allow-unauthenticated")

    try:
        proc = subprocess.run(deploy_cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] Deployment failed with exit code {e.returncode}")
        return {"status": "ERROR", "message": str(e)}

    # 5. Fetch live URL
    url_cmd = [
        "gcloud", "run", "services", "describe", service_name,
        "--project", target_project,
        "--region", region,
        "--format", "value(status.url)"
    ]
    try:
        url_res = subprocess.run(url_cmd, capture_output=True, text=True, check=True)
        service_url = url_res.stdout.strip()
    except Exception:
        service_url = f"https://{service_name}-{target_project}.{region}.run.app"

    print("\n" + "*" * 72)
    print(" [SUCCESS] GoogleOpenAgentOps Dashboard Deployed to Google Cloud Run!")
    print(f" Live Dashboard URL: {service_url}")
    print(f" GCP Trace Console:  https://console.cloud.google.com/traces/overview?project={target_project}")
    print(f" GCP Cloud Run Logs: https://console.cloud.google.com/run/detail/{region}/{service_name}/logs?project={target_project}")
    print("*" * 72 + "\n")

    if open_browser:
        try:
            webbrowser.open(service_url)
        except Exception:
            pass

    return {
        "status": "SUCCESS",
        "service_url": service_url,
        "project_id": target_project,
        "region": region,
        "service_name": service_name
    }


def get_ssh_setup_command(repo_url: str = "https://github.com/abhimanyu/GoogleOpenAgentOps.git") -> str:
    """Generate the one-line SSH/Cloud Shell command for users to deploy remotely."""
    return f"""ssh -t <YOUR_GCP_VM_OR_USER> 'bash -s' << 'EOF'
sudo apt-get update && sudo apt-get install -y git python3-pip
git clone {repo_url}
cd GoogleOpenAgentOps
pip install -e .
google-openagentops deploy
EOF"""
