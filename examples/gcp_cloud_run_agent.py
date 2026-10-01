"""
Production Google Cloud Run Agent Deployment with GoogleOpenAgentOps.
Auto-adapts to Cloud Run environment, Google Cloud Project ID, and Cloud Trace.
"""

import os
import GoogleOpenAgentOps as agentops

# Initialize and auto-detect Google Cloud Project & API Keys
agentops.init(
    project_id=os.getenv("GOOGLE_CLOUD_PROJECT", "hackathon-gcp-prod"),
    auto_gcp_observability=True,
    print_banner=True
)

SESSION_ID = "cloud-run-demo-01"

@agentops.track_agent(name="CloudResourceOptimizerAgent", model="gemini-3.8-flash")
def optimize_cloud_resources(service_tier: str, session_id: str):
    thought = (
        "1. Query Google Cloud Monitoring CPU & Memory utilization metrics.\n"
        "2. Identify over-provisioned Cloud Run instances.\n"
        "3. Adjust concurrency and memory to minimize Google Cloud invoice."
    )
    return {
        "target_service": "payments-api",
        "recommended_memory": "512Mi",
        "monthly_savings_usd": 420.00,
        "_thought": thought
    }

@agentops.track_tool(name="apply_cloud_run_patch")
def apply_cloud_run_patch(service_name: str, memory: str, session_id: str = "", span_id: str = ""):
    return {"status": "PATCH_APPLIED", "service": service_name, "memory": memory}

if __name__ == "__main__":
    print("Running Google Cloud Agent with auto-adapted GCP Observability...")
    with agentops.start_trace(SESSION_ID, "Cloud Run Workload Optimization"):
        result = optimize_cloud_resources("enterprise", session_id=SESSION_ID)
        tool_res = apply_cloud_run_patch("payments-api", "512Mi", session_id=SESSION_ID)

    print("Workflow complete. Spans tracked with Cloud Trace correlation.")
