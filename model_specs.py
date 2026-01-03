"""
Centralized configuration for AI model specifications and pricing.
"""

# Pricing per Million Tokens (USD)
# Updated as of late 2024 (Estimates)
PRICING = {
    # Claude 4.5 Family (Estimates based on Opus/Haiku tiers)
    "claude-opus-4-5-20251101": {
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50,
    },
    "claude-sonnet-4-5-20250929": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-haiku-4-5-20251001": {
        "input": 0.25,
        "output": 1.25,
        "cache_write": 0.30,
        "cache_read": 0.03,
    },
    "claude-3-7-sonnet-20250219": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-3-5-sonnet": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-3-5-sonnet-20241022": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "claude-3-opus": {
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50,
    },
    "claude-3-opus-20240229": {
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50,
    },
    "claude-3-haiku": {
        "input": 0.25,
        "output": 1.25,
        "cache_write": 0.30,
        "cache_read": 0.03,
    },
    "claude-3-haiku-20240307": {
        "input": 0.25,
        "output": 1.25,
        "cache_write": 0.30,
        "cache_read": 0.03,
    },
    # Fallbacks / Aliases
    "claude-3-5-haiku": {
        "input": 1.00,
        "output": 5.00,
        "cache_write": 1.25,
        "cache_read": 0.10,
    },
    "claude-3-5-haiku-20241022": {
        "input": 1.00,
        "output": 5.00,
        "cache_write": 1.25,
        "cache_read": 0.10,
    },
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
    if "sonnet" in model_lower and "3-7" in model_lower:
        return PRICING["claude-3-7-sonnet-20250219"]
    if "haiku" in model_lower and "3-5" in model_lower:
        return PRICING["claude-3-5-haiku-20241022"]
    if "sonnet" in model_lower and "3-5" in model_lower:
        return PRICING["claude-3-5-sonnet-20241022"]
    if "opus" in model_lower:
        return PRICING["claude-3-opus-20240229"]

    # Default fallback (Sonnet pricing)
    return PRICING["claude-3-5-sonnet"]
