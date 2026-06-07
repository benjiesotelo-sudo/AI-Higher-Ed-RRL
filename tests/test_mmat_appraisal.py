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


def test_extract_orders_text_top_to_bottom(tmp_path):
    # A page whose blocks are stored out of reading order (the lower block is
    # written to the content stream first) must still extract top-to-bottom, not
    # in PDF-stream order. This is the multi-column / reading-order repair the
    # appraiser depends on: methods paragraphs must read in their visual order.
    p = tmp_path / "out_of_order.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(72, 600, 520, 740), "ZZBOTTOM section text content here")
    page.insert_textbox(fitz.Rect(72, 80, 520, 220), "AATOP section text content here")
    doc.save(str(p))
    doc.close()
    res = extract_text(p)
    top_idx = res.text.find("AATOP")
    bot_idx = res.text.find("ZZBOTTOM")
    assert top_idx != -1 and bot_idx != -1
    assert top_idx < bot_idx


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


from click.testing import CliRunner

from rrl.cli import main


def test_appraise_extract_and_status_cli(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "pdfs" / "2023").mkdir(parents=True)
    _make_pdf(tmp_path / "pdfs" / "2023" / "good.pdf", _EN_PARA)

    conn = connect(tmp_path / "data" / "rrl.sqlite")
    init_schema(conn)
    _insert_paper(conn, "good", pdf_filename="2023/good.pdf")
    conn.close()

    runner = CliRunner()
    r1 = runner.invoke(main, ["--db", "data/rrl.sqlite", "appraise", "extract"])
    assert r1.exit_code == 0, r1.output
    assert "ok: 1" in r1.output

    r2 = runner.invoke(main, ["--db", "data/rrl.sqlite", "appraise", "status"])
    assert r2.exit_code == 0, r2.output
    assert "ok: 1" in r2.output


def test_in_scope_excludes_null_pdf_filename(tmp_path):
    # Defensive: a 'downloaded' row with a NULL pdf_filename (corrupt/hand-edited)
    # must be excluded, not fed to extract_text (which would crash the run).
    conn = connect(tmp_path / "rrl.sqlite")
    init_schema(conn)
    _insert_paper(conn, "ok1", pdf_filename="2023/ok1.pdf")
    _insert_paper(conn, "nofile", pdf_status="downloaded", pdf_filename=None)
    ids = {pid for pid, _ in in_scope_papers(conn)}
    assert ids == {"ok1"}


def test_appraise_extract_idempotent_cli(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "pdfs" / "2023").mkdir(parents=True)
    _make_pdf(tmp_path / "pdfs" / "2023" / "good.pdf", _EN_PARA)
    conn = connect(tmp_path / "data" / "rrl.sqlite")
    init_schema(conn)
    _insert_paper(conn, "good", pdf_filename="2023/good.pdf")
    conn.close()

    runner = CliRunner()
    r1 = runner.invoke(main, ["--db", "data/rrl.sqlite", "appraise", "extract"])
    assert r1.exit_code == 0, r1.output
    r2 = runner.invoke(main, ["--db", "data/rrl.sqlite", "appraise", "extract"])
    assert r2.exit_code == 0, r2.output
    assert "No new papers" in r2.output


def test_mmat_samples_and_import_log_tables(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite")
    init_schema(conn)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"mmat_samples", "mmat_import_log"} <= names


from rrl.appraise.persist import set_disposition


def test_set_disposition_upserts_on_transition(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO papers (paper_id,title,authors_json,year,first_seen_at,last_updated_at) "
                 "VALUES ('p1','T','[]',2023,'now','now')")
    set_disposition(conn, "p1", "ok")
    set_disposition(conn, "p1", "appraised", "rated")  # must update, not IntegrityError
    rows = conn.execute("SELECT disposition, detail FROM mmat_dispositions WHERE paper_id='p1'").fetchall()
    assert len(rows) == 1 and rows[0]["disposition"] == "appraised" and rows[0]["detail"] == "rated"


from rrl.appraise.persist import reconcile_dispositions


def test_reconcile_dispositions_sums_to_inscope(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    for pid in ("a", "b", "c"):
        conn.execute("INSERT INTO papers (paper_id,title,authors_json,year,included,"
                     "pdf_status,pdf_filename,first_seen_at,last_updated_at) "
                     "VALUES (?,?,?,?,?,?,?,?,?)",
                     (pid, "T", "[]", 2023, 1, "downloaded", f"2023/{pid}.pdf", "now", "now"))
    set_disposition(conn, "a", "appraised")
    set_disposition(conn, "b", "not_assessable")
    set_disposition(conn, "c", "no_text_layer")
    r = reconcile_dispositions(conn)
    assert r["balanced"] is True
    assert r["in_scope"] == 3 and r["dispositioned"] == 3


from rrl.appraise.engine import work_id, normalize_text, quote_present


def test_work_id_is_deterministic():
    a = work_id("p1", "classify", 1, "classify-v1")
    assert a == work_id("p1", "classify", 1, "classify-v1")
    assert a != work_id("p1", "classify", 2, "classify-v1")


def test_quote_present_handles_linewrap_and_softhyphen():
    text = "the educa-\ntion of stu­dents in higher   education"
    assert quote_present("education of students", text) is True
    assert quote_present("not in the text at all", text) is False


import json

from rrl.appraise.engine import build_classify_work


def test_build_classify_work_selects_ok_papers_and_embeds_workid(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    pdf_root = tmp_path / "pdfs"; (pdf_root / "2023").mkdir(parents=True)
    _make_pdf(pdf_root / "2023" / "good.pdf", _EN_PARA)
    _insert_paper(conn, "good", pdf_filename="2023/good.pdf")
    set_disposition(conn, "good", "ok")
    out = tmp_path / "c.work.jsonl"
    n = build_classify_work(conn, pass_n=1, prompt_version="classify-v1",
                            pdf_root=pdf_root, out_path=out)
    assert n == 1
    line = json.loads(out.read_text().splitlines()[0])
    assert line["paper_id"] == "good" and line["task"] == "classify"
    assert line["work_id"] == work_id("good", "classify", 1, "classify-v1")
    assert "higher education" in line["text"] and "schema" in line
