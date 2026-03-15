import config
import validation_learning
from ts_gui import (
    _build_context_phrase,
    _build_full_correction_text,
    _collect_validation_review_actions,
    _extract_compact_terms,
    _is_simple_dictionary_candidate,
    _prepare_review_finding,
)


class DummyVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def test_validation_memory_promotes_rejected_pairs(tmp_path):
    memory_path = tmp_path / "validation_memory.json"
    memory = validation_learning.ValidationLearningMemory(
        path=memory_path,
        promotion_threshold=2,
    )

    memory.record_rejection("Bowenion", "Bowenian", reason="domain spelling")
    memory.record_rejection("Bowenion", "Bowenian", reason="domain spelling")
    memory.save()

    reloaded = validation_learning.ValidationLearningMemory(
        path=memory_path,
        promotion_threshold=2,
    )
    assert reloaded.is_blocked("Bowenion", "Bowenian")
    assert "bowenion->bowenian" in reloaded.blocked_pairs
    assert "bowenion->bowenian" not in reloaded.pending_rejections


def test_filter_validation_findings_respects_approved_terms_and_memory(tmp_path, monkeypatch):
    approved_terms_path = tmp_path / "approve_terms.txt"
    approved_terms_path.write_text("Bowenian\n", encoding="utf-8")

    memory_path = tmp_path / "validation_memory.json"
    memory = validation_learning.ValidationLearningMemory(
        path=memory_path,
        promotion_threshold=1,
    )
    memory.record_rejection("Differentiation of self", "Differentiation-of-self")
    memory.save()

    monkeypatch.setattr(validation_learning, "_approved_terms_path", lambda: approved_terms_path)
    monkeypatch.setattr(validation_learning, "_memory_path", lambda: memory_path)

    findings = [
        {
            "original_text": "Bowenian",
            "suggested_correction": "Bowenion",
            "reasoning": "Name spelling",
        },
        {
            "original_text": "Differentiation of self",
            "suggested_correction": "Differentiation-of-self",
            "reasoning": "Hyphenation",
        },
        {
            "original_text": "triangle process",
            "suggested_correction": "triangles process",
            "reasoning": "Grammar",
        },
    ]

    filtered = validation_learning.filter_validation_findings(findings)

    assert filtered.suppressed_by_approved_terms == 1
    assert filtered.suppressed_by_memory == 1
    assert filtered.suppressed_by_error_type == 0
    assert filtered.findings == [findings[2]]


def test_filter_validation_findings_injects_aliases(tmp_path, monkeypatch):
    approved_terms_path = tmp_path / "approve_terms.txt"
    approved_terms_path.write_text("Bowenion = Bowenian\n", encoding="utf-8")
    memory_path = tmp_path / "validation_memory.json"

    monkeypatch.setattr(validation_learning, "_approved_terms_path", lambda: approved_terms_path)
    monkeypatch.setattr(validation_learning, "_memory_path", lambda: memory_path)

    filtered = validation_learning.filter_validation_findings(
        [
            {
                "error_type": "proper_noun",
                "original_text": "Bowenion",
                "suggested_correction": "Bowenian",
                "reasoning": "Known alias pair",
            }
        ],
        transcript_text="Bowenion described emotional cutoff in this talk.",
    )

    assert filtered.injected_aliases == 0
    assert filtered.suppressed_by_error_type == 0
    assert filtered.suppressed_by_alias_dictionary == 1
    assert filtered.findings == []


def test_runtime_terms_file_path_is_used(tmp_path):
    original_path = config.VALIDATION_APPROVED_TERMS_PATH
    custom_terms_path = tmp_path / "custom_terms.txt"
    custom_terms_path.write_text("Bowenion = Bowenian\n", encoding="utf-8")

    try:
        config.set_validation_approved_terms_path(custom_terms_path)
        filtered = validation_learning.filter_validation_findings(
            [
                {
                    "error_type": "proper_noun",
                    "original_text": "Bowenion",
                    "suggested_correction": "Bowenian",
                    "reasoning": "Known alias pair",
                }
            ],
            transcript_text="Bowenion appears in this transcript.",
        )
    finally:
        config.set_validation_approved_terms_path(original_path)

    assert filtered.suppressed_by_alias_dictionary == 1
    assert filtered.findings == []


def test_append_approved_terms_deduplicates_normalized_values(tmp_path):
    approved_terms_path = tmp_path / "approve_terms.txt"
    approved_terms_path.write_text("Bowen theory\n", encoding="utf-8")

    added = validation_learning.append_approved_terms(
        ["  Bowen   theory  ", "Family projection process", ""],
        path=approved_terms_path,
    )

    assert added == 1
    assert approved_terms_path.read_text(encoding="utf-8").splitlines() == [
        "Bowen theory",
        "Family projection process",
    ]


def test_append_validation_aliases_deduplicates_existing_pairs(tmp_path):
    approved_terms_path = tmp_path / "approve_terms.txt"
    approved_terms_path.write_text("Bowenion = Bowenian\n", encoding="utf-8")

    added = validation_learning.append_validation_aliases(
        [
            ("Bowenion", "Bowenian"),
            ("triangeling", "triangling"),
        ],
        path=approved_terms_path,
    )

    assert added == 1
    assert approved_terms_path.read_text(encoding="utf-8").splitlines() == [
        "Bowenion = Bowenian",
        "triangeling = triangling",
    ]


def test_replace_alias_occurrences_replaces_all_token_matches():
    updated, count = validation_learning.replace_alias_occurrences(
        "Bowenion taught Bowenion theory. Bowenionic stays untouched.",
        "Bowenion",
        "Bowenian",
    )

    assert count == 2
    assert updated == "Bowenian taught Bowenian theory. Bowenionic stays untouched."


def test_filter_validation_findings_drops_disallowed_error_types():
    filtered = validation_learning.filter_validation_findings(
        [
            {
                "error_type": "grammar",
                "original_text": "He lead the group yesterday",
                "suggested_correction": "He led the group yesterday",
                "reasoning": "Tense correction",
            },
            {
                "error_type": "spelling",
                "original_text": "Differenciation of self",
                "suggested_correction": "Differentiation of self",
                "reasoning": "Known domain spelling",
            },
        ]
    )

    assert filtered.suppressed_by_error_type == 1
    assert filtered.findings == [
        {
            "error_type": "spelling",
            "original_text": "Differenciation of self",
            "suggested_correction": "Differentiation of self",
            "reasoning": "Known domain spelling",
        }
    ]


def test_extract_compact_terms_reduces_context_to_changed_span():
    compact_original, compact_suggested = _extract_compact_terms(
        "thus alienated both the Popee and the Jesuits",
        "thus alienated both the Pope and the Jesuits",
    )

    assert compact_original == "Popee"
    assert compact_suggested == "Pope"


def test_build_full_correction_text_reconstructs_context():
    rebuilt = _build_full_correction_text(
        "thus alienated both the Popee and the Jesuits",
        "Popee",
        "Pope",
    )

    assert rebuilt == "thus alienated both the Pope and the Jesuits"


def test_build_context_phrase_returns_local_snippet():
    snippet = _build_context_phrase(
        "thus alienated both the Popee and the Jesuits in the dispute",
        "Popee",
    )

    assert snippet == "thus alienated both the Popee and the Jesuits in"


def test_is_simple_dictionary_candidate_rejects_phrase_rewrites():
    finding = {
        "error_type": "proper_noun",
        "original_text": "Galileo, Denier is",
        "suggested_correction": "Galileo and the Deniers",
    }

    compact_original, compact_suggested = _extract_compact_terms(
        finding["original_text"],
        finding["suggested_correction"],
    )

    assert compact_original == "Galileo, Denier is"
    assert compact_suggested == "Galileo and the Deniers"
    assert not _is_simple_dictionary_candidate(
        finding,
        compact_original,
        compact_suggested,
    )
    assert _prepare_review_finding(finding) is None


def test_is_simple_dictionary_candidate_accepts_single_word_proper_noun():
    finding = {
        "error_type": "proper_noun",
        "original_text": "Taiko",
        "suggested_correction": "Tycho",
    }

    compact_original, compact_suggested = _extract_compact_terms(
        finding["original_text"],
        finding["suggested_correction"],
    )

    assert _is_simple_dictionary_candidate(
        finding,
        compact_original,
        compact_suggested,
    )


def test_collect_validation_review_actions_auto_saves_dictionary_entries():
    finding_apply = {
        "original_text": "thus alienated both the Popee and the Jesuits",
        "suggested_correction": "thus alienated both the Pope and the Jesuits",
        "reasoning": "Spelling",
        "display_original": "Popee",
        "display_suggested": "Pope",
    }
    finding_reject = {
        "original_text": "Bowenion",
        "suggested_correction": "Bowenian",
        "reasoning": "Name spelling",
        "display_original": "Bowenion",
        "display_suggested": "Bowenian",
    }

    actions = _collect_validation_review_actions(
        [
            {
                "apply": DummyVar(True),
                "correction": DummyVar("Pope"),
                "display_original": "Popee",
                "original_finding": finding_apply,
            },
            {
                "apply": DummyVar(False),
                "correction": DummyVar("Bowenian"),
                "display_original": "Bowenion",
                "original_finding": finding_reject,
            },
        ]
    )

    corrections, rejected_findings, approved_terms, aliases = actions
    assert corrections == [
        {
            **finding_apply,
            "suggested_correction": "thus alienated both the Pope and the Jesuits",
        }
    ]
    assert rejected_findings == [{**finding_reject, "suggested_correction": "Bowenian"}]
    assert approved_terms == ["Pope"]
    assert aliases == [("Popee", "Pope")]
