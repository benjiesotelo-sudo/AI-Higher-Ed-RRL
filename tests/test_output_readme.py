from pathlib import Path
import pytest
from rrl.output.readme import update_appendix, BEGIN_MARK, END_MARK, MissingMarkers

def test_refuses_when_markers_missing(tmp_path):
    p = tmp_path / "README.md"
    p.write_text("# No markers here\n", encoding="utf-8")
    with pytest.raises(MissingMarkers):
        update_appendix(p, "new content")
    assert p.read_text(encoding="utf-8") == "# No markers here\n"

def test_replaces_only_between_markers(tmp_path):
    p = tmp_path / "README.md"
    original = (
        "# Header\n\nIntro text.\n\n"
        f"{BEGIN_MARK}\n_old appendix_\n{END_MARK}\n\nMore handwritten content.\n"
    )
    p.write_text(original, encoding="utf-8")
    update_appendix(p, "## Fresh\n\n_new content_")
    text = p.read_text(encoding="utf-8")
    assert "# Header" in text
    assert "More handwritten content." in text
    assert "_old appendix_" not in text
    assert "_new content_" in text
    assert BEGIN_MARK in text and END_MARK in text

def test_preserves_handwritten_bytes_outside_block(tmp_path):
    p = tmp_path / "README.md"
    handwritten_top = "# A\n\nSome\n  indented\n  content with trailing\n  whitespace   \n\n"
    handwritten_bot = "\n\n## Footer\n\nLine.\n"
    original = handwritten_top + f"{BEGIN_MARK}\nold\n{END_MARK}" + handwritten_bot
    p.write_text(original, encoding="utf-8")
    update_appendix(p, "new")
    text = p.read_text(encoding="utf-8")
    assert text.startswith(handwritten_top)
    assert text.endswith(handwritten_bot)
