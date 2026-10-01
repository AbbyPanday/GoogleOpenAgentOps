"""
Active Google Gemini Model Pricing & Token Economics Registry.
CRITICAL CONSTRAINT: Strictly uses active production models.
All deprecated legacy models (gemini-1.0-pro, text-bison, PaLM) are strictly excluded.
"""

from typing import Any, Dict, Tuple
from google_openagentops.models import TokenMetrics

# Official rates per 1,000,000 tokens (USD)
MODEL_PRICING: Dict[str, Dict[str, Any]] = {
    "gemini-3.8-flash": {
        "input_price_per_million": 0.15,
        "output_price_per_million": 0.60,
        "display_name": "Google Gemini 3.8 Flash (GA - Autonomous Agents & Coding)",
        "context_window": 1_048_576
    },
    "gemini-3.8-live": {
        "input_price_per_million": 0.20,
        "output_price_per_million": 0.80,
        "display_name": "Google Gemini 3.8 Live (GA - Real-Time Voice & Orchestration)",
        "context_window": 1_048_576
    },
    "gemini-3.5-flash": {
        "input_price_per_million": 0.10,
        "output_price_per_million": 0.40,
        "display_name": "Google Gemini 3.5 Flash (GA - High Efficiency Agentic)",
        "context_window": 1_048_576
    },
    "gemini-3-flash": {
        "input_price_per_million": 0.10,
        "output_price_per_million": 0.40,
        "display_name": "Google Gemini 3 Flash (Preview - Advanced Multimodal Reasoning)",
        "context_window": 1_048_576
    },
    "gemini-omni-1.1-flash": {
        "input_price_per_million": 0.25,
        "output_price_per_million": 1.00,
        "display_name": "Google Gemini Omni 1.1 Flash (Preview - Multimodal & Video)",
        "context_window": 1_048_576
    },
    "gemini-3.1-flash-image": {
        "input_price_per_million": 0.15,
        "output_price_per_million": 0.60,
        "display_name": "Google Gemini 3.1 Flash Image (GA - Visual Engine)",
        "context_window": 1_048_576
    },
    "gemini-3-pro-image": {
        "input_price_per_million": 0.20,
        "output_price_per_million": 0.80,
        "display_name": "Google Gemini 3 Pro Image (GA - High-Fidelity Visual Engine)",
        "context_window": 1_048_576
    },
    "default": {
        "input_price_per_million": 0.15,
        "output_price_per_million": 0.60,
        "display_name": "Google Gemini 3.8 Flash (Default Agent Model)",
        "context_window": 1_048_576
    }
}


def calculate_token_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> TokenMetrics:
    """Calculates exact token economics down to micro-cents based on active Google Gemini rates."""
    key = model_name.lower().strip()
    config = MODEL_PRICING.get(key)
    if not config:
        for k, v in MODEL_PRICING.items():
            if k in key:
                config = v
                break
    if not config:
        config = MODEL_PRICING["default"]

    in_price = config["input_price_per_million"] / 1_000_000.0
    out_price = config["output_price_per_million"] / 1_000_000.0

    prompt_cost = prompt_tokens * in_price
    completion_cost = completion_tokens * out_price
    total_cost = prompt_cost + completion_cost

    return TokenMetrics(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        prompt_cost_usd=round(prompt_cost, 7),
        completion_cost_usd=round(completion_cost, 7),
        total_cost_usd=round(total_cost, 7)
    )


def estimate_token_count(text: Any) -> int:
    """Estimates token count using character heuristic (~4 chars per token)."""
    if not text:
        return 0
    if isinstance(text, (dict, list)):
        import json
        text = json.dumps(text)
    return max(1, len(str(text)) // 4)
