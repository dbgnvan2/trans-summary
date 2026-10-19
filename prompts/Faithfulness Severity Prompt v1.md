You are given a SOURCE transcript and a numbered list of CLAIMS from a summary of it. A faithfulness check flagged each claim as not supported by the source. A summary written by a careful person is good, not perfect. For each claim, decide whether it is WRONG or only NOT QUITE RIGHT. A claim may be followed by the sentence that came before it in the summary; that sentence is context only. Judge the claim.

A claim is WRONG when any part of it would give a reader a false idea of what the source says:
- W1. It states a fact, name, date, number, place, event, quote, study, or description of a person that the source does not contain, even if it may be true elsewhere.
- W2. The source contradicts it: a different number, date, relationship or outcome; a description of the talk that the source contradicts; or a hedged statement made definite where the source hedges or declines it.
- W3. It credits words, a story, a question or a view to the wrong person.
- W4. It states a conclusion, position, plan or future event that the speaker never states and that does not follow from what the speaker says, or that runs against a position the speaker states.

A claim is NOT QUITE RIGHT when every fact in it is in the source, each is credited to the right person, and it was flagged only because:
- N1. It is a fair paraphrase or summary of the source.
- N2. It interprets, frames, connects or emphasizes what the speaker says, including applying ideas the speaker states to material the speaker discusses, without adding a new fact.
- N3. It places real content at the wrong point in the talk (for example, says the speaker closes with something said earlier), or describes the talk's order loosely.

If any part of a claim is WRONG, the claim is WRONG. If you are unsure, answer WRONG.

Speaker labels: when the source includes a transcript note saying it has no speaker labels, it often cannot show who said a passage. Then crediting a passage to a participant in the conversation is W3 only when the context shows that someone else said it.

Evidence: for NOT QUITE RIGHT, quote the source words that support the claim, up to 25 words, copied exactly from the source. For WRONG, quote the source words the claim conflicts with, or write absent. Inside the evidence, write any double quotation mark as a single quotation mark.

EXAMPLES (subjects unrelated to any source):
- NOT QUITE RIGHT, N3: "The conductor ends by thanking the volunteers", when she thanked them in her opening remarks.
- NOT QUITE RIGHT, N2: "The baker treats the late delivery as a lesson in planning", when she said the flour came late and that she now orders a week ahead.
- WRONG, W3: "The librarian says the roof leaked twice", when a visitor said it.
- WRONG, W4: "The choir will tour next spring", when no tour is mentioned.
END OF EXAMPLES

Return ONLY a JSON array, one object per claim, in order:
[{"index": 1, "severity": "wrong|not_quite_right", "type": "W1|W2|W3|W4|N1|N2|N3", "evidence": "<source words, or absent>"}]
No prose before or after the JSON.
