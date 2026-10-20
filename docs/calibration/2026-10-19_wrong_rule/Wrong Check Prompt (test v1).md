You are given a SOURCE transcript and a numbered list of CLAIMS from a summary of it. A faithfulness check flagged each claim. Most flagged claims are fine: a careful person's summary paraphrases, condenses, interprets and connects. Your only job is to find the claims that are WRONG in one of three specific ways. Everything else is not_quite_right. A claim may be followed by the sentence that came before it in the summary; that sentence is context only. Judge the claim.

A claim is WRONG only when one of these is true:
- W2. Reversed or contradicted. The source says something that conflicts with the claim: the opposite outcome, a different number, date or relationship, who did what to whom turned around, or a statement made definite where the speaker hedges it or declines it.
- W3. Wrong person. The claim credits words, a story, an experience, a question or a view to one person, and the source shows it belongs to someone else.
- W4. Invented event or plan. The claim says the speaker did, announced, found, decided or plans something, or states a conclusion as the speaker's own, and nothing in the source says it or leads to it.

Do not judge whether names, numbers, dates or places are in the source. Another check handles those.

A claim is not_quite_right when it is:
- N1. A fair paraphrase or summary of what the source says, even when it is not word for word.
- N2. An interpretation, framing, emphasis or connection of what the speaker says, without a new event or a reversed point.
- N3. Real content placed at a different point in the talk, or the talk's order described loosely.

Answer wrong only when you can show it from the source. If you are unsure, answer not_quite_right.

Evidence: for W2 and W3, quote the source words the claim conflicts with, up to 25 words, copied exactly from the source. If you cannot quote such words, the claim is not W2 or W3. For W4, write absent. For not_quite_right, quote the source words closest to the claim, up to 25 words, copied exactly. Inside the evidence, write any double quotation mark as a single quotation mark.

Speaker labels: when the source includes a transcript note saying it has no speaker labels, it often cannot show who said a passage. Then crediting a passage to a participant in the conversation is W3 only when the context shows that someone else said it.

EXAMPLES (subjects unrelated to any source):
- not_quite_right, N3: "The conductor ends by thanking the volunteers", when she thanked them in her opening remarks.
- not_quite_right, N2: "The baker treats the late delivery as a lesson in planning", when she said the flour came late and that she now orders a week ahead.
- not_quite_right, N1: "The coach says practice matters more than talent", when he said "talent gets you in the door, but it's the hours that keep you there."
- WRONG, W2: "The mayor says the bridge will close", when she said it will stay open.
- WRONG, W2: "The study proves coffee prevents headaches", when the speaker said it "might help some people, we don't know yet."
- WRONG, W3: "The librarian says the roof leaked twice", when a visitor said it.
- WRONG, W4: "The choir will tour next spring", when no tour is mentioned.
END OF EXAMPLES

Return ONLY a JSON array, one object per claim, in order:
[{"index": 1, "severity": "wrong|not_quite_right", "type": "W2|W3|W4|N1|N2|N3", "evidence": "<source words, or absent>"}]
No prose before or after the JSON.
