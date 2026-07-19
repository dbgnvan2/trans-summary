#!/usr/bin/env python3
"""Generate templates/styles/bundle-reference.docx.

Takes pandoc's default DOCX reference and reduces the heading font sizes for the
bundle export (main = Heading 1, section = Heading 2). Re-run after a pandoc
upgrade to refresh the committed reference doc. Requires pandoc on PATH.

Usage:
    python scripts/gen_bundle_reference_docx.py

Spec: docs/spec_bundle_export_2026-07-16.md#BE.11
"""

import re
import subprocess
import zipfile
from pathlib import Path

# style_id -> new size in half-points (pt = val / 2). Reduced ~15-20% from the
# pandoc defaults (Title 56, Heading1 40, Heading2 32, Heading3 28).
SIZES = {"Title": 44, "Heading1": 32, "Heading2": 26, "Heading3": 24}

OUT = Path(__file__).resolve().parent.parent / "templates" / "styles" / "bundle-reference.docx"


def _set_size(xml: str, style_id: str, half_pts: int) -> str:
    pat = re.compile(
        r'(<w:style\b[^>]*w:styleId="' + re.escape(style_id) + r'"[^>]*>)(.*?)(</w:style>)',
        re.S,
    )

    def repl(m):
        head, body, tail = m.groups()
        body = re.sub(r'<w:sz w:val="\d+"', f'<w:sz w:val="{half_pts}"', body)
        body = re.sub(r'<w:szCs w:val="\d+"', f'<w:szCs w:val="{half_pts}"', body)
        return head + body + tail

    return pat.sub(repl, xml)


def main() -> int:
    default = subprocess.run(
        ["pandoc", "--print-default-data-file", "reference.docx"],
        capture_output=True, check=True,
    ).stdout

    tmp = OUT.parent / "_ref_default.docx"
    tmp.write_bytes(default)
    try:
        with zipfile.ZipFile(tmp) as zin:
            names = zin.namelist()
            styles = zin.read("word/styles.xml").decode("utf-8")
            for style_id, half_pts in SIZES.items():
                styles = _set_size(styles, style_id, half_pts)
            OUT.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zout:
                for name in names:
                    data = styles.encode("utf-8") if name == "word/styles.xml" else zin.read(name)
                    zout.writestr(name, data)
    finally:
        tmp.unlink(missing_ok=True)

    print(f"Wrote {OUT} (heading sizes: {SIZES})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
