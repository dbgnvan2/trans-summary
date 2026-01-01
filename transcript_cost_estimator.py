#!/usr/bin/env python3
"""
Estimates the token usage and cost for processing a transcript through the pipeline.

Usage:
    python transcript_cost_estimator.py "path/to/your/transcript.txt"
"""

import argparse
from pathlib import Path
import config
from transcript_utils import estimate_token_count

# Pricing per Million Tokens (USD) - Mirrored from analyze_token_usage.py
PRICING = {
    "claude-3-5-sonnet-20241022": {
        "input": 3.00,
        "output": 15.00,
        "cache_write": 3.75,
        "cache_read": 0.30
    },
    "claude-3-opus-20240229": {
        "input": 15.00,
        "output": 75.00,
        "cache_write": 18.75,
        "cache_read": 1.50
    },
    "claude-3-haiku-20240307": {
        "input": 0.25,
        "output": 1.25,
        "cache_write": 0.30,
        "cache_read": 0.03
    },
    "claude-3-5-haiku-20241022": {
        "input": 1.00,
        "output": 5.00,
        "cache_write": 1.25,
        "cache_read": 0.10
    }
}


def get_pricing(model_name):
    """Find pricing for a model name, handling versions/dates."""
    if model_name in PRICING:
        return PRICING[model_name]

    # Fallback logic for partial matches
    if "haiku" in model_name.lower() and "3-5" in model_name:
        return PRICING["claude-3-5-haiku-20241022"]
    if "sonnet" in model_name.lower() and "3-5" in model_name:
        return PRICING["claude-3-5-sonnet-20241022"]
    if "opus" in model_name.lower():
        return PRICING["claude-3-opus-20240229"]

    return PRICING["claude-3-5-sonnet-20241022"]


class CostEstimator:
    """Estimates the cost of the transcript processing pipeline."""

    def __init__(self, transcript_path: Path, logger=None):
        self.logger = logger
        if not transcript_path.exists():
            raise FileNotFoundError(
                f"Transcript file not found: {transcript_path}")
        self.transcript_content = transcript_path.read_text(encoding='utf-8')
        self.transcript_tokens = estimate_token_count(self.transcript_content)
        self.costs = []
        self._log(f"Transcript: {transcript_path.name}")
        self._log(f"Estimated Tokens: {self.transcript_tokens:,}\n")

    def _log(self, message: str):
        if self.logger:
            self.logger.info(message)
        else:
            print(message)

    def _calculate_cost(self, step_name: str, model: str, input_tokens: int, output_tokens: int, is_cached_read: bool = False, cached_tokens: int = 0, is_cache_write: bool = False):
        """Calculates and records the cost for a single pipeline step."""
        prices = get_pricing(model)

        cost_input = 0.0
        cost_output = 0.0
        cost_cache_read = 0.0
        cost_cache_write = 0.0

        if is_cache_write:
            # Entire input is written to cache
            cost_cache_write = (input_tokens / 1_000_000) * \
                prices.get('cache_write', prices['input'] * 1.25)
        elif is_cached_read:
            # Cost for the prompt itself (normal input) + cost for reading from cache
            cost_input = (input_tokens / 1_000_000) * prices['input']
            cost_cache_read = (cached_tokens / 1_000_000) * \
                prices['cache_read']
        else:
            # This is a fresh call (standard input)
            cost_input = (input_tokens / 1_000_000) * prices['input']

        cost_output = (output_tokens / 1_000_000) * prices['output']
        total_cost = cost_input + cost_output + cost_cache_read + cost_cache_write

        self.costs.append({
            "step": step_name,
            "cost": total_cost,
            "input": input_tokens + cached_tokens if is_cached_read else input_tokens,
            "output": output_tokens,
            "model": model,
            "breakdown": {
                "input": cost_input,
                "output": cost_output,
                "cache_write": cost_cache_write,
                "cache_read": cost_cache_read
            }
        })
        return total_cost

    def estimate_formatting(self):
        """Estimate cost for the initial formatting step (cache write)."""
        prompt = (config.PROMPTS_DIR /
                  config.PROMPT_FORMATTING_FILENAME).read_text()
        prompt_tokens = estimate_token_count(prompt)

        input_tokens = prompt_tokens + self.transcript_tokens
        # Output is roughly the same size as the input transcript
        output_tokens = self.transcript_tokens

        self._calculate_cost(
            "1. Formatting", config.FORMATTING_MODEL, input_tokens, output_tokens, is_cache_write=True)

    def estimate_summarization_steps(self):
        """Estimate costs for all steps that use the cached transcript."""
        # The transcript itself is now cached, so we pay the 'cache_read' price for it.

        # 2a. Key Items (Topics, Themes, etc.)
        prompt = (config.PROMPTS_DIR /
                  config.PROMPT_EXTRACTS_FILENAME).read_text()
        prompt_tokens = estimate_token_count(prompt)
        output_tokens = int(self.transcript_tokens *
                            config.TARGET_EXTRACTS_PERCENT)
        self._calculate_cost("2a. Key Items", config.DEFAULT_MODEL, prompt_tokens,
                             output_tokens, is_cached_read=True, cached_tokens=self.transcript_tokens)

        # 2b. Scored Emphasis
        prompt = (config.PROMPTS_DIR /
                  config.PROMPT_EMPHASIS_SCORING_FILENAME).read_text()
        prompt_tokens = estimate_token_count(prompt)
        # Heuristic: ~20 items per 10k transcript tokens, each item ~150 output tokens
        num_items = (self.transcript_tokens / 10000) * 20
        output_tokens = int(num_items * 150)
        self._calculate_cost("2b. Scored Emphasis", config.DEFAULT_MODEL, prompt_tokens,
                             output_tokens, is_cached_read=True, cached_tokens=self.transcript_tokens)

        # 2c. Key Terms
        prompt = (config.PROMPTS_DIR /
                  config.PROMPT_KEY_TERMS_FILENAME).read_text()
        prompt_tokens = estimate_token_count(prompt)
        # Heuristic: Output is ~15% of transcript size
        output_tokens = int(self.transcript_tokens * 0.15)
        self._calculate_cost("2c. Key Terms", config.DEFAULT_MODEL, prompt_tokens,
                             output_tokens, is_cached_read=True, cached_tokens=self.transcript_tokens)

        # 2d. Blog Post
        prompt = (config.PROMPTS_DIR / config.PROMPT_BLOG_FILENAME).read_text()
        prompt_tokens = estimate_token_count(prompt)
        # Heuristic: Based on configured minimum characters
        output_tokens = estimate_token_count(" " * config.MIN_BLOG_CHARS)
        self._calculate_cost("2d. Blog Post", config.DEFAULT_MODEL, prompt_tokens,
                             output_tokens, is_cached_read=True, cached_tokens=self.transcript_tokens)

    def estimate_structured_steps(self):
        """Estimate costs for structured summary and abstract generation."""
        # Heuristic: The JSON input for these steps is ~30% of the transcript size
        json_input_tokens = int(self.transcript_tokens * 0.3)

        # 3a. Structured Summary
        prompt = (config.PROMPTS_DIR /
                  config.PROMPT_STRUCTURED_SUMMARY_FILENAME).read_text()
        prompt_tokens = estimate_token_count(prompt) + json_input_tokens
        output_tokens = estimate_token_count(
            " " * config.DEFAULT_SUMMARY_WORD_COUNT * 5)  # 5 chars/word
        self._calculate_cost("3a. Structured Summary", config.AUX_MODEL, prompt_tokens,
                             output_tokens, is_cached_read=True, cached_tokens=self.transcript_tokens)

        # 3b. Structured Abstract
        prompt = (config.PROMPTS_DIR /
                  config.PROMPT_STRUCTURED_ABSTRACT_FILENAME).read_text()
        prompt_tokens = estimate_token_count(prompt) + json_input_tokens
        output_tokens = estimate_token_count(
            " " * config.ABSTRACT_MIN_WORDS * 5)
        self._calculate_cost("3b. Structured Abstract", config.AUX_MODEL, prompt_tokens,
                             output_tokens, is_cached_read=True, cached_tokens=self.transcript_tokens)

    def estimate_validation_steps(self):
        """Estimate cost for validation steps that use an LLM."""
        # Header Validation is the main one. It sends the whole transcript.
        # The current implementation does not use caching for this step.
        prompt = (config.PROMPTS_DIR /
                  config.PROMPT_FORMATTING_HEADER_VALIDATION_FILENAME).read_text()
        prompt_tokens = estimate_token_count(prompt)
        input_tokens = prompt_tokens + self.transcript_tokens
        output_tokens = 1000  # Report is usually short
        self._calculate_cost("4. Header Validation",
                             config.AUX_MODEL, input_tokens, output_tokens)

    def run_full_estimation(self):
        """Run all estimation steps."""
        self.estimate_formatting()
        self.estimate_summarization_steps()
        self.estimate_structured_steps()
        self.estimate_validation_steps()
        self.print_report()

    def print_report(self):
        """Print the final cost report."""
        total_cost = sum(c['cost'] for c in self.costs)
        total_write = sum(c['breakdown']['cache_write'] for c in self.costs)
        total_read = sum(c['breakdown']['cache_read'] for c in self.costs)
        total_input = sum(c['breakdown']['input'] for c in self.costs)
        total_output = sum(c['breakdown']['output'] for c in self.costs)

        self._log("=" * 100)
        self._log("PIPELINE COST ESTIMATION REPORT")
        self._log("=" * 100)
        self._log(f"Total Estimated Cost: ${total_cost:.4f}")
        self._log(f"  - Input (Standard): ${total_input:.4f}")
        self._log(f"  - Output:           ${total_output:.4f}")
        self._log(f"  - Cache Write:      ${total_write:.4f}")
        self._log(f"  - Cache Read:       ${total_read:.4f}")
        self._log("-" * 100)
        self._log(
            f"{'Step':<25} | {'Model':<25} | {'Input':>8} | {'Output':>8} | {'Write':>8} | {'Read':>8} | {'Cost':>8}")
        self._log("-" * 100)

        for item in self.costs:
            bd = item['breakdown']
            self._log(
                f"{item['step']:<25} | {item['model']:<25} | ${bd['input']:>7.4f} | ${bd['output']:>7.4f} | ${bd['cache_write']:>7.4f} | ${bd['cache_read']:>7.4f} | ${item['cost']:>7.4f}")

        self._log("-" * 100)
        self._log(
            "\nDisclaimer: This is an estimate. Actual token counts and costs may vary based on")
        self._log(
            "model responses, prompt template changes, and API pricing updates.")
        self._log("=" * 100)


def main():
    """Main function to handle command-line execution."""
    parser = argparse.ArgumentParser(
        description="Estimate the cost of processing a transcript through the full pipeline."
    )
    parser.add_argument(
        "transcript_file",
        help="Path to the raw transcript file (e.g., 'source/My Transcript.txt')"
    )
    args = parser.parse_args()

    try:
        transcript_path = Path(args.transcript_file)
        estimator = CostEstimator(transcript_path)
        estimator.run_full_estimation()

    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
