"""Unit tests for Active Google Gemini 3.x models pricing and zero deprecated models."""
import unittest
from google_openagentops.pricing import MODEL_PRICING, calculate_token_cost, estimate_token_count

class TestOpenAgentOpsPricing(unittest.TestCase):
    def test_active_models_present(self):
        expected_models = [
            "gemini-3.8-flash",
            "gemini-3.8-live",
            "gemini-3.5-flash",
            "gemini-3-flash",
            "gemini-omni-1.1-flash",
            "gemini-3.1-flash-image",
            "gemini-3-pro-image"
        ]
        for m in expected_models:
            self.assertIn(m, MODEL_PRICING)
            self.assertGreater(MODEL_PRICING[m]["input_price_per_million"], 0)
            self.assertGreater(MODEL_PRICING[m]["output_price_per_million"], 0)

    def test_zero_deprecated_models(self):
        deprecated_models = [
            "gemini-1.0-pro", "gemini-pro", "text-bison", "chat-bison", "palm-2", "text-embedding-gecko"
        ]
        for dep in deprecated_models:
            self.assertNotIn(dep, MODEL_PRICING, f"Deprecated model {dep} must NEVER be present.")

    def test_calculate_token_cost_exactness(self):
        cost = calculate_token_cost("gemini-3.8-flash", 10_000, 2_000)
        # 10,000 * 0.15 / 1,000,000 = 0.0015
        # 2,000 * 0.60 / 1,000,000 = 0.0012
        # Total = 0.0027
        self.assertEqual(cost["prompt_cost_usd"], 0.0015)
        self.assertEqual(cost["completion_cost_usd"], 0.0012)
        self.assertEqual(cost["total_cost_usd"], 0.0027)

    def test_estimate_token_count(self):
        self.assertEqual(estimate_token_count(""), 0)
        toks = estimate_token_count("Google Gemini 3.8 Flash Agentic Orchestration")
        self.assertGreater(toks, 5)
        self.assertLess(toks, 30)

if __name__ == "__main__":
    unittest.main()
