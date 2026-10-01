"""Unit tests for OpenAgentOps Tracker, State Machine, and Session Stitching."""
import unittest
from google_openagentops.tracker import OpenAgentOpsTracker
from google_openagentops.models import SpanKind, AgentState

class TestOpenAgentOpsTracker(unittest.TestCase):
    def setUp(self):
        self.tracker = OpenAgentOpsTracker()

    def test_session_creation(self):
        sess = self.tracker.get_or_create_session("sess-001", {"track": "developer_tools"})
        self.assertEqual(sess.session_id, "sess-001")
        self.assertEqual(sess.status, "ACTIVE")
        self.assertEqual(sess.metadata["track"], "developer_tools")

    def test_trace_lifecycle(self):
        trace = self.tracker.start_trace("sess-002", "Root Trajectory")
        self.assertEqual(trace.session_id, "sess-002")
        self.assertEqual(trace.status, "RUNNING")
        
        ended = self.tracker.end_trace(trace.trace_id, "OK")
        self.assertIsNotNone(ended)
        self.assertEqual(ended.status, "OK")
        self.assertGreaterEqual(ended.duration_ms, 0)

    def test_span_and_thought_recording(self):
        span = self.tracker.start_span("sess-003", name="ThemeAgent", agent_name="ThemeAgent", model="gemini-3.8-flash")
        self.assertEqual(span.agent_name, "ThemeAgent")
        
        self.tracker.record_thought("sess-003", span.span_id, "Evaluating CI/CD pipeline bottlenecks...")
        sess = self.tracker.get_session("sess-003")
        self.assertEqual(sess.metrics.thought_loops_count, 1)

        ended_span = self.tracker.end_span(span.span_id, output_data={"theme": "developer_tools"})
        self.assertIsNotNone(ended_span)
        self.assertEqual(ended_span.status, "OK")
        self.assertGreater(ended_span.metrics.total_cost_usd, 0)

    def test_handoff_recording(self):
        h = self.tracker.record_handoff("sess-004", "AgentA", "AgentB", "Forwarding context", {"key": "val"})
        self.assertEqual(h.from_agent, "AgentA")
        self.assertEqual(h.to_agent, "AgentB")
        sess = self.tracker.get_session("sess-004")
        self.assertEqual(len(sess.handoffs), 1)
        self.assertEqual(sess.current_agent, "AgentB")

if __name__ == "__main__":
    unittest.main()
