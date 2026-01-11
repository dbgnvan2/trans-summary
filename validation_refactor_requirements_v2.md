# Transcript Validation System Refactor Requirements v2.0

## Executive Summary

Refactor `transcript_initial_validation.py` to reduce token costs by 60-80% and improve accuracy through chunked processing, safer replacement logic, and better error detection.

**Critical Corrections from v1.0:**
- Chunks measured in WORDS not tokens (2500 words = ~8K tokens)
- Must include deduplication for overlap regions
- Medium confidence should auto-apply by default (with review flag)
- Must return structured statistics from run_iterative_validation()
- Must add ValidationMetrics class for tracking
- Must handle edge cases (tiny last chunks, empty results)

---

## 1. CHUNKED PROCESSING

### 1.1 Core Changes
- Split transcript into 2500-WORD chunks (not tokens) with 0-word overlap
- Process each chunk independently through validation API
- Aggregate findings from all chunks
- Each finding must include chunk_id for traceability

### 1.2 Deduplication Logic (CRITICAL - MISSING FROM V1.0)
- After aggregating findings from all chunks, deduplicate based on (original_text, suggested_correction) pairs
- Findings in overlap regions will appear in multiple chunks - keep only one instance
- Log when duplicates are removed for debugging

### 1.3 Edge Case Handling (ADDITION)
- If final chunk is < 30% of target chunk size, merge with previous chunk
- Prevents tiny chunks that waste API calls
- Log when this happens

### 1.4 Token Estimation Logging (ADDITION)
- Estimate tokens using 4 chars/token approximation
- Log comparison: full-document tokens vs chunked total
- Show estimated savings percentage

### 1.5 Method Signature
```
validate_chunked(transcript_path, chunk_size=3000, overlap=200, model=None) -> List[Dict]
```

Return format: List of findings, each with all standard fields PLUS chunk_id and chunk_text

---

## 2. ENHANCED PROMPT REQUIREMENTS

### 2.1 Confidence Scoring
Add required field: `confidence` with values "high", "medium", "low"

**Definitions:**
- high: Unambiguous error with clear correction
- medium: Probable error, context-dependent
- low: Uncertain or subjective

### 2.2 Error Type Categories
Replace current categories with these 9 types:
- spelling
- homophone (sounds similar, not generic "phonetic")
- proper_noun
- word_boundary
- capitalization
- repetition
- punctuation
- incomplete
- grammar

Remove "other" category - force specific categorization.

### 2.3 Context Length Requirements
Change from "3-10 words" to "5-30 words for uniqueness"

Rationale: Short phrases create ambiguous matches. Must include surrounding context.

### 2.4 Single-Pass Emphasis
Add instruction: "This is a single-pass review. Find ALL errors. You will not review this section again."

### 2.5 Prompt File Location
`prompts/transcript_error_detection_prompt.md`

---

## 3. CORRECTION VALIDATION SYSTEM

### 3.1 Validation Function Signature
```
validate_correction(correction: Dict, chunk_text: str) -> Tuple[bool, error_message: str]
```

**Second parameter is CRITICAL:** Must pass chunk_text to verify original_text exists.

### 3.2 Validation Checks (in order)
1. Required fields present: error_type, original_text, suggested_correction, confidence, reasoning
2. Error type is one of the 9 defined types
3. Confidence is one of: high, medium, low
4. original_text ≠ suggested_correction (actual change exists)
5. Word count in original_text is 5-30 (inclusive)
6. Neither field is empty or whitespace-only
7. original_text exists in chunk_text (exact or fuzzy ≥ 0.85)

### 3.3 Type-Specific Validation (ADDITION)
- `repetition`: Verify original_text contains duplicate words
- `word_boundary`: Verify spacing issues exist (multiple spaces or no spaces)

### 3.4 Return Format
- If valid: (True, "")
- If invalid: (False, "specific error message")

### 3.5 Batch Validation
Before applying any corrections, validate entire batch and log statistics:
- Count valid vs invalid
- Group invalid by error type for analysis
- Log warning for each invalid correction with reason

---

## 4. SAFE REPLACEMENT ALGORITHM

### 4.1 Position-Based Tracking
- Find ALL positions where original_text appears in content
- Store as tuples: (start_pos, end_pos, replacement_text)
- Track source correction for each position (for logging)

### 4.2 Uniqueness Logic
**1 match found:** Add to replacement list

**0 matches found:**
- Try fuzzy match (threshold ≥ 0.95)
- If fuzzy succeeds: Add with fuzzy position
- If fuzzy fails: Skip and log reason

**Multiple matches found:**
- Count words in original_text
- If < 7 words: Skip (ambiguous), log warning
- If ≥ 7 words: Add ALL positions (phrase is specific)

### 4.3 Application Strategy
- Sort all replacements by start_pos DESCENDING
- Apply back-to-front to avoid offset corruption
- Each replacement: content = content[:start] + replacement + content[end:]

### 4.4 Return Format
```
(modified_content: str, applied_count: int, skipped_reasons: List[str])
```

### 4.5 Fuzzy Thresholds (CORRECTED)
- Auto-apply: ≥ 0.95 (95% similarity)
- Manual review: 0.90-0.94
- Reject: < 0.90

**Rationale:** 90% too permissive. Example: "affect" vs "defect" = 87% similar but completely different.

---

## 5. HALLUCINATION DETECTION

### 5.1 Detection Logic
For each finding:
1. Check if original_text exists exactly in content
2. If not found, try fuzzy match (threshold ≥ 0.85)
3. If fuzzy ratio < 0.85: Mark as hallucination

### 5.2 Return Format
```
(valid_findings: List[Dict], hallucinated: List[Dict])
```

Both lists contain full correction dictionaries.

### 5.3 Logging Requirements
- WARNING for each hallucination: First 50 chars + fuzzy ratio
- ERROR summary: Total count filtered
- INFO: Breakdown by error_type for hallucinations

### 5.4 Integration Point
Call immediately after parsing JSON, BEFORE validation:
```
findings = parse_json_response(response_text)
findings, hallucinated = detect_hallucinations(findings, chunk_text)
validated = [f for f in findings if validate_correction(f, chunk_text)[0]]
```

### 5.5 Hallucination Analysis (ADDITION)
Track patterns:
- Count by error_type (which types hallucinate most?)
- Count by confidence (are low-confidence more likely to hallucinate?)
- Log this analysis to help tune prompts

---

## 6. CONFIDENCE-BASED FILTERING

### 6.1 Default Configuration (CORRECTED FROM V1.0)
```
VALIDATION_AUTO_APPLY_CONFIDENCE = {'high', 'medium'}  # Changed: medium included
VALIDATION_REVIEW_CONFIDENCE = {'medium'}              # Flag but still apply
VALIDATION_SKIP_CONFIDENCE = {'low'}                   # Skip entirely
```

**Key Change:** Medium-confidence corrections auto-apply by default for automation. They're also flagged for optional review.

### 6.2 Filtering Logic
Separate findings into three lists:
- high_confidence
- medium_confidence  
- low_confidence

Apply based on configuration settings.

### 6.3 Review File Generation (ADDITION)
If VALIDATION_REVIEW_CONFIDENCE is non-empty:
- Generate markdown file listing all review-flagged corrections
- Include: error_type, original_text, suggested_correction, reasoning
- Save to: `{transcript_stem}_review.md`

---

## 7. ITERATIVE VALIDATION IMPROVEMENTS

### 7.1 Signature Change
```
run_iterative_validation(
    transcript_path: Path,
    max_iterations: int = 5,        # Changed from "iterations"
    model: str = None,
    use_chunked: bool = True        # New parameter
) -> Dict[str, Any]                 # Changed return type
```

### 7.2 Return Structure (CRITICAL - MISSING FROM V1.0)
Must return dictionary with these keys:
- final_file: Path
- total_iterations: int
- total_corrections: int
- final_error_count: int
- converged: bool (true if error_count reached 0)
- stalled: bool (true if stopped due to stalling)
- iteration_stats: List[Dict] (per-iteration metrics)
- token_usage: Dict with input/output token counts
- processing_time_seconds: float

### 7.3 Progress Tracking
Track state across iterations:
- previous_error_count
- stalled_iterations (counter)
- total_corrections_applied
- per-iteration statistics

### 7.4 Improvement Rate Calculation
```
improvement_rate = (previous_count - current_count) / previous_count

If improvement_rate < 0.20:  # Less than 20% improvement
    stalled_iterations += 1
else:
    stalled_iterations = 0  # Reset on good progress
```

### 7.5 Exit Conditions
Stop iteration if ANY of:
1. No errors found (converged)
2. Stalled for MAX_STALLED_ITERATIONS (default: 2)
3. Max iterations reached
4. Error count INCREASED (regression - possible bug)

### 7.6 Enhanced Logging
Use visual separators and status indicators:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 Iteration 2/5: Validating transcript...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Found: 12 errors
Applied: 12 corrections
Improvement: 50.0% reduction ✓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Use ⚠️ for warnings, ✓ for success, ❌ for errors.

### 7.7 Stall Recommendations (ADDITION)
When stalled, provide actionable feedback:
- List possible causes (ambiguous errors, low confidence, systemic issues)
- Suggest next steps (manual review, adjust confidence settings)
- Provide statistics to help diagnose (confidence breakdown, error types)

---

## 8. JSON PARSING ROBUSTNESS

### 8.1 Strategy Sequence
Try these strategies IN ORDER until one succeeds:

1. **Strip markdown fences:** Remove ```json and ``` patterns, parse cleaned string
2. **Extract first array:** Find first '[' and use JSONDecoder.raw_decode()
3. **Balanced bracket matching:** Find matching ']' for first '[', parse substring
4. **Raise exception:** If all fail, raise JSONDecodeError (do NOT return empty list)

### 8.2 Enhanced Error Context (CRITICAL ADDITION)
When JSONDecodeError occurs, log ALL of:
- Error message and position (line, column, character)
- 50 characters before and after error position
- Response length in characters
- Diagnostic checks:
  - Are markdown fences present?
  - Are brackets balanced? (count [ vs ])
  - Is response suspiciously long or short?

### 8.3 Post-Parse Validation (ADDITION)
After successful parsing:
1. Verify result is a list
2. Verify not absurdly large (> 1000 findings = likely parsing error)
3. Verify all elements are dictionaries
4. Remove non-dict elements with warning

### 8.4 Method Signature
```
_parse_json_response(response_text: str) -> List[Dict]
```

Raises JSONDecodeError if all strategies fail.

---

## 9. CONFIGURATION ADDITIONS

Add to `config.py`:

```
# Chunked Processing
VALIDATION_CHUNK_SIZE = 3000           # WORDS per chunk (not tokens)
VALIDATION_CHUNK_OVERLAP = 200         # WORDS overlap

# Context Requirements  
VALIDATION_MIN_CONTEXT_WORDS = 5       # Min words for unique context
VALIDATION_MAX_CONTEXT_WORDS = 30      # Max words to include
VALIDATION_MIN_UNIQUE_WORDS = 7        # Threshold for ambiguous matches

# Fuzzy Matching Thresholds
VALIDATION_FUZZY_AUTO_APPLY = 0.95     # 95% similarity for auto-apply
VALIDATION_FUZZY_REVIEW = 0.90         # 90% for manual review
VALIDATION_FUZZY_REJECT = 0.85         # < 85% reject
VALIDATION_FUZZY_HALLUCINATION = 0.85  # Hallucination detection threshold

# Confidence Filtering (CORRECTED)
VALIDATION_AUTO_APPLY_CONFIDENCE = {'high', 'medium'}  # Changed: medium included
VALIDATION_REVIEW_CONFIDENCE = {'medium'}
VALIDATION_SKIP_CONFIDENCE = {'low'}

# Iteration Control
VALIDATION_MAX_ITERATIONS = 5
VALIDATION_STALL_THRESHOLD = 0.20      # Stop if < 20% improvement
VALIDATION_MAX_STALLED_ITERATIONS = 2

# Error Types (for validation)
VALIDATION_ERROR_TYPES = {
    'spelling', 'homophone', 'proper_noun', 'word_boundary',
    'capitalization', 'repetition', 'punctuation', 'incomplete', 'grammar'
}

# Logging
VALIDATION_VERBOSE_LOGGING = True
VALIDATION_SAVE_REVIEW_FILE = True
```

---

## 10. TESTING REQUIREMENTS

### 10.1 New Unit Tests Required

Add to `test_initial_validation_logic.py`:

1. **test_chunked_processing** - Verify chunk creation, overlap, coverage
2. **test_deduplication** - Same error in overlap appears only once
3. **test_position_based_replacement** - Multiple matches handled correctly
4. **test_cascading_replacements** - Back-to-front prevents offset issues
5. **test_confidence_filtering** - Correct categorization by confidence
6. **test_hallucination_detection** - Non-existent text filtered
7. **test_validation_failure_handling** - Invalid corrections rejected
8. **test_iterative_stall_detection** - Stops after 2 stalled iterations
9. **test_fuzzy_matching_thresholds** - 95% auto-applies, 88% skips
10. **test_json_parsing_robustness** - Handles fences, trailing text, preambles

### 10.2 Integration Test Requirements

Create `test_validation_integration.py`:

**Full pipeline test:**
- Sample transcript with known errors
- Verify all expected errors detected
- Verify corrections applied correctly
- Verify token usage reduced by > 60%

**Test data structure:**
```
tests/test_data/
├── sample_short.txt (500 words, 3 known errors)
├── sample_short_errors.json (expected corrections)
├── sample_medium.txt (5K words, 15 errors)
├── sample_medium_errors.json
├── sample_long.txt (30K words, 50 errors)
└── sample_long_errors.json
```

**Error specification format:**
```json
{
  "transcript": "sample_short.txt",
  "expected_errors": [
    {
      "error_type": "proper_noun",
      "original_contains": "Bowin",
      "correction_contains": "Bowen",
      "approximate_word_position": 125
    }
  ]
}
```

---

## 11. VALIDATION METRICS TRACKING (MAJOR ADDITION - NOT IN V1.0)

### 11.1 ValidationMetrics Class

Create class to track:
- iterations: List of per-iteration stats
- api_calls: int count
- tokens_used: Dict with 'input' and 'output' keys
- corrections_found: int total
- corrections_applied: int total
- corrections_skipped: int total
- hallucinations_detected: int total
- start_time: datetime
- end_time: datetime

### 11.2 Required Methods

**record_iteration(iteration_num, errors_found, errors_applied)**
- Store stats for one iteration

**record_api_call(input_tokens, output_tokens)**
- Increment call count
- Accumulate token usage

**calculate_summary() -> Dict**
- Compute totals and averages
- Return structured summary

**log_summary(logger)**
- Format and log human-readable summary
- Use visual separators
- Include key metrics: iterations, tokens, corrections, time

### 11.3 Integration

Instantiate ValidationMetrics at start of run_iterative_validation()
Record metrics after each iteration
Log summary at end
Include summary in return dictionary

---

## 12. MIGRATION PATH

### 12.1 Backwards Compatibility

Keep existing `validate()` method with deprecation warning in:
- Docstring
- Log output on every call

Add CLI flag: `--no-chunked` to use old method

Default behavior: Use chunked processing

### 12.2 Deprecation Warning Format

Log message:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  DEPRECATION WARNING
Using full-document validation (validate)
Consider validate_chunked() for 60-80% cost savings
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 12.3 Migration Guide Document

Create `MIGRATION.md` with:
- Overview of changes
- Breaking changes (none expected)
- Migration steps for CLI users
- Migration steps for programmatic users
- Configuration updates needed
- Rollback plan
- Expected differences (token usage, timing, accuracy)
- Testing recommendations

---

## 13. DOCUMENTATION UPDATES

### 13.1 README.md Section

Add detailed "Validation Process" section covering:
- Overview of chunked processing
- 6 process steps (chunking, detection, filtering, validation, application, iteration)
- Token savings statistics
- Configuration options
- Usage examples (basic and advanced)
- Output file descriptions
- Troubleshooting Q&A

### 13.2 Inline Documentation

Add comprehensive docstrings to ALL new methods using this template:

**Include:**
- One-line summary
- Detailed description of process/algorithm
- Args section with types and descriptions
- Returns section with type and structure
- Raises section if applicable
- Example usage
- Notes about important behaviors

**Format:**
Use Google-style docstrings with proper formatting.

### 13.3 Configuration Documentation

Add module-level docstring to `config.py` explaining:
- Purpose of validation settings
- How chunked processing works
- Relationship between settings
- Reference to README for details

---

## 14. SUCCESS METRICS

### 14.1 Performance Targets

**Token Reduction:** ≥ 60% reduction per validation pass
- Measure: input_tokens from API response
- Baseline: 150K tokens per iteration
- Goal: 20-30K tokens per iteration

**Cost Reduction:** ≥ 60% reduction in API costs
- Calculate: (input_tokens × input_price + output_tokens × output_price) / 1M

**Processing Speed:** Similar or faster wall-clock time
- Despite more API calls, smaller payloads should compensate

### 14.2 Quality Targets

**Recall:** ≥ 95% of known errors detected
- Test with transcripts containing documented errors

**Precision:** False positive rate < 5%
- Test on clean, validated transcripts

**Hallucination Rate:** < 2% of corrections
- Track corrections for non-existent text

**Validation Pass Rate:** > 90% of LLM suggestions pass validation

### 14.3 Iteration Targets

**Average Iterations:** ≤ 2 to achieve clean transcript

**Convergence Rate:** 90% of transcripts clean within 3 iterations

**Stall Rate:** < 10% of validations stall before clean

### 14.4 Measurement Strategy

Use ValidationMetrics class to track all metrics
Log comprehensive summary after each run
Aggregate statistics across multiple transcripts for analysis
Compare against baseline (old system) on same test set

---

## 15. IMPLEMENTATION PRIORITY

### Phase 1 (Week 1) - CRITICAL
1. Chunked processing implementation
2. Deduplication logic
3. Safe replacement algorithm
4. Configuration updates

**Must complete before proceeding.**

### Phase 2 (Week 2) - HIGH PRIORITY
4. Enhanced prompt updates
5. Correction validation system
6. Hallucination detection
7. Confidence filtering

**Ensures quality and accuracy.**

### Phase 3 (Week 3) - MEDIUM PRIORITY
8. Iterative validation improvements
9. Metrics tracking system
10. JSON parsing enhancements

**Improves user experience.**

### Phase 4 (Week 4) - IMPORTANT
11. Testing suite
12. Documentation updates
13. Migration guide
14. Backwards compatibility

**Ensures maintainability.**

---

## 16. RISK MITIGATION

### 16.1 Key Risks

**Chunk boundary errors:** Mitigated by 200-word overlap

**API rate limits:** Still fewer calls than iterative full-doc (6 vs 20+)

**Breaking changes:** Mitigated by backwards compatibility

**Quality regression:** Mitigated by extensive testing

### 16.2 Rollback Plan

**Immediate:** Use `--no-chunked` flag

**Code rollback:** `git checkout v1.0`

**Configuration:** Set VALIDATION_CHUNK_SIZE very high to effectively disable

### 16.3 Rollback Triggers

Token usage > 50% of baseline (should be 20%)
Error detection rate < 90% of baseline
False positive rate > 10%
System instability

---

## APPENDIX A: CRITICAL CLARIFICATIONS

### A.1 Word-Based vs Token-Based Chunking

**Use WORDS not TOKENS:**
- Chunk size: 3000 words
- Overlap: 200 words
- Estimated tokens: ~12,000 per chunk (approximate)

**Why words?**
- More predictable
- No tokenizer dependency
- Simpler implementation

### A.2 Confidence Filtering Logic

**Key principle:** Sets can overlap
- High-confidence: Auto-apply
- Medium-confidence: Auto-apply AND flag for review
- Low-confidence: Skip

This allows automation while still providing review capability.

### A.3 Return Values Matter

All major functions MUST return structured data:
- validate_chunked() → List[Dict]
- apply_corrections_safe() → Tuple[str, int, List[str]]
- detect_hallucinations() → Tuple[List[Dict], List[Dict]]
- run_iterative_validation() → Dict[str, Any]

This enables testing, debugging, and metrics collection.

### A.4 Deduplication is Critical

Without deduplication:
- Same error appears multiple times from overlap regions
- Artificially inflates error counts
- May apply same correction multiple times
- Wastes API tokens

Always deduplicate after aggregating chunk findings.

### A.5 Edge Cases Must Be Handled

- Empty transcripts
- Transcripts shorter than chunk size
- Last chunk < 30% of target size
- Zero errors found
- All errors hallucinations
- JSON parsing failures

Each should have explicit handling and logging.

---

**END OF REQUIREMENTS DOCUMENT v2.0**

**Changes from v1.0:**
- Removed all code examples
- Focused on specifications and requirements only  
- Added critical missing requirements (deduplication, metrics, edge cases)
- Corrected errors (word vs token, confidence defaults)
- Clarified ambiguous specifications
- Added structured return types
- Enhanced validation requirements
- Expanded success metrics

**Document Size:** Concise, focused on requirements that can be handed to AI coding agents.
