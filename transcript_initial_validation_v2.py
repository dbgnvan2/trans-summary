"""
Transcript Initial Validation Script V2
Validates the initial transcript for transcription errors using LLM with chunked processing and safe replacement.
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Set

from anthropic import Anthropic

import config
import model_specs
import transcript_utils


class ValidationMetrics:
    """Tracks metrics for the validation process."""

    def __init__(self):
        self.start_time = datetime.now()
        self.end_time = None
        self.iterations: List[Dict] = []
        self.api_calls = 0
        self.tokens_used = {'input': 0, 'output': 0, 'cache_creation': 0, 'cache_read': 0}
        self.corrections_found = 0
        self.corrections_applied = 0
        self.corrections_skipped = 0
        self.hallucinations_detected = 0
        self.model_name = None

    def record_iteration(self, iteration_num: int, errors_found: int, errors_applied: int):
        self.iterations.append({
            'iteration': iteration_num,
            'found': errors_found,
            'applied': errors_applied,
            'timestamp': datetime.now().isoformat()
        })
        self.corrections_found += errors_found
        self.corrections_applied += errors_applied

    def record_api_call(self, usage: Any):
        self.api_calls += 1
        self.tokens_used['input'] += getattr(usage, 'input_tokens', 0)
        self.tokens_used['output'] += getattr(usage, 'output_tokens', 0)
        self.tokens_used['cache_creation'] += getattr(usage, 'cache_creation_input_tokens', 0) or 0
        self.tokens_used['cache_read'] += getattr(usage, 'cache_read_input_tokens', 0) or 0

    def calculate_summary(self) -> Dict:
        self.end_time = datetime.now()
        duration = (self.end_time - self.start_time).total_seconds()
        
        # Calculate Cost
        pricing = model_specs.get_pricing(self.model_name or config.DEFAULT_MODEL)
        
        input_cost = (self.tokens_used['input'] / 1_000_000) * pricing['input']
        output_cost = (self.tokens_used['output'] / 1_000_000) * pricing['output']
        cache_create_cost = (self.tokens_used['cache_creation'] / 1_000_000) * pricing['cache_write']
        cache_read_cost = (self.tokens_used['cache_read'] / 1_000_000) * pricing['cache_read']
        
        total_cost = input_cost + output_cost + cache_create_cost + cache_read_cost
        
        return {
            'total_duration_seconds': duration,
            'total_api_calls': self.api_calls,
            'total_tokens': self.tokens_used,
            'total_cost': total_cost,
            'model_used': self.model_name,
            'total_corrections_found': self.corrections_found,
            'total_corrections_applied': self.corrections_applied,
            'total_corrections_skipped': self.corrections_skipped,
            'hallucinations_detected': self.hallucinations_detected,
            'iterations': self.iterations
        }

    def log_summary(self, logger: logging.Logger):
        summary = self.calculate_summary()
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info("VALIDATION V2 SUMMARY")
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(f"Model: {summary['model_used']}")
        logger.info(f"Duration: {summary['total_duration_seconds']:.2f}s")
        logger.info(f"API Calls: {summary['total_api_calls']}")
        logger.info(f"Tokens: In={summary['total_tokens']['input']}, Out={summary['total_tokens']['output']}")
        logger.info(f"        Cache: Create={summary['total_tokens']['cache_creation']}, Read={summary['total_tokens']['cache_read']}")
        logger.info(f"Cost: ${summary['total_cost']:.4f}")
        logger.info(f"Corrections: Found={summary['total_corrections_found']}, Applied={summary['total_corrections_applied']}")
        logger.info(f"Hallucinations: {summary['hallucinations_detected']}")
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


class TranscriptValidatorV2:
    def __init__(self, api_key: str, logger: logging.Logger = None):
        self.api_key = api_key
        self.logger = logger or logging.getLogger(__name__)
        self.client = None
        self.metrics = ValidationMetrics()
        self._setup_client()

    def _setup_client(self):
        self.client = Anthropic(api_key=self.api_key)

    def validate_chunked(self, transcript_path: Path, model: str = config.DEFAULT_MODEL) -> List[Dict[str, Any]]:
        """
        Validate transcript using chunked processing.
        Splits by words, processes each chunk, aggregates and deduplicates findings.
        """
        self.metrics.model_name = model
        self.logger.info(f"Starting V2 validation (Chunked) for: {transcript_path.name}")
        
        if not transcript_path.exists():
            raise FileNotFoundError(f"Transcript not found: {transcript_path}")

        with open(transcript_path, 'r', encoding='utf-8') as f:
            full_text = f.read()

        words = full_text.split()
        total_words = len(words)
        
        chunk_size = config.VALIDATION_CHUNK_SIZE
        overlap = config.VALIDATION_CHUNK_OVERLAP
        
        chunks = []
        start = 0
        while start < total_words:
            end = start + chunk_size
            # Edge Case: Merge small final chunk
            if end >= total_words:
                end = total_words
            elif (total_words - end) < (chunk_size * 0.3):
                # If remaining words are < 30% of chunk size, extend this chunk to end
                end = total_words
            
            chunk_text = " ".join(words[start:end])
            chunks.append({
                'id': len(chunks),
                'text': chunk_text,
                'start_word': start,
                'end_word': end
            })
            
            if end == total_words:
                break
                
            start = end - overlap

        self.logger.info(f"Split into {len(chunks)} chunks (Size: {chunk_size}, Overlap: {overlap})")
        
        all_findings = []
        
        for i, chunk in enumerate(chunks):
            self.logger.info(f"Processing Chunk {i+1}/{len(chunks)} ({len(chunk['text'])} chars)...")
            chunk_findings = self._process_single_chunk(chunk, model)
            all_findings.extend(chunk_findings)

        # Deduplication
        unique_findings = self._deduplicate_findings(all_findings)
        
        # Hallucination Check (Global Context)
        valid_findings, hallucinations = self.detect_hallucinations(unique_findings, full_text)
        
        self.metrics.hallucinations_detected += len(hallucinations)
        if hallucinations:
             self.logger.warning(f"Detected {len(hallucinations)} hallucinations (removed).")

        return valid_findings

    def _process_single_chunk(self, chunk: Dict, model: str) -> List[Dict]:
        """Call API for a single chunk."""
        prompt_path = config.PROMPTS_DIR / "transcript_error_detection_prompt_v2.md"
        if not prompt_path.exists():
            raise FileNotFoundError(f"V2 Prompt not found: {prompt_path}")
            
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_full_text = f.read()
            
        # SPLIT PROMPT: Instructions (System) vs Input (User)
        # We split at "## Input Text" or just put the whole template (minus the chunk) in system
        split_marker = "## Input Text"
        if split_marker in prompt_full_text:
            instructions, _ = prompt_full_text.split(split_marker, 1)
        else:
            # Fallback if marker missing
            instructions = prompt_full_text.replace("{chunk_text}", "")
            
        # 1. System Message: Contains the heavy instructions (CACHED)
        system_content = instructions.strip()
        system_message = transcript_utils.create_system_message_with_cache(system_content)
        
        # 2. User Message: Contains ONLY the chunk text
        user_content = f"## Input Text\n\n<transcript_chunk>\n{chunk['text']}\n</transcript_chunk>"
        messages = [{"role": "user", "content": user_content}]
        
        try:
            response_msg = transcript_utils.call_claude_with_retry(
                self.client,
                model=model,
                messages=messages,
                system=system_message,
                max_tokens=8000, # Adjusted for Haiku limit
                logger=self.logger,
                stream=True,
                timeout=config.TIMEOUT_FORMATTING
            )
            
            self.metrics.record_api_call(response_msg.usage)
            
            findings = self._parse_json_response(response_msg.content[0].text)
            
            # Tag with chunk info
            for f in findings:
                f['chunk_id'] = chunk['id']
                
            return findings
            
        except Exception as e:
            self.logger.error(f"Error processing chunk {chunk['id']}: {e}")
            return []

    def _parse_json_response(self, response_text: str) -> List[Dict]:
        """Robust JSON parsing with multiple fallback strategies."""
        # Strategy 1: Strip Fences
        clean_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()
        
        try:
            return json.loads(clean_text)
        except json.JSONDecodeError:
            pass
            
        # Strategy 2: Raw Decode from first '['
        try:
            start_idx = response_text.find('[')
            if start_idx != -1:
                return json.JSONDecoder().raw_decode(response_text[start_idx:])[0]
        except json.JSONDecodeError:
            pass

        # Strategy 3: Heuristic substring
        try:
            start_idx = response_text.find('[')
            end_idx = response_text.rfind(']')
            if start_idx != -1 and end_idx != -1:
                return json.loads(response_text[start_idx:end_idx+1])
        except json.JSONDecodeError:
            pass

        self.logger.error("Failed to parse JSON response.")
        return []

    def _deduplicate_findings(self, findings: List[Dict]) -> List[Dict]:
        """Deduplicate findings from overlapping chunks based on original_text + suggested_correction."""
        seen = set()
        unique = []
        duplicates = 0
        
        for f in findings:
            # Create a signature
            sig = (f.get('original_text', '').strip(), f.get('suggested_correction', '').strip())
            if sig not in seen:
                seen.add(sig)
                unique.append(f)
            else:
                duplicates += 1
                
        if duplicates > 0:
            self.logger.info(f"Deduplicated {duplicates} findings from overlap regions.")
            
        return unique

    def detect_hallucinations(self, findings: List[Dict], full_text: str) -> Tuple[List[Dict], List[Dict]]:
        """
        Check if original_text exists in the content.
        Returns (valid_findings, hallucinations).
        """
        valid = []
        hallucinations = []
        
        # Normalize full text once for fuzzy matching speed
        full_text_norm = transcript_utils.normalize_text(full_text)
        
        for f in findings:
            original = f.get('original_text', '')
            if not original:
                continue
                
            # Exact Match
            if original in full_text:
                valid.append(f)
                continue
                
            # Fuzzy Match
            # We search in a generalized way since we don't have the exact chunk context here easily 
            # (although we could pass it if we kept map). 
            # For V2 global check, we can use the util.
            start, end, ratio = transcript_utils.find_text_in_content(original, full_text)
            
            if ratio >= config.VALIDATION_FUZZY_HALLUCINATION:
                valid.append(f)
            else:
                f['hallucination_score'] = ratio
                hallucinations.append(f)
                self.logger.warning(f"Hallucination detected (ratio {ratio:.2f}): '{original[:50]}...'")

        return valid, hallucinations

    def validate_correction(self, correction: Dict, chunk_text: str = None) -> Tuple[bool, str]:
        """
        Validate semantic correctness of a finding.
        """
        required = ['error_type', 'original_text', 'suggested_correction', 'confidence']
        if any(k not in correction for k in required):
            return False, "Missing required fields"
            
        error_type = correction['error_type']
        if error_type not in config.VALIDATION_ERROR_TYPES:
            return False, f"Invalid error type: {error_type}"
            
        orig = correction['original_text']
        sugg = correction['suggested_correction']
        
        if orig == sugg:
             return False, "Original and correction are identical"
             
        word_count = len(orig.split())
        if word_count < config.VALIDATION_MIN_CONTEXT_WORDS or word_count > config.VALIDATION_MAX_CONTEXT_WORDS:
            return False, f"Context length {word_count} outside range [{config.VALIDATION_MIN_CONTEXT_WORDS}-{config.VALIDATION_MAX_CONTEXT_WORDS}]"
            
        return True, ""

    def apply_corrections_safe(self, transcript_path: Path, corrections: List[Dict], output_path: Path = None) -> Tuple[Path, int, List[str]]:
        """
        Apply corrections safely using position tracking and back-to-front replacement.
        """
        with open(transcript_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        replacements = [] # List of (start, end, replacement_text, source_correction)
        skipped_reasons = []
        
        # 1. Locate all matches
        for corr in corrections:
            original = corr['original_text']
            replacement = corr['suggested_correction']
            
            # Find all occurrences
            # Note: This finds ALL, but we need to be careful if multiple exist.
            # Strategy: If unique (count=1), apply. If count > 1 and word count >= 7, apply all.
            # Else skip as ambiguous.
            
            matches = [m.span() for m in re.finditer(re.escape(original), content)]
            
            if len(matches) == 1:
                start, end = matches[0]
                replacements.append((start, end, replacement, corr))
            elif len(matches) > 1:
                if len(original.split()) >= config.VALIDATION_MIN_UNIQUE_WORDS:
                    # Specific enough to apply to all
                    for start, end in matches:
                        replacements.append((start, end, replacement, corr))
                else:
                    msg = f"Skipped ambiguous: '{original[:20]}...' found {len(matches)} times, context too short."
                    skipped_reasons.append(msg)
                    self.logger.warning(msg)
            else:
                # 0 matches - Try Fuzzy
                start, end, ratio = transcript_utils.find_text_in_content(original, content)
                if ratio >= config.VALIDATION_FUZZY_AUTO_APPLY:
                     replacements.append((start, end, replacement, corr))
                else:
                     msg = f"Skipped not found (best fuzzy {ratio:.2f}): '{original[:20]}...'"
                     skipped_reasons.append(msg)
                     self.logger.warning(msg)

        # 2. Sort Descending by Start Position
        # Deduplicate replacements overlapping in position (sanity check)
        # Sort by start desc
        replacements.sort(key=lambda x: x[0], reverse=True)
        
        # 3. Apply
        applied_count = 0
        final_content = content
        
        # Track intervals to prevent overlap
        # Since we go back-to-front, we mostly care about not modifying already modified region?
        # Actually, if we have overlapping replacements, back-to-front doesn't solve "nested" or "crossed".
        # We need to check for overlaps.
        
        valid_replacements = []
        last_start = float('inf') 
        
        for start, end, repl_text, source in replacements:
            # Since sorted reverse, current 'end' must be <= last_start to be non-overlapping
            if end <= last_start:
                valid_replacements.append((start, end, repl_text))
                last_start = start
            else:
                 msg = f"Skipped overlapping replacement at {start}-{end}"
                 skipped_reasons.append(msg)
                 self.logger.warning(msg)

        for start, end, repl_text in valid_replacements:
            final_content = final_content[:start] + repl_text + final_content[end:]
            applied_count += 1
            
        # 4. Save
        if output_path is None:
            output_path = transcript_path.parent / f"{transcript_path.stem}_validated{transcript_path.suffix}"
            
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(final_content)
            
        return output_path, applied_count, skipped_reasons

    def run_iterative_validation_v2(self, transcript_path: Path, max_iterations: int = 5, model: str = config.DEFAULT_MODEL) -> Dict[str, Any]:
        """
        Full V2 iterative validation pipeline (Headless).
        """
        current_file = transcript_path
        stalled_count = 0
        previous_error_count = float('inf')
        
        self.metrics.start_time = datetime.now()
        
        for i in range(1, max_iterations + 1):
            self.logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            self.logger.info(f"🔄 Iteration {i}/{max_iterations}: Validating...")
            self.logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            
            # 1. Validate
            # Pass the model explicitly from run_iterative arguments
            findings = self.validate_chunked(current_file, model=model)
            self.metrics.model_name = model
            
            # 2. Filter (Confidence)
            to_apply = []
            to_review = []
            
            for f in findings:
                conf = f.get('confidence', 'low').lower()
                if conf in config.VALIDATION_AUTO_APPLY_CONFIDENCE:
                    to_apply.append(f)
                if conf in config.VALIDATION_REVIEW_CONFIDENCE:
                    to_review.append(f)
            
            # 3. Convergence Check
            error_count = len(to_apply)
            self.metrics.record_iteration(i, len(findings), 0) # Applied updated later
            
            if error_count == 0:
                self.logger.info("✅ Convergence reached (0 errors).")
                break
                
            # 4. Stall Check
            improvement = (previous_error_count - error_count) / previous_error_count if previous_error_count != float('inf') else 1.0
            if improvement < config.VALIDATION_STALL_THRESHOLD:
                stalled_count += 1
            else:
                stalled_count = 0
                
            if stalled_count >= config.VALIDATION_MAX_STALLED_ITERATIONS:
                self.logger.warning("⚠️  Validation stalled. Stopping.")
                break
                
            previous_error_count = error_count

            # 5. Apply
            # Determine new filename
            stem = current_file.stem
            # Strip _vN
            base_match = re.match(r'^(.*)_v\d+$', stem)
            base_name = base_match.group(1) if base_match else stem
            
            new_file = current_file.parent / f"{base_name}_v{i}{current_file.suffix}"
            
            out_path, applied, skipped = self.apply_corrections_safe(current_file, to_apply, new_file)
            
            self.metrics.iterations[-1]['applied'] = applied
            self.metrics.corrections_applied += applied
            self.metrics.corrections_skipped += len(skipped)
            
            self.logger.info(f"Applied {applied} corrections. ({len(skipped)} skipped)")
            current_file = out_path
            
            # 6. Generate Review File if needed
            if to_review and config.VALIDATION_SAVE_REVIEW_FILE:
                review_path = current_file.parent / f"{base_name}_review.md"
                self._save_review_file(to_review, review_path)
            
            # 7. Save Comprehensive Changes Log
            changes_log_path = current_file.parent / f"{base_name}_changes.md"
            self._save_changes_log(to_apply, changes_log_path, iteration=i)

        self.metrics.log_summary(self.logger)
        return {
            'final_file': current_file,
            'metrics': self.metrics.calculate_summary()
        }

    def _save_review_file(self, findings: List[Dict], path: Path):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"# Validation Review Items\n\nGenerated: {datetime.now()}\n\n")
            for item in findings:
                f.write(f"## {item.get('error_type')} ({item.get('confidence')})\n")
                f.write(f"**Original:** `{item.get('original_text')}`\n\n")
                f.write(f"**Correction:** `{item.get('suggested_correction')}`\n\n")
                f.write(f"**Reason:** {item.get('reasoning')}\n\n---\n")

    def _save_changes_log(self, findings: List[Dict], path: Path, iteration: int):
        mode = 'a' if path.exists() and iteration > 1 else 'w'
        with open(path, mode, encoding='utf-8') as f:
            if iteration == 1 and mode == 'w':
                f.write(f"# Comprehensive Change Log\nGenerated: {datetime.now()}\n\n")
            
            f.write(f"\n## Iteration {iteration} ({len(findings)} corrections)\n\n")
            f.write("| Type | Confidence | Original | Correction | Reason |\n")
            f.write("|------|------------|----------|------------|--------|\n")
            
            for item in findings:
                orig = item.get('original_text', '').replace('\n', ' ').replace('|', '\\|')
                corr = item.get('suggested_correction', '').replace('\n', ' ').replace('|', '\\|')
                reason = item.get('reasoning', '').replace('\n', ' ').replace('|', '\\|')
                f.write(f"| {item.get('error_type')} | {item.get('confidence')} | {orig} | {corr} | {reason} |\n")
            f.write("\n")

def main():
    """CLI Entry point for standalone testing."""
    parser = argparse.ArgumentParser(description="Transcript Initial Validation V2 (Standalone)")
    parser.add_argument("input_file", type=Path, help="Path to transcript file")
    parser.add_argument("--iterations", "-n", type=int, default=1, help="Max iterations")
    parser.add_argument("--model", default=config.DEFAULT_MODEL, help="Model name")
    
    args = parser.parse_args()
    
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set.")
        return

    logging.basicConfig(level=logging.INFO, format='%(message)s')
    logger = logging.getLogger("TranscriptValidatorV2")
    
    validator = TranscriptValidatorV2(os.getenv("ANTHROPIC_API_KEY"), logger)
    validator.run_iterative_validation_v2(args.input_file, args.iterations, model=args.model)

if __name__ == "__main__":
    main()