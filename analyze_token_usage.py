#!/usr/bin/env python3
"""
Analyze token usage and calculate costs from the CSV log.

Usage:
    python analyze_token_usage.py
"""

import csv
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import config

# Pricing per Million Tokens (USD)
# Updated as of late 2024 (Estimates)
PRICING = {
    "claude-3-5-sonnet": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30
    },
    "claude-3-opus": {
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50
    },
    "claude-3-haiku": {
        "input": 0.25,
        "output": 1.25,
        "cache_write": 0.30,
        "cache_read": 0.03
    },
    # Fallbacks / Aliases
    "claude-3-5-haiku": {  # Assuming similar to 3-haiku or slightly higher, using placeholder
        "input": 1.00,  # Adjust as needed
        "output": 5.00,
        "cache_write": 1.25,
        "cache_read": 0.10
    }
}


def get_pricing(model_name):
    """Find pricing for a model name, handling versions/dates."""
    model_lower = model_name.lower()
    for key in PRICING:
        if key in model_lower:
            return PRICING[key]
    # Default fallback (Sonnet pricing)
    return PRICING["claude-3-5-sonnet"]


def parse_cache_info(cache_str):
    """Parse the cache column string."""
    # Formats: "No", "Yes (Read 1234)", "Yes (Created 1234)"
    read_match = re.search(r'Read (\d+)', cache_str)
    create_match = re.search(r'Created (\d+)', cache_str)

    cache_read = int(read_match.group(1)) if read_match else 0
    cache_write = int(create_match.group(1)) if create_match else 0

    return cache_read, cache_write


def generate_usage_report(since_timestamp: datetime = None) -> str:
    """Generate a formatted string report of token usage and costs."""
    log_file = config.LOGS_DIR / "token_usage.csv"

    if not log_file.exists():
        return f"❌ Log file not found: {log_file}"

    lines = []
    lines.append(f"Reading log file: {log_file}")

    # Aggregators
    total_cost = 0.0
    total_input_cost = 0.0
    total_output_cost = 0.0
    total_cache_read_cost = 0.0
    total_cache_write_cost = 0.0

    by_script = defaultdict(
        lambda: {"cost": 0.0, "calls": 0, "input_cost": 0.0, "output_cost": 0.0, "cache_read_cost": 0.0, "cache_write_cost": 0.0})
    by_model = defaultdict(lambda: {"cost": 0.0, "calls": 0})

    rows = []

    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if since_timestamp:
                    try:
                        row_ts = datetime.strptime(
                            row['Timestamp'], "%Y-%m-%d %H:%M:%S")
                        if row_ts < since_timestamp:
                            continue
                    except (ValueError, KeyError):
                        continue
                rows.append(row)
    except Exception as e:
        return f"❌ Error reading CSV: {e}"

    lines.append(f"Processing {len(rows)} records...\n")

    for row in rows:
        script = row['Script Name']
        # Header is 'Items' in transcript_utils.py for model name
        model = row['Items']

        try:
            total_input = int(row['Tokens Sent'])
            total_output = int(row['Tokens Response'])
        except ValueError:
            continue

        # Try to use explicit columns if available, otherwise fall back to parsing string
        if 'Cache Creation Tokens' in row and 'Cache Read Tokens' in row:
            try:
                cache_write = int(row['Cache Creation Tokens'])
                cache_read = int(row['Cache Read Tokens'])
            except (ValueError, TypeError):
                cache_read, cache_write = parse_cache_info(
                    row.get('Cache', ''))
        else:
            cache_read, cache_write = parse_cache_info(row.get('Cache', ''))

        # Calculate base input (Total - Cache parts)
        # Note: Anthropic usage.input_tokens usually includes cache creation tokens but
        # pricing treats them differently.
        # If cached read: input_tokens = base + read
        # If cached create: input_tokens = base + create

        base_input = max(0, total_input - cache_read - cache_write)

        prices = get_pricing(model)

        cost_input = (base_input / 1_000_000) * prices['input']
        cost_output = (total_output / 1_000_000) * prices['output']
        cost_cache_read = (cache_read / 1_000_000) * prices['cache_read']
        cost_cache_write = (cache_write / 1_000_000) * prices['cache_write']

        row_cost = cost_input + cost_output + cost_cache_read + cost_cache_write

        # Aggregate
        total_cost += row_cost
        total_input_cost += cost_input
        total_output_cost += cost_output
        total_cache_read_cost += cost_cache_read
        total_cache_write_cost += cost_cache_write

        by_script[script]["cost"] += row_cost
        by_script[script]["calls"] += 1
        by_script[script]["input_cost"] += cost_input
        by_script[script]["output_cost"] += cost_output
        by_script[script]["cache_read_cost"] += cost_cache_read
        by_script[script]["cache_write_cost"] += cost_cache_write

        by_model[model]["cost"] += row_cost
        by_model[model]["calls"] += 1

    # --- REPORT ---

    lines.append("="*100)
    if since_timestamp:
        lines.append(
            f"TOKEN USAGE ANALYSIS (Since {since_timestamp.strftime('%Y-%m-%d %H:%M:%S')})")
    else:
        lines.append(f"TOKEN USAGE ANALYSIS (Cumulative)")
    lines.append("="*100)
    lines.append(f"Total Estimated Cost: ${total_cost:.4f}")
    lines.append(f"  - Input (Standard): ${total_input_cost:.4f}")
    lines.append(f"  - Output:           ${total_output_cost:.4f}")
    lines.append(f"  - Cache Write:      ${total_cache_write_cost:.4f}")
    lines.append(f"  - Cache Read:       ${total_cache_read_cost:.4f}")
    lines.append(f"Total API Calls:      {len(rows)}")
    lines.append("-" * 100)

    lines.append("\nCOST BY SCRIPT:")
    lines.append(
        f"{'Script Name':<30} | {'Calls':<6} | {'Input':>8} | {'Output':>8} | {'Write':>8} | {'Read':>8} | {'Cost':>8}")
    lines.append("-" * 100)

    # Sort by cost descending
    sorted_scripts = sorted(
        by_script.items(), key=lambda x: x[1]['cost'], reverse=True)

    for script, data in sorted_scripts:
        lines.append(
            f"{script:<30} | {data['calls']:<6} | ${data['input_cost']:>7.4f} | ${data['output_cost']:>7.4f} | ${data['cache_write_cost']:>7.4f} | ${data['cache_read_cost']:>7.4f} | ${data['cost']:>7.4f}")

    lines.append("\nCOST BY MODEL:")
    lines.append(f"{'Model Name':<40} | {'Calls':<6} | {'Cost ($)':<10}")
    lines.append("-" * 100)

    sorted_models = sorted(
        by_model.items(), key=lambda x: x[1]['cost'], reverse=True)
    for model, data in sorted_models:
        lines.append(f"{model:<40} | {data['calls']:<6} | ${data['cost']:.4f}")

    lines.append("\n" + "="*100)
    return "\n".join(lines)


def main():
    print(generate_usage_report())


if __name__ == "__main__":
    main()
