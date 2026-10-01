"""
Multi-Agent Swarm with Sequential Handoffs and Tool Calls.
"""

import time
import google_openagentops

SESSION_ID = "hackathon-swarm-001"

@google_openagentops.track_tool(name="GcpCatalogTool")
def query_gcp_catalog(service_type: str, session_id: str, span_id: str):
    return {"compute": "Cloud Run", "database": "Firestore", "ai": "Gemini 3.8 Flash"}

def run_swarm():
    # Start trace
    with google_openagentops.start_trace(session_id=SESSION_ID, name="Hackathon Idea Director Swarm"):
        # 1. Theme Agent
        span1 = google_openagentops.tracker.start_span(SESSION_ID, name="ThemeDomainAgent", model="gemini-3.5-flash")
        google_openagentops.tracker.record_thought(SESSION_ID, span1.span_id, "Selected developer tools vertical.")
        google_openagentops.tracker.end_span(span1.span_id, output_data={"theme": "developer_tools"})

        # Handoff 1
        google_openagentops.tracker.record_handoff(SESSION_ID, "ThemeDomainAgent", "CorporatePainPointAgent", "Delegating vertical")

        # 2. Pain Point Agent
        span2 = google_openagentops.tracker.start_span(SESSION_ID, name="CorporatePainPointAgent", model="gemini-3.5-flash")
        google_openagentops.tracker.end_span(span2.span_id, output_data={"pain_point": "CI/CD Flaky Test Storms", "roi": "$180,000/yr"})

        # Handoff 2
        google_openagentops.tracker.record_handoff(SESSION_ID, "CorporatePainPointAgent", "SolutionArchitectAgent", "Architecting swarm")

        # 3. Architect Agent + Tool Call
        span3 = google_openagentops.tracker.start_span(SESSION_ID, name="SolutionArchitectAgent", model="gemini-3.8-flash")
        query_gcp_catalog("serverless", session_id=SESSION_ID, span_id=span3.span_id)
        google_openagentops.tracker.record_thought(SESSION_ID, span3.span_id, "Cloud Run selected for low-latency auto-healing container sandboxes.")
        google_openagentops.tracker.end_span(span3.span_id, output_data={"solution": "HealCode Auto-Medic", "services": ["Cloud Run", "Gemini 3.8 Flash"]})

if __name__ == "__main__":
    print("Executing Multi-Agent Swarm...")
    run_swarm()
    print("Swarm executed successfully. Spans, Handoffs, and State Transitions tracked.")
    import sys
    if "--serve" in sys.argv:
        google_openagentops.launch_dashboard(port=8000, blocking=True)
    else:
        srv = google_openagentops.launch_dashboard(port=8000, blocking=False)
        print("Open http://localhost:8000 to view dashboard or run with --serve.")
        srv.server_close()
