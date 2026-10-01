"""
Typesafe AI (JEV) Decision & Model Routing Integration for GoogleOpenAgentOps.
Provides discrete, high-frequency (<1ms local) evaluation primitives:
- Task Complexity Scoring (0.00 to 1.00)
- Antigravity Skill Recommender
- Active Google Gemini 3.x Production Model Routing
"""

import time
from typing import Any, Dict, List, Optional, Tuple


class JevDecisionEngine:
    """
    High-frequency decision engine for autonomous agent workflows.
    Evaluates cognitive load, multi-step depth, and domain requirements
    to select the optimal skill and Gemini model.
    """

    COMPLEXITY_THRESHOLD = 0.60

    HIGH_COMPLEXITY_KEYWORDS = [
        "architect", "distributed", "concurrency", "swarm", "refactor",
        "security", "pipeline", "consensus", "state machine", "microservices",
        "scalability", "multi-agent", "formal proof", "fault-tolerant"
    ]

    LOW_COMPLEXITY_KEYWORDS = [
        "typo", "format", "quick", "one-liner", "summary", "translate",
        "regex", "rename", "simple function", "docstring"
    ]

    SKILL_MAPPING = {
        "swarm": ["roo-code", "GoogleOpenAgentOps"],
        "multi-agent": ["roo-code", "GoogleOpenAgentOps"],
        "architecture": ["roo-code", "gsd-workflow"],
        "test": ["ralph-loop"],
        "bug": ["ralph-loop"],
        "fix": ["ralph-loop"],
        "cloud": ["google-cloud-auth-verification", "GoogleOpenAgentOps"],
        "gcp": ["google-cloud-auth-verification", "GoogleOpenAgentOps"],
        "css": ["modern-web-guidance"],
        "frontend": ["modern-web-guidance"],
        "ui": ["modern-web-guidance"],
        "token": ["agentic-context-engineering"],
        "prompt": ["agentic-context-engineering"],
    }

    def evaluate_task(self, task_prompt: str) -> Dict[str, Any]:
        """Evaluates incoming task prompt and returns typed decision primitives."""
        start_time = time.perf_counter()
        lower = task_prompt.lower()

        # 1. Complexity Score Primitive
        score = 0.35
        for kw in self.HIGH_COMPLEXITY_KEYWORDS:
            if kw in lower:
                score += 0.12
        for kw in self.LOW_COMPLEXITY_KEYWORDS:
            if kw in lower:
                score -= 0.10
        score = max(0.05, min(0.99, round(score, 2)))

        # 2. Category Primitive
        if score >= 0.70:
            category = "complex_engineering"
        elif score >= 0.40:
            category = "standard_coding"
        else:
            category = "quick_task"

        # 3. Model Routing
        if "voice" in lower or "speech" in lower or "live audio" in lower:
            routed_model = "gemini-3.8-live"
            reason = "Real-time bidirectional audio/voice interaction"
        elif "image" in lower or "mockup" in lower or "visual asset" in lower:
            routed_model = "gemini-3.1-flash-image"
            reason = "Visual creation engine"
        elif score >= self.COMPLEXITY_THRESHOLD:
            routed_model = "gemini-3.8-flash"
            reason = f"High complexity ({score:.2f} >= {self.COMPLEXITY_THRESHOLD}) -> Deep reasoning & autonomous coding"
        else:
            routed_model = "gemini-3.5-flash"
            reason = f"Low-to-moderate complexity ({score:.2f} < {self.COMPLEXITY_THRESHOLD}) -> Rapid execution & cost efficiency"

        # 4. Recommended Skills
        recommended_skills = set()
        for kw, skills in self.SKILL_MAPPING.items():
            if kw in lower:
                recommended_skills.update(skills)

        if not recommended_skills:
            recommended_skills.add("gsd-workflow")

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return {
            "prompt": task_prompt,
            "complexity_score": score,
            "category": category,
            "routed_model": routed_model,
            "routing_reason": reason,
            "recommended_skills": sorted(list(recommended_skills)),
            "decision_latency_ms": round(elapsed_ms, 3),
            "decision_cost_usd": 0.0
        }


jev_engine = JevDecisionEngine()


def evaluate_task(task_prompt: str) -> Dict[str, Any]:
    """Top-level convenience function for Jev decision evaluation."""
    return jev_engine.evaluate_task(task_prompt)


def route_model(task_prompt: str) -> str:
    """Returns the routed active Gemini model name for a task."""
    return jev_engine.evaluate_task(task_prompt)["routed_model"]
