"""
Gemini API Key Agent Deployment with GoogleOpenAgentOps.
Auto-detects and synchronizes GEMINI_API_KEY and GOOGLE_API_KEY.
"""

import os
import GoogleOpenAgentOps as agentops

# Simulate setting GEMINI_API_KEY if not already present
if not os.getenv("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = "AIzaSyFakeKeyForDemonstrationOnly12345"

# Auto-detects GEMINI_API_KEY
session = agentops.init(session_id="gemini-key-sess-01", print_banner=True)

@agentops.track_agent(name="GeminiSummarizerAgent", model="gemini-3.8-flash")
def summarize_document(text: str, session_id: str):
    return {
        "summary": "Document processed successfully with Gemini 3.8 Flash.",
        "_thought": "Extracting key executive bullets and action items."
    }

if __name__ == "__main__":
    with agentops.start_trace("gemini-key-sess-01", "Document Summarization"):
        res = summarize_document("Long enterprise RFP document...", session_id="gemini-key-sess-01")
        print("Summary result:", res["summary"])
