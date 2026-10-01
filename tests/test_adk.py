"""
Unit tests for Google ADK (Agent Development Kit) Integration and Multi-Solution Linking.
"""

import unittest
from google_openagentops.integrations.adk import GoogleADKTracker, track_adk_agent
from google_openagentops.tracker import tracker
from google_openagentops.models import AgentState


class TestGoogleADKIntegration(unittest.TestCase):
    def setUp(self):
        tracker.sessions.clear()
        tracker.solutions.clear()
        tracker.active_traces.clear()

    def test_adk_tracker_registration(self):
        adk = GoogleADKTracker(
            solution_id="sol-cust-support",
            solution_name="CustomerSupportAgent",
            default_model="gemini-3.8-flash"
        )
        solutions = tracker.get_solutions()
        self.assertEqual(len(solutions), 1)
        self.assertEqual(solutions[0]["solution_id"], "sol-cust-support")
        self.assertEqual(solutions[0]["solution_name"], "CustomerSupportAgent")

    def test_multi_adk_solution_correlation(self):
        # Register Solution 1: Support Bot
        bot_support = GoogleADKTracker(solution_id="sol-support", solution_name="SupportBot")
        
        # Register Solution 2: Billing Bot
        bot_billing = GoogleADKTracker(solution_id="sol-billing", solution_name="BillingBot")

        self.assertEqual(len(tracker.get_solutions()), 2)

        # Execute Support Bot task
        @bot_support.track_agent(agent_name="TriageAgent")
        def run_triage(query: str):
            return {"status": "Escalated", "target": "BillingBot"}

        # Execute Billing Bot tool
        @bot_billing.track_tool(tool_name="VerifyInvoice")
        def verify_invoice(invoice_id: str):
            return {"invoice_id": invoice_id, "paid": True}

        res1 = run_triage("Check my bill #9928")
        self.assertEqual(res1["status"], "Escalated")

        res2 = verify_invoice("9928")
        self.assertEqual(res2["paid"], True)

        # Verify sessions and spans
        sessions = tracker.get_all_sessions()
        self.assertGreaterEqual(len(sessions), 1)
        active_sess = sessions[0]
        self.assertGreaterEqual(len(active_sess["spans"]), 1)
        self.assertGreaterEqual(len(active_sess["state_transitions"]), 1)

    def test_adk_handoff(self):
        adk_a = GoogleADKTracker(solution_name="FrontDesk")
        adk_a.start_session()
        adk_a.record_handoff(target_agent="SpecialistAgent", context={"priority": "high"})

        sess = tracker.get_session(tracker.get_active_session_id())
        self.assertEqual(len(sess.handoffs), 1)
        self.assertEqual(sess.handoffs[0].to_agent, "SpecialistAgent")


if __name__ == "__main__":
    unittest.main()
