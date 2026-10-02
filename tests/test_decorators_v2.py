"""
Unit test suite for GoogleOpenAgentOps v2.0 AgentOps Parity Decorators,
Session Replay, CI/CD telemetry, and Guardrails.
"""

import asyncio
import unittest
from google_openagentops import (
    session,
    agent,
    operation,
    tool,
    workflow,
    guardrail,
    session_scope,
    tracker,
    SpanKind
)


class TestDecoratorsV2(unittest.TestCase):

    def setUp(self):
        tracker.sessions.clear()
        tracker.active_traces.clear()
        tracker.cicd_events.clear()

    def test_session_scope_context_manager(self):
        with session_scope(session_id="test-sess-1", session_name="Unit Test Session") as s:
            self.assertEqual(s.session_id, "test-sess-1")
            self.assertEqual(s.status, "ACTIVE")
        
        saved = tracker.get_session("test-sess-1")
        self.assertIsNotNone(saved)
        self.assertEqual(saved.status, "COMPLETED")

    def test_session_decorator(self):
        @session(session_id="dec-sess-1", session_name="Dec Session")
        def run_pipeline():
            return "ok"

        res = run_pipeline()
        self.assertEqual(res, "ok")
        saved = tracker.get_session("dec-sess-1")
        self.assertIsNotNone(saved)
        self.assertEqual(saved.status, "COMPLETED")

    def test_agent_decorator_function(self):
        @session(session_id="agent-sess-1")
        def main_flow():
            @agent(name="ResearchAgent", role="Web Researcher", model="gemini-3.8-flash")
            def do_research(query):
                return {
                    "summary": f"Findings for {query}",
                    "_thought": "Found 3 relevant scientific papers on arXiv."
                }
            return do_research("quantum computing")

        result = main_flow()
        self.assertIn("Findings for quantum computing", result["summary"])
        
        sess = tracker.get_session("agent-sess-1")
        self.assertEqual(len(sess.spans), 1)
        span = sess.spans[0]
        self.assertEqual(span.name, "ResearchAgent")
        self.assertEqual(span.agent_name, "ResearchAgent")
        self.assertEqual(span.agent_role, "Web Researcher")
        self.assertEqual(span.thought, "Found 3 relevant scientific papers on arXiv.")
        self.assertEqual(span.span_kind, SpanKind.AGENT.value)

    def test_agent_decorator_class(self):
        with session_scope(session_id="class-sess-1"):
            @agent(name="CodingAgent", role="Full Stack Developer")
            class CodingAgent:
                def run(self, task):
                    return {"code": f"# Implementation for {task}"}

            bot = CodingAgent()
            res = bot.run("build rest api")
            self.assertIn("build rest api", res["code"])

        sess = tracker.get_session("class-sess-1")
        self.assertEqual(len(sess.spans), 1)
        self.assertEqual(sess.spans[0].agent_name, "CodingAgent")

    def test_tool_decorator(self):
        with session_scope(session_id="tool-sess-1"):
            @agent(name="CalculatorAgent")
            def calc_agent(a, b):
                @tool(name="multiplier")
                def multiply(x, y):
                    return x * y
                return multiply(a, b)

            res = calc_agent(6, 7)
            self.assertEqual(res, 42)

        sess = tracker.get_session("tool-sess-1")
        span = sess.spans[0]
        self.assertEqual(len(span.tool_calls), 1)
        self.assertEqual(span.tool_calls[0].tool_name, "multiplier")
        self.assertEqual(span.tool_calls[0].result, 42)

    def test_operation_and_workflow_decorators(self):
        with session_scope(session_id="wf-sess-1"):
            @workflow(name="DataETLWorkflow")
            def run_etl():
                @operation(name="CleanseData")
                def clean(data):
                    return [d.strip() for d in data]

                return clean([" a ", " b "])

            res = run_etl()
            self.assertEqual(res, ["a", "b"])

        sess = tracker.get_session("wf-sess-1")
        self.assertEqual(len(sess.spans), 2)
        kinds = [s.span_kind for s in sess.spans]
        self.assertIn(SpanKind.WORKFLOW.value, kinds)
        self.assertIn(SpanKind.OPERATION.value, kinds)

    def test_guardrail_decorator(self):
        with session_scope(session_id="guard-sess-1"):
            @guardrail(name="PII_Validator")
            def check_pii(text):
                return "SSN" not in text

            self.assertTrue(check_pii("Safe user prompt"))
            self.assertFalse(check_pii("Contains SSN: 000-00-0000"))

        sess = tracker.get_session("guard-sess-1")
        guard_spans = [s for s in sess.spans if s.span_kind == SpanKind.GUARDRAIL.value]
        self.assertEqual(len(guard_spans), 2)
        self.assertEqual(guard_spans[0].status, "OK")
        self.assertEqual(guard_spans[1].status, "ERROR")

    def test_session_replay_construction(self):
        with session_scope(session_id="replay-sess-1"):
            @agent(name="WorkerAgent")
            def worker():
                @tool(name="fetch_db")
                def db():
                    return {"rows": 5}
                return db()
            worker()

        events = tracker.get_session_replay("replay-sess-1")
        self.assertGreater(len(events), 0)
        types = [e["event_type"] for e in events]
        self.assertTrue(any("START" in t for t in types))
        self.assertTrue(any("TOOL" in t for t in types))

    def test_cicd_event_tracking(self):
        ev = tracker.record_cicd_event(
            pipeline_name="GitHub Actions • ADK Deploy",
            run_id="gh-12345",
            commit_sha="c0ffee123",
            branch="staging",
            status="SUCCESS",
            duration_ms=4500,
            provider="github-actions"
        )
        self.assertEqual(ev.pipeline_name, "GitHub Actions • ADK Deploy")
        
        all_events = tracker.get_cicd_events()
        self.assertEqual(len(all_events), 1)
        self.assertEqual(all_events[0]["commit_sha"], "c0ffee123")

    def test_async_agent_and_tool(self):
        async def async_main():
            with session_scope(session_id="async-sess-1"):
                @agent(name="AsyncAgent")
                async def run_async():
                    @tool(name="async_fetch")
                    async def fetch():
                        await asyncio.sleep(0.01)
                        return "async-data"
                    return await fetch()
                return await run_async()

        res = asyncio.run(async_main())
        self.assertEqual(res, "async-data")
        sess = tracker.get_session("async-sess-1")
        self.assertEqual(len(sess.spans), 1)
        self.assertEqual(sess.spans[0].agent_name, "AsyncAgent")
        self.assertEqual(len(sess.spans[0].tool_calls), 1)


if __name__ == "__main__":
    unittest.main()
