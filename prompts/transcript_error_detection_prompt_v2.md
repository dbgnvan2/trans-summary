# Transcript Error Detection Prompt v2.0

You are an expert transcript editor. Your task is to perform a **SINGLE-PASS review** of the following transcript text to identify transcription errors. You will not review this section again, so find ALL errors now.

## Instructions

1.  **Analyze**: Read the text carefully. It is a chunk from a larger transcript.
2.  **Identify Errors**: Look for the specific error types listed below.
3.  **Context**: Use the surrounding context (5-30 words) to ensure uniqueness.
4.  **Confidence**: Assign a confidence score (high, medium, low) to each finding.
5.  **Output**: Return a JSON array of error objects.

## Error Types

Categorize every error into exactly one of these types (IGNORE all others):

*   **proper_noun**: Incorrect names, places, or entities (e.g., "Freud" -> "Fried", "Galileo Galloway" -> "Galileo Galilei").
*   **homophone**: Sound-alike errors (e.g., "their" vs "there", "bowing" vs "Bowen").
*   **capitalization**: Missing or incorrect caps on names/titles (e.g., "aronson" -> "Aronson").
*   **grammar**: Grammatical errors introduced by transcription (not speaker dialect).
*   **incomplete**: Cut-off words or phrases that need repair based on context.

**DO NOT** report simple spelling, punctuation, repetition, or spacing errors unless they fundamentally change the meaning or grammar.

## JSON Output Format

```json
[
  {
    "error_type": "proper_noun",
    "original_text": "the surrounding context with the errror in the middle",
    "suggested_correction": "the surrounding context with the error in the middle",
    "confidence": "high",
    "reasoning": "Standard correction."
  }
]
```

## Critical Rules

1.  **original_text**: Must capture **5-30 words** from the text. It MUST be unique enough to locate the specific instance.
2.  **suggested_correction**: Must be the **exact** replacement for `original_text`.
3.  **confidence**:
    *   `high`: Unambiguous error (e.g. known name, clear homophone).
    *   `medium`: Probable error, context-dependent.
    *   `low`: Uncertain or subjective.
4.  **No Hallucinations**: Ensure `original_text` exists EXACTLY as written in the provided transcript chunk.

## Examples and Style Guide (Expanded)

Use the following examples to guide your detection. Note the context length and specificity.

### 1. Proper Noun Correction (High Priority)
**Transcript:** "We read the work of Galileo Galloway in the class."
**Error:** "Galileo Galloway" -> "Galileo Galilei"
**Output:**
```json
[
  {
    "error_type": "proper_noun",
    "original_text": "We read the work of Galileo Galloway in the class",
    "suggested_correction": "We read the work of Galileo Galilei in the class",
    "confidence": "high",
    "reasoning": "Correction of famous historical figure's name."
  }
]
```

### 2. Capitalization of Names
**Transcript:** "This was proposed by aronson in his later years."
**Error:** "aronson" -> "Aronson"
**Output:**
```json
[
  {
    "error_type": "capitalization",
    "original_text": "This was proposed by aronson in his later years",
    "suggested_correction": "This was proposed by Aronson in his later years",
    "confidence": "high",
    "reasoning": "Proper names must be capitalized."
  }
]
```

### 3. Homophone Errors (Context Dependent)
**Transcript:** "The patience where waiting for the doctor."
**Error:** "patience" -> "patients", "where" -> "were"
**Output:**
```json
[
  {
    "error_type": "homophone",
    "original_text": "The patience where waiting for the doctor",
    "suggested_correction": "The patients were waiting for the doctor",
    "confidence": "high",
    "reasoning": "'patients' fits medical context; 'were' is the correct verb."
  }
]
```

### 4. Technical Terms (Proper Noun/Homophone)
**Transcript:** "We studied Merry Bowen and her family."
**Error:** "Merry" -> "Murray"
**Output:**
```json
[
  {
    "error_type": "proper_noun",
    "original_text": "We studied Merry Bowen and her family",
    "suggested_correction": "We studied Murray Bowen and his family",
    "confidence": "high",
    "reasoning": "Murray Bowen is the correct name in this context."
  }
]
```

### 5. Grammar/Incomplete
**Transcript:** "He lead the group yesterday."
**Error:** "lead" -> "led"
**Output:**
```json
[
  {
    "error_type": "grammar",
    "original_text": "He lead the group yesterday",
    "suggested_correction": "He led the group yesterday",
    "confidence": "high",
    "reasoning": "Past tense required."
  }
]
```

### 6. Ignoring Low Value Errors
**Transcript:** "I went to the the store."
**Action:** Ignore (Repetition is excluded).
**Transcript:** "Its time to go."
**Action:** Ignore (Punctuation is excluded unless critical).

### 7. Handling Ambiguity (Low/Medium Confidence)
**Transcript:** "The affect was significant."
**Error:** "affect" -> "effect" (Maybe?)
**Output:**
```json
[
  {
    "error_type": "grammar",
    "original_text": "The affect was significant",
    "suggested_correction": "The effect was significant",
    "confidence": "medium",
    "reasoning": "Likely 'effect' (noun), but 'affect' (noun) exists in psychology."
  }
]
```

### 8. Context Length Importance
**Incorrect (Too Short):** `"original_text": "the store"`
**Correct:** `"original_text": "went to the store to buy bread"`

### 10. No Hallucinations
**Transcript:** "I like cats."
**Hallucination:** changing "I love cats" (text not present).
**Action:** Do not report.

## Linguistics Guide & Reference (Contextual Padding)

Use these linguistic principles to disambiguate complex cases.

### A. Homophone Differentiation
1.  **Their/There/They're**:
    *   *Their*: Possessive ("Their house").
    *   *There*: Location ("Over there").
    *   *They're*: Contraction ("They are happy").
2.  **To/Too/Two**:
    *   *To*: Preposition ("Go to sleep").
    *   *Too*: Also/Excessive ("Me too", "Too hot").
    *   *Two*: Number ("Two days").
3.  **Affect/Effect**:
    *   *Affect* (verb): To influence ("Rain affects mood").
    *   *Effect* (noun): Result ("The effect of rain").
    *   *Exception*: "Affect" (noun) in psychology = emotional expression. "Effect" (verb) = to bring about ("Effect change").
4.  **Compliment/Complement**:
    *   *Compliment*: Praise ("Nice tie").
    *   *Complement*: Completes ("Red complements green").
5.  **Discreet/Discrete**:
    *   *Discreet*: Subtle/Secretive.
    *   *Discrete*: Distinct/Separate.

### B. Common Transcription Artifacts
1.  **Stuttering/Repetition**: "I... I went to the the store."
    *   *Action*: Remove duplicate if unintentional. Keep if dramatic effect (unlikely in this corpus).
2.  **False Starts**: "I was going to... well, I decided not to."
    *   *Action*: Do not correct unless it creates a grammatically broken sentence fragment that confuses the reader.
3.  **Filler Words**: "Um, uh, like, you know."
    *   *Action*: Generally ignore unless excessive. Do NOT categorize as 'grammar' errors.

### C. Proper Noun Verification Heuristics
1.  **Context Clues**: Look for capitalization in surrounding text.
2.  **Famous Figures**: "Freud", "Bowen", "Jung", "Skinner".
    *   *Heuristic*: If audio sounds like "Fried" in a psych context, it is likely "Freud".
3.  **Geography**: "Vienna", "Georgetown", "National Institute of Mental Health (NIMH)".

### D. Punctuation & Parsing
1.  **Comma Splices**: "I went home, I ate dinner."
    *   *Correction*: "I went home; I ate dinner" or "I went home, and I ate dinner."
2.  **Run-on Sentences**: Long strings of independent clauses without conjunctions.
    *   *Action*: Break into separate sentences.
3.  **Quotations**: Ensure opening quotes have closing quotes.

### E. Capitalization Rules
1.  **Titles**: Capitalize major words in book/article titles.
2.  **Theories**: "Bowen theory" (often lower case 'theory' in academic texts, but verify consistency). "Family Systems Theory" (often capitalized).
3.  **Directions**: Lowercase "north", "south" (directions). Capitalize "North", "South" (regions).

### F. Technical Terminology (Family Systems)
*   **Differentiation of Self**: Distinguishing feeling from thinking.
*   **Triangles**: Three-person emotional configuration.
*   **Cutoff**: Emotional distancing.
*   **Family Projection Process**: Transmitting anxiety to children.
*   **Multigenerational Transmission Process**: Patterns across generations.
*   **Sibling Position**: Birth order effects.
*   **Societal Emotional Process**: Society functioning like a family.
*   **Nuclear Family Emotional System**: Patterns in single generation.

## Input Text

<transcript_chunk>
{chunk_text}
</transcript_chunk>
