"""Replace ONLY the content between BEGIN/END markers. Refuse if markers missing."""
from __future__ import annotations
from pathlib import Path

BEGIN_MARK = "<!-- BEGIN AUTO-GENERATED -->"
END_MARK = "<!-- END AUTO-GENERATED -->"

class MissingMarkers(RuntimeError):
    pass

def update_appendix(readme_path: Path, new_inner: str) -> None:
    text = readme_path.read_text(encoding="utf-8")
    if BEGIN_MARK not in text or END_MARK not in text:
        raise MissingMarkers(
            f"README.md must contain both {BEGIN_MARK} and {END_MARK}. "
            "Add them around the auto-generated section and re-run."
        )
    start = text.index(BEGIN_MARK) + len(BEGIN_MARK)
    end = text.index(END_MARK)
    if start > end:
        raise MissingMarkers(f"{BEGIN_MARK} must appear before {END_MARK}.")
    new_block = "\n" + new_inner.strip("\n") + "\n"
    new_text = text[:start] + new_block + text[end:]
    readme_path.write_text(new_text, encoding="utf-8")
