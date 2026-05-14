# AI in Higher Education RRL Pipeline — Design Spec

**Status:** Approved 2026-05-14
**Owner:** benjiesotelo@gmail.com
**Scope:** This document is the authoritative design for the automated literature-collection pipeline. It defines architecture, data model, per-stage behavior, and operational constraints. An implementation plan will be derived from this spec separately.

---

## 1. Purpose & success criteria

Build a Python CLI pipeline that harvests, deduplicates, screens, and downloads open-access academic papers on AI/GenAI/ChatGPT/LLM adoption in higher education. Outputs are:

1. A two-sheet `.xlsx` RRL matrix with structured metadata per included paper.
2. Downloaded OA PDFs in a year-bucketed directory.
3. Structured `.jsonl` logs of search queries, API responses, dedup decisions, screening rejections, and PDF download attempts.
4. A `README.md` with hand-written project explanation plus a clearly-delimited auto-generated run-statistics appendix.

**Success criteria:**
- Reproducible: rerunning the pipeline against the same inputs produces the same matrix (modulo new papers added upstream).
- Auditable: every paper in the matrix can be traced back to its raw API records and every exclusion can be traced back to a documented rule.
- Resumable: a crash or interruption at any stage is recoverable by rerunning the same command.
- Honest: the README explicitly states the scope limitations (OA-only, date range, topic-boundary edge cases).

## 2. Inclusion criteria (locked)

**Topic — INCLUDED:**
- Faculty using ChatGPT / LLMs / GenAI to teach (lesson planning, feedback, grading assistance, instruction integration).
- Students using AI tools for coursework (surveys, attitudes, academic integrity, learning outcomes).
- Institutional policy / governance (university policies, syllabus statements, academic integrity frameworks, faculty development).
- AI literacy programs that teach students **to use** AI (prompting, evaluation, ethical use).

**Topic — EXCLUDED:**
- K-12 contexts where higher education is not also present.
- AI-as-CS-subject (machine learning courses, AI/ML curriculum design as a discipline).

**Date:** 2020–2026 inclusive. Papers are tagged `era_tag = 'pre_chatgpt'` (year ≤ 2022) or `'post_chatgpt'` (year ≥ 2023).

**Language:** English. Verified via API metadata first (`papers.language == 'en'`). When the API did not supply a language (`papers.language IS NULL`), `langdetect` is run against the abstract; the detected value is written back to `papers.language` before the filter is applied. Records that fail both — null language with no abstract to detect from — are excluded with `exclusion_reason = 'non_english'`.

**Access:** **Open access only.** The pipeline downloads only papers with a legally accessible PDF (via Unpaywall, OpenAlex OA URL, or CORE fallback). Closed-access papers are excluded from the corpus. The README states this scope limitation prominently.

**Study type:** Permissive — empirical, reviews, conceptual, policy all welcomed.

**Quality:** Peer-reviewed preferred but not strictly required. Quality is signaled in two output tiers:
- `high_confidence` — peer-reviewed OR DOAJ-listed, work_type in {journal-article, proceedings-article, review}, publisher not on predatory blocklist. `book-chapter` qualifies only when publisher is on the academic-press allowlist.
- `review_needed` — passes topic/date/OA filters but doesn't meet `high_confidence` criteria. Surfaced for manual judgment.

## 3. Architectural overview

A staged Python CLI pipeline with state persisted in a single SQLite file. Five stages, each a separate module with stable interfaces. State flows forward through SQLite; stages do not call each other directly.

```
harvest → dedup → enrich → screen → export
   ↓        ↓        ↓        ↓        ↓
                SQLite (data/rrl.sqlite)
                                          → pdfs/<year>/*.pdf
                                          → output/rrl_matrix.xlsx
                                          → output/run_manifest.json
                                          → README.md (appendix block)
                                          → logs/*.jsonl
```

**Why staged:** harvest is slow and rarely changes; screening rules will be iterated many times. Separating stages allows tuning screen/enrich rules without re-hitting search APIs.

**Repo layout:**
```
ai-higher-ed-rrl/
├── README.md                       # hand-written + auto-generated appendix
├── pyproject.toml                  # uv/pip-installable; deps pinned
├── .env.example                    # OPENALEX_EMAIL, S2_API_KEY, CORE_API_KEY
├── rrl/
│   ├── __init__.py
│   ├── cli.py                      # click entrypoint
│   ├── config.py                   # AI_TERMS, HE_TERMS, K12_TERMS, blocklist, allowlist, rate plans
│   ├── db.py                       # SQLite schema + migrations + connection
│   ├── http.py                     # shared session, rate-limited, polite-pool User-Agent
│   ├── logging_setup.py            # structlog → jsonl files + console
│   ├── search/
│   │   ├── base.py                 # SearchAdapter protocol; QuerySpec; RawRecord
│   │   ├── openalex.py
│   │   ├── eric.py
│   │   ├── semantic_scholar.py
│   │   ├── crossref.py             # fallback / on-demand
│   │   └── core_api.py             # PDF fallback only
│   ├── dedup/
│   │   └── grouping.py             # DOI/OpenAlex/signature cascade; canonical resolution
│   ├── enrich/
│   │   ├── doaj.py
│   │   └── unpaywall.py
│   ├── screen/
│   │   └── rules.py                # topic regex, K-12, OA, date, era, tiering
│   └── output/
│       ├── pdf.py                  # download w/ validation + retries
│       ├── matrix.py               # openpyxl writer, two sheets
│       └── readme.py               # appendix-block-only writer
├── tests/
│   ├── fixtures/                   # canned API responses, sample.pdf, seed_db.sql
│   └── test_*.py
├── data/   (gitignored)
├── pdfs/   (gitignored)
├── logs/   (gitignored)
├── output/
│   ├── rrl_matrix.xlsx
│   └── run_manifest.json
└── docs/superpowers/specs/
    └── 2026-05-14-rrl-pipeline-design.md
```

**CLI commands:**
```
rrl harvest [--only ADAPTER[,...]] [--since YYYY-MM-DD]
rrl dedup   [--review]   |   rrl dedup --merge LOSER_ID WINNER_ID
rrl enrich  [--only doaj|unpaywall|openalex]
rrl screen  [--dry-run]
rrl export  [--retry-failed]
rrl all     [--skip STAGE[,...]]
rrl status  [--paper PAPER_ID]
```

Exit codes: `0` success, `1` user error, `2` system error.

## 4. Data model (SQLite)

Six tables. All `TEXT` columns are UTF-8; all timestamps are ISO 8601 UTC. SQLite is run with `PRAGMA journal_mode=WAL`.

```sql
-- 1. Every harvest invocation
CREATE TABLE search_runs (
  run_id          TEXT PRIMARY KEY,
  adapter         TEXT NOT NULL,
  query_hash      TEXT NOT NULL,
  query_payload   TEXT NOT NULL,
  started_at      TEXT NOT NULL,
  finished_at     TEXT,
  status          TEXT NOT NULL,            -- 'running' | 'ok' | 'error'
  records_found   INTEGER,
  records_new     INTEGER,
  error_message   TEXT,
  cursor_state    TEXT                       -- resume token / cursor for crash recovery
);

-- 2. Raw normalized API records, one per (adapter, external_id)
CREATE TABLE raw_records (
  raw_id          INTEGER PRIMARY KEY,
  run_id          TEXT NOT NULL REFERENCES search_runs(run_id),
  adapter         TEXT NOT NULL,
  external_id     TEXT NOT NULL,
  doi             TEXT,
  title           TEXT,
  title_norm      TEXT,
  authors_json    TEXT,
  first_author    TEXT,
  year            INTEGER,
  venue           TEXT,
  abstract        TEXT,
  language        TEXT,
  raw_payload     TEXT NOT NULL,             -- full API JSON
  fetched_at      TEXT NOT NULL,
  UNIQUE (adapter, external_id)
);
CREATE INDEX idx_raw_doi      ON raw_records(doi)        WHERE doi IS NOT NULL;
CREATE INDEX idx_raw_titleyr  ON raw_records(title_norm, year, first_author);

-- 3. Canonical papers (post-dedup, post-enrich, post-screen)
CREATE TABLE papers (
  paper_id            TEXT PRIMARY KEY,       -- deterministic from dedup key
  doi                 TEXT UNIQUE,
  title               TEXT NOT NULL,
  authors_json        TEXT NOT NULL,
  year                INTEGER NOT NULL,
  era_tag             TEXT,                    -- 'pre_chatgpt' | 'post_chatgpt'
  venue               TEXT,
  publisher           TEXT,
  work_type           TEXT,
  language            TEXT,
  abstract            TEXT,
  citation_count      INTEGER,

  -- Enrichment
  is_in_doaj          INTEGER,                 -- 0 | 1 | NULL
  is_peer_reviewed    INTEGER,
  is_oa               INTEGER,
  oa_status           TEXT,                    -- gold | green | bronze | hybrid | closed
  oa_pdf_url          TEXT,

  -- Screening
  included            INTEGER,                 -- 0 | 1
  exclusion_reason    TEXT,                    -- 'not_oa' | 'off_topic' | 'wrong_date' | 'non_english' | 'k12_only'
  quality_tier        TEXT,                    -- 'high_confidence' | 'review_needed'
  topic_match_score   REAL,

  -- Output
  pdf_filename        TEXT,
  pdf_status          TEXT,                    -- 'downloaded' | 'oa_link_dead' | 'not_attempted' | 'merged_to_winner'

  first_seen_at       TEXT NOT NULL,
  last_updated_at     TEXT NOT NULL
);
CREATE INDEX idx_papers_year     ON papers(year);
CREATE INDEX idx_papers_included ON papers(included);
CREATE INDEX idx_papers_tier     ON papers(quality_tier);

-- 4. Provenance: which raw_records back each canonical paper
CREATE TABLE paper_sources (
  paper_id        TEXT NOT NULL REFERENCES papers(paper_id),
  raw_id          INTEGER NOT NULL REFERENCES raw_records(raw_id),
  PRIMARY KEY (paper_id, raw_id)
);
CREATE INDEX idx_paper_sources_raw ON paper_sources(raw_id);

-- 5. Append-only PDF download log
CREATE TABLE pdf_attempts (
  attempt_id      INTEGER PRIMARY KEY,
  paper_id        TEXT NOT NULL REFERENCES papers(paper_id),
  source          TEXT NOT NULL,               -- 'unpaywall' | 'openalex_oa_url' | 'core'
  url             TEXT NOT NULL,
  http_status     INTEGER,
  content_type    TEXT,
  bytes_received  INTEGER,
  outcome         TEXT NOT NULL,               -- 'ok' | 'http_error' | 'not_pdf' | 'timeout' | 'rate_limited'
  error_message   TEXT,
  attempted_at    TEXT NOT NULL
);

-- 6. Manual dedup merges (from `rrl dedup --merge`)
CREATE TABLE paper_merges (
  loser_id        TEXT PRIMARY KEY REFERENCES papers(paper_id),
  winner_id       TEXT NOT NULL REFERENCES papers(paper_id),
  merged_at       TEXT NOT NULL,
  merged_by       TEXT NOT NULL                -- 'manual' (only value used today; column reserved for future automated-merge rules)
);

-- Schema versioning
CREATE TABLE schema_version (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);
```

**Invariants:**
- `raw_records.UNIQUE(adapter, external_id)` — re-harvesting cannot duplicate.
- `papers.paper_id` is deterministic from the dedup key — re-running dedup is idempotent.
- `papers.doi UNIQUE` — the most common dedup failure mode is prevented at the DB level.
- `pdf_attempts` is append-only — every retry leaves a trail.
- Every UPSERT updates `last_updated_at`.

**Lifecycle of one paper:**
1. `harvest` → 1+ rows in `raw_records`.
2. `dedup` → 1 row in `papers` + 1+ rows in `paper_sources`.
3. `enrich` → DOAJ / Unpaywall / OpenAlex flags populated.
4. `screen` → `included`, `quality_tier`, `era_tag`, `exclusion_reason` populated.
5. `export` → `pdf_attempts` rows; on success, `pdf_filename` + `pdf_status` set on `papers`.

**Matrix query:**
```sql
SELECT ... FROM papers
WHERE included = 1
  AND pdf_status = 'downloaded'
  AND paper_id NOT IN (SELECT loser_id FROM paper_merges)
```

## 5. Search stage

**Principle:** Search maximizes recall. Topic filtering happens in `screen`, not in the query.

### Common interface (`search/base.py`)

```python
@dataclass(frozen=True)
class QuerySpec:
    ai_terms: list[str]
    he_terms: list[str]
    year_min: int
    year_max: int
    language: str = "en"

@dataclass(frozen=True)
class RawRecord:
    external_id: str
    doi: str | None
    title: str
    authors: list[dict]
    year: int | None
    venue: str | None
    abstract: str | None
    language: str | None
    raw_payload: dict

class SearchAdapter(Protocol):
    name: str
    def search(self, q: QuerySpec, run_id: str) -> Iterator[RawRecord]: ...
```

### Query terms (`config.py`)

```python
AI_TERMS = [
    "artificial intelligence",
    "generative AI", "generative artificial intelligence", "GenAI",
    "ChatGPT", "GPT-3", "GPT-3.5", "GPT-4", "GPT-4o",
    "large language model", "LLM", "LLMs",
    "Bard", "Gemini", "Claude", "Copilot",
]
HE_TERMS = [
    "higher education", "university", "universities",
    "college", "colleges", "undergraduate", "postgraduate",
    "graduate student", "tertiary education",
    "faculty", "professor", "instructor", "lecturer", "academia",
]
```

Bare "AI" is **excluded** — too noisy across unrelated domains.

### Per-adapter behavior

| Adapter | Endpoint | Auth | Rate plan | Date filter | Lang filter | Expected volume |
|---|---|---|---|---|---|---|
| OpenAlex | `api.openalex.org/works` | polite pool (`mailto:<email>` in User-Agent; required env var) | 10 req/s, cursor pagination, 200/page | `from_publication_date:2020-01-01` | `language:en` | ~15–25k |
| ERIC | `api.ies.ed.gov/eric/` | none | self-throttle 1 req/s, `rows=2000` | `publicationdateyear:[2020 TO 2026]` | corpus predominantly English | ~3–5k |
| Semantic Scholar | `api.semanticscholar.org/graph/v1/paper/search/bulk` | `S2_API_KEY` env var (5 req/s with, 1 req/s without) | token-paginated, 100/page | `year=2020-2026` | filter post-hoc on `language` | ~8–15k |
| CrossRef | `api.crossref.org/works` | polite pool (`mailto:` query param) | ~50 req/s | `from-pub-date:2020` | none — post-hoc | **on-demand only** (used by enrich for missing metadata) |
| CORE | `api.core.ac.uk/v3/` | `CORE_API_KEY` env var | 10 req/min | n/a | n/a | **on-demand only** (used by export for PDF fallback) |

Total raw search budget: ~25k–45k records before dedup. Wall-clock for a clean run: ~45–90 min.

> **S2 API key is practically required.** Without it, S2 throttles to 1 req/s; an ~8–15k-record harvest takes 3–4 hours just for S2. With a free key, it drops to ~30 minutes. The README setup section must call this out prominently.

### Query rendering

Each adapter renders `(AI terms) AND (HE terms) AND date AND lang` in its native syntax:
- **OpenAlex**: `filter=abstract.search:"<AI terms>",abstract.search:"<HE terms>",from_publication_date:2020-01-01,language:en,type:journal-article|book-chapter|proceedings-article`
- **ERIC**: Solr-like — `q=(title:(...) OR description:(...)) AND (descriptor:"Higher Education" OR description:(...)) AND publicationdateyear:[2020 TO 2026]`
- **Semantic Scholar**: `query=(<AI terms>) (<HE terms>)&year=2020-2026&fieldsOfStudy=Education,Computer Science`

Query strings are SHA-256-hashed into `search_runs.query_hash` for repeat-run detection.

### Shared HTTP layer (`http.py`)

One `requests.Session`, wrapped with:
- per-host token bucket per the rate plan
- 3 retries with exponential backoff on 429 / 5xx / connection errors (`urllib3.Retry`)
- 30s default timeout (60s for PDF downloads)
- `User-Agent: rrl-pipeline/<ver> (mailto:<OPENALEX_EMAIL>)` on every request

### Failure modes

- **Adapter unrecoverable** (4xx other than 429): `search_runs.status='error'`; other adapters continue.
- **Mid-pagination crash**: cursor/token checkpointed in `search_runs.cursor_state`; resume picks up.
- **One adapter offline**: `rrl harvest --only=openalex,eric` skips the broken one.

### Out of scope for this stage

- No relevance scoring, no abstract-content sniffing, no topic decisions. All deferred to `screen`.
- No metadata enrichment. Deferred to `enrich`.
- No PDF fetching. Deferred to `export`.

### Incremental harvest

`rrl harvest --since 2026-04-01` adds a `from_publication_date:2026-04-01` filter to each adapter. The pipeline supports this from day one even if the first run goes full range.

## 6. Dedup stage

**The hardest part of the pipeline.** Same paper appears across OpenAlex, ERIC, and S2 under different IDs and title variants.

### Dedup-key cascade

For every `raw_record`, compute a dedup key using the first applicable rule:

1. **DOI key** — `normalize_doi(doi)` (lowercase; strip `https://doi.org/`; strip trailing punctuation). Highest confidence.
2. **OpenAlex ID key** — `openalex:W<id>`. OpenAlex's own reconciliation (preprint + journal version) is trustworthy.
3. **Signature key** — `sig:sha1(title_norm | year | first_author_norm)` where:
   - `title_norm` = lowercase, strip non-alphanumeric, collapse whitespace, drop stopwords (`the a an of for and to in on with`), strip diacritics.
   - `first_author_norm` = lowercase family name only, stripped of accents/punctuation.
   - Year is **exact** — preprint year `2023` and journal-version year `2024` produce different sigs; this false-negative class is caught by the optional review tool.

The **first** key that resolves wins.

**Fallback for records that resolve none of the three:** if a `raw_record` has no DOI, no OpenAlex ID, and either a missing title or missing first-author, it gets a singleton key `singleton:raw_<raw_id>` and becomes its own paper. This is rare and logged at WARN level; it covers degenerate API responses without silently dropping them.

### `paper_id` derivation

`paper_id = sha1(dedup_key)[:16]`. Deterministic. Re-running `dedup` produces identical `paper_id`s.

### Algorithm (single pass, ~O(N))

```
1. Load all raw_records into memory.
2. For each raw_record:
     dk = compute_dedup_key(raw)
     pid = sha1(dk)[:16]
     group_map[pid].append(raw)
3. For each (pid, raws):
     canonical = build_canonical_paper(raws)
     UPSERT into papers (pid, ...canonical...)
     For each raw: ensure paper_sources(pid, raw.raw_id).
```

UPSERT (`ON CONFLICT(paper_id) DO UPDATE`) keeps the stage idempotent.

### Canonical field resolution

When multiple `raw_records` back one paper:

| Field | Rule |
|---|---|
| `doi` | first non-null, normalized |
| `title` | longest non-null; tie-break by source priority `openalex > crossref > eric > s2` |
| `authors_json` | source with the most authors; tie-break by ORCID presence |
| `year` | minimum year across sources (favors original over reprint) |
| `venue` | source priority above |
| `abstract` | longest non-null |
| `language` | majority vote; OpenAlex fallback |
| `citation_count` | max across sources |
| `work_type` | source priority above |

### Known dedup-cascade gaps (accepted)

- Preprint + journal version with different DOIs and slightly different titles → different signatures. Caught by review tool, not auto-merged.
- Title-only updates between preprint and journal (subtitle change) → won't match.
- Author-name variants beyond diacritic stripping (e.g., transliteration differences) → won't match.

### Fuzzy review (`rrl dedup --review`)

A second mode that flags likely duplicates without merging:
- Block by `(first_author_norm, year ± 1)`.
- Within each block, compute `rapidfuzz.token_sort_ratio` on titles.
- Write pairs with similarity ≥ 0.85 to `data/dedup_review.csv`, sorted descending.
- User eyeballs; `rrl dedup --merge LOSER WINNER` writes to `paper_merges`.

Final queries respect merges via `paper_id NOT IN (SELECT loser_id FROM paper_merges)`.

**Merge resolution rules** when `rrl dedup --merge LOSER WINNER` runs:
- `paper_sources` rows pointing at `loser_id` are repointed to `winner_id` (provenance accumulates on the winner).
- If `winner` lacks a downloaded PDF and `loser` has one, the file is moved and `winner.pdf_filename` / `pdf_status` are copied from `loser` (and `loser.pdf_status` set to `'merged_to_winner'`).
- `pdf_attempts` rows stay attached to their original `paper_id` for audit trail.
- Enrichment columns: if `winner` is missing a field that `loser` has (e.g., `winner.is_in_doaj IS NULL` but `loser.is_in_doaj = 1`), copy from loser. This handles cases where the merge is correct but the winner came from a metadata-poor source.

### Out of scope

- No abstract-content similarity matching (too expensive at corpus size, too noisy).
- No author-network analysis.
- No automatic fuzzy merging — deterministic cascade only; everything fuzzy is human-reviewed.

## 7. Enrich stage

Goal: populate quality / OA flags from authoritative external sources. No topic decisions here.

### Three passes (all idempotent)

**1. OpenAlex-derived flags** — lifted from `raw_records.raw_payload` for OpenAlex records. Free; no API call.

| Column | Source field |
|---|---|
| `is_oa` | `open_access.is_oa` |
| `oa_status` | `open_access.oa_status` |
| `oa_pdf_url` | `best_oa_location.pdf_url` (initial; Unpaywall overrides below) |
| `work_type` | `type` |
| `is_peer_reviewed` | derived: `type` in {journal-article, book-chapter, proceedings-article, review} AND `primary_location.source.type != 'repository'` |
| `publisher` | `primary_location.source.host_organization_name` |
| `citation_count` | `cited_by_count` |

Papers found only via ERIC or S2 (no OpenAlex match) get these from their own payloads where available.

**2. DOAJ verification** (`enrich/doaj.py`)

For each paper with an ISSN:
- `GET https://doaj.org/api/v3/search/journals/issn:<ISSN>`
- Set `is_in_doaj = 1` if returned, else `0`. No ISSN → `NULL`.
- OpenAlex/DOAJ mismatches are logged; DOAJ wins.
- Rate: 2 req/s polite. Cached in DB.

**3. Unpaywall PDF lookup** (`enrich/unpaywall.py`)

For each paper with a DOI:
- `GET https://api.unpaywall.org/v2/<DOI>?email=<OPENALEX_EMAIL>`
- If `best_oa_location.url_for_pdf` exists, overwrite `oa_pdf_url`.
- No DOI → skip; OpenAlex's `oa_pdf_url` stands; CORE fallback runs in export if needed.
- Rate: very generous; not a practical concern.

### `oa_pdf_url` precedence by end of enrich

1. Unpaywall `best_oa_location.url_for_pdf` (if DOI present)
2. OpenAlex `best_oa_location.pdf_url`
3. CORE title/DOI search — only attempted in `export` if 1 and 2 are dead AND the paper passes screening

## 8. Screen stage

Goal: decide `included`, `exclusion_reason`, `quality_tier`, `era_tag`. **All decisions derived from columns already in `papers` — no network calls.** Re-runnable cheaply (seconds).

### Filter chain (first rejection wins)

```
1. date_in_range?     year >= 2020 AND year <= 2026
2. language_english?  language == 'en' (langdetect fallback on abstract)
3. is_open_access?    is_oa == 1 AND oa_pdf_url IS NOT NULL
4. topic_match?       (see below)
5. not_k12_only?      (see below)
   → if all pass: included = 1, assign quality_tier and era_tag
```

### Topic match

Two compiled case-insensitive regexes:
- `AI_RE` = `\b(artificial intelligence|generative AI|GenAI|ChatGPT|GPT-3|GPT-3\.5|GPT-4|GPT-4o|large language model|LLM|LLMs|Bard|Gemini|Claude|Copilot)\b`
- `HE_RE` = `\b(higher education|universit(?:y|ies)|colleges?|undergraduate|postgraduate|graduate student|tertiary education|faculty|professor|instructor|lecturer|academia)\b`

Run both against `title + " " + abstract + " " + venue`. Require **≥1 unique hit on each side**. `topic_match_score` = total unique hits across both regexes (float, ~0–20+).

Failing this filter → `exclusion_reason = 'off_topic'`.

### K-12 exclusion

`K12_RE` = `\b(K-12|K12|kindergarten|elementary school|primary school|secondary school|high school|middle school|grade [1-9]|grade 1[0-2])\b`

Rules:
- K12 hits ≥ 1 AND HE hits == 0 → reject with `exclusion_reason = 'k12_only'`.
- Both hit → don't reject, but force `quality_tier = 'review_needed'` regardless of other quality signals.

### AI-as-CS-curriculum

No auto-exclusion rule. Detecting "course about AI" vs "course using AI" via regex has too many false positives. Strong CS-curriculum markers (`AI curriculum`, `teaching machine learning`, `introductory AI course`) bump the paper to `review_needed` rather than rejecting.

### Era tagging

- `era_tag = 'post_chatgpt'` if `year >= 2023`
- `era_tag = 'pre_chatgpt'` if `year <= 2022`

Month-resolution complexity for the Nov–Dec 2022 edge cases is intentionally skipped.

### Quality tiering (only for `included = 1`)

`high_confidence` requires **all** of:
- `is_peer_reviewed = 1` OR `is_in_doaj = 1`
- `work_type` in {`journal-article`, `proceedings-article`, `review`}, OR `work_type = 'book-chapter'` AND `publisher` in `ACADEMIC_PRESS_ALLOWLIST`
- `publisher` not in `PREDATORY_BLOCKLIST`
- No K-12 ambiguity (per rule above)

Otherwise → `review_needed`.

### Predatory venue policy (explicit)

The pipeline does **not** maintain a comprehensive predatory list. There is no free machine-readable source, and alternatives (Beall's, Cabells) are paywalled, dated, or contested. Instead:
- Trust DOAJ membership as a positive signal.
- Use OpenAlex's `is_peer_reviewed` / `type` baseline.
- Ship a tiny `PREDATORY_BLOCKLIST` (~10 entries) of universally-acknowledged repeat offenders.
- Anything dubious lands in `review_needed` for human inspection.

`ACADEMIC_PRESS_ALLOWLIST` (~10 entries): Springer, Routledge, Cambridge UP, Oxford UP, MIT Press, Elsevier, Wiley, Palgrave Macmillan, Taylor & Francis, Sage. Used only to qualify `book-chapter` entries for `high_confidence`.

Both lists live in `config.py` and are documented in the README.

### Out of scope

- No LLM-based topic classification.
- No embedding-based relevance scoring.
- No journal-impact / venue-ranking weighting.

## 9. Output stage

### PDF download (`output/pdf.py`)

Iterates papers where `included = 1 AND pdf_status IS NULL`. For each, tries URLs in order, recording every attempt in `pdf_attempts`:

1. `papers.oa_pdf_url` (Unpaywall preferred, OpenAlex fallback)
2. CORE search by DOI (if 1 fails and DOI present): `GET api.core.ac.uk/v3/search/works/?q=doi:<doi>` → first hit's `download_url`
3. CORE search by title (if 2 fails)

**Validation** — before committing to disk:
- Starts with `%PDF-` magic bytes.
- `Content-Type` should be `application/pdf` (warn-only; some servers lie).
- Size ≥ 10KB.
- Failed validation → discard, log, try next URL.

**On success**: write to `pdfs/<year>/<paper_id>.pdf`; set `pdf_filename` and `pdf_status = 'downloaded'`.

**On all URLs failing**: `pdf_status = 'oa_link_dead'`. `included` stays 1 (the screening decision was correct) but matrix query excludes by `pdf_status`.

**Rate/retries**: shared `http.py`, 2 req/s per host, 3 retries with backoff, 60s timeout. Re-running `rrl export` skips papers with `pdf_status IS NOT NULL`. Force retry: `rrl export --retry-failed`.

### Matrix xlsx (`output/matrix.py`)

Single file `output/rrl_matrix.xlsx`, two sheets, identical schema:

- **Sheet `high_confidence`** — `WHERE quality_tier = 'high_confidence'`
- **Sheet `review_needed`** — `WHERE quality_tier = 'review_needed'`

Both sheets filtered further by the matrix query (Section 4).

Columns:

| # | Column | Notes |
|---|---|---|
| 1 | `paper_id` | |
| 2 | `title` | |
| 3 | `authors` | joined `; `, "Family, Given" |
| 4 | `year` | |
| 5 | `era_tag` | |
| 6 | `venue` | |
| 7 | `publisher` | |
| 8 | `work_type` | |
| 9 | `doi` | hyperlinked to `https://doi.org/<doi>` |
| 10 | `language` | |
| 11 | `is_in_doaj` | Yes / No / N/A |
| 12 | `is_peer_reviewed` | Yes / No |
| 13 | `is_oa` | Yes (always — corpus is OA-only) |
| 14 | `oa_status` | gold / green / bronze / hybrid |
| 15 | `citation_count` | |
| 16 | `topic_match_score` | float |
| 17 | `pdf_filename` | hyperlinked relative path |
| 18 | `source_apis` | comma-separated adapter names |
| 19 | `abstract` | wrapped, last column |

Formatting:
- Header row bold, frozen pane.
- Auto-fit column widths (abstract capped at 60 chars).
- Hyperlinks on DOI and pdf_filename.
- No conditional formatting, formulas, or charts.

### README (`output/readme.py`)

The file has two sections delimited by HTML comments:
```markdown
[hand-written content — what the repo is, methodology, install, run,
 inclusion/exclusion criteria, limitations, OA-only scope honesty,
 S2 API key prominently flagged in setup]

<!-- BEGIN AUTO-GENERATED -->
[regenerated on every `rrl export`]
<!-- END AUTO-GENERATED -->

[optional more hand-written content]
```

`readme.py`:
- Reads the file. Locates both markers.
- **If either marker missing**: refuse to write. Print instructions on adding markers. Exit nonzero. Never touch hand-written content.
- **If markers found**: regenerate the block. Bytes outside the block are unchanged.

Auto-generated content includes: last run timestamp, per-stage counts, era breakdown, quality-tier breakdown, top exclusion reasons, per-adapter contribution, PDF success rate.

### Run manifest (`output/run_manifest.json`)

Written once per `rrl export` invocation:

```json
{
  "schema_version": 1,
  "pipeline_version": "0.1.0",
  "run_id": "uuid",
  "run_at_utc": "2026-05-14T14:33:00Z",
  "query_terms": { "ai_terms": [...], "he_terms": [...], "year_min": 2020, "year_max": 2026 },
  "query_terms_hash": "sha256:...",
  "screen_rule_version": "v1",
  "counts": {
    "raw_records": 0,
    "papers_after_dedup": 0,
    "papers_after_screen_included": 0,
    "papers_in_matrix": 0
  },
  "stage_runtimes_seconds": { "harvest": 0, "dedup": 0, "enrich": 0, "screen": 0, "export": 0 },
  "matrix_file": "rrl_matrix.xlsx",
  "matrix_sha256": "..."
}
```

Purpose: reproducibility. The SHA-256 lets a future reader verify the xlsx hasn't been hand-edited post-pipeline.

### Logs (`logs/*.jsonl`)

One JSON-lines file per stage per date (`logs/harvest-2026-05-14.jsonl`). Console output is human-formatted via `structlog.ConsoleRenderer`; file output is structured JSON.

Events logged:
- `query_sent`, `page_received`, `adapter_error`
- `dedup_merge` (paper_id, raw_ids, key_type)
- `doaj_mismatch`, `unpaywall_skip_no_doi`
- `screen_excluded` (paper_id, reason, hit counts)
- `pdf_attempt` (paper_id, source, url, http_status, outcome, bytes)

### Out of scope

- No PDF parsing, OCR, text extraction.
- No citation-network analysis.
- No xlsx formulas, charts, cross-sheet references.

## 10. CLI, error handling, ops

### Error-handling philosophy

**Per-record recoverable** (transient HTTP, malformed individual records): log, increment counter, continue. HTTP layer retries 3× with backoff; final state lands in an `error_*` column or `pdf_status`.

**Per-stage recoverable** (one adapter down): log, set `search_runs.status='error'` for that adapter, continue others. User can rerun with `--only`.

**Unrecoverable** (DB locked, disk full, missing required env var): log with context, exit nonzero, state remains consistent (WAL mode + 500-row batched commits + UPSERTs). Re-running picks up.

### State consistency

- `PRAGMA journal_mode=WAL` at startup.
- All writes are batched in 500-row transactions with explicit `COMMIT`.
- Every stage uses `ON CONFLICT(...) DO UPDATE` — no insert-then-update two-step.
- `raw_records.fetched_at` and `papers.last_updated_at` let `rrl status` show staleness unambiguously.

### Dependencies (`pyproject.toml`)

```toml
[project]
requires-python = ">=3.11"
dependencies = [
  "click>=8.1",
  "requests>=2.31",
  "urllib3>=2.0",
  "openpyxl>=3.1",
  "structlog>=24.1",
  "rapidfuzz>=3.5",
  "langdetect>=1.0",
  "pyyaml>=6.0",
]
[project.optional-dependencies]
dev = ["pytest>=8", "pytest-cov", "responses>=0.25", "ruff", "mypy"]
```

No async (rates don't justify the complexity). No SQLAlchemy (six tables, raw SQL is clearer). No pandas (openpyxl writes xlsx directly; pandas adds ~80MB for one feature).

### Configuration

`rrl/config.py`:
- `AI_TERMS`, `HE_TERMS`, `K12_TERMS`
- `YEAR_MIN = 2020`, `YEAR_MAX = 2026`
- `PREDATORY_BLOCKLIST` (~10 entries)
- `ACADEMIC_PRESS_ALLOWLIST` (~10 entries)
- Per-adapter rate plans

`.env` (loaded from `.env.example`):
- `OPENALEX_EMAIL` — **required**; used in User-Agent for OpenAlex + as `email` param for Unpaywall.
- `SEMANTIC_SCHOLAR_API_KEY` — *practically required* for reasonable harvest speeds; pipeline runs without it but logs a warning at startup.
- `CORE_API_KEY` — optional; only needed if CORE PDF fallback is invoked.

Missing required env vars → fail fast with clear messages.

### Testing strategy (`pytest`)

**Unit (~80%)**: per-adapter `render_query`, `parse_record`, `paginate`; `normalize_doi`, `normalize_title`, `normalize_author_name`; `dedup_key_cascade`; `canonical_field_resolution`; each screen filter individually; PDF validation (good, HTML page, tiny, bad magic bytes); README marker handling (missing → refuse; present → preserve outside-block).

**Module integration (~15%)**: `harvest` end-to-end with mocked HTTP; `dedup` over 100 raw → 70 papers fixture; `screen` over 200 enriched papers, asserting counts per exclusion_reason and tier.

**End-to-end (~5%)**: full pipeline against canned responses; final xlsx, `run_manifest.json` schema, and `README.md` marker behavior all asserted.

**Fixtures** in `tests/fixtures/`: anonymized real-shape API responses, `sample.pdf` (tiny valid), `not_a_pdf.html`, `seed_db.sql`.

**HTTP mocking**: `responses` library. No live API calls in CI.

**Manual smoke tests** (not in CI): `rrl harvest --only=openalex --since 2026-01-01` for small live slice; `rrl export --limit 5` for real PDF downloads.

### Performance targets (sanity-check, not contract)

| Stage | Wall-clock for ~25k raw / ~15k papers | Bottleneck |
|---|---|---|
| harvest | 45–90 min | API rate limits (S2 dominates without key) |
| dedup | < 1 min | in-memory grouping |
| enrich | 15–30 min | Unpaywall + DOAJ HTTP |
| screen | < 30 s | pure SQL + regex |
| export | 1–3 h | PDF downloads at 2 req/s per host |

Total clean run: ~3–5 hours. Re-running individual stages: minutes (except export).

### What this section explicitly does NOT cover

- CI workflow file (trivial; out of scope to spec).
- Packaging/release process (this is a research tool).
- Telemetry / metrics endpoint (overkill for single-user).
- Live API contract tests (manual only).

## 11. Honest limitations (must appear in README)

1. **OA-only corpus.** The matrix does not represent the full literature on AI in higher ed. Closed-access papers in key journals (Computers & Education, Studies in Higher Education, Internet & Higher Education) are missing.
2. **Topic boundary is regex-based.** The off-topic / K-12 / AI-as-curriculum boundary is heuristic; `review_needed` exists to surface borderline calls for human judgment.
3. **Predatory venue detection is best-effort.** No comprehensive free machine-readable list exists; the pipeline uses DOAJ + a tiny blocklist as proxies.
4. **Dedup has known gaps.** Preprint-vs-journal pairs without shared DOIs may both appear; the `--review` tool surfaces likely duplicates for manual merge but does not auto-merge.
5. **The pipeline does not interpret content.** No NLP extraction of methods, sample, findings; those columns are intentionally absent.
6. **English-only.** Non-English literature is rejected. Significant work in Mandarin, Spanish, Portuguese, and other languages is excluded.

## 12. Open items deferred to implementation

These are details that the spec considers settled but that the implementation plan should make concrete:

- Exact contents of `PREDATORY_BLOCKLIST` and `ACADEMIC_PRESS_ALLOWLIST` (initial values listed above; refinable).
- Per-adapter polite-pool / User-Agent string format conventions.
- ERIC's descriptor-vs-keyword query weighting (will tune during implementation against real responses).
- Exact CORE PDF-fallback URL parsing (CORE v3 schema varies by version).
- README hand-written content (drafted during implementation; this spec only contracts the marker rule).
