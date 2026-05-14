"""rrl CLI entrypoint. Stages are wired in later tasks; this is the skeleton."""
from __future__ import annotations
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
    load_dotenv()
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
    counts = run_harvest(ctx.obj["db"], only=only_list)
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
    click.echo("export: not yet implemented")
    raise click.exceptions.Exit(2)

@main.command(name="all")
@click.option("--skip", default=None, help="Comma-separated stage names to skip")
@click.pass_context
def run_all(ctx, skip):
    """Run all stages in order; resumable."""
    click.echo("all: not yet implemented")
    raise click.exceptions.Exit(2)

@main.command()
@click.option("--paper", default=None, help="Show full lifecycle of one paper_id")
@click.pass_context
def status(ctx, paper):
    """Show per-stage counts and last-run timestamps."""
    db: Path = ctx.obj["db"]
    if not db.exists():
        click.echo(f"No database at {db}. Run `rrl harvest` to create it.")
        return
    click.echo(f"DB: {db}")
