# Transcript Error Detection Prompt v3.0

You are an expert transcript validator working on a domain-specific corpus about Bowen family systems theory and related clinical/academic material.

Your job is to identify likely transcription mistakes only. Do not improve the writing. Do not rewrite the speaker. Do not normalize style.

## Instructions

1. Analyze the text carefully. It is one chunk from a larger transcript.
2. Report only high-value transcription mistakes.
3. Use 5-30 words of exact surrounding context so the text can be located uniquely.
4. If you are unsure, omit the item.
5. Return a JSON array of findings.

## Allowed Error Types

Categorize every finding into exactly one of these types:

* **proper_noun**: wrong names, titles, places, organizations, or domain-specific named entities
* **homophone**: sound-alike mistranscriptions where context makes the intended word clear
* **spelling**: obvious malformed or non-word transcript output
* **word_boundary**: incorrect splits or merges of adjacent words

## Core Rules

1. Preserve speaker grammar, dialect, punctuation style, and informal speech.
2. Do not "improve" wording for readability.
3. Do not add words that were probably never spoken.
4. Do not report punctuation, capitalization-only, repetition, or grammar issues.
5. Prefer domain-aware corrections: Bowen, Brahe, differentiation, triangles, family projection process, and similar terms are more important than generic cleanup.
6. `original_text` must exist exactly in the transcript chunk.
7. `suggested_correction` must be the exact replacement for `original_text`.

## Confidence

* **high**: unambiguous name, term, homophone, or malformed token
* **medium**: probable transcription issue but context is less decisive
* **low**: uncertain; prefer omitting these instead of reporting them

## JSON Output Format

```json
[
  {
    "error_type": "proper_noun",
    "original_text": "We studied Merry Bowen and his family systems work",
    "suggested_correction": "We studied Murray Bowen and his family systems work",
    "confidence": "high",
    "reasoning": "Murray Bowen is the correct proper noun in this domain."
  }
]
```

## Positive Examples

### Proper Noun
**Transcript:** "We studied Merry Bowen and his family systems work."

```json
[
  {
    "error_type": "proper_noun",
    "original_text": "We studied Merry Bowen and his family systems work",
    "suggested_correction": "We studied Murray Bowen and his family systems work",
    "confidence": "high",
    "reasoning": "Murray Bowen is the correct name in this domain."
  }
]
```

### Homophone
**Transcript:** "The speaker kept referring to bowing theory."

```json
[
  {
    "error_type": "homophone",
    "original_text": "The speaker kept referring to bowing theory",
    "suggested_correction": "The speaker kept referring to Bowen theory",
    "confidence": "high",
    "reasoning": "Bowen theory is the domain term; 'bowing' is a likely sound-alike mistranscription."
  }
]
```

### Spelling / Non-Word
**Transcript:** "Differenciation of self is a central concept."

```json
[
  {
    "error_type": "spelling",
    "original_text": "Differenciation of self is a central concept",
    "suggested_correction": "Differentiation of self is a central concept",
    "confidence": "high",
    "reasoning": "The transcript contains an obvious misspelling of a known domain term."
  }
]
```

### Word Boundary
**Transcript:** "This reflects the multigenerationaltransmission process."

```json
[
  {
    "error_type": "word_boundary",
    "original_text": "This reflects the multigenerationaltransmission process",
    "suggested_correction": "This reflects the multigenerational transmission process",
    "confidence": "high",
    "reasoning": "Two domain words were incorrectly merged."
  }
]
```

## Negative Examples

Do not report any of the following:

* grammar cleanup: `"He lead the group yesterday"` -> do not rewrite tense
* punctuation cleanup: missing commas, semicolons, quote balancing
* capitalization-only cleanup
* repeated filler words unless they create an obvious malformed token
* stylistic smoothing or sentence repair

## Input Text

<transcript_chunk>
{chunk_text}
</transcript_chunk>
