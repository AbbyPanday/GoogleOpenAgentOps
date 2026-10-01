"""Unit tests for OpenInference and OpenTelemetry Export Compliance."""
import unittest
from google_openagentops.tracker import tracker
from google_openagentops.exporters import export_openinference

class TestOpenTelemetryExport(unittest.TestCase):
    def test_export_openinference(self):
        sess_id = "test-export-sess"
        tracker.start_trace(sess_id, "Test Trace")
        span = tracker.start_span(sess_id, "ArchitectAgent", model="gemini-3.8-flash")
        tracker.end_span(span.span_id, output_data={"result": "OK"}, prompt_tokens=500, completion_tokens=100)

        export_data = export_openinference(sess_id)
        self.assertIsNotNone(export_data)
        self.assertIn("resourceSpans", export_data)
        self.assertIn("spans", export_data)
        self.assertIn("session", export_data)

        # Validate OTel format
        res_spans = export_data["resourceSpans"]
        self.assertGreater(len(res_spans), 0)
        scope_spans = res_spans[0]["scopeSpans"]
        self.assertGreater(len(scope_spans), 0)
        otel_span = scope_spans[0]["spans"][0]
        self.assertEqual(otel_span["name"], "ArchitectAgent")

        # Verify OpenInference attributes
        attr_map = {a["key"]: a["value"] for a in otel_span["attributes"]}
        self.assertEqual(attr_map["openinference.span.kind"], "AGENT")
        self.assertEqual(attr_map["llm.model_name"], "gemini-3.8-flash")

if __name__ == "__main__":
    unittest.main()
