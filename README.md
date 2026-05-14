# AI in Higher Education RRL Pipeline

A Python CLI that harvests, dedupes, screens, and downloads open-access academic papers on AI / GenAI / ChatGPT / LLM adoption in higher education.

## Scope

**Included:** faculty using LLMs to teach; students using AI for coursework; institutional policy/governance; AI-literacy programs that teach students to use AI.

**Excluded:** K-12-only contexts; AI/ML as a CS subject; closed-access papers (corpus is OA-only).

**Date range:** 2020–2026. Papers are tagged `pre_chatgpt` (≤2022) or `post_chatgpt` (≥2023).

## Setup

1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -e .[dev]`
3. `cp .env.example .env` and fill in `OPENALEX_EMAIL`.
4. **Strongly recommended:** add `SEMANTIC_SCHOLAR_API_KEY`. Without it, S2 throttles to 1 req/s — an 8–15k record harvest takes 3–4 hours just for S2. With a free key, it drops to ~30 minutes.
5. Optional: `CORE_API_KEY` for PDF fallback.

## Usage

```
rrl harvest      # search OpenAlex + ERIC + S2
rrl dedup        # build canonical paper rows
rrl enrich       # DOAJ + Unpaywall + OpenAlex flags
rrl screen       # topic / OA / quality filtering
rrl export       # download PDFs, write xlsx, update README appendix
rrl all          # run all stages, resumable
rrl status       # show progress
```

## Limitations

1. OA-only corpus — significant closed-access literature is missing.
2. Topic boundary is regex-based; `review_needed` tier surfaces borderline papers for manual judgment.
3. Predatory-venue detection is best-effort (DOAJ + tiny blocklist).
4. Dedup has known gaps — preprint/journal pairs without shared DOIs may both appear; `rrl dedup --review` surfaces likely duplicates.
5. No content extraction (methods/findings columns intentionally absent).
6. English-only.

<!-- BEGIN AUTO-GENERATED -->
_Auto-generated section. Populated by `rrl export`._
<!-- END AUTO-GENERATED -->
