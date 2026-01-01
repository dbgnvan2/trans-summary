# Abstract Quality Assessment and Revision Prompt

Use this prompt in your Python script by inserting the source document and abstract into the designated placeholders.

---

```
You are evaluating and revising an abstract/summary against its source document.

## Source Document
<source_document>
{source_document}
</source_document>

## Abstract to Evaluate
<abstract>
{abstract}
</abstract>

## Task

Complete the following three tasks in order:

### TASK 1: ASSESSMENT

Evaluate the abstract across these dimensions (1-5 scale):

1. **Coverage Accuracy** — Are claims in the abstract supported by the source?
2. **Completeness** — Does the abstract capture major themes?
3. **Proportionality** — Does emphasis match the source?
4. **Factual Precision** — Are specific details (names, dates, terms) correct?
5. **Interpretive Validity** — Are evaluative statements justified?

For each dimension, provide:
- Score (1-5)
- Specific findings (unsupported claims, missing themes, errors, etc.)

Conclude with:
- Overall score
- Summary (2-3 sentences)
- Numbered list of specific recommendations for revision

### TASK 2: SHORT ABSTRACT (Target: 150 words)

Write a revised short abstract that:
- Addresses the recommendations from Task 1
- Identifies the document type and speaker attribution (e.g., interview, lecture, presentation)
- Captures the core theoretical contribution
- Mentions key concepts and their significance
- Notes concrete outcomes or future plans if stated in source
- Uses precise, economical language

### TASK 3: EXTENDED ABSTRACT (Target: 350-400 words)

Write a revised extended abstract that:
- Addresses all recommendations from Task 1
- Identifies document type and speaker attribution
- Covers major themes proportionally
- Includes at least one concrete illustrative example from the source
- Captures methodological insights
- Addresses clinical or practical utility if discussed
- Notes limitations or caveats acknowledged by the speaker
- Mentions concrete outcomes or future plans if stated in source

## Output Format

```
## ASSESSMENT

### Dimension Scores
| Dimension | Score |
|-----------|-------|
| Coverage Accuracy | |
| Completeness | |
| Proportionality | |
| Factual Precision | |
| Interpretive Validity | |
| **Overall** | |

### Findings

**Coverage Accuracy:**
[findings]

**Completeness:**
- Major themes in source: [list]
- Themes present in abstract: [list]
- Themes missing: [list]

**Proportionality:**
[findings]

**Factual Precision:**
[findings]

**Interpretive Validity:**
[findings]

### Summary
[2-3 sentence assessment]

### Recommendations
1. [recommendation]
2. [recommendation]
...

---

## SHORT ABSTRACT

[revised 150-word abstract]

---

## EXTENDED ABSTRACT

[revised 350-400 word abstract]
```
```
