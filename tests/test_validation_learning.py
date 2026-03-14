import validation_learning
from ts_gui import _collect_validation_review_actions


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
        [],
        transcript_text="Bowenion described emotional cutoff in this talk.",
    )

    assert filtered.injected_aliases == 1
    assert filtered.suppressed_by_error_type == 0
    assert filtered.findings == [
        {
            "error_type": "alias",
            "original_text": "Bowenion",
            "suggested_correction": "Bowenian",
            "confidence": "high",
            "reasoning": (
                "Deterministic alias from approve_terms.txt: "
                "Bowenion = Bowenian"
            ),
        }
    ]


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


def test_collect_validation_review_actions_splits_apply_reject_and_approve():
    finding_apply = {
        "original_text": "teh family",
        "suggested_correction": "the family",
        "reasoning": "Spelling",
    }
    finding_reject = {
        "original_text": "Bowenion",
        "suggested_correction": "Bowenian",
        "reasoning": "Name spelling",
    }

    actions = _collect_validation_review_actions(
        [
            {
                "apply": DummyVar(True),
                "approve_term": DummyVar(False),
                "save_alias": DummyVar(True),
                "correction": DummyVar("the family"),
                "original_finding": finding_apply,
            },
            {
                "apply": DummyVar(False),
                "approve_term": DummyVar(True),
                "save_alias": DummyVar(False),
                "correction": DummyVar("Bowenian"),
                "original_finding": finding_reject,
            },
        ]
    )

    corrections, rejected_findings, approved_terms, aliases = actions
    assert corrections == [{**finding_apply, "suggested_correction": "the family"}]
    assert rejected_findings == [{**finding_reject, "suggested_correction": "Bowenian"}]
    assert approved_terms == ["Bowenion"]
    assert aliases == [("teh family", "the family")]
