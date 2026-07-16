# M3 spec coverage — structured intermediates + schema contracts

Spec: [`spec_unattended_robustness_2026-07-15.md`](spec_unattended_robustness_2026-07-15.md) §M3.
Scope decision (2026-07-15): codec layer first — markdown stays the wire format,
JSON is a derived sidecar, generation prompts unchanged. U4 (every boundary
schema-validated, drift is a hard error not a silent zero) is delivered by this
layer regardless of wire format.

## Acceptance criteria → tests

| AC | Requirement | Status | Verified by |
|----|-------------|--------|-------------|
| **M3.A** | JSON Schema per structured boundary, versioned, in `schemas/` | ✅ done | `schemas/{bowen,emphasis,key_terms,topics,themes,abstract_input}.schema.json`; `test_artifact_contracts.py::test_m3a_schemas_valid_and_versioned` |
| **M3.B.1** | Producer whose output violates the schema records ERROR, does not save a malformed artifact | ✅ done | Producer self-check: `artifact_contracts.verify_saved_artifact` + `extraction_pipeline._self_validate_saved_summary`; `test_artifact_contracts.py::test_m3b1_verify_saved_artifact_errors_on_drift_no_sidecar`, `::test_m3b_save_summary_drift_leaves_file_no_sidecar`; abstract-input: `abstract_pipeline.prepare_abstract_input` + `::test_abstract_input_empty_topic_name_fails_closed` |
| **M3.C.1** | Round-trip on a real sample: `parse(save(obj)) == obj` for every boundary | ✅ done | `test_artifact_contracts.py::test_m3c1_roundtrip_real_samples` (param per boundary, incl. H3 themes) — field-level equality on real fixtures |
| **M3.C.2** | A corrupted/old-format artifact yields a schema error, not empty | ✅ done | `test_artifact_contracts.py::test_m3c2_drift_is_error_not_silent_zero`, `::test_all_headers_no_body_is_drift_not_empty`; gate: `test_release_gate.py::test_m3c2_drifted_bowen_artifact_blocks`, `::test_m3c2_all_headers_no_body_bowen_blocks`, `::test_m3c2_drifted_boundary_blocks` (emphasis/key-terms/topics) |
| **M3.D.1** | Real legacy markdown artifacts load into the schema | ✅ done | `test_artifact_contracts.py::test_m3d1_legacy_markdown_migrates` (all real `where_roots` + `societal_emotional` + H3 `monika_h3_themes` fixtures); `::test_themes_migrates_both_bold_and_h3_numbered_formats` |

## Consumer-side gate (U4)

`release_gate.check_artifact_contracts` validates every on-disk structured
artifact in `_CONTRACT_ARTIFACTS` (bowen, emphasis, key-terms, topics, both
themes) through the codec; drift → `Verdict(ERROR)` → **BLOCK**
(`config.GATE_BLOCKING_CHECKS` includes `artifact_contracts`). A legitimately
empty artifact (bare H1/H2 header, no body) validates as an empty object and
passes. Real-run PASS: `test_release_gate.py::test_m3c_all_wired_boundaries_pass_on_real_run`.

## Real-data safety (P6) before hard-blocking

A drive sweep validated the codec against **every** structured artifact across all
6 real projects before each boundary became a hard blocker: bowen/emphasis/
key-terms/topics/interpretive-themes 0-fail; structural-themes surfaced one real
`### N.` (H3) file the bold-only parser missed — the migration shim was extended
to read both formats, after which the sweep is 0-fail across all boundaries.

## Empty-vs-drift discriminant

`artifact_contracts._has_body`: H1/H2 section headers are scaffolding (benign
empty); H3+ item headers or any non-heading line with zero parsed items are drift.
100% mutation-killed.

## Not covered / deferred (see TODO.md § "M3 schema contracts")

- Themes `number` is positional (the literal `**N.**`/`### N.` label isn't
  captured — no consumer reads it).
- JSON sidecar is write-only so far (durable provenance; no consumer prefers it yet).
- Two adjacent, non-M3 issues flagged: emphasis all-items-content-rejected raw
  fallback; a whitespace-only topic-name edge in strategy-1 topic parsing.
