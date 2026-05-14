# AI in Higher Education RRL Pipeline

A Python CLI that harvests, deduplicates, screens, and downloads **open-access** academic papers on AI / GenAI / ChatGPT / LLM **adoption** in higher education, then produces an RRL (review-of-related-literature) matrix in xlsx, the downloaded PDFs, and structured logs.

## What this is for

A reproducible, auditable corpus you can read and cite. Two output tiers — `high_confidence` and `review_needed` — surface borderline papers for manual judgment rather than silently dropping them.

## Scope

**Included.** Faculty using ChatGPT / LLMs to teach. Students using AI tools for coursework (surveys, attitudes, academic integrity, learning outcomes). Institutional policy / governance. AI-literacy programs that teach students *to use* AI.

**Excluded.** K-12-only contexts. AI/ML as a CS subject ("AI-as-curriculum"). Closed-access papers. Non-English papers.

**Date range:** 2020–2026, tagged `pre_chatgpt` (≤2022) and `post_chatgpt` (≥2023).

**Sources:** OpenAlex (primary), ERIC (education-specific gray lit), Semantic Scholar (broad). DOAJ + Unpaywall for quality + OA verification. CrossRef + CORE on demand.

## Setup

1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -e .[dev]`
3. `cp .env.example .env`, then fill in:
   - **`OPENALEX_EMAIL`** — required. Used in the User-Agent for OpenAlex and as the `email` param for Unpaywall.
   - **`SEMANTIC_SCHOLAR_API_KEY`** — *practically required.* Without a key, Semantic Scholar throttles to 1 req/s; an 8–15k-record harvest takes 3–4 hours just for S2. With a free key (https://www.semanticscholar.org/product/api), it drops to ~30 minutes. **The pipeline runs without it but logs a warning at startup.**
   - **`CORE_API_KEY`** — optional. Only used if Unpaywall + OpenAlex OA links both fail for a paper.

## Usage

```bash
rrl harvest              # search OpenAlex + ERIC + S2 → raw_records
rrl dedup                # build canonical papers (DOI → OpenAlex ID → signature)
rrl dedup --review       # write data/dedup_review.csv of likely duplicates
rrl dedup --merge L W    # manually merge paper L into paper W
rrl enrich               # DOAJ + Unpaywall + OpenAlex flags
rrl screen               # apply topic / OA / quality filters
rrl export               # download PDFs → output/rrl_matrix.xlsx + README appendix
rrl all                  # run every stage in order, resumable
rrl status               # counts and last-run timestamps
rrl status --paper PID   # full lifecycle of one paper
```

All stages are idempotent and resumable. A crash mid-stage = rerun the same command; nothing is duplicated.

## Output

- `output/rrl_matrix.xlsx` — two sheets, `high_confidence` and `review_needed`. Columns are bibliographic + quality flags. No NLP-extracted fields (methods/findings) — you fill those manually while reading.
- `pdfs/<year>/<paper_id>.pdf` — downloaded OA PDFs.
- `output/run_manifest.json` — pipeline version, query terms hash, counts, SHA-256 of the xlsx. For reproducibility.
- `logs/<stage>-YYYY-MM-DD.jsonl` — every search query, dedup decision, screening rejection, PDF attempt.
- `data/rrl.sqlite` — internal state (WAL mode). Inspectable; restartable.

## Limitations (read this before citing)

1. **OA-only corpus.** Significant closed-access literature in flagship journals (Computers & Education, Studies in Higher Education, Internet & Higher Education) is **not** in the matrix. This is *not* "the literature" — it is the open-access slice of it.
2. **Topic boundary is regex-based.** The K-12-only / AI-as-curriculum exclusions and the AI/HE inclusion are keyword filters. The `review_needed` tier exists to surface borderline calls for human judgment.
3. **Predatory-venue detection is best-effort.** No comprehensive free machine-readable list exists. We use DOAJ membership + a tiny blocklist of universally-acknowledged repeat offenders. Anything dubious lands in `review_needed`.
4. **Dedup has known gaps.** Preprint/journal pairs without shared DOIs may both appear; `rrl dedup --review` surfaces likely duplicates for manual merge.
5. **No content interpretation.** Methods, sample, findings, theoretical framework — those columns are intentionally absent. They cannot be auto-extracted reliably.
6. **English-only.** Significant work in Mandarin, Spanish, Portuguese, and other languages is excluded.

## Architecture

```
harvest → dedup → enrich → screen → export
   ↓        ↓        ↓        ↓        ↓
            SQLite (data/rrl.sqlite)
                                       → pdfs/<year>/*.pdf
                                       → output/rrl_matrix.xlsx
                                       → output/run_manifest.json
                                       → README.md (auto-generated block below)
                                       → logs/*.jsonl
```

Full design spec: `docs/superpowers/specs/2026-05-14-rrl-pipeline-design.md`.

## Development

```bash
pytest -q            # all tests; uses mocked HTTP via the `responses` library
ruff check rrl       # lint
mypy rrl             # types
```

No live API calls in CI. For a live smoke test: `rrl harvest --only=openalex --since 2026-01-01` (small slice).

<!-- BEGIN AUTO-GENERATED -->
_Auto-generated section. Populated by `rrl export`._
<!-- END AUTO-GENERATED -->
