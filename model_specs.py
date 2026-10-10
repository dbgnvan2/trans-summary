"""
Centralized configuration for AI model specifications and pricing.
"""

# Pricing per Million Tokens (USD)
# Updated as of January 2026, reflecting user-provided 5min Cache Write and Cache Hit/Refresh rates.
PRICING = {
    # Claude 5 family (Anthropic list prices, 2026-10). Cache write = 1.25x input
    # (5-minute TTL); cache read as published, else 0.1x input.
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_write": 5.00, "cache_read": 0.20},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_write": 2.50, "cache_read": 0.20},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_write": 0.125, "cache_read": 0.01},
    "claude-fable-5-1": {"input": 10.00, "output": 50.00, "cache_write": 12.50, "cache_read": 0.25},
    "claude-opus-5": {"input": 5.00, "output": 25.00, "cache_write": 6.25, "cache_read": 0.50},
    "claude-sonnet-5": {"input": 2.00, "output": 10.00, "cache_write": 2.50, "cache_read": 0.20},
    "claude-sonnet-4-6": {  # Claude Sonnet 4.6
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30
    },
    "claude-opus-4-6": {  # Claude Opus 4.6
        "input": 5.00,
        "output": 25.00,
        "cache_write": 6.25,
        "cache_read": 0.50
    },
    # Claude 4.5 Family (Estimates based on Opus/Haiku tiers)
    "claude-opus-4-5-20251101": {  # Claude Opus 4.5
        "input": 5.00,
        "output": 25.00,
        "cache_write": 6.25,  # 5min Cache Write
        "cache_read": 0.50    # Cache Hit/Refresh
    },
    "claude-sonnet-4-5-20250929": {  # Claude Sonnet 4.5
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30
    },
    "claude-haiku-4-5-20251001": {  # Claude Haiku 4.5
        "input": 1.00,
        "output": 5.00,
        "cache_write": 1.25,
        "cache_read": 0.10
    },
    "claude-opus-4-1-20250805": {  # Claude Opus 4.1
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50
    },
    "claude-opus-4-20250514": {  # Claude Opus 4
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50
    },
    "claude-sonnet-4-20250514": {  # Claude Sonnet 4
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30
    },
    "claude-3-5-sonnet": {  # No new data, keep old for now
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30
    },
    "claude-3-5-sonnet-20241022": {  # No new data, keep old for now
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30
    },
    "claude-3-7-sonnet-20250219": {  # Claude 3.7 Sonnet (Beta)
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30
    },
    "claude-3-opus": {  # No new data, keep old for now
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50
    },
    "claude-3-haiku": {  # Claude Haiku 3
        "input": 0.25,
        "output": 1.25,
        "cache_write": 0.30,
        "cache_read": 0.03
    },
    "claude-3-haiku-20240307": {  # Claude Haiku 3
        "input": 0.25,
        "output": 1.25,
        "cache_write": 0.30,
        "cache_read": 0.03
    },
    # Fallbacks / Aliases
    "claude-3-5-haiku": {  # Claude Haiku 3.5
        "input": 0.80,
        "output": 4.00,
        "cache_write": 1.00,
        "cache_read": 0.08
    },
    "claude-3-5-haiku-20241022": {  # Claude Haiku 3.5
        "input": 0.80,
        "output": 4.00,
        "cache_write": 1.00,
        "cache_read": 0.08
    }
}


def get_pricing(model_name: str) -> dict:
    """
    Find pricing for a model name, handling versions/dates.

    Args:
        model_name: The name of the model (e.g., "claude-3-5-sonnet-20241022")

    Returns:
        Dictionary with 'input', 'output', 'cache_write', 'cache_read' costs per million tokens.
    """
    model_lower = model_name.lower()

    # Direct match first
    if model_name in PRICING:
        return PRICING[model_name]

    # Check for keys inside the model name (e.g. "claude-3-5-sonnet" matching "claude-3-5-sonnet-latest")
    for key in PRICING:
        if key in model_lower:
            return PRICING[key]

    # Fallback logic for partial matches
    if "haiku" in model_lower and "4-5" in model_lower:
        return PRICING["claude-haiku-4-5-20251001"]
    if "opus" in model_lower and "4-5" in model_lower:
        return PRICING["claude-opus-4-5-20251101"]
    if "sonnet" in model_lower and "4-5" in model_lower:
        return PRICING["claude-sonnet-4-5-20250929"]
    if "haiku" in model_lower and "3-5" in model_lower:
        return PRICING["claude-3-5-haiku"]  # Changed to generic alias
    if "sonnet" in model_lower and "3-5" in model_lower:
        return PRICING["claude-3-5-sonnet"]  # Changed to generic alias
    if "opus" in model_lower and "3" in model_lower:
        return PRICING["claude-3-opus"]
    if "haiku" in model_lower and "3" in model_lower:
        return PRICING["claude-3-haiku"]  # Changed to generic alias

    # Default fallback (Sonnet pricing)
    return PRICING["claude-3-5-sonnet"]  # FIXED: changed PRIC to PRICING


# --------------------------------------------------------------------------- MV.1
# What each model accepts, so request code never sends a field a model rejects
# (docs/plan_v5_models_2026-10-10.md#MV.1).
#   temperature: the model accepts a sampling temperature (5-family: rejected).
#   thinking:    "always"   - thinks by default and cannot be fully switched off
#                             (5-family); the reply starts with a thinking block.
#                "adaptive" - thinks only when asked (4.6).
#                "budget"   - legacy budget_tokens thinking, not used here.
#   effort_levels / default_effort: output_config.effort values the model takes.
#   max_output:  largest max_tokens.
_ALL_EFFORT = ("low", "medium", "high", "xhigh", "max")
_V5 = {"temperature": False, "thinking": "always", "effort_levels": _ALL_EFFORT,
       "default_effort": "high", "max_output": 128000}
_V46 = {"temperature": True, "thinking": "adaptive",
        "effort_levels": ("low", "medium", "high", "max"), "default_effort": "high",
        "max_output": 128000}
_LEGACY = {"temperature": True, "thinking": "budget", "effort_levels": (),
           "default_effort": None, "max_output": 8192}

MODEL_CAPABILITIES = {
    "claude-opus-5-5": {**_V5, "default_effort": "medium"},
    "claude-haiku-5-5": {**_V5, "default_effort": "medium"},
    "claude-sonnet-5-5": dict(_V5),
    "claude-fable-5-1": dict(_V5),
    "claude-opus-5": dict(_V5),
    "claude-sonnet-5": dict(_V5),
    "claude-opus-4-6": dict(_V46),
    "claude-sonnet-4-6": dict(_V46),
    "claude-haiku-4-5-20251001": {**_LEGACY, "max_output": 64000},
    "claude-sonnet-4-5-20250929": {**_LEGACY, "max_output": 64000},
    "claude-opus-4-5-20251101": {**_LEGACY, "effort_levels": ("low", "medium", "high"),
                                 "default_effort": "high", "max_output": 64000},
}


def capabilities(model_name: str) -> dict:
    """Capabilities for ``model_name``: an exact entry, else by family — any
    claude-{opus,sonnet,haiku,fable,mythos}-5* name is treated as 5-family,
    -4-6 as 4.6, anything else as a legacy model (temperature accepted, no effort).

    Tests: tests/test_v5_models.py::test_mv1_capabilities_known_models
    """
    import re
    name = (model_name or "").lower()
    if name in MODEL_CAPABILITIES:
        return MODEL_CAPABILITIES[name]
    if re.match(r"claude-(opus|sonnet|haiku|fable|mythos)-5", name):
        return dict(_V5)
    if re.search(r"-4-6", name):
        return dict(_V46)
    return dict(_LEGACY)
