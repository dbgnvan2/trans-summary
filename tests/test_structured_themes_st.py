"""ST — the theme stages return JSON that must match a schema, and the pipeline writes
the markdown file from it in one layout (docs/plan_structured_themes_2026-10-14.md).
No model calls: the request tests use a fake client with the real request builder."""
import copy
import json

import pytest

import artifact_contracts as ac
from artifact_contracts import SchemaError


def _structural(n=3):
    return {"version": "2", "artifact": "themes", "kind": "structural",
            "rationale": "Chosen because they cover the talk.",
            "items": [{"number": i, "title": f"Structural Theme {i}",
                       "description": f"What theme {i} is about.",
                       "key_evidence": [f"Section {i}: a quote", "Section 9: another"],
                       "coverage_role": "Spans about a third of the talk."}
                      for i in range(1, n + 1)]}


def _interpretive(n=5, nested=(1,)):
    return {"version": "2", "artifact": "themes", "kind": "interpretive",
            "rationale": "These derive from the structural themes.",
            "items": [{"number": i, "title": f"Interpretive Theme {i}",
                       "description": f"The dynamic in theme {i}.",
                       "nested_under": list(nested),
                       "key_evidence": [f"Section {i}: the speaker's example"],
                       "lens_fuel_value": "Enables lenses on reactivity."}
                      for i in range(1, n + 1)]}


# --------------------------------------------------------------------------- ST.1
def test_st1_full_objects_are_accepted():
    assert ac.check_structured_themes(_structural()) is not None
    assert ac.check_structured_themes(_interpretive(), structural_count=3) is not None
    # through the shared schema too (the codec's validate), alongside version 1
    ac.validate("themes", _structural())
    ac.validate("themes", _interpretive())
    ac.validate("themes", {"version": "1", "artifact": "themes", "kind": "structural",
                           "items": [{"number": 1, "name": "A", "description": "B"}]})


def test_st1_rationale_is_optional_in_the_saved_object():
    obj = _structural()
    del obj["rationale"]
    assert ac.check_structured_themes(obj) is obj


@pytest.mark.parametrize("field", ["title", "description", "key_evidence", "coverage_role"])
def test_st1_missing_required_field_rejected(field):
    obj = _structural()
    del obj["items"][1][field]
    with pytest.raises(SchemaError, match=field):
        ac.check_structured_themes(obj)


def test_st1_extra_field_rejected():
    obj = _structural()
    obj["items"][0]["summary"] = "a closing note"
    with pytest.raises(SchemaError, match="summary"):
        ac.check_structured_themes(obj)
    obj = _structural()
    obj["closing_paragraph"] = "a closing note"
    with pytest.raises(SchemaError, match="closing_paragraph"):
        ac.check_structured_themes(obj)


@pytest.mark.parametrize("bad", ["", "   ", "Title with **bold**", "Two\nlines"])
def test_st1_bad_title_rejected(bad):
    obj = _structural()
    obj["items"][0]["title"] = bad
    with pytest.raises(SchemaError, match="title"):
        ac.check_structured_themes(obj)


@pytest.mark.parametrize("field", ["description", "coverage_role"])
def test_st1_empty_text_rejected(field):
    obj = _structural()
    obj["items"][2][field] = " \n "
    with pytest.raises(SchemaError, match=field):
        ac.check_structured_themes(obj)


def test_st1_empty_evidence_rejected():
    obj = _structural()
    obj["items"][0]["key_evidence"] = []
    with pytest.raises(SchemaError, match="key_evidence"):
        ac.check_structured_themes(obj)
    obj["items"][0]["key_evidence"] = ["Section 1", ""]
    with pytest.raises(SchemaError, match="key_evidence"):
        ac.check_structured_themes(obj)


@pytest.mark.parametrize("numbers", [[1, 3, 2], [2, 3, 4], [1, 1, 2], [0, 1, 2]])
def test_st1_numbers_out_of_order_rejected(numbers):
    obj = _structural()
    for it, n in zip(obj["items"], numbers):
        it["number"] = n
    with pytest.raises(SchemaError, match="number"):
        ac.check_structured_themes(obj)


def test_st1_nested_under_missing_structural_theme_rejected():
    obj = _interpretive(nested=(1, 4))
    ac.check_structured_themes(obj, structural_count=4)
    with pytest.raises(SchemaError, match="no structural theme 4"):
        ac.check_structured_themes(obj, structural_count=3)
    obj = _interpretive(nested=())
    with pytest.raises(SchemaError, match="nested_under"):
        ac.check_structured_themes(obj, structural_count=3)


@pytest.mark.parametrize("title", ["Summary", "Conclusion", "Structural Themes (3 total)",
                                   "# Heading"])
def test_st1_scaffolding_title_rejected(title):
    """A title the theme parsers skip as a heading would vanish from the page."""
    obj = _structural()
    obj["items"][2]["title"] = title
    with pytest.raises(SchemaError, match="heading"):
        ac.check_structured_themes(obj)


def test_st1_kind_fields_do_not_mix():
    obj = _structural()
    obj["items"][0]["nested_under"] = [1]
    with pytest.raises(SchemaError):
        ac.check_structured_themes(obj)
    obj = _interpretive()
    obj["kind"] = "structural"
    with pytest.raises(SchemaError):
        ac.check_structured_themes(obj)


def test_st1_version_1_object_is_not_structured():
    with pytest.raises(SchemaError, match="version-2"):
        ac.check_structured_themes({"version": "1", "artifact": "themes", "kind": "structural",
                                    "items": [{"number": 1, "name": "A", "description": "B"}]})


# --------------------------------------------------------------------------- fake client
from types import SimpleNamespace

import config
import transcript_utils as tu


def _msg(text):
    return SimpleNamespace(
        type="message", role="assistant", stop_reason="end_turn", stop_details=None,
        model="claude-sonnet-5-5",
        content=[SimpleNamespace(type="thinking", thinking="..."),
                 SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5,
                              cache_creation_input_tokens=0, cache_read_input_tokens=0))


class _Client:
    """Fake Anthropic client: returns the replies in order (the last one repeats) and
    records each request's keyword arguments."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []
        outer = self

        def reply(kw):
            outer.requests.append(kw)
            n = min(len(outer.requests), len(outer.replies)) - 1
            return _msg(outer.replies[n])

        class _Messages:
            def create(self, **kw):
                return reply(kw)

            def stream(self, **kw):
                msg = reply(kw)

                class _Ctx:
                    def __enter__(self_inner):
                        return SimpleNamespace(get_final_message=lambda: msg)

                    def __exit__(self_inner, *a):
                        return False
                return _Ctx()

        self.messages = _Messages()


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(tu, "log_token_usage", lambda *a, **k: None)
    monkeypatch.setattr("time.sleep", lambda s: None)


# --------------------------------------------------------------------------- ST.2
def test_st2_request_has_format_and_effort(quiet):
    fmt = {"type": "json_schema", "schema": ac.themes_model_schema("structural")}
    client = _Client("{}")
    tu.call_claude_with_retry(client, "claude-sonnet-5-5", [{"role": "user", "content": "x"}],
                              max_tokens=1000, effort="medium", output_format=fmt,
                              stream=True, min_length=1)
    sent = client.requests[0]["extra_body"]["output_config"]
    assert sent == {"effort": "medium", "format": fmt}


def test_st2_format_without_effort(quiet):
    fmt = {"type": "json_schema", "schema": ac.themes_model_schema("interpretive")}
    client = _Client("{}")
    tu.call_claude_with_retry(client, "claude-sonnet-5-5", [{"role": "user", "content": "x"}],
                              max_tokens=1000, effort=None, output_format=fmt, min_length=1)
    assert client.requests[0]["extra_body"]["output_config"] == {"format": fmt}
    # and a request without a format is unchanged
    client = _Client("hello")
    tu.call_claude_with_retry(client, "claude-sonnet-5-5", [{"role": "user", "content": "x"}],
                              max_tokens=1000, effort="high", min_length=1)
    assert client.requests[0]["extra_body"]["output_config"] == {"effort": "high"}


def _walk(node):
    yield node
    if isinstance(node, dict):
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


@pytest.mark.parametrize("kind", ["structural", "interpretive"])
def test_st2_model_schema_matches_stored_fields(kind):
    """The model is asked for exactly the stored fields (one source), every object
    closes additionalProperties (the API requires it), and no keyword the API does not
    enforce is sent."""
    model = ac.themes_model_schema(kind)
    stored = ac.load_schema("themes")["$defs"][f"{kind}_theme"]
    item = model["properties"]["themes"]["items"]
    assert set(item["properties"]) == set(stored["properties"])
    assert item["required"] == stored["required"]
    assert model["required"] == ["themes", "rationale"]
    for node in _walk(model):
        if isinstance(node, dict):
            assert not set(node) & {"$ref", "minLength", "minimum", "minItems", "pattern"}
            if node.get("type") == "object":
                assert node["additionalProperties"] is False


# --------------------------------------------------------------------------- ST.4
import random
import re
from pathlib import Path

import faithfulness_judge as fj
from transcript_utils import extract_section

FIXTURES = Path(__file__).resolve().parent / "fixtures"
RATIONALE = "RATIONALE-MARKER: why these themes were chosen and how well they cover it."
# Text pieces that have broken the theme parsers or could: labels, headings, rules,
# list markers, roll-up counts, scaffolding words, quotes, line breaks.
_PIECES = ['Kerr said "the family is an emotional unit."', "Sections 3–4:", "a colon: here",
           "**bold** words", "# not a heading", "---", "(3 total)", "Summary", "Rationale",
           "1. numbered", "- dash", "ellipsis…", "back\\slash", "tab\there",
           "two\n\nparagraphs", "‘curly’", "Nested under structural theme(s): 2",
           "**Key evidence:** an inline label", "<b>html</b>", "50%", "### Heading",
           "**2. Not a theme**", "Closing paragraph: a note", "\n**Coverage / role:** x"]


def _text(rng, n=None):
    return " ".join(rng.choice(_PIECES) for _ in range(n or rng.randint(1, 6)))


def _title(rng, i):
    words = [p for p in _PIECES if "*" not in p and "\n" not in p and "total" not in p]
    return f"Theme {i}: " + " ".join(rng.choice(words) for _ in range(rng.randint(1, 3)))


def _reply_obj(rng, kind, n, structural_count=4):
    themes = []
    for i in range(1, n + 1):
        t = {"number": i, "title": _title(rng, i), "description": _text(rng),
             "key_evidence": [_text(rng, 2) for _ in range(rng.randint(1, 4))]}
        if kind == "structural":
            t["coverage_role"] = _text(rng)
        else:
            t["nested_under"] = sorted(rng.sample(range(1, structural_count + 1),
                                                  min(structural_count, rng.randint(1, 2))))
            t["lens_fuel_value"] = _text(rng)
        themes.append(t)
    return ac.structured_themes_from_reply(
        json.dumps({"themes": themes, "rationale": RATIONALE}), kind,
        structural_count if kind == "interpretive" else None)


def _expected_evidence(it):
    return "Key evidence: " + " ".join(f"- {e}" for e in it["key_evidence"])


def _assert_round_trip(obj, structural=None):
    kind = obj["kind"]
    md = ac.themes_to_markdown(obj, structural)
    titles = [it["title"] for it in obj["items"]]
    # the judge's parser: titles, descriptions and evidence exactly
    assert tu.parse_theme_blocks_with_evidence(md) == [
        (it["title"], it["description"], _expected_evidence(it)) for it in obj["items"]]
    # the page's parser: same themes, same numbers, nothing trimmed or unclassified
    blocks = tu.theme_display_blocks(md)
    assert [(int(n), name) for n, name, _ in blocks] == [(it["number"], it["title"])
                                                       for it in obj["items"]]
    assert tu.trimmed_theme_notes(md) == []
    assert tu.unclassified_theme_fields(md) == []
    # the format check (codec, release gate) and the judge input
    items = ac.codec("themes").parse_markdown(md, kind)["items"]
    assert [i["name"] for i in items] == titles
    judged = fj.with_theme_evidence(items, md)
    # the stage's own content check, and the section loader used by summarize-only runs
    heading = "Structural Themes" if kind == "structural" else "Interpretive Themes"
    import extraction_pipeline as ep
    assert ep._is_valid_section_content(heading, md)
    assert tu.parse_theme_blocks_with_evidence(extract_section(md, heading)) == \
        tu.parse_theme_blocks_with_evidence(md)
    # rationale never reaches a reader
    rationale = obj.get("rationale") or RATIONALE
    for reader_text in (md, tu.themes_for_prompt(md), json.dumps(judged),
                        json.dumps(blocks)):
        assert rationale not in reader_text
    return md


def test_st4_round_trip_generated():
    for seed in range(200):
        rng = random.Random(seed)
        structural = _reply_obj(rng, "structural", rng.randint(1, 4))
        _assert_round_trip(structural)
        interpretive = _reply_obj(rng, "interpretive", rng.randint(1, 8),
                                  len(structural["items"]))
        md = _assert_round_trip(interpretive, structural)
        # nested_under is shown with the structural titles
        first = interpretive["items"][0]["nested_under"][0]
        assert f"{first} ({structural['items'][first - 1]['title']})" in md


def _fixture_to_v2(text, kind):
    """A real theme file as the version-2 object the model would have returned."""
    themes = []
    for i, (_number, name, body) in enumerate(tu.theme_display_blocks(text), start=1):
        matches = list(tu._THEME_FIELD_RE.finditer(body))
        fields = {m.group(1).strip().lower(): body[m.end():(matches[j + 1].start()
                  if j + 1 < len(matches) else len(body))].strip()
                  for j, m in enumerate(matches)}
        evidence = fields["key evidence"]
        bullets = [ln[2:] for ln in evidence.split("\n") if ln.startswith("- ")]
        t = {"number": i, "title": name, "description": fields["description"],
             "key_evidence": bullets if len(bullets) == len(evidence.split("\n"))
             else [evidence]}
        if kind == "structural":
            t["coverage_role"] = fields["coverage / role"]
        else:
            nested = next(v for k, v in fields.items() if k.startswith("nested under"))
            t["nested_under"] = [n for n in sorted({int(x) for x in re.findall(r"\d+", nested)})
                                 if n <= 4] or [1]
            t["lens_fuel_value"] = fields["lens fuel value"]
        themes.append(t)
    return ac.structured_themes_from_reply(
        json.dumps({"themes": themes, "rationale": RATIONALE}), kind)


THEME_FIXTURES = sorted(FIXTURES.rglob("*themes*.md"))


@pytest.mark.parametrize("path", THEME_FIXTURES, ids=lambda p: str(p.relative_to(FIXTURES)))
def test_st4_round_trip_real_fixtures(path):
    kind = "structural" if "structural" in path.name else "interpretive"
    obj = _fixture_to_v2(path.read_text(encoding="utf-8"), kind)
    assert obj["items"]
    _assert_round_trip(obj)


def test_st4_v1_objects_still_render_as_before():
    obj = {"version": "1", "artifact": "themes", "kind": "structural",
           "items": [{"number": 1, "name": "A", "description": "B"}]}
    assert ac.themes_to_markdown(obj) == "## Structural Themes\n\n**1. A**\n**Description:** B\n"


def test_st4_last_field_starting_with_hash_is_kept():
    """The last theme's last field may begin with "# " (ST review of the trimming code:
    ``^`` matched the start of the value, so the page lost the field's text)."""
    obj = _structural(2)
    obj["items"][1]["coverage_role"] = "# 1 theme in the talk: spans most of it."
    md = ac.themes_to_markdown(obj)
    assert tu.trimmed_theme_notes(md) == []
    assert "# 1 theme in the talk" in tu.theme_display_blocks(md)[1][2]


def test_st4_heading_after_last_field_still_cut_in_h3_format():
    """In the old ``### N.`` format a later ``### Summary Paragraph`` stays inside the
    last theme's block; the anchor change above must still cut it (TD)."""
    md = ("## Structural Themes\n\n### 1. First\n**Description:** One.\n"
          "**Coverage / role:** Most of it.\n\n### 2. Second\n**Description:** Two.\n"
          "**Coverage / role:** The rest.\n\n### Summary Paragraph\nWhy these were chosen.\n")
    assert tu.trimmed_theme_notes(md) == [("Second", "heading after the last field")]
    assert "Why these" not in tu.theme_display_blocks(md)[1][2]


# --------------------------------------------------------------------------- ST.3
import logging

import extraction_pipeline as ep


def _reply(kind, n=3, **change):
    obj = _structural(n) if kind == "structural" else _interpretive(n)
    themes = obj["items"]
    for key, value in change.items():
        themes[0][key] = value
    return json.dumps({"themes": themes, "rationale": "notes"})


def _run(monkeypatch, kind, *replies, structural=None):
    client = _Client(*replies)
    monkeypatch.setattr(ep, "get_anthropic_client", lambda: client)
    result = ep._generate_structured_themes(kind, "claude-sonnet-5-5", logging.getLogger("st"),
                                            "SYSTEM", structural=structural)
    return result, client


def test_st3_invalid_reply_retried_then_fails(quiet, monkeypatch):
    bad = ["not json at all", _reply("structural", title=""),
           _reply("structural", number=2)]
    with pytest.raises(ValueError) as err:
        _run(monkeypatch, "structural", *bad)
    assert "number" in str(err.value)  # the last attempt's reason


def test_st3_retries_count_and_last_error(quiet, monkeypatch):
    client = _Client("{not json", _reply("structural", title=""), _reply("structural", number=5))
    monkeypatch.setattr(ep, "get_anthropic_client", lambda: client)
    with pytest.raises(ValueError):
        ep._generate_structured_themes("structural", "claude-sonnet-5-5",
                                       logging.getLogger("st"), "SYSTEM")
    assert len(client.requests) == config.MAX_RETRIES


def test_st3_valid_reply_after_a_bad_one(quiet, monkeypatch):
    (obj, md), client = _run(monkeypatch, "structural", "{not json", _reply("structural"))
    assert len(client.requests) == 2
    assert [it["title"] for it in obj["items"]] == ["Structural Theme 1", "Structural Theme 2",
                                                    "Structural Theme 3"]
    assert md == ac.themes_to_markdown(obj)
    req = client.requests[-1]
    assert req["extra_body"]["output_config"]["format"] == {
        "type": "json_schema", "schema": ac.themes_model_schema("structural")}
    assert req["system"]  # the cached transcript is sent


def test_st3_interpretive_checks_nested_under_against_structural(quiet, monkeypatch):
    structural = _structural(2)
    dangling = _reply("interpretive", nested_under=[3])
    with pytest.raises(ValueError, match="no structural theme 3"):
        _run(monkeypatch, "interpretive", dangling, structural=structural)
    (obj, md), client = _run(monkeypatch, "interpretive", dangling, _reply("interpretive"),
                             structural=structural)
    assert len(client.requests) == 2
    # the prompt carries the rendered structural themes, without their rationale
    content = client.requests[-1]["messages"][0]["content"]
    prompt = content if isinstance(content, str) else "".join(b["text"] for b in content)
    assert "**1. Structural Theme 1**" in prompt
    assert structural["rationale"] not in prompt
    assert "1 (Structural Theme 1)" in md


def test_st3_interpretive_needs_structural(monkeypatch):
    with pytest.raises(ValueError, match="structural"):
        ep._generate_structured_themes("interpretive", "m", logging.getLogger("st"), "S")


# --------------------------------------------------------------------------- ST.6
@pytest.mark.parametrize("kind", ["structural", "interpretive"])
def test_st6_prompts_describe_fields(kind):
    """The prompt names every field the schema asks for and the rationale, and has no
    layout or closing-paragraph instruction left (the cause of the label drift)."""
    text = (config.PROMPTS_DIR / getattr(config, ep._THEME_PROMPTS[kind])).read_text(
        encoding="utf-8")
    fields = ac.load_schema("themes")["$defs"][f"{kind}_theme"]["properties"]
    for field in [*fields, "rationale"]:
        assert f"`{field}`" in text, field
    for layout in ("**N. Title**", "Output format", "Example output structure",
                   "Example structure", "**Description:**", "After listing the themes",
                   "After the list", "(7 total)", "(3 total)"):
        assert layout not in text, layout
    assert "not published" in text  # the rationale is not where reader content goes


# --------------------------------------------------------------------------- ST.5
def _titled(kind, prefix, n):
    obj = _structural(n) if kind == "structural" else _interpretive(n, nested=(1, n and 2))
    for it in obj["items"]:
        it["title"] = f"{prefix} {it['title']}"
    return json.dumps({"themes": obj["items"], "rationale": f"{prefix} RATIONALE"})


class _ThemeClient(_Client):
    """Answers a theme request (one with a format) from the kind's own reply list."""

    def __init__(self, structural, interpretive):
        super().__init__("unused")
        self.kinds = []
        outer = self
        queues = {"structural": list(structural), "interpretive": list(interpretive)}

        def pick(kw):
            schema = kw["extra_body"]["output_config"]["format"]["schema"]
            props = schema["properties"]["themes"]["items"]["properties"]
            kind = "structural" if "coverage_role" in props else "interpretive"
            outer.kinds.append(kind)
            return _msg(queues[kind].pop(0))

        class _Messages:
            def stream(self, **kw):
                outer.requests.append(kw)
                msg = pick(kw)

                class _Ctx:
                    def __enter__(self_inner):
                        return SimpleNamespace(get_final_message=lambda: msg)

                    def __exit__(self_inner, *a):
                        return False
                return _Ctx()

        self.messages = _Messages()


def _core(tmp_path, monkeypatch, client, verdicts):
    """Run Core (PART 1-8) with the real theme stages and fake everything else.
    Returns (ok, project folder, stem, the theme texts the validator saw)."""
    stem = "ST5-Talk"
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(config, "SOURCE_DIR", tmp_path / "source")
    (tmp_path / "source").mkdir(exist_ok=True)
    proj = tmp_path / "projects" / stem
    proj.mkdir(parents=True, exist_ok=True)
    (proj / f"{stem}{config.SUFFIX_FORMATTED}").write_text("## Section 1\nText.\n",
                                                           encoding="utf-8")
    monkeypatch.setattr(ep, "_load_formatted_transcript", lambda _f: "## Section 1\nText.\n")
    monkeypatch.setattr(ep, "parse_filename_metadata", lambda f: {
        "stem": stem, "title": stem, "presenter": "P", "author": "P",
        "date": "1980-00-00", "filename": f})
    monkeypatch.setattr(ep, "create_system_message_with_cache",
                        lambda _t: [{"type": "text", "text": "c"}])
    texts = {"Topics": "## Topics\n\n### Topic A\nD.\n*_(~20% of transcript; Sections 1)_*\n",
             "Key Terms": "## Key Terms\n\n### Term A\nDef.\n",
             "Lens": "## Lenses (Ranked)\n\n1. **Lens A**\nRationale.\n"}
    monkeypatch.setattr(ep, "_generate_with_cached_transcript", lambda name, *a, **k: next(
        v for key, v in texts.items() if key.lower().split()[0] in name.lower()))
    monkeypatch.setattr(ep.abstract_pipeline, "generate_abstract", lambda *a, **k: "Abstract.")
    seen = []

    def _validate(model, logger, system, structural, interpretive, lenses):
        seen.append((structural, interpretive))
        return {**verdicts[len(seen) - 1], "top_lens": {"title": "Lens A"}}

    monkeypatch.setattr(ep, "_validate_themes_and_lenses", _validate)
    monkeypatch.setattr(ep, "_top_lens_is_grounded", lambda *a: True)
    monkeypatch.setattr(ep, "get_anthropic_client", lambda: client)
    ok = ep.summarize_transcript(f"{stem}{config.SUFFIX_YAML}", "claude-sonnet-5-5", "k", "a",
                                 False, True, True, True, logger=logging.getLogger("st5"))
    return ok, proj, stem, seen


def test_st5_all_producers_write_json_and_md(quiet, tmp_path, monkeypatch):
    """Core PART 1/2 and the validation-loop regeneration both go through the
    structured stage; the saved .json is the version-2 object and the .md is its
    rendering. The validator rejects the first structural set, so the interpretive set
    is regenerated against the new structural numbers and the second sets are saved."""
    verdicts = [{"structural_themes_valid": False, "interpretive_themes_valid": True},
                {"structural_themes_valid": True, "interpretive_themes_valid": True}]
    client = _ThemeClient([_titled("structural", "First", 3), _titled("structural", "Second", 2)],
                          [_titled("interpretive", "First", 5),
                           _titled("interpretive", "Second", 4)])
    ok, proj, stem, seen = _core(tmp_path, monkeypatch, client, verdicts)
    assert ok is True
    assert client.kinds == ["structural", "interpretive", "structural", "interpretive"]
    # the validator saw the rendered markdown, first and second sets
    assert "**1. First Structural Theme 1**" in seen[0][0]
    assert "**1. Second Structural Theme 1**" in seen[1][0]
    assert "**1. Second Interpretive Theme 1**" in seen[1][1]

    saved = {}
    for kind, suffix in (("structural", config.SUFFIX_STRUCTURAL_THEMES),
                         ("interpretive", config.SUFFIX_INTERPRETIVE_THEMES)):
        md = (proj / f"{stem}{suffix}").read_text(encoding="utf-8")
        obj = json.loads(ac.json_sidecar_path(proj / f"{stem}{suffix}").read_text(encoding="utf-8"))
        assert obj["version"] == "2" and obj["kind"] == kind
        assert obj["rationale"] == "Second RATIONALE"  # kept in the JSON ...
        assert "RATIONALE" not in md                     # ... never in the markdown
        assert all(it["title"].startswith("Second ") for it in obj["items"])
        saved[kind] = (obj, md)
    structural_obj, structural_md = saved["structural"]
    interpretive_obj, interpretive_md = saved["interpretive"]
    assert structural_md == ac.themes_to_markdown(structural_obj)
    assert interpretive_md == ac.themes_to_markdown(interpretive_obj, structural_obj)
    assert "2 (Second Structural Theme 2)" in interpretive_md


def _pair(proj, stem, kind):
    suffix = config.SUFFIX_STRUCTURAL_THEMES if kind == "structural" else config.SUFFIX_INTERPRETIVE_THEMES
    md = proj / f"{stem}{suffix}"
    return md, ac.json_sidecar_path(md)


def test_st5_markdown_that_does_not_read_back_is_not_saved(tmp_path, monkeypatch):
    """ST review: a rendering that does not read back to the object is a renderer bug.
    It raises and writes nothing; the earlier run's pair stays as it was."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    old = ac.structured_themes_from_reply(_titled("structural", "Old", 2), "structural")
    md_path = ep._save_themes(old, ac.themes_to_markdown(old), "Talk_yaml.md", None)
    before = (md_path.read_text(encoding="utf-8"),
              ac.json_sidecar_path(md_path).read_text(encoding="utf-8"))
    new = ac.structured_themes_from_reply(_titled("structural", "New", 2), "structural")
    with pytest.raises(SchemaError, match="nothing saved"):
        ep._save_themes(new, ac.themes_to_markdown(old), "Talk_yaml.md", None)
    assert (md_path.read_text(encoding="utf-8"),
            ac.json_sidecar_path(md_path).read_text(encoding="utf-8")) == before


def test_st5_failed_format_check_removes_the_stale_json(tmp_path, monkeypatch):
    """P8: a theme file that fails its format check must not keep the earlier run's
    JSON next to it (the two would disagree)."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    obj = ac.structured_themes_from_reply(_titled("structural", "Old", 2), "structural")
    md_path = ep._save_themes(obj, ac.themes_to_markdown(obj), "Talk_yaml.md", None)
    assert ac.json_sidecar_path(md_path).exists()
    ep._save_summary("## Structural Themes\n\nProse with no theme in it.\n", "Talk_yaml.md",
                     "structural-themes")
    assert md_path.exists() and not ac.json_sidecar_path(md_path).exists()


def test_st5_failed_interpretive_stage_leaves_earlier_pair_untouched(quiet, tmp_path,
                                                                    monkeypatch):
    """ST review (P8): new structural themes are not saved when the interpretive stage
    fails, so they never sit next to the earlier run's interpretive file, which names
    the earlier structural themes."""
    stem = "ST5-Talk"
    proj = tmp_path / "projects" / stem
    proj.mkdir(parents=True)
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    old_s = ac.structured_themes_from_reply(_titled("structural", "Old", 2), "structural")
    old_i = ac.structured_themes_from_reply(_titled("interpretive", "Old", 3), "interpretive", 2)
    ep._save_themes(old_s, ac.themes_to_markdown(old_s), f"{stem}{config.SUFFIX_YAML}", None)
    ep._save_themes(old_i, ac.themes_to_markdown(old_i, old_s), f"{stem}{config.SUFFIX_YAML}",
                    None)
    files = [p for kind in ("structural", "interpretive") for p in _pair(proj, stem, kind)]
    before = [p.read_text(encoding="utf-8") for p in files]
    bad = _reply("interpretive", nested_under=[9])
    client = _ThemeClient([_titled("structural", "New", 2)], [bad] * config.MAX_RETRIES)
    ok, _proj, _stem, _seen = _core(tmp_path, monkeypatch, client, verdicts=[])
    assert ok is False
    assert client.kinds == ["structural"] + ["interpretive"] * config.MAX_RETRIES
    assert [p.read_text(encoding="utf-8") for p in files] == before


def test_st3_unexpected_reply_field_rejected():
    """ST review: a reply with a field beside themes and rationale (a closing note under
    a new name) is rejected, not silently dropped."""
    reply = json.loads(_reply("structural"))
    reply["summary"] = "These themes were chosen because..."
    with pytest.raises(SchemaError, match="summary"):
        ac.structured_themes_from_reply(json.dumps(reply), "structural")
    with pytest.raises(SchemaError, match="not a JSON object"):
        ac.structured_themes_from_reply("[1, 2]", "structural")


@pytest.mark.parametrize("model, accepted", [("claude-sonnet-5-5", True),
                                             ("claude-sonnet-4-6", True),
                                             ("claude-sonnet-4-5-20250929", True),
                                             ("claude-3-5-haiku-20241022", False)])
def test_st2_format_only_for_models_that_accept_it(quiet, model, accepted):
    """ST review: a model without structured output fails before any request, with the
    reason, instead of a "malformed request" from the API."""
    fmt = {"type": "json_schema", "schema": ac.themes_model_schema("structural")}
    client = _Client("{}")
    call = lambda: tu.call_claude_with_retry(  # noqa: E731
        client, model, [{"role": "user", "content": "x"}], max_tokens=1000, effort=None,
        output_format=fmt, min_length=1)
    if accepted:
        call()
        assert client.requests[0]["extra_body"]["output_config"]["format"] == fmt
    else:
        with pytest.raises(ValueError, match="JSON-schema output format"):
            call()
        assert client.requests == []


# --------------------------------------------------------------------------- ST.7
def test_st7_legacy_fixtures_unchanged():
    """Old theme files parse exactly as before ST: judge blocks and input, page blocks,
    trimmed notes, unclassified fields, prompt text and codec items, for every real
    theme fixture. The snapshot holds hashes made with the pre-ST code (commit ab31244)."""
    import importlib.util
    folder = FIXTURES / "st7_theme_parse_snapshot"
    spec = importlib.util.spec_from_file_location("make_snapshot", folder / "make_snapshot.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    expected = json.loads((folder / "snapshot.json").read_text(encoding="utf-8"))
    assert len(expected) >= 21
    current = mod.snapshot(FIXTURES)
    for name, hashes in expected.items():
        assert current[name] == hashes, name
