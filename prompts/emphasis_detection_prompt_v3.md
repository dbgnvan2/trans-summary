EMPHASIS EXTRACTION - Extract passages where speaker signals importance.

═══════════════════════════════════════════════════════════════
EXPLICIT MARKERS (21 categories) - rank shown:
═══════════════════════════════════════════════════════════════

A1[95-100%] PERSONAL IMPORTANCE: "I found this [extraordinary/fascinating/incredible/remarkable]"
A2[90-95%] META-COMMENTARY: "that's a huge [contribution/insight]", "real important concept"
A3[85-90%] CONVICTION: "I believe", "I'm convinced", "we can safely say"
A4[95-100%] HIGHLIGHTING: "the key thing", "what I want to emphasize"
A5[90-95%] DISCOVERY: "I never knew", "I'd never heard of", "I stumbled across"
A6[85-90%] PRACTICAL RELEVANCE: "so relevant to", "that's what helps", "direct bearing"
A7[85-92%] EPISTEMIC HUMILITY: "I guess...[+substantive claim]", "I don't know, but..."
A8[90-98%] PARALLEL THINKING: "sharp parallel", "same idea of", "identical to", "equivalent terms"
A9[90-100%] DIRECT ADDRESS: "I don't know about you guys", "[Concept], right?"
A10[85-95%] AFFECTIVE: "in awe of", "I had no idea", "so compelling"
A11[88-95%] PROVISIONAL CONJECTURE: "crawl out on limb", "my conjecture", "without claiming breakthroughs", "treacherous route"
A12[87-93%] PERSONAL JOURNEY: "over the course of X years", "hallmark of my effort", "I devoured [book]"
A13[85-94%] LISTENER VALIDATION: "well said", "good point" + elaboration 100+ words
A14[87-96%] SOURCE COMMENTARY: "favorite quote", "most useful", "better than any X"
A15[88-94%] METACOGNITIVE STRUGGLE: "trying to think through", "I've grappled with"
A16[85-92%] QUALIFIED ASSERTION: "to my knowledge, no one has", "I hasten to add"
A17[90-96%] OPEN THEORY: "keeping theory open", "not closed system"
A18[92-98%] VULNERABILITY: "slow learner", "humbling experience", "I wish I'd seen sooner"
A19[90-96%] NARRATIVE CLIMAX: "that woke me up", "I suddenly recognized", "incredibly useful"
A20[87-93%] DIFFICULTY: "so difficult to pull off", "it's hard to"
A21[92-98%] CERTAINTY: "I know within me", "like the back of my hand"

═══════════════════════════════════════════════════════════════
IMPLICIT MARKERS (16 categories) - rank shown:
═══════════════════════════════════════════════════════════════

B1[90-100%] REPETITION: Same concept 2-3x within 1-3 sentences, "in other words..."
B2[85-100%] SUPERLATIVES: "Most/-est", "only/alone/solely", "absolutely"
B3[85-100%] DEFINITIONAL: "X is...", "the definition of"
B4[85-100%] CONTRAST: "Not X, but Y", "the difference between"
B5[85-100%] CONCLUSIVE: "So..." [synthesis], "that's where I've come out"
B6[85-100%] RHETORICAL Q+A: Speaker poses then answers substantively
B7[85-100%] FRAMING: "my intent here today", "the most unique feature"
B8[85-100%] ANOMALY: "Unbelievably", "remarkably", "serendipitously"
B9[88-95%] NEGATIVE SPACE: "leave no room for", repeated negation
B10[90-95%] IMPOSSIBILITY: "it's impossible to", "can't be done"
B11[88-94%] TIME SCALE: "2000 years", deep time references
B12[87-93%] EXTENDED ELABORATION: Same concept across 3+ sections
B13[87-93%] ASPIRATIONAL: "the hardest challenge"
B14[85-90%] SELF-CORRECTION: "probably better way to say it"
B15[88-94%] SELF-ADDRESS: "It's the [X], stupid"
B16[88-94%] FUTURE PROJECTION: "not in my lifetime"

═══════════════════════════════════════════════════════════════
CLINICAL FORMAT (6 categories):
═══════════════════════════════════════════════════════════════

C1[90-98%] Client insight: "I'm learning", "what I'm learning is", "I can see where"
C2[88-95%] Therapist framing: "I was thinking", "as you're talking, I'm thinking"
C3[90-95%] Utility attribution: "you found useful", "seemed to trigger something"
C4[87-93%] Thinking aloud: "I'm thinking out loud", "I don't know" [within exploration]
C5[88-94%] Client pattern: "my tendency would have been", "I can see definite changes"
C6[92-98%] Theory-to-life: "such a good example", explicit triangle identification

═══════════════════════════════════════════════════════════════
EXCLUSIONS:
═══════════════════════════════════════════════════════════════

DO NOT EXTRACT:
- Procedural statements ("I'm going to talk about")
- Neutral transitions ("Next slide")
- Formulaic courtesy
- General exposition without evaluation

═══════════════════════════════════════════════════════════════
EXTRACTION RULES:
═══════════════════════════════════════════════════════════════

PRONOUN RESOLUTION:
If vague pronoun (that/this/these), scan backward for antecedent.

TRUNCATION:
Truncate at natural break: completed thought, "And/But/So" at clause start.
Target: 50-150 words | Maximum: 200 words

QUALITY:
Continuous verbatim only (no ellipsis).
Quote must stand alone without context.

OUTPUT FORMAT:
[Explicit/Implicit/Clinical - Category - Rank: XX%] Concept: {{descriptor}}
"{{continuous verbatim quote}}"
(Location reference)
