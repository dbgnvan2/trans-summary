"""
Centralized configuration for AI model specifications and pricing.
"""

# Pricing per Million Tokens (USD)
# Updated as of January 2026, reflecting user-provided 5min Cache Write and Cache Hit/Refresh rates.
PRICING = {
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
