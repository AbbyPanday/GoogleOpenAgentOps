"""
Unit tests for Google Cloud Platform Environment Auto-Adaptation Engine.
"""

import os
import unittest
from google_openagentops.context import (
    auto_discover_gcp_context,
    detect_gcp_project_id,
    detect_gcp_runtime,
    detect_api_keys
)


class TestGCPContext(unittest.TestCase):
    def test_local_runtime_detection(self):
        runtime = detect_gcp_runtime()
        self.assertIn(runtime, ["Local / Workstation", "Google Cloud Run", "Google Kubernetes Engine (GKE)", "Google Compute Engine (GCE)"])

    def test_project_id_environment_cascade(self):
        os.environ["GOOGLE_CLOUD_PROJECT"] = "test-cascade-project-456"
        proj = detect_gcp_project_id()
        self.assertEqual(proj, "test-cascade-project-456")
        del os.environ["GOOGLE_CLOUD_PROJECT"]

    def test_api_key_detection_and_sync(self):
        os.environ["GEMINI_API_KEY"] = "test-gemini-key-abc"
        if "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]

        has_key, src = detect_api_keys()
        self.assertTrue(has_key)
        self.assertEqual(src, "GEMINI_API_KEY")
        # Verify sync into GOOGLE_API_KEY
        self.assertEqual(os.environ.get("GOOGLE_API_KEY"), "test-gemini-key-abc")

        del os.environ["GEMINI_API_KEY"]
        del os.environ["GOOGLE_API_KEY"]

    def test_console_urls_generated_when_project_present(self):
        ctx = auto_discover_gcp_context(explicit_project="my-awesome-gcp-project")
        self.assertEqual(ctx.project_id, "my-awesome-gcp-project")
        self.assertIn("https://console.cloud.google.com/traces/traces?project=my-awesome-gcp-project", ctx.console_trace_url)
        self.assertIn("https://console.cloud.google.com/monitoring/metrics-explorer?project=my-awesome-gcp-project", ctx.console_monitoring_url)
        self.assertIn("https://console.cloud.google.com/logs/query", ctx.console_logging_url)


if __name__ == "__main__":
    unittest.main()
