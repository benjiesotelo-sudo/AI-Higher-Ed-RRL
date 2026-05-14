"""rrl CLI entrypoint. Stages are wired in later tasks; this is the skeleton."""
from __future__ import annotations
import json
from pathlib import Path

import click
from dotenv import load_dotenv

DEFAULT_DB = Path("data/rrl.sqlite")
DEFAULT_LOG_DIR = Path("logs")

@click.group()
@click.option("--db", type=click.Path(path_type=Path), default=DEFAULT_DB, show_default=True)
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def main(ctx: click.Context, db: Path, verbose: bool) -> None:
    """RRL pipeline for AI-in-higher-ed literature."""
    # Load .env from the current working directory only (not walking up the
    # filesystem). override=True so values in .env take precedence over any
    # stale value left in the shell environment (e.g., the .env.example
    # placeholder). Tests that chdir to a tmp dir without a .env are unaffected.
    load_dotenv(dotenv_path=Path(".env"), override=True)
    ctx.ensure_object(dict)
    ctx.obj["db"] = db
    ctx.obj["verbose"] = verbose

@main.command()
@click.option("--only", default=None, help="Comma-separated adapter names")
@click.option("--since", default=None, help="YYYY-MM-DD; harvest only papers since this date")
@click.pass_context
def harvest(ctx, only, since):
    """Search OpenAlex / ERIC / Semantic Scholar; persist raw_records."""
    from rrl.harvest import harvest as run_harvest
    only_list = [a.strip() for a in only.split(",")] if only else None
    counts = run_harvest(ctx.obj["db"], only=only_list, since=since)
    for adapter, n in counts.items():
        click.echo(f"{adapter}: {n} new records")

@main.command()
@click.option("--review", is_flag=True, help="Write data/dedup_review.csv")
@click.option("--merge", nargs=2, type=str, default=None, metavar="LOSER WINNER")
@click.pass_context
def dedup(ctx, review, merge):
    """Build canonical papers from raw_records."""
    from rrl.db import connect, init_schema
    from rrl.dedup.grouping import run_dedup
    from rrl.dedup.review import write_review_csv
    from rrl.dedup.merge import merge_papers
    db_path = ctx.obj["db"]
    conn = connect(db_path); init_schema(conn)
    if merge:
        loser, winner = merge
        merge_papers(conn, loser, winner, pdf_root=Path("pdfs"))
        click.echo(f"merged {loser} into {winner}")
        return
    if review:
        n = write_review_csv(conn, Path("data/dedup_review.csv"))
        click.echo(f"wrote {n} candidate pair(s) to data/dedup_review.csv")
        return
    summary = run_dedup(conn)
    click.echo(f"raw_records: {summary['raw_records']}; papers: {summary['papers_created']}")

@main.command()
@click.option("--only", default=None, help="doaj|unpaywall|openalex")
@click.pass_context
def enrich(ctx, only):
    """Attach DOAJ + Unpaywall + OpenAlex quality flags."""
    from rrl.db import connect, init_schema
    from rrl.config import Settings
    from rrl.http import build_session
    from rrl.enrich.openalex_flags import enrich_from_openalex_payloads
    from rrl.enrich.doaj import enrich_papers_with_doaj
    from rrl.enrich.unpaywall import enrich_papers_with_unpaywall
    settings = Settings.from_env()
    conn = connect(ctx.obj["db"]); init_schema(conn)
    sess = build_session(settings.openalex_email)
    passes = (only or "openalex,doaj,unpaywall").split(",")
    if "openalex" in passes:
        s = enrich_from_openalex_payloads(conn); click.echo(f"openalex: {s}")
    if "doaj" in passes:
        s = enrich_papers_with_doaj(conn, sess); click.echo(f"doaj: {s}")
    if "unpaywall" in passes:
        s = enrich_papers_with_unpaywall(conn, sess, settings.openalex_email); click.echo(f"unpaywall: {s}")

@main.command()
@click.option("--dry-run", is_flag=True)
@click.pass_context
def screen(ctx, dry_run):
    """Apply topic/OA/quality filters; assign tier and era."""
    from rrl.db import connect, init_schema
    from rrl.screen.runner import run_screen
    conn = connect(ctx.obj["db"]); init_schema(conn)
    summary = run_screen(conn, dry_run=dry_run)
    for k, v in sorted(summary.items()):
        click.echo(f"{k}: {v}")

@main.command()
@click.option("--retry-failed", is_flag=True)
@click.pass_context
def export(ctx, retry_failed):
    """Download PDFs, write xlsx + manifest, update README appendix."""
    from rrl.config import Settings
    from rrl.http import build_session
    from rrl.output.runner import run_export
    settings = Settings.from_env()
    sess = build_session(settings.openalex_email)
    summary = run_export(
        ctx.obj["db"],
        session=sess,
        pdf_root=Path("pdfs"),
        matrix_path=Path("output/rrl_matrix.xlsx"),
        manifest_path=Path("output/run_manifest.json"),
        readme_path=Path("README.md"),
        core_api_key=settings.core_api_key,
        retry_failed=retry_failed,
    )
    click.echo(json.dumps(summary, indent=2, default=str))

@main.command(name="all")
@click.option("--skip", default="", help="Comma-separated stage names to skip")
@click.pass_context
def run_all(ctx, skip):
    """Run all stages in order; resumable."""
    from rrl.config import Settings
    from rrl.db import connect, init_schema
    from rrl.http import build_session
    skipped = {s.strip() for s in skip.split(",") if s.strip()}

    if "harvest" not in skipped:
        from rrl.harvest import harvest as run_harvest
        click.echo("== harvest ==")
        run_harvest(ctx.obj["db"])

    db = ctx.obj["db"]
    conn = connect(db); init_schema(conn)

    if "dedup" not in skipped:
        from rrl.dedup.grouping import run_dedup
        click.echo("== dedup ==")
        click.echo(run_dedup(conn))

    if "enrich" not in skipped:
        settings = Settings.from_env()
        sess = build_session(settings.openalex_email)
        from rrl.enrich.openalex_flags import enrich_from_openalex_payloads
        from rrl.enrich.doaj import enrich_papers_with_doaj
        from rrl.enrich.unpaywall import enrich_papers_with_unpaywall
        click.echo("== enrich ==")
        enrich_from_openalex_payloads(conn)
        enrich_papers_with_doaj(conn, sess)
        enrich_papers_with_unpaywall(conn, sess, settings.openalex_email)

    if "screen" not in skipped:
        from rrl.screen.runner import run_screen
        click.echo("== screen ==")
        click.echo(run_screen(conn))

    if "export" not in skipped:
        settings = Settings.from_env()
        sess = build_session(settings.openalex_email)
        from rrl.output.runner import run_export
        click.echo("== export ==")
        run_export(
            db=db,
            session=sess,
            pdf_root=Path("pdfs"),
            matrix_path=Path("output/rrl_matrix.xlsx"),
            manifest_path=Path("output/run_manifest.json"),
            readme_path=Path("README.md"),
            core_api_key=settings.core_api_key,
        )

@main.command()
@click.option("--paper", default=None, help="Show full lifecycle of one paper_id")
@click.pass_context
def status(ctx, paper):
    """Show per-stage counts and last-run timestamps."""
    from rrl.db import connect, init_schema
    db = ctx.obj["db"]
    if not db.exists():
        click.echo(f"No database at {db}. Run `rrl harvest` to create it.")
        return
    conn = connect(db); init_schema(conn)
    if paper:
        row = conn.execute("SELECT * FROM papers WHERE paper_id=?", (paper,)).fetchone()
        if not row:
            click.echo(f"No paper with id {paper}")
            return
        for k in row.keys():
            click.echo(f"{k}: {row[k]}")
        sources = conn.execute(
            """SELECT rr.adapter, rr.external_id FROM paper_sources ps
               JOIN raw_records rr ON rr.raw_id = ps.raw_id WHERE ps.paper_id=?""",
            (paper,),
        ).fetchall()
        click.echo("sources: " + ", ".join(f"{s['adapter']}:{s['external_id']}" for s in sources))
        return
    n = lambda sql, *a: conn.execute(sql, a).fetchone()[0]
    click.echo(f"raw_records: {n('SELECT COUNT(*) FROM raw_records')}")
    click.echo(f"papers: {n('SELECT COUNT(*) FROM papers')}")
    click.echo(f"papers included: {n('SELECT COUNT(*) FROM papers WHERE included = 1')}")
    click.echo(f"papers downloaded: {n('SELECT COUNT(*) FROM papers WHERE pdf_status = ?', 'downloaded')}")
    click.echo("search_runs:")
    for r in conn.execute("SELECT adapter, status, finished_at, records_new FROM search_runs ORDER BY started_at DESC").fetchall():
        click.echo(f"  {r['adapter']:<10} {r['status']:<7} {r['finished_at'] or '':<28} new={r['records_new']}")
