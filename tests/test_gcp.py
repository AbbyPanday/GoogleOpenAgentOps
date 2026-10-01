"""
Unit tests for Google Cloud Platform Observability Integration in OpenAgentOps.
"""

import io
import json
import logging
import os
import unittest

from google_openagentops.tracker import tracker
from google_openagentops.gcp import (
    get_gcp_project_id,
    format_gcp_trace_id,
    format_gcp_span_id,
    GCPCloudTraceExporter,
    GCPCloudMonitoringExporter,
    GCPCloudLoggingHandler,
    configure_gcp_observability
)


import uuid

class TestGCPObservability(unittest.TestCase):
    def setUp(self):
        self.sess_id = f"test-gcp-sess-{uuid.uuid4().hex[:6]}"
        self.project_id = "test-gcp-project-123"

    def test_project_id_resolution(self):
        self.assertEqual(get_gcp_project_id("explicit-proj"), "explicit-proj")
        os.environ["GOOGLE_CLOUD_PROJECT"] = "env-proj-789"
        self.assertEqual(get_gcp_project_id(), "env-proj-789")
        del os.environ["GOOGLE_CLOUD_PROJECT"]

    def test_trace_and_span_hex_formatting(self):
        raw_trace = "trace-1790865315-abcdef012345"
        formatted_trace = format_gcp_trace_id(raw_trace)
        self.assertEqual(len(formatted_trace), 32)
        # Should be valid hex
        int(formatted_trace, 16)

        raw_span = "span-1790865-994bae"
        formatted_span = format_gcp_span_id(raw_span)
        self.assertEqual(len(formatted_span), 16)
        int(formatted_span, 16)

    def test_cloud_trace_span_structure(self):
        exporter = GCPCloudTraceExporter(project_id=self.project_id)
        tracker.start_trace(self.sess_id, "GCP Cloud Trace Test")
        span = tracker.start_span(self.sess_id, "GeminiAgent", model="gemini-3.8-flash")
        tracker.end_span(span.span_id, output_data={"status": "OK"}, thought="Evaluating infra", prompt_tokens=100, completion_tokens=50)

        spans = exporter.build_trace_spans(self.sess_id)
        self.assertGreater(len(spans), 0)
        s0 = spans[0]
        self.assertTrue(s0["name"].startswith(f"projects/{self.project_id}/traces/"))
        self.assertIn("/spans/", s0["name"])
        self.assertIn("attribute_map", s0["attributes"])
        attr_map = s0["attributes"]["attribute_map"]
        self.assertEqual(attr_map["/agentops/model"]["string_value"]["value"], "gemini-3.8-flash")
        self.assertEqual(attr_map["/agentops/tokens/total"]["int_value"], 150)

    def test_cloud_monitoring_time_series(self):
        exporter = GCPCloudMonitoringExporter(project_id=self.project_id)
        tracker.start_trace(self.sess_id, "GCP Monitoring Test")
        span = tracker.start_span(self.sess_id, "MonitorAgent", model="gemini-3.5-flash")
        tracker.end_span(span.span_id, prompt_tokens=200, completion_tokens=80)

        series = exporter.build_time_series(self.sess_id)
        self.assertGreater(len(series), 0)
        metric_types = [s["metric"]["type"] for s in series]
        self.assertIn("custom.googleapis.com/agentops/tokens", metric_types)
        self.assertIn("custom.googleapis.com/agentops/cost_usd", metric_types)
        self.assertIn("custom.googleapis.com/agentops/latency_ms", metric_types)

    def test_cloud_logging_structured_json_with_trace_context(self):
        stream = io.StringIO()
        handler = GCPCloudLoggingHandler(project_id=self.project_id, stream=stream)

        rec = logging.LogRecord(
            name="google_openagentops.gcp",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Agent completed task successfully",
            args=(),
            exc_info=None
        )
        rec.trace_id = "trace-1234567890abcdef"
        rec.span_id = "span-abcdef0123"
        rec.agent_name = "GeminiAgent"
        rec.model = "gemini-3.8-flash"
        rec.cost_usd = 0.00045

        handler.emit(rec)
        output = stream.getvalue().strip()
        data = json.loads(output)

        self.assertEqual(data["message"], "Agent completed task successfully")
        self.assertEqual(data["severity"], "INFO")
        self.assertTrue(data["logging.googleapis.com/trace"].startswith(f"projects/{self.project_id}/traces/"))
        self.assertTrue(data["logging.googleapis.com/trace_sampled"])
        self.assertIn("logging.googleapis.com/spanId", data)
        self.assertEqual(data["agent_name"], "GeminiAgent")

    def test_configure_gcp_observability(self):
        obs = configure_gcp_observability(project_id=self.project_id)
        self.assertIsNotNone(obs)
        self.assertEqual(obs.project_id, self.project_id)


if __name__ == "__main__":
    unittest.main()
