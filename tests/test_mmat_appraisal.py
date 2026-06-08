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


def test_quote_present_tolerates_dropped_citation_and_minor_elision():
    text = "Participants reported that students used AI (Smith, 2020) for writing tasks during the term."
    # model dropped the inline citation mid-quote -> still a faithful quote
    assert quote_present("students used AI for writing tasks", text) is True
    # genuinely fabricated content -> must still fail
    assert quote_present("students avoided all digital tools entirely", text) is False


def test_quote_present_accepts_high_word_coverage_reconstruction():
    text = "The study used a survey design with a small convenience sample of teachers in three schools."
    # faithful reconstruction: same words, reordered/elided (not a clean substring/subsequence)
    assert quote_present("a small convenience sample of teachers used a survey design", text) is True
    # fabrication: words mostly absent from the source
    assert quote_present("randomized controlled trial double blind placebo allocation concealment masking", text) is False


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


from rrl.appraise.persist import import_classify_answers


def _classify_round(tmp_path, conn, bucket, s1="yes", s2="yes"):
    pdf_root = tmp_path / "pdfs"; (pdf_root / "2023").mkdir(parents=True, exist_ok=True)
    _make_pdf(pdf_root / "2023" / "g.pdf", _EN_PARA)
    _insert_paper(conn, "g", pdf_filename="2023/g.pdf"); set_disposition(conn, "g", "ok")
    work = tmp_path / "c.work.jsonl"
    build_classify_work(conn, 1, "classify-v1", pdf_root, work)
    wl = json.loads(work.read_text().splitlines()[0])
    ans = tmp_path / "c.answers.jsonl"
    ans.write_text(json.dumps({"work_id": wl["work_id"], "bucket": bucket,
        "s1": s1, "s2": s2, "mm_quant_family": None, "rationale": "r",
        "source_quote": "higher education", "confidence": 0.9}) + "\n")
    return import_classify_answers(conn, work, ans, model="m", engine="harness")


def test_import_classify_persists_and_sets_quote_present(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    _classify_round(tmp_path, conn, "qualitative")
    row = conn.execute("SELECT mmat_category, coder, flagged FROM mmat_classifications "
                       "WHERE paper_id='g'").fetchone()
    assert row["mmat_category"] == "qualitative" and row["coder"] == "llm_pass_1"
    assert row["flagged"] == 0


def test_import_classify_s1_trigger_routes_not_assessable(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    _classify_round(tmp_path, conn, "qualitative", s1="no")
    disp = conn.execute("SELECT disposition FROM mmat_dispositions WHERE paper_id='g'").fetchone()
    assert disp["disposition"] == "not_assessable"


def test_import_classify_reimport_replaces_not_raises(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    pdf_root = tmp_path / "pdfs"; (pdf_root / "2023").mkdir(parents=True)
    _make_pdf(pdf_root / "2023" / "g.pdf", _EN_PARA)
    _insert_paper(conn, "g", pdf_filename="2023/g.pdf"); set_disposition(conn, "g", "ok")
    work = tmp_path / "c.work.jsonl"; build_classify_work(conn, 1, "classify-v1", pdf_root, work)
    wl = json.loads(work.read_text().splitlines()[0])
    ans = tmp_path / "c.answers.jsonl"
    ans.write_text(json.dumps({"work_id": wl["work_id"], "bucket": "qualitative", "s1": "yes",
        "s2": "yes", "mm_quant_family": None, "rationale": "r",
        "source_quote": "higher education", "confidence": 0.9}) + "\n")
    import_classify_answers(conn, work, ans, "m", "harness")
    import_classify_answers(conn, work, ans, "m", "harness")   # same key, second import
    n = conn.execute("SELECT COUNT(*) FROM mmat_classifications WHERE paper_id='g'").fetchone()[0]
    assert n == 1


from rrl.appraise.engine import build_rate_work, CRITERIA


def test_build_rate_work_emits_category_criteria_and_skips_not_assessable(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    pdf_root = tmp_path / "pdfs"; (pdf_root / "2023").mkdir(parents=True)
    _make_pdf(pdf_root / "2023" / "g.pdf", _EN_PARA)
    _insert_paper(conn, "g", pdf_filename="2023/g.pdf"); set_disposition(conn, "g", "ok")
    conn.execute("INSERT INTO mmat_classifications (paper_id,coder,mmat_category,prompt_version,"
                 "model,engine,created_at) VALUES ('g','llm_pass_1','qualitative','classify-v1','m','h','now')")
    out = tmp_path / "r.work.jsonl"
    n = build_rate_work(conn, pass_n=1, prompt_version="rate-v1", pdf_root=pdf_root, out_path=out)
    assert n == 1
    line = json.loads(out.read_text().splitlines()[0])
    assert line["task"] == "rate" and line["mmat_category"] == "qualitative"
    assert line["criteria"] == CRITERIA["qualitative"]


from rrl.appraise.persist import import_rate_answers


def _rate_round(tmp_path, conn, category, ratings):
    pdf_root = tmp_path / "pdfs"; (pdf_root / "2023").mkdir(parents=True, exist_ok=True)
    _make_pdf(pdf_root / "2023" / "g.pdf", _EN_PARA)
    _insert_paper(conn, "g", pdf_filename="2023/g.pdf"); set_disposition(conn, "g", "ok")
    conn.execute("INSERT INTO mmat_classifications (paper_id,coder,mmat_category,prompt_version,"
                 "model,engine,created_at) VALUES ('g','llm_pass_1',?,'classify-v1','m','h','now')",
                 (category,))
    work = tmp_path / "r.work.jsonl"; build_rate_work(conn, 1, "rate-v1", pdf_root, work)
    wl = json.loads(work.read_text().splitlines()[0])
    lines = [json.dumps({"work_id": wl["work_id"], "criterion_id": cid,
             "rating": ratings.get(cid, "yes"), "rationale": "r",
             "source_quote": "higher education", "confidence": 0.9}) for cid in wl["criteria"]]
    ans = tmp_path / "r.answers.jsonl"; ans.write_text("\n".join(lines) + "\n")
    return import_rate_answers(conn, work, ans, model="m", engine="harness")


def test_import_rate_persists_full_set_and_marks_appraised(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    _rate_round(tmp_path, conn, "qualitative", {})
    n = conn.execute("SELECT COUNT(*) FROM mmat_appraisals WHERE paper_id='g'").fetchone()[0]
    assert n == 5
    disp = conn.execute("SELECT disposition FROM mmat_dispositions WHERE paper_id='g'").fetchone()
    assert disp["disposition"] == "appraised"


def test_import_rate_incomplete_set_rejects_whole_paper(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    pdf_root = tmp_path / "pdfs"; (pdf_root / "2023").mkdir(parents=True)
    _make_pdf(pdf_root / "2023" / "g.pdf", _EN_PARA)
    _insert_paper(conn, "g", pdf_filename="2023/g.pdf"); set_disposition(conn, "g", "ok")
    conn.execute("INSERT INTO mmat_classifications (paper_id,coder,mmat_category,prompt_version,"
                 "model,engine,created_at) VALUES ('g','llm_pass_1','qualitative','classify-v1','m','h','now')")
    work = tmp_path / "r.work.jsonl"; build_rate_work(conn, 1, "rate-v1", pdf_root, work)
    wl = json.loads(work.read_text().splitlines()[0])
    ans = tmp_path / "r.answers.jsonl"
    ans.write_text(json.dumps({"work_id": wl["work_id"], "criterion_id": "1.1", "rating": "yes",
                   "rationale": "r", "source_quote": "higher education"}) + "\n")  # only 1 of 5
    import_rate_answers(conn, work, ans, model="m", engine="harness")
    assert conn.execute("SELECT COUNT(*) FROM mmat_appraisals WHERE paper_id='g'").fetchone()[0] == 0


from rrl.appraise.persist import status_counts, assign_samples


def test_status_counts_reports_dispositions_and_log(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO papers (paper_id,title,authors_json,year,included,pdf_status,"
                 "pdf_filename,first_seen_at,last_updated_at) VALUES "
                 "('g','T','[]',2023,1,'downloaded','2023/g.pdf','now','now')")
    set_disposition(conn, "g", "appraised")
    s = status_counts(conn)
    assert s["dispositions"]["appraised"] == 1 and s["reconciliation"]["balanced"] is True


def test_assign_samples_deterministic_and_disjoint(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    for i in range(20):
        pid = f"p{i:02d}"
        conn.execute("INSERT INTO papers (paper_id,title,authors_json,year,included,pdf_status,"
                     "pdf_filename,first_seen_at,last_updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                     (pid, "T", "[]", 2023, 1, "downloaded", f"2023/{pid}.pdf", "now", "now"))
        set_disposition(conn, pid, "ok")
    pilot = assign_samples(conn, role="pilot", n=5, seed=42)
    calib = assign_samples(conn, role="calibration", n=5, seed=42)
    assert set(pilot).isdisjoint(calib)
    assert assign_samples(conn, role="pilot", n=5, seed=42) == pilot


def test_assign_samples_tops_up_to_n_preserving_existing(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    for i in range(30):
        pid = f"p{i:02d}"
        conn.execute("INSERT INTO papers (paper_id,title,authors_json,year,included,pdf_status,"
                     "pdf_filename,first_seen_at,last_updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                     (pid, "T", "[]", 2023, 1, "downloaded", f"2023/{pid}.pdf", "now", "now"))
        set_disposition(conn, pid, "ok")
    first = assign_samples(conn, role="pilot", n=5, seed=42)
    assert len(first) == 5
    grown = assign_samples(conn, role="pilot", n=8, seed=42)
    assert len(grown) == 8 and set(first) <= set(grown)        # superset: originals retained
    assert assign_samples(conn, role="pilot", n=8, seed=42) == grown  # idempotent at n


def test_assign_samples_stratifies_by_tier(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    for i in range(20):
        pid = f"p{i:02d}"
        tier = "high_confidence" if i < 10 else "review_needed"
        conn.execute("INSERT INTO papers (paper_id,title,authors_json,year,included,pdf_status,"
                     "pdf_filename,quality_tier,first_seen_at,last_updated_at) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (pid, "T", "[]", 2023, 1, "downloaded", f"2023/{pid}.pdf", tier, "now", "now"))
        set_disposition(conn, pid, "ok")
    hc = assign_samples(conn, role="strat", n=3, seed=1, tier="high_confidence")
    both = assign_samples(conn, role="strat", n=6, seed=1, tier="review_needed")  # top up to 6
    assert len(hc) == 3 and len(both) == 6 and set(hc) <= set(both)
    rn_added = set(both) - set(hc)
    qt = dict(conn.execute("SELECT paper_id, quality_tier FROM papers").fetchall())
    assert all(qt[pid] == "review_needed" for pid in rn_added)
    strata = dict(conn.execute("SELECT paper_id, stratum FROM mmat_samples WHERE role='strat'").fetchall())
    assert strata[hc[0]] == "high_confidence" and strata[next(iter(rn_added))] == "review_needed"


def test_cli_classify_emit_import_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(); (tmp_path / "pdfs" / "2023").mkdir(parents=True)
    _make_pdf(tmp_path / "pdfs" / "2023" / "g.pdf", _EN_PARA)
    conn = connect(tmp_path / "data" / "rrl.sqlite"); init_schema(conn)
    _insert_paper(conn, "g", pdf_filename="2023/g.pdf"); set_disposition(conn, "g", "ok"); conn.close()
    r = CliRunner().invoke(main, ["--db", "data/rrl.sqlite", "appraise", "classify",
                                  "--emit", "c.work.jsonl", "--pass", "1"])
    assert r.exit_code == 0, r.output
    wl = json.loads((tmp_path / "c.work.jsonl").read_text().splitlines()[0])
    (tmp_path / "c.answers.jsonl").write_text(json.dumps({"work_id": wl["work_id"],
        "bucket": "qualitative", "s1": "yes", "s2": "yes", "mm_quant_family": None,
        "rationale": "r", "source_quote": "higher education", "confidence": 0.9}) + "\n")
    r2 = CliRunner().invoke(main, ["--db", "data/rrl.sqlite", "appraise", "classify",
                                   "--import", "c.answers.jsonl", "--work", "c.work.jsonl"])
    assert r2.exit_code == 0, r2.output
    conn = connect(tmp_path / "data" / "rrl.sqlite")
    assert conn.execute("SELECT mmat_category FROM mmat_classifications WHERE paper_id='g'"
                        ).fetchone()["mmat_category"] == "qualitative"


def test_cli_import_records_model_provenance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(); (tmp_path / "pdfs" / "2023").mkdir(parents=True)
    _make_pdf(tmp_path / "pdfs" / "2023" / "g.pdf", _EN_PARA)
    conn = connect(tmp_path / "data" / "rrl.sqlite"); init_schema(conn)
    _insert_paper(conn, "g", pdf_filename="2023/g.pdf"); set_disposition(conn, "g", "ok"); conn.close()
    db = ["--db", "data/rrl.sqlite", "appraise"]
    haiku = "claude-haiku-4-5-20251001"
    assert CliRunner().invoke(main, db + ["classify", "--emit", "c.work.jsonl", "--pass", "1"]).exit_code == 0
    cw = json.loads((tmp_path / "c.work.jsonl").read_text().splitlines()[0])
    (tmp_path / "c.answers.jsonl").write_text(json.dumps({"work_id": cw["work_id"],
        "bucket": "quant_descriptive", "s1": "yes", "s2": "yes", "mm_quant_family": None,
        "rationale": "r", "source_quote": "higher education", "confidence": 0.9}) + "\n")
    assert CliRunner().invoke(main, db + ["classify", "--import", "c.answers.jsonl",
        "--work", "c.work.jsonl", "--model", haiku]).exit_code == 0
    assert CliRunner().invoke(main, db + ["rate", "--emit", "r.work.jsonl", "--pass", "1"]).exit_code == 0
    rw = json.loads((tmp_path / "r.work.jsonl").read_text().splitlines()[0])
    (tmp_path / "r.answers.jsonl").write_text("\n".join(json.dumps({"work_id": rw["work_id"],
        "criterion_id": c, "rating": "yes", "rationale": "r", "source_quote": "higher education",
        "confidence": 0.9}) for c in rw["criteria"]) + "\n")
    assert CliRunner().invoke(main, db + ["rate", "--import", "r.answers.jsonl",
        "--work", "r.work.jsonl", "--model", haiku]).exit_code == 0
    conn = connect(tmp_path / "data" / "rrl.sqlite")
    assert conn.execute("SELECT DISTINCT model FROM mmat_classifications").fetchone()[0] == haiku
    assert conn.execute("SELECT DISTINCT model FROM mmat_appraisals").fetchone()[0] == haiku


import subprocess


def test_work_files_are_gitignored():
    out = subprocess.run(["git", "check-ignore", "sample.work.jsonl", "sample.answers.jsonl",
                          "sample.rejects.jsonl"], capture_output=True, text=True)
    assert "work.jsonl" in out.stdout and "answers.jsonl" in out.stdout


from rrl.appraise.prompts import render_classify, render_rate


def test_render_classify_includes_screening_and_buckets():
    p = render_classify("SOME PAPER TEXT", pass_n=1)
    assert "S1" in p and "S2" in p and "mixed_methods" in p and "SOME PAPER TEXT" in p
    assert "verbatim" in p.lower()


def test_render_rate_carries_criteria_and_gotchas():
    p = render_rate("rct", ["2.1", "2.4"], "PAPER", pass_n=1)
    assert "2.1" in p and "2.4" in p and "PAPER" in p
    assert "PRO" in p  # the 2.4 patient-reported-outcome gotcha
    m = render_rate("mixed_methods", ["5.4"], "PAPER", pass_n=2)
    assert "no divergence" in m.lower()


def test_work_lines_carry_rendered_prompt(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    pdf_root = tmp_path / "pdfs"; (pdf_root / "2023").mkdir(parents=True)
    _make_pdf(pdf_root / "2023" / "g.pdf", _EN_PARA)
    _insert_paper(conn, "g", pdf_filename="2023/g.pdf"); set_disposition(conn, "g", "ok")
    out = tmp_path / "c.work.jsonl"
    build_classify_work(conn, 1, "classify-v1", pdf_root, out)
    line = json.loads(out.read_text().splitlines()[0])
    assert "prompt" in line and "S1" in line["prompt"] and "higher education" in line["prompt"]


def test_harness_runbook_exists_and_describes_loop():
    from rrl.appraise.prompts import load_template
    rb = load_template("harness_runbook.md")
    assert "work.jsonl" in rb and "answers.jsonl" in rb and "work_id" in rb


def test_emit_restricted_to_pilot_sample(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    pdf_root = tmp_path / "pdfs"; (pdf_root / "2023").mkdir(parents=True)
    for pid in ("a", "b"):
        _make_pdf(pdf_root / "2023" / f"{pid}.pdf", _EN_PARA)
        _insert_paper(conn, pid, pdf_filename=f"2023/{pid}.pdf"); set_disposition(conn, pid, "ok")
    assign_samples(conn, role="pilot", n=1, seed=1)
    out = tmp_path / "c.work.jsonl"
    n = build_classify_work(conn, 1, "classify-v1", pdf_root, out, restrict_role="pilot")
    assert n == 1


def test_cli_pilot_select_and_only_sample(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(); (tmp_path / "pdfs" / "2023").mkdir(parents=True)
    conn = connect(tmp_path / "data" / "rrl.sqlite"); init_schema(conn)
    for pid in ("a", "b", "c"):
        _make_pdf(tmp_path / "pdfs" / "2023" / f"{pid}.pdf", _EN_PARA)
        _insert_paper(conn, pid, pdf_filename=f"2023/{pid}.pdf"); set_disposition(conn, pid, "ok")
    conn.close()
    r = CliRunner().invoke(main, ["--db", "data/rrl.sqlite", "appraise", "pilot",
                                  "--select", "--n", "2", "--seed", "1"])
    assert r.exit_code == 0, r.output
    r2 = CliRunner().invoke(main, ["--db", "data/rrl.sqlite", "appraise", "classify",
                                   "--emit", "p.work.jsonl", "--only-sample", "pilot"])
    assert r2.exit_code == 0, r2.output
    lines = (tmp_path / "p.work.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2


def test_rate_prompt_carries_locked_thresholds():
    # complete-outcome-data cutoff (2.3 / 3.3) and nonresponse cutoff (4.4) are
    # baked in as uniform yardsticks (MMAT manual: agree a cutoff, apply uniformly).
    assert "80%" in render_rate("rct", ["2.3"], "X", 1)
    assert "80%" in render_rate("quant_nonrandomized", ["3.3"], "X", 1)
    assert "60%" in render_rate("quant_descriptive", ["4.4"], "X", 1)
