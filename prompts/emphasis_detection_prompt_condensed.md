# EMPHASIS DETECTION PROMPT (Condensed)

Extract passages where speakers signal importance through explicit markers or rhetorical structure. Include BOTH marker AND content. Rank 0-100%, keep only ≥85%.

---

## FORMAT DETECTION (Required First)

**Identify type:**
- **Lecture:** Single speaker, structured → scan section-by-section
- **Interview:** Q&A format → scan full responses, track question-response pairs
- **Clinical:** Therapist-client → prioritize client insights, track dialogue

---

## EXPLICIT EMPHASIS (Category A) - 21 Types

### Pattern Recognition Table

| Category | Key Indicators | Rank |
|----------|---------------|------|
| **A1. Personal Importance** | "I found this [extraordinary/fascinating]", "I think this is [important/crucial]" | 85-100 |
| **A2. Meta-Commentary** | "real important concept", "that's the power of", "huge [noun]" | 85-100 |
| **A3. Conviction** | "I believe", "we can safely say", "I'm convinced" | 85-100 |
| **A4. Highlighting** | "the key thing", "what I want to emphasize", "pay attention to" | 85-100 |
| **A5. Discovery** | "I never knew", "I'd never heard", "I stumbled across" | 85-100 |
| **A6. Practical Relevance** | "so relevant to", "that's what helps", "direct bearing on" | 85-100 |
| **A7. Epistemic Humility** | "I guess... [but substantive claim]", "I don't know, but..." | 85-92 |
| **A8. Parallel Thinking** | "sharp parallel with", "same idea of", "fundamentally equivalent" | 90-98 |
| **A9. Direct Address** | "I don't know about you, but", "[concept], right?" | 90-100 |
| **A10. Affective** | "in awe of", "maddening", "I had no idea", strong emotion | 85-95 |
| **A11. Conjecture** | "crawl out on a limb", "here is my conjecture" | 88-95 |
| **A12. Personal Journey** | "hallmark of my effort", "over the course of X years", "I devoured" | 87-93 |
| **A13. Listener Validation** | "well said", "good point" + elaboration | 85-94 |
| **A14. Source Commentary** | "favorite quote", "most useful", "better than any X" | 87-96 |
| **A15. Metacognitive** | "trying to think through", "I've grappled with", "deepen understanding" | 88-94 |
| **A16. Qualified Assertion** | "to my knowledge, no one has", "I hasten to add" | 85-92 |
| **A17. Open Theory** | "keeping theory open", "not closed system", "many unanswered questions" | 90-96 |
| **A18. Vulnerability** | "slow learner", "I wish I'd seen sooner", "humbling experience" | 92-98 |
| **A19. Narrative Climax** | "that woke me up", "I suddenly recognized", "incredibly useful" | 90-96 |
| **A20. Difficulty** | "so difficult to pull off", "it's hard to", "it's one thing... another thing" | 87-93 |
| **A21. Conviction** | "I know within me", "like the back of my hand", "a lot surer" | 92-98 |

---

## IMPLICIT EMPHASIS (Category B) - 16 Types

| Category | Key Indicators | Rank |
|----------|---------------|------|
| **B1. Repetition** | Same concept 2-3x, "in other words...", parallel structure | 85-100 |
| **B2. Superlatives** | "Most", "-est", "only/alone/solely", "absolutely" | 85-100 |
| **B3. Definitional** | "X is...", "definition of", "big difference there" | 85-100 |
| **B4. Contrast** | "Not X, but Y", "unlike X", "difference between" | 85-100 |
| **B5. Conclusive** | "So..." [synthesis], "the idea is", "that's where I've come out" | 85-100 |
| **B6. Rhetorical Q+A** | Speaker asks then answers substantively | 85-100 |
| **B7. Framing** | "hallmark of", "my intent is", "most unique feature" | 85-100 |
| **B8. Anomaly** | "Unbelievably", "remarkably", "serendipitously" | 85-100 |
| **B9. Negative Space** | "leave no room for", "that's not going to", repeated negation | 88-95 |
| **B10. Impossibility** | "impossible to", "can't be done" | 90-95 |
| **B11. Time Scale** | "2000 years", "3.7 billion years", deep time | 88-94 |
| **B12. Extended Elaboration** | Same concept across 3+ sections/slides | 87-93 |
| **B13. Aspirational** | "truly seem to want", "hardest challenge", "capacity to" | 87-93 |
| **B14. Self-Correction** | "probably better way", immediate refinement | 85-90 |
| **B15. Self-Address** | "it's the X, stupid", internal dialogue external | 88-94 |
| **B16. Future Projection** | "not in my lifetime", "history will treat", "eventually" | 88-94 |

---

## CLINICAL FORMAT ONLY (Category C) - 6 Types

| Category | Key Indicators | Rank |
|----------|---------------|------|
| **C1. Client Insight** | "I'm learning", "I can see where", "pieces I didn't understand" | 90-98 |
| **C2. Therapist Framing** | "I was thinking", "as you're talking", "definition I came up with" | 88-95 |
| **C3. Utility Attribution** | "you found useful", "possibly useful to you" | 90-95 |
| **C4. Real-Time Processing** | "thinking out loud", "I don't know" [+ exploration] | 87-93 |
| **C5. Client Pattern** | "I learned early", "my tendency would be", "I can see changes" | 88-94 |
| **C6. Theory-to-Life** | "such a good example", explicit triangle identification | 92-98 |

---

## FORMAT-SPECIFIC INSTRUCTIONS

### LECTURE:
- Scan section-by-section
- Check section openings/closings
- Look for isolated emphasis (single sentences)
- Priority: A1-A6, A10, A14, B1-B8

### INTERVIEW:
- Analyze question type (signals importance)
- Treat question + response as unit
- **Scan ENTIRE response** for multiple embedded emphasis points
- Don't skip "digression" - may contain emphasis
- Priority: A15-A17, A21, B16 + all lecture categories

### CLINICAL:
- **Prioritize client insights** (C1, C5)
- Track back-and-forth validation
- Follow problem → insight → integration arc
- Note theory-life connections
- Priority: All C categories, then A18-A20

---

## RANKING GUIDE

**95-100%:** Multiple markers combined, direct "emphasize" language, superlatives + personal
**90-95%:** Strong markers ("critical", "power of"), clear repetition, core definitions
**85-90%:** Moderate markers ("important", "interesting"), single intensifier, structural emphasis
**<85%:** Exclude

**Adjust +5-10% if:** Multiple types converge, structural boundary, returns to concept, extended elaboration
**Adjust -5-10% if:** Formulaic, preliminary, routine context

---

## EXCLUSIONS

**Never capture:**
- Pure description without evaluation
- Neutral transitions
- Quotes without speaker emphasis
- Procedural statements
- Formulaic courtesy
- Audience questions unless speaker emphasizes importance

---

## OUTPUT FORMAT

```
[Explicit/Implicit/Clinical - Rank: XX%] Concept: {{descriptor}}
"{{full quote with marker + content}}"
(Section N – Title)
```

---

## QUALITY CHECKS

- [ ] Used correct format protocol?
- [ ] All items ≥85%?
- [ ] Expected yield? (Lecture: 8-15, Interview: 12-20, Clinical: 10-18)
- [ ] Scanned full transcript?
- [ ] Excluded false positives?

---

## CRITICAL REMINDERS

**Lecture:** Section-by-section, isolated markers
**Interview:** FULL response scanning, embedded points, don't skip tangents
**Clinical:** Client validation = primary evidence

**Hard rule:** Include marker AND content. If multiple emphasis in same passage, extract separately.

---

**Version:** 1.0 | **Threshold:** ≥85% | **Coverage:** ~94% tested
