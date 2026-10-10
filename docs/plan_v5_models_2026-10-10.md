# Plan: run the pipeline on the Claude 5 models (MV.1–MV.8)

Status: approved and implemented 2026-10-10. Request (2026-10-10): "fix this so I can set the models to
the v5 series … leave the option for temperature and thinking levels."

## What breaks today on a 5-family model

Verified live on 2026-10-10 (judge prompt, Kerr transcript):
- `temperature` → HTTP 400 "`temperature` is deprecated for this model" on
  claude-opus-5-5 and claude-sonnet-5-5 (also documented for Fable 5.1 / Haiku 5.5
  non-default values). `call_claude_with_retry` always sends it.
- Thinking is on by default on 5-family models and the reply starts with a
  `thinking` block. `validate_api_response` rejects any reply whose first block is
  not text, and 17 call sites read `message.content[0].text`.
- Thinking tokens count toward `max_tokens`; several calls use 4096 (judge, summary),
  so a long think can truncate the answer.
- New `stop_reason: "refusal"` is treated as "Unexpected stop_reason".
- `model_specs.PRICING` has no 5-family entries, so the GUI model lists do not offer
  them and the cost estimate falls back to Sonnet 3.5 prices.

## Acceptance criteria and tests

- **MV.1 Model capabilities in one table** — `model_specs.MODEL_CAPABILITIES`
  (+ `capabilities(model)` with family fallback): accepts `temperature`; thinking
  style (`budget` for Haiku 4.5 and older, `adaptive` for 4.6, `always` for 5-family);
  effort levels supported and default; max output tokens. Pricing for
  claude-haiku-5-5, claude-sonnet-5-5, claude-opus-5-5, claude-fable-5-1,
  claude-opus-5, claude-sonnet-5. Editorial/model data lives in model_specs/config,
  not in call sites.
  - Tests: `tests/test_v5_models.py::test_mv1_capabilities_known_models`,
    `test_mv1_unknown_v5_name_uses_family_defaults`, `test_mv1_pricing_present`.
- **MV.2 One request builder** — `transcript_utils.model_request_params(model,
  temperature)` returns the model-specific fields: `temperature` only where accepted
  (otherwise dropped, logged once per model); `output_config.effort` from the effort
  setting (MV.6) when the model supports that level; nothing that 400s. Used by
  `call_claude_with_retry` for both streaming and non-streaming calls.
  - Tests: `test_mv2_v5_request_has_no_temperature`, `test_mv2_v4_keeps_temperature`,
    `test_mv2_effort_sent_only_when_supported`.
- **MV.3 Read the answer, not the first block** — `transcript_utils.response_text(message)`
  joins all `text` blocks (thinking blocks ignored); `validate_api_response` requires
  at least one text block instead of `content[0]` being text; every
  `content[0].text` call site (17) uses `response_text`.
  - Tests: `test_mv3_thinking_then_text_is_valid`, `test_mv3_no_text_block_rejected`,
    `test_mv3_no_content0_text_left` (source scan, excludes tests).
- **MV.4 Room for thinking** — for models that think, `max_tokens` gets
  `config.THINKING_TOKEN_HEADROOM` added (capped at the model's max output), so a
  4096-token answer budget is still 4096 tokens of answer. Long requests already
  stream.
  - Test: `test_mv4_headroom_added_and_capped`.
- **MV.5 Refusals** — `stop_reason: "refusal"` raises a named `RefusalError` (with
  `stop_details` category), not retried as-is. For claude-opus-5-5, claude-sonnet-5-5
  and claude-fable-5-1 the request opts into server-side fallbacks
  (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`) unless
  `config.REFUSAL_FALLBACKS_ENABLED` is False; Haiku 5.5 has no server-side fallback.
  - Tests: `test_mv5_refusal_raises_named_error`, `test_mv5_fallback_only_for_supported_models`.
- **MV.6 Keep temperature and thinking-level options** — temperatures stay as they
  are (config TEMP_*) and are used on models that accept them. New setting
  `EFFORT` ("model default" | low | medium | high | xhigh | max), persisted in
  runtime settings and chosen in the GUI next to the model lists; on 5-family models
  it is the thinking-level control (thinking cannot be switched off on Opus 5.5 /
  Fable 5.1). Unsupported level for a model → omitted with a log line, never a 400.
  - Tests: `test_mv6_effort_setting_persists`, `test_mv6_gui_effort_choices`.
- **MV.7 Model lists** — GUI model dropdowns list the 5-family models (from PRICING).
  `find_available_models.py` probes without `temperature`.
  - Tests: `test_mv7_v5_in_model_list`, `test_mv7_probe_has_no_temperature`.
- **MV.8 Live check (opt-in, costs cents)** — `tests/test_v5_models_live.py`, run only
  with `RUN_LIVE_API=1`: one short call per 5-family model through
  `call_claude_with_retry`, plus the caching beta header, must succeed.
  - Test: `test_mv8_live_call_each_v5_model`.

## Not changed (decision for you)

- Defaults stay on the 4.6 models; you pick 5-family models in the GUI.
- The faithfulness, theme and key-term judges stay on claude-sonnet-4-6
  (config constants). Switching a judge needs the gold-set re-calibration first;
  the 2026-10-10 spot test favours claude-sonnet-5-5. Separate step.

## Order

MV.1 → MV.3 → MV.2 → MV.4 → MV.5 → MV.6 → MV.7 → MV.8; tests first for each; full
suite; learning-qa sweep; CHANGELOG; push.

## Adjacent issues found, not fixed

- `ANTHROPIC_CACHE_BETA_HEADER = "prompt-caching-2024-07-31"` is an obsolete beta
  (caching is GA). MV.8 checks it is still accepted; removing it is a separate change.

## Sweep (learning-qa, 2026-10-10) — 6 findings, all fixed

- Judges no longer follow the GUI Effort setting: they send `config.JUDGE_EFFORT`
  (None), which is also part of the judge cache logic version.
- The output-critic skill script's two `content[0].text` sites use `response_text`;
  the source scan now covers every `.py` outside tests/.venv/.claude.
- `formatting_max_tokens` reads the capability table for 5-family models and leaves
  `THINKING_TOKEN_HEADROOM` for thinking.
- A refusal-fallback answer is priced at the model that served it and logged.
- The cost estimate adds thinking tokens for 5-family models by effort
  (`config.THINKING_TOKENS_ESTIMATE`).
- The once-per-model notices use the module logger when none is passed.
Live (`pytest --live-api tests/test_v5_models_live.py`): 5 passed on 2026-10-10.
