"""
Unit tests for Jev Decision & Routing Engine in GoogleOpenAgentOps.
"""

import unittest
from google_openagentops.jev import evaluate_task, route_model, JevDecisionEngine


class TestJevDecisionEngine(unittest.TestCase):
    def test_high_complexity_routes_to_gemini_38_flash(self):
        prompt = "Architect a distributed fault-tolerant multi-agent swarm pipeline on Cloud Run."
        res = evaluate_task(prompt)
        self.assertGreaterEqual(res["complexity_score"], 0.60)
        self.assertEqual(res["routed_model"], "gemini-3.8-flash")
        self.assertIn("roo-code", res["recommended_skills"])

    def test_low_complexity_routes_to_gemini_35_flash(self):
        prompt = "Fix the typo in this variable name."
        res = evaluate_task(prompt)
        self.assertLess(res["complexity_score"], 0.60)
        self.assertEqual(res["routed_model"], "gemini-3.5-flash")

    def test_voice_prompt_routes_to_live(self):
        prompt = "Stream real-time voice response to user audio."
        model = route_model(prompt)
        self.assertEqual(model, "gemini-3.8-live")

    def test_decision_latency_under_5ms(self):
        res = evaluate_task("Write a quick script")
        self.assertLess(res["decision_latency_ms"], 5.0)


if __name__ == "__main__":
    unittest.main()
