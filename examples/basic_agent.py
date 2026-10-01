"""
Basic Google Gemini / Agentic script instrumented with OpenAgentOps.
"""

import time
import google_openagentops

SESSION_ID = "gemini-basic-001"

@google_openagentops.track_agent(name="IncidentTriagerAgent", model="gemini-3.8-flash")
def triage_production_incident(log_chunk: str, session_id: str):
    # Simulated Gemini 3.8 Flash inference with chain-of-thought
    thought = "1. Parse stack trace.\n2. Identify OOM in worker thread.\n3. Recommend heap increase."
    return {
        "root_cause": "OOM in payment-worker pod",
        "action": "Scale memory limit from 512Mi to 1Gi",
        "_thought": thought
    }

if __name__ == "__main__":
    print("Running basic agent with OpenAgentOps tracking...")
    with google_openagentops.start_trace(session_id=SESSION_ID, name="Production Triage"):
        res = triage_production_incident("Error 137: Pod killed due to OOM", session_id=SESSION_ID)
        print("Agent Output:", res)

    print("\nExporting OpenInference Trace:")
    import json
    print(json.dumps(google_openagentops.export_openinference(SESSION_ID), indent=2))
