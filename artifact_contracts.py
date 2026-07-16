"""M3 — structured artifact contracts (schema-validated pipeline boundaries).

Purpose: kill the P19 producer/consumer format-drift *class*. Every structured
boundary (bowen, emphasis, key-terms, topics, themes, abstract-input) becomes a
schema-validated object instead of a wall of independent regexes that silently
return ``[]``/``0`` on drift.

Scope decision (2026-07-15): the codec layer ships first — markdown stays the
wire format the model emits and the pipeline saves, JSON is a *derived* durable
sidecar, and the generation prompts are NOT yet rewritten to emit JSON. U4 (every
boundary schema-validated, drift is a hard error not a silent zero) is delivered
by this layer regardless of wire format.

Each boundary has:
  * a JSON Schema in ``schemas/<key>.schema.json`` (the versioned contract),
  * ``parse_markdown``  — the migration shim (delegates to the ONE canonical
    text parser already used by the consumer), returning the schema object,
  * ``validate``        — raises ``SchemaError`` on drift (never a silent zero),
  * ``render_markdown`` — regenerates display markdown from a validated object,
  * ``to_json`` / ``from_json`` — the durable structured serialization.

A parse that yields zero items from *non-empty* input is contract drift and is
raised loudly (``SchemaError``), never returned as an empty pass — the
distinction the P19 class turns on.

Spec:  docs/spec_unattended_robustness_2026-07-15.md#M3
Tests: tests/test_artifact_contracts.py
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

SCHEMAS_DIR = Path(__file__).parent / "schemas"
SCHEMA_VERSION = "1"


class SchemaError(ValueError):
    """A boundary artifact does not conform to its schema, or a non-empty
    artifact parsed to zero items (contract drift). Distinct from a benign
    absent/empty source so callers can fail closed (P19/M3.C)."""


# --------------------------------------------------------------------------- schema loading
@lru_cache(maxsize=None)
def load_schema(key: str) -> dict:
    path = SCHEMAS_DIR / f"{key}.schema.json"
    if not path.exists():
        raise SchemaError(f"schema not found for artifact {key!r}: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _validator(key: str):
    from jsonschema import Draft202012Validator

    return Draft202012Validator(load_schema(key))


def _has_body(text: Optional[str]) -> bool:
    """True when ``text`` carries a MEANINGFUL body — content that should have
    parsed into items. Discriminates a legitimately-empty artifact from drift:

      * a bare section header (``## Bowen References`` / ``# Title``, H1–H2) with
        nothing under it is a benign empty -> no body;
      * any non-heading content line is a body;
      * an H3+ heading (``### Concept``) is an ITEM header — its presence with
        zero parsed items is itself drift (the all-headers-no-body case: quote
        bodies dropped entirely), so it counts as a body.

    Without the H3 rule, an all-headers drift would read as benign-empty and slip
    past the gate silently (P19). H1/H2 stay scaffolding so the empty case passes."""
    from transcript_utils import strip_yaml_frontmatter

    stripped = strip_yaml_frontmatter(text or "")
    for line in stripped.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            hashes = len(s) - len(s.lstrip("#"))
            if hashes >= 3:  # H3+ item header implies content that must parse
                return True
            continue  # H1/H2 section scaffolding
        return True  # non-heading content
    return False


def validate(key: str, obj: dict) -> dict:
    """Validate ``obj`` against the ``key`` schema; return it on success, raise
    ``SchemaError`` (listing every violation) on failure."""
    errors = sorted(_validator(key).iter_errors(obj), key=lambda e: list(e.path))
    if errors:
        detail = "; ".join(
            f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}"
            for e in errors[:10]
        )
        raise SchemaError(f"{key} artifact violates schema: {detail}")
    return obj


# --------------------------------------------------------------------------- bowen
def bowen_from_markdown(text: str) -> dict:
    import transcript_utils as tu

    items = [
        {"concept": c, "quote": q, "timestamp": t}
        for c, q, t in tu.parse_bowen_references_text(text)
    ]
    return {"version": SCHEMA_VERSION, "artifact": "bowen", "items": items}


def bowen_to_markdown(obj: dict) -> str:
    from extraction_pipeline import _format_bowen_refs

    refs = [(i["concept"], i["quote"], i.get("timestamp")) for i in obj["items"]]
    body = _format_bowen_refs(refs)
    return f"## Bowen References\n\n{body}".rstrip() + "\n"


# --------------------------------------------------------------------------- emphasis
def emphasis_from_markdown(text: str) -> dict:
    import transcript_utils as tu

    items = []
    for it in tu.parse_scored_emphasis_output(text):
        items.append(
            {
                # Normalize case ("explicit"/"EXPLICIT" -> "Explicit"): the parser
                # accepts any-case, and a cosmetic case variant is not content drift
                # — blocking the whole boundary on it would be a false positive (P7).
                # A genuinely wrong type ("Emphatic") still fails the enum -> ERROR.
                "type": it["type"].strip().title(),
                "category": it["category"],
                "score": int(it["score"]),
                "concept": it["concept"],
                "quote": it["quote"],
                "timestamp": it.get("timestamp"),
            }
        )
    return {"version": SCHEMA_VERSION, "artifact": "emphasis", "items": items}


def emphasis_to_markdown(obj: dict) -> str:
    blocks = []
    for it in obj["items"]:
        ts = f" | {it['timestamp']}" if it.get("timestamp") else ""
        header = f"[{it['type']} - {it['category']} - Rank: {it['score']}%{ts}] Concept: {it['concept']}"
        blocks.append(f'{header}\n\n"{it["quote"]}"')
    return "\n\n".join(blocks) + "\n"


# --------------------------------------------------------------------------- key terms
def key_terms_from_markdown(text: str) -> dict:
    import transcript_utils as tu
    from validation_pipeline import _parse_key_terms_section

    content = tu.strip_yaml_frontmatter(text)
    items = [
        {"term": term, "definition": definition}
        for term, definition in _parse_key_terms_section(content)
    ]
    return {"version": SCHEMA_VERSION, "artifact": "key_terms", "items": items}


def key_terms_to_markdown(obj: dict) -> str:
    blocks = ["## Key Terms"]
    for it in obj["items"]:
        blocks.append(f"### {it['term']}\n{it['definition']}")
    return "\n\n".join(blocks) + "\n"


# --------------------------------------------------------------------------- topics
def topics_from_markdown(text: str) -> dict:
    import summary_pipeline as sp
    import transcript_utils as tu

    content = tu.strip_yaml_frontmatter(text)
    items = sp.parse_topics_structure(content)
    return {"version": SCHEMA_VERSION, "artifact": "topics", "items": items}


def topics_to_markdown(obj: dict) -> str:
    blocks = ["## Topics"]
    for it in obj["items"]:
        meta = f"*_(~{it['percentage']}% of transcript; Sections {it['sections']})_*"
        blocks.append(f"### {it['name']}\n{it['description']}\n{meta}")
    return "\n\n".join(blocks) + "\n"


# --------------------------------------------------------------------------- themes
def themes_from_markdown(text: str, kind: str) -> dict:
    # ``number`` is positional (1..n in document order), reusing the ONE shared
    # theme parser. The model's literal ``**N.**`` label is intentionally not
    # captured: the pipeline orders themes positionally and no consumer reads the
    # literal number, so capturing it would add a signal nothing uses at the cost
    # of a second theme-regex (the P19 duplication this layer exists to avoid).
    import transcript_utils as tu

    items = [
        {"number": i + 1, "name": name, "description": description}
        for i, (name, description) in enumerate(
            tu.parse_bold_numbered_theme_blocks(text)
        )
    ]
    return {"version": SCHEMA_VERSION, "artifact": "themes", "kind": kind, "items": items}


def themes_to_markdown(obj: dict) -> str:
    title = "Structural" if obj.get("kind") == "structural" else "Interpretive"
    blocks = [f"## {title} Themes"]
    for it in obj["items"]:
        blocks.append(f"**{it['number']}. {it['name']}**\n**Description:** {it['description']}")
    return "\n\n".join(blocks) + "\n"


# --------------------------------------------------------------------------- codec registry
class Codec:
    """Bundles a boundary's schema key with its markdown parse/render so callers
    validate + (de)serialize through one object."""

    def __init__(self, key: str,
                 from_markdown: Callable[..., dict],
                 to_markdown: Callable[[dict], str]):
        self.key = key
        self._from_markdown = from_markdown
        self._to_markdown = to_markdown

    def parse_markdown(self, text: str, *args) -> dict:
        """Legacy markdown -> validated schema object. A non-empty artifact that
        parses to zero items is contract drift -> ``SchemaError`` (P19), not an
        empty pass. Truly empty input — blank, frontmatter-only, or a bare section
        header with no body (a legitimately zero-item run) -> a valid empty object,
        NOT a mislabeled drift error."""
        obj = self._from_markdown(text, *args)
        if not obj.get("items") and _has_body(text):
            raise SchemaError(
                f"{self.key}: non-empty artifact body parsed to zero items — "
                f"producer/consumer format drift (P19), not a clean empty."
            )
        return validate(self.key, obj)

    def render_markdown(self, obj: dict) -> str:
        return self._to_markdown(validate(self.key, obj))

    def to_json(self, obj: dict, *, indent: int = 2) -> str:
        return json.dumps(validate(self.key, obj), indent=indent, ensure_ascii=False)

    def from_json(self, text: str) -> dict:
        return validate(self.key, json.loads(text))


# Markdown-wire boundaries. ``abstract_input`` has a schema (schemas/
# abstract_input.schema.json) but NO markdown codec by design: it is an assembled
# object (abstract_pipeline.AbstractInput), not a saved-markdown artifact, so its
# producer is pinned by a JSON validate() hook at assembly time (wired in the
# abstract-input staging step), not by a markdown round-trip.
CODECS: dict[str, Codec] = {
    "bowen": Codec("bowen", bowen_from_markdown, bowen_to_markdown),
    "emphasis": Codec("emphasis", emphasis_from_markdown, emphasis_to_markdown),
    "key_terms": Codec("key_terms", key_terms_from_markdown, key_terms_to_markdown),
    "topics": Codec("topics", topics_from_markdown, topics_to_markdown),
    "themes": Codec("themes", themes_from_markdown, themes_to_markdown),
}


def codec(key: str) -> Codec:
    if key not in CODECS:
        raise SchemaError(f"no codec registered for artifact {key!r}")
    return CODECS[key]


# --------------------------------------------------------------------------- save/load helpers
def json_sidecar_path(md_path) -> Path:
    """The structured JSON sidecar next to a markdown artifact:
    ``<base> - bowen-references.md`` -> ``<base> - bowen-references.json``."""
    return Path(md_path).with_suffix(".json")


def write_json_sidecar(md_path, key: str, obj: dict) -> Path:
    """Write the validated object as the durable JSON sidecar; return its path."""
    path = json_sidecar_path(md_path)
    path.write_text(codec(key).to_json(obj) + "\n", encoding="utf-8")
    return path


def load_and_validate(md_path, key: str, *parse_args) -> Optional[dict]:
    """Read a saved markdown artifact and return its validated object, or None if
    the file is absent. Raises ``SchemaError`` on drift (M3.C consumer check)."""
    p = Path(md_path)
    if not p.exists():
        return None
    return codec(key).parse_markdown(p.read_text(encoding="utf-8"), *parse_args)


def verify_saved_artifact(md_path, key: str, *parse_args, expect_items: bool = False) -> dict:
    """Producer self-check (M3.B): re-read the just-saved artifact, validate it,
    and — when the producer actually extracted items — require it parsed back to
    >0 items. A saved file that drifts to zero (or violates the schema) is a
    format-contract failure, not a save. Returns the validated object; raises
    ``SchemaError`` on any failure so the producer records a retryable ERROR and
    does NOT leave a malformed artifact authoritative."""
    obj = load_and_validate(md_path, key, *parse_args)
    if obj is None:
        raise SchemaError(f"{key}: no artifact written at {md_path}")
    if expect_items and not obj.get("items"):
        raise SchemaError(
            f"{key}: saved artifact parsed to zero items despite extracted content "
            f"— producer/consumer format drift (P19)."
        )
    return obj
