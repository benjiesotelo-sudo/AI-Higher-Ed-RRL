from pathlib import Path

from rrl.db import connect, init_schema


def test_mmat_tables_created(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite")
    init_schema(conn)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert {"mmat_classifications", "mmat_appraisals", "mmat_dispositions"} <= names


def test_mmat_appraisals_unique_constraint(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite")
    init_schema(conn)
    conn.execute(
        "INSERT INTO papers (paper_id, title, authors_json, year, "
        "first_seen_at, last_updated_at) VALUES ('p1','T','[]',2023,'now','now')"
    )
    row = ("p1", "llm_pass_1", "qualitative", "1.1", "yes", None, None, None, None,
           "classify-v1", "test-model", "harness", "now")
    cols = ("paper_id, coder, mmat_category, criterion_id, rating, rationale, "
            "source_quote, quote_verified, adjudication_note, prompt_version, "
            "model, engine, created_at")
    ins = f"INSERT INTO mmat_appraisals ({cols}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
    conn.execute(ins, row)
    import sqlite3
    with __import__("pytest").raises(sqlite3.IntegrityError):
        conn.execute(ins, row)  # same (paper_id, coder, criterion_id, prompt_version)


import fitz  # PyMuPDF

from rrl.appraise.pdftext import extract_text, looks_english, MIN_TEXT_CHARS


def _make_pdf(path, text):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(72, 72, 520, 760), text)
    doc.save(str(path))
    doc.close()


_EN_PARA = (
    "This study examines the use of artificial intelligence in higher education. "
    "The research questions are clear and the data were collected from university "
    "students who used these tools for their coursework during the term. "
) * 4  # > 500 chars, stopword-rich English


def test_looks_english_true_for_english():
    assert looks_english("the study of the data in the university was clear") is True


def test_looks_english_false_for_non_english():
    assert looks_english("lorem ipsum dolor sit amet consectetur adipiscing") is False


def test_extract_ok_for_english_pdf(tmp_path):
    p = tmp_path / "doc.pdf"
    _make_pdf(p, _EN_PARA)
    res = extract_text(p)
    assert res.disposition == "ok"
    assert res.char_count >= MIN_TEXT_CHARS
    assert "higher education" in res.text


def test_extract_no_text_layer_for_missing_file(tmp_path):
    res = extract_text(tmp_path / "nope.pdf")
    assert res.disposition == "no_text_layer"
    assert res.char_count == 0


def test_extract_no_text_layer_for_tiny_text(tmp_path):
    p = tmp_path / "scan.pdf"
    _make_pdf(p, "Hi")  # far below MIN_TEXT_CHARS -> looks like a scan
    res = extract_text(p)
    assert res.disposition == "no_text_layer"


def test_extract_non_english(tmp_path):
    p = tmp_path / "es.pdf"
    _make_pdf(p, ("lorem ipsum dolor sit amet consectetur adipiscing elit sed "
                  "eiusmod tempor incididunt ut labore dolore magna aliqua ") * 6)
    res = extract_text(p)
    assert res.disposition == "non_english"


from rrl.appraise.runner import in_scope_papers, run_extract


def _insert_paper(conn, pid, *, included=1, pdf_status="downloaded", pdf_filename=None):
    conn.execute(
        "INSERT INTO papers (paper_id, title, authors_json, year, included, "
        "pdf_status, pdf_filename, first_seen_at, last_updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (pid, "T", "[]", 2023, included, pdf_status, pdf_filename, "now", "now"),
    )


def test_in_scope_excludes_not_downloaded_and_losers(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite")
    init_schema(conn)
    _insert_paper(conn, "keep", pdf_filename="2023/keep.pdf")
    _insert_paper(conn, "nodl", pdf_status="not_retrievable", pdf_filename=None)
    _insert_paper(conn, "loser", pdf_filename="2023/loser.pdf")
    conn.execute(
        "INSERT INTO paper_merges (loser_id, winner_id, merged_at, merged_by) "
        "VALUES ('loser','keep','now','test')"
    )
    ids = {pid for pid, _ in in_scope_papers(conn)}
    assert ids == {"keep"}


def test_run_extract_records_dispositions_and_is_idempotent(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite")
    init_schema(conn)
    pdf_root = tmp_path / "pdfs"
    (pdf_root / "2023").mkdir(parents=True)
    _make_pdf(pdf_root / "2023" / "good.pdf", _EN_PARA)
    _insert_paper(conn, "good", pdf_filename="2023/good.pdf")
    _insert_paper(conn, "missing", pdf_filename="2023/missing.pdf")  # file absent

    counts = run_extract(conn, pdf_root=pdf_root)
    assert counts == {"ok": 1, "no_text_layer": 1}
    rows = dict(conn.execute(
        "SELECT paper_id, disposition FROM mmat_dispositions"
    ).fetchall())
    assert rows == {"good": "ok", "missing": "no_text_layer"}

    # Idempotent: a second run does nothing (both already dispositioned).
    counts2 = run_extract(conn, pdf_root=pdf_root)
    assert counts2 == {}
    assert conn.execute("SELECT COUNT(*) FROM mmat_dispositions").fetchone()[0] == 2
