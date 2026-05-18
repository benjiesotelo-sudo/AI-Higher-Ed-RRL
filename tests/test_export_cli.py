import json
import responses
from pathlib import Path
from click.testing import CliRunner
from rrl.cli import main
from rrl.db import connect, init_schema
from rrl.output.readme import BEGIN_MARK, END_MARK

@responses.activate
def test_export_creates_matrix_manifest_pdfs_and_updates_readme(tmp_path, monkeypatch, fixtures_dir):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    monkeypatch.delenv("ELSEVIER_API_KEY", raising=False)
    monkeypatch.delenv("ELSEVIER_INSTTOKEN", raising=False)
    monkeypatch.delenv("CORE_API_KEY", raising=False)
    conn = connect(tmp_path / "data/rrl.sqlite"); init_schema(conn)
    conn.execute("""INSERT INTO papers (paper_id, title, authors_json, year, era_tag, language,
        is_oa, oa_pdf_url, is_peer_reviewed, work_type, publisher,
        included, quality_tier, first_seen_at, last_updated_at)
        VALUES ('p1','T','[]',2023,'post_chatgpt','en',1,'https://x/y.pdf',1,'journal-article','Springer',
                1,'high_confidence','now','now')""")
    pdf_bytes = (fixtures_dir / "sample.pdf").read_bytes()
    responses.add(responses.GET, "https://x/y.pdf", body=pdf_bytes,
                  content_type="application/pdf", status=200)
    (tmp_path / "README.md").write_text(
        f"# A\n\nIntro.\n\n{BEGIN_MARK}\nold\n{END_MARK}\n\nFooter.\n", encoding="utf-8")
    r = CliRunner().invoke(main, ["export"])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "output/rrl_matrix.xlsx").exists()
    assert (tmp_path / "output/run_manifest.json").exists()
    pdfs = list((tmp_path / "pdfs").rglob("*.pdf"))
    assert len(pdfs) == 1
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "Run statistics" in readme or "Last run" in readme
    assert "# A" in readme and "Footer." in readme
