# Judge re-calibration: claude-sonnet-5-5 (2026-10-10)

Plan: `docs/plan_judge_recalibration_sonnet55_2026-10-10.md`. Raw results:
`docs/calibration/2026-10-10_*.json`. Gold set: 43 faithfulness cases (33 existing +
10 Kerr cases k1–k10, labels per D1) and the theme gold (20 grounded / 13 ungrounded).
Bars: recall ≥ 0.9 and precision ≥ 0.7 for both judges.

## Gold sets, real abstracts, injected fabrication

| Model / run | Faith. recall | Faith. precision | Theme recall | Theme precision | Real abstracts | Injected caught | Misses |
|---|---|---|---|---|---|---|---|
| Sonnet 4.6 (current) run 1 | 0.91 | 0.95 | 1.00 | 1.00 | 3/3 | yes | k1, k2, k4 |
| Sonnet 5.5 default (high) run 1 | 0.91 | 1.00 | 1.00 | 1.00 | 3/3 | yes | k4, k6 |
| Sonnet 5.5 default (high) run 2 | 0.95 | 1.00 | 1.00 | 1.00 | 3/3 | yes | k6 |
| Sonnet 5.5 default (high) run 3 | 0.95 | 1.00 | 1.00 | 1.00 | 3/3 | yes | k6 |
| Sonnet 5.5 medium run 1 | 0.95 | 1.00 | 1.00 | 1.00 | 3/3 | yes | k4 |
| Sonnet 5.5 medium run 2 | 1.00 | 1.00 | 1.00 | 1.00 | 3/3 | yes | — |
| Sonnet 5.5 medium run 3 | 0.95 | 1.00 | 1.00 | 0.93 | 3/3 | yes | k4 + 1 theme |

- Every run of every model clears the bars.
- Sonnet 4.6 misreads the speaker labels (k1, k2) and accepts the boat "took over" (k4).
- Sonnet 5.5 reads the speakers correctly in every run and has precision 1.00 (no false
  alarms) on the gold set. It accepts the overview-style framing k6 ("central to Bowen
  theory's explanation…") in every default run — it is more lenient on writer's framing.

## Stability (JC.4: pass/fail changes across 3 runs)

- Sonnet 5.5 default: **1** — k4, the boat "took over" (borderline by design).
- Sonnet 5.5 medium: **2** — k4, and one real theme ("Physical Illness as System
  Disruptor…") judged ungrounded in one run of three.
- Malformed judge replies retried: 0 in the final runs. Earlier, before the parser fix,
  Sonnet 5.5 returned a single verdict as a bare object instead of a one-item array;
  `_extract_json_array` now accepts that shape, and a malformed reply is asked for again
  once (`config.JUDGE_PARSE_ATTEMPTS`).

## Real prose (JC.5): 602 claims in 12 artifacts from 4 talks

Rejected claims: Sonnet 4.6 **86**, Sonnet 5.5 default **55**, medium **77**.
Sonnet 5.5 default changes 59 verdicts: 14 newly rejected, 45 newly
accepted (mostly blog rhetoric — the blog is advisory — and overview/summary framing).

### Newly rejected by Sonnet 5.5 (default)

| Talk | Artifact | Claim | 4.6 | 5.5 |
|---|---|---|---|---|
| Societal Emotional Process | abstract-generated | The interviewee traces her deterioration to a convergence of nodal events in 2015—her mother's death, her husband's retirement, her mother-in-law's dementia diagnosis, the loss of her naturopathic doctor, and the death of her dog—which functioned not as causes but as revelaers of a self-deficit accumulated over decades. | entailed | contradicted |
| Systems Biology Meets Bowen  | abstract-generated | Michael Kerr presents a webinar exploring the convergence between systems biology and Bowen family systems theory, arguing that biological sciences are moving toward frameworks long familiar to Bowen theorists. | entailed | unsupported |
| Systems Biology Meets Bowen  | abstract-generated | Drawing on recent cancer research literature, particularly work by Marta Bertoluzzo and colleagues on niche reconstruction, Kerr examines how cancer arises not from driver genes alone but from breakdown of healthy tissue niches into cancer-permissive environments. | entailed | unsupported |
| Systems Biology Meets Bowen  | summary-generated | The presentation draws on three recent books on cancer research and theory, particularly the final chapter of *Rethinking Cancer*, to construct an argument that cancer prevention, detection, and treatment must shift from targeting cancer cells to restoring the tissue environments (niches) in which cancer arises. | entailed | unsupported |
| Systems Biology Meets Bowen  | overview | Cumulative allostatic load from chronic stress creates physiological conditions that permit cancer to arise and progress. | entailed | unsupported |
| Systems Biology Meets Bowen  | blog | This is the same argument that family systems thinking has made about human behavior for more than half a century. | entailed | unsupported |
| Systems Biology Meets Bowen  | blog | A mechanism of indirect coordination in which the actions of agents modify their shared environment in ways that influence the subsequent actions of other agents, enabling complex collective behavior without central direction. | entailed | unsupported |
| Where Roots Bowen Theory Res | abstract-generated | Kerr contends that Bowen theory represents a paradigm shift comparable to the transition from geocentric to heliocentric models of the solar system, and that recognizing the sources of its core concepts in fundamental physical and biological processes strengthens its theoretical foundation. | entailed | unsupported |
| Where Roots Bowen Theory Res | abstract-generated | Kerr begins by tracing the 2,000-year suppression of heliocentrism from Aristarchus through Copernicus, Kepler, Galileo, and Newton to Einstein, demonstrating how paradigm shifts face organized institutional resistance and require convergent evidence from multiple independent domains before displacing entrenched models. | entailed | unsupported |
| Where Roots Bowen Theory Res | blog | This means that the cost of differentiation work is not primarily intellectual. | entailed | unsupported |
| Why Families Repeat the Same | summary-generated | This process is not malicious; it feels like love and protection to those generating it. | entailed | unsupported |
| Why Families Repeat the Same | summary-generated | Kerr notes that by the early 1990s, statistics showed rising divorce rates and youth criminality—indicators that societal regression had already begun, roughly fifteen years after Bowen predicted it. | entailed | contradicted |
| Why Families Repeat the Same | summary-generated | Yet understanding the system, even without the power to alter it, has value: it reduces reactivity, provides orientation, and preserves the observer's functioning. | entailed | unsupported |
| Why Families Repeat the Same | summary-generated | The conversation ends where it began—with gratitude—as Kerr expresses hope that he will live long enough to witness societal change, a hope grounded not in optimism but in the differentiated capacity to observe, understand, and remain functional within systems larger than any individual can control. | entailed | unsupported |

### Newly accepted by Sonnet 5.5 (default)

| Talk | Artifact | Claim | 4.6 | 5.5 |
|---|---|---|---|---|
| Societal Emotional Process | overview | For family systems clinicians and students, this presentation offers a rare extended first-person account of what a rise in differentiation of self looks and feels like from the inside. | unsupported | entailed |
| Societal Emotional Process | overview | That distinction matters clinically: it illustrates how crisis can function as a catalyst rather than merely a stressor. | unsupported | entailed |
| Societal Emotional Process | overview | Michael Kerr presented this case in December 2021 to illustrate Bowen's claim that differentiation of self can rise through unusual life experience, not only through family-of-origin work. | unsupported | entailed |
| Societal Emotional Process | blog | They simply removed the last of the adaptive capacity that had been managing it. | unsupported | entailed |
| Systems Biology Meets Bowen  | summary-generated | This physiological cascade connects relational and psychological stress to cellular-level cancer progression through a continuous chain: chronic anxiety activates the stress response, which generates allostatic load—the cumulative physiological cost of sustained activation. | unsupported | entailed |
| Systems Biology Meets Bowen  | blog | For decades, cancer research operated on a straightforward premise: find the broken gene, fix the broken gene, stop the cancer. | unsupported | entailed |
| Systems Biology Meets Bowen  | blog | It was a logical approach, and it produced genuine discoveries. | unsupported | entailed |
| Systems Biology Meets Bowen  | blog | If anyone had reason to trust the reductionist playbook, it was him. | unsupported | entailed |
| Systems Biology Meets Bowen  | blog | Then, in 2014, Weinberg said something that stopped the field in its tracks. | unsupported | entailed |
| Systems Biology Meets Bowen  | blog | That kind of reckoning, from that kind of source, is rare in science. | unsupported | entailed |
| Systems Biology Meets Bowen  | blog | The problem was not that this research was wrong. | unsupported | entailed |
| Systems Biology Meets Bowen  | blog | It was that it was incomplete in ways that only became visible over time. | unsupported | entailed |
| Systems Biology Meets Bowen  | blog | Something was being missed. | unsupported | entailed |
| Systems Biology Meets Bowen  | blog | Mena Bissell, a researcher at Lawrence Berkeley National Laboratory whose work Kerr highlighted in his lecture, spent years demonstrating exactly this. | contradicted | entailed |
| Systems Biology Meets Bowen  | blog | They are looking at the parts when the explanation lives in the pattern. | unsupported | entailed |
| Systems Biology Meets Bowen  | blog | These are not minor theoretical refinements. | unsupported | entailed |
| Systems Biology Meets Bowen  | blog | They represent a different way of asking the question. | unsupported | entailed |
| Systems Biology Meets Bowen  | blog | The Extended Evolutionary Synthesis, which Kerr discussed in his lecture, formalizes this broader view at the level of evolutionary biology. | unsupported | entailed |
| Systems Biology Meets Bowen  | blog | The convergence is not coincidental. | unsupported | entailed |
| Systems Biology Meets Bowen  | blog | One of the most striking sections of Kerr's lecture addressed the role of chronic stress in cancer progression — a connection that has historically been underemphasized in oncology research but is now gaining serious scientific attention. | unsupported | entailed |
| Systems Biology Meets Bowen  | blog | Chronic anxiety — the kind that is embedded in relational patterns across generations — is one of the primary drivers of sustained stress-response activation. | unsupported | entailed |
| Where Roots Bowen Theory Res | abstract-generated | Abstract - Where Roots of Bowen Theory Reside in the Brain (June video) | unsupported | entailed |
| Where Roots Bowen Theory Res | overview | Kerr opens by reviewing the 2,000-year suppression of heliocentrism from Aristarchus through Einstein, using this arc as a model for how paradigm shifts face resistance before eventual vindication. | contradicted | entailed |
| Where Roots Bowen Theory Res | overview | The extended Q&A, involving participants Amy Post, Dave Galloway, Kathy Kerr, and Janice Norton, focuses on chronic anxiety as the central disruptor of differentiation — examining it at cellular, organismic, familial, and individual levels simultaneously. | unsupported | entailed |
| Where Roots Bowen Theory Res | overview | Clinicians and students who understand this material gain a framework for situating Bowen theory within a broader scientific context. | unsupported | entailed |
| Where Roots Bowen Theory Res | overview | Knowing that the individuality and togetherness life forces may have roots in cellular differentiation versus state-holding dynamics — as Bertolaso's cancer research suggests — makes those forces feel less abstract and more grounded in observable biological processes. | unsupported | entailed |
| Where Roots Bowen Theory Res | overview | The neuroscience material is equally practical. | unsupported | entailed |
| Where Roots Bowen Theory Res | overview | Understanding that determination is a locatable neural function within the salience network — and that chronic anxiety competes directly with it — gives clinicians a concrete way to think about why sustained effort toward differentiation of self is difficult and what is happening in the brain when it succeeds or fails. | unsupported | entailed |
| Where Roots Bowen Theory Res | overview | Dopamine drives the wanting circuit independently of the liking circuit, with direct implications for understanding driven behavior in family emotional systems. | unsupported | entailed |
| Where Roots Bowen Theory Res | overview | A Stanford electrode implantation study located a specific neural node for determination within the salience network. | contradicted | entailed |
| Where Roots Bowen Theory Res | blog | A nine-year-old boy with a brain tumor fired his family therapist, directed his own treatment through visualization and peer support, and survived. | contradicted | entailed |
| Where Roots Bowen Theory Res | blog | A Stanford research team accidentally discovered that the feeling driving that kind of behavior — not fear, not dread, but the specific positive urge to *push harder and keep going* — can be located in a single anatomical node inside the brain. | contradicted | entailed |
| Where Roots Bowen Theory Res | blog | These two facts, one clinical and one neuroscientific, turn out to be about the same thing. | unsupported | entailed |
| Where Roots Bowen Theory Res | blog | And for anyone working with family systems — whether as a therapist, a researcher, or someone trying to change their own patterns — the implications are worth sitting with carefully. | unsupported | entailed |
| Where Roots Bowen Theory Res | blog | Understanding that competition may be one of the most practically useful things a person working in family systems can do. | unsupported | entailed |
| Where Roots Bowen Theory Res | blog | The determination node, in that framing, is what gets activated when the wall is finally reached. | unsupported | entailed |
| Where Roots Bowen Theory Res | blog | Two threads in the Q&A pushed the determination finding beyond the clinical and into something more vivid. | unsupported | entailed |
| Where Roots Bowen Theory Res | blog | And at a certain point, he told his parents to keep going to family therapy — and stopped attending himself. | contradicted | entailed |
| Where Roots Bowen Theory Res | blog | Neuroscience now has a name for what that nine-year-old was running on. | unsupported | entailed |
| Where Roots Bowen Theory Res | blog | And a location for it in the brain. | unsupported | entailed |
| Where Roots Bowen Theory Res | blog | The picture that emerges from Kerr's lecture, the electrode study, and the Q&A discussion is not comfortable, but it is clarifying. | unsupported | entailed |
| Where Roots Bowen Theory Res | blog | That determination is produced by a specific node in the emotional salience network. | unsupported | entailed |
| Where Roots Bowen Theory Res | blog | It is a matter of having enough determination available — enough activation of that specific node — to sustain forward movement in the face of a system that is continuously pulling toward the familiar equilibrium. | unsupported | entailed |
| Why Families Repeat the Same | summary-generated | Kerr illustrates this through a sailboat incident: when his wife remained calm and non-reactive as he took the helm, she modeled differentiation in real time. | contradicted | entailed |
| Why Families Repeat the Same | overview | For a reader who understands this material, the practical stakes are concrete. | unsupported | entailed |

## Cost

Baseline $1.20; Sonnet 5.5 default $1.31; medium $1.09 (each: 3 runs + real prose; 4.6 one
run). Earlier interrupted runs added roughly $1. Total about $4.60.

## Decision and switch (JC.6, 2026-10-10)

Author decision: "switch, default effort". `FAITHFULNESS_JUDGE_MODEL` and
`THEME_JUDGE_MODEL` = `claude-sonnet-5-5`, `JUDGE_EFFORT` = None (model default, high);
`JUDGE_LOGIC_VERSION` = 2026-10-10 so no cached Sonnet 4.6 verdict is reused; pins in
`tests/test_judge_model_pin.py` updated (model and effort). The blog's second stage uses
the theme judge, so it moved too. Live check after the switch (production config):
roots_bowen PASS, where_roots FAIL, dave_g FAIL, injected fabrication caught.
Accepted trade-off: Sonnet 5.5 is more lenient than 4.6 on the writer's own framing
(k6; 45 real-prose claims newly accepted). The key-terms judge (disabled) stays on 4.6.
