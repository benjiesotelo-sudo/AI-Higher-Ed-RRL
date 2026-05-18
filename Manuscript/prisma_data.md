# PRISMA 2020 Reporting Data

Source: `data/rrl.sqlite` snapshot as of **2026-05-18**. All counts are pulled directly from SQL queries against the canonical database (queries are documented inline below for reproducibility); none rely on log files. The PRISMA 2020 flow diagram (Figure 1 in the manuscript) is intended to be rendered from this file.

---

## §1 — Identification

Total records identified from electronic database searches and supplementary sources, before any deduplication.

| Source | Records | Notes |
|---|---:|---|
| OpenAlex | 6,816 | Primary source. Polite-pool API; 2020–2026 publication window; English; types `journal-article \| book-chapter \| proceedings-article \| review`. |
| ERIC | 16,177 | Education-specific index. Single-token AI × HE query (ERIC's default field cannot run phrase searches). |
| Semantic Scholar | 40,305 | Broad-coverage CS-leaning index. With API key for 5 req/s throughput. |
| Dean-provided | 6 | Six supplementary PDFs hand-curated by the dean and ingested as `adapter='dean_provided'` raw records. |
| **Total** | **63,304** | |

```sql
SELECT adapter, COUNT(*) FROM raw_records GROUP BY adapter;
```

---

## §2 — Deduplication

Records were deduplicated by a three-step cascade (DOI → OpenAlex work ID → normalized title + year + first-author signature) implemented in `rrl/dedup/grouping.py`.

| Metric | Count |
|---|---:|
| Total raw records | 63,304 |
| Unique canonical papers after dedup | **62,291** |
| Papers found by 2+ different databases (cross-database duplicates) | 956 |
| Papers with 2+ raws from the same database (within-database duplicates) | 57 |
| Surplus raw records collapsed into existing groups | 57 |

Net dedup reduction: 63,304 → 62,291 (1,013 records collapsed; 1.6%).

```sql
SELECT COUNT(*) FROM papers;
-- cross-database duplicates
SELECT COUNT(*) FROM (
  SELECT p.paper_id FROM papers p
  JOIN paper_sources ps ON ps.paper_id=p.paper_id
  JOIN raw_records  rr ON rr.raw_id=ps.raw_id
  GROUP BY p.paper_id HAVING COUNT(DISTINCT rr.adapter) > 1
);
```

---

## §3 — Enrichment

After dedup, every paper was passed through three enrichment passes:
- **OpenAlex flag lift** (`rrl/enrich/openalex_flags.py`) — derives `is_oa`, `oa_status`, `oa_pdf_url`, `work_type`, `publisher`, `citation_count`, `is_peer_reviewed` from cached OpenAlex `raw_payload`s. Only fires for papers with an OpenAlex source.
- **DOAJ verification** — `is_in_doaj` looked up by ISSN.
- **Unpaywall lookup** — authoritative best-OA PDF URL by DOI. Overrides OpenAlex if it has one.

| Field set | Papers | Notes |
|---|---:|---|
| Has at least one OpenAlex raw (flag lift eligible) | 6,815 | Of 62,291. The 55,476 without an OpenAlex source are ERIC- or S2-only and carry no work-type / publisher / citation flags. |
| `doaj_checked_at` populated | 62,291 | Every paper checked exactly once; those without an ISSN are recorded as checked-and-skipped so the resumable run does not re-try them. |
| `unpaywall_checked_at` populated | 44,937 | Only papers with a DOI are looked up. The remaining 17,354 have no DOI (mostly ERIC and a sliver of S2). |
| `is_in_doaj = 1` | 403 | Journals indexed in the Directory of Open Access Journals. |
| `is_peer_reviewed = 1` | 6,696 | From OpenAlex work-type + source-type signal, plus dean-curation override on 6 papers. |
| Open access with retrievable PDF URL (`is_oa=1 AND oa_pdf_url IS NOT NULL`) | 21,168 | The pool from which §4's `not_oa` exclusion is the complement. |

```sql
SELECT COUNT(*) FROM papers WHERE doaj_checked_at IS NOT NULL;
SELECT COUNT(*) FROM papers WHERE unpaywall_checked_at IS NOT NULL;
SELECT COUNT(*) FROM papers WHERE is_oa=1 AND oa_pdf_url IS NOT NULL;
```

---

## §4 — Screening (exclusion reasons)

Screening rules in `rrl/screen/rules.py`. Filters apply in order; each excluded paper is tagged with one canonical reason (the first one to fire).

| Exclusion reason | Count |
|---|---:|
| `not_oa` (no retrievable OA PDF URL) | 37,671 |
| `not_peer_reviewed` (work type / source-type signal) | 17,704 |
| `non_english` | 4,834 |
| `off_topic` (failed AI × HE token gate) | 1,024 |
| `non_empirical` (review / editorial / conceptual phrasing) | 507 |
| `k12_only` (K-12 terms present, no HE terms) | 31 |
| `wrong_date` (outside 2020–2026) | 0 |
| **Total excluded** | **61,771** |
| **Total included** | **520** |

```sql
SELECT exclusion_reason, COUNT(*) FROM papers WHERE included=0 GROUP BY exclusion_reason;
```

---

## §5 — Per-database contribution to included papers

For each database, how many included papers were found in it, and how many were found *only* in it.

| Database | Found in (included papers) | Unique to this database |
|---|---:|---:|
| OpenAlex | 516 | 496 |
| ERIC | 0 | 0 |
| Semantic Scholar | 24 | 0 |
| Dean-provided | 4 | 0 |

OpenAlex contributed every included paper that was not dean-supplied. Semantic Scholar overlapped with OpenAlex on 20 papers and with the dean-provided set on 4 papers; it contributed zero unique included papers. ERIC's contribution was zero in this run — its records lack DOIs, so the Unpaywall lookup is skipped and the `not_oa` gate excludes the entire ERIC corpus; the methodological gap and a quantified upper-bound recovery (1,087 candidate papers) are documented in the manuscript Limitations §4.3 and in this repository's `PROGRESS.md`.

```sql
WITH found_by AS (
  SELECT DISTINCT p.paper_id, rr.adapter
  FROM papers p
  JOIN paper_sources ps ON ps.paper_id=p.paper_id
  JOIN raw_records  rr ON rr.raw_id=ps.raw_id
  WHERE p.included=1
)
SELECT adapter,
       COUNT(*) AS found_in,
       SUM(CASE WHEN (SELECT COUNT(DISTINCT adapter) FROM found_by fb2
                       WHERE fb2.paper_id=fb.paper_id) = 1
                THEN 1 ELSE 0 END) AS unique_to
FROM found_by fb
GROUP BY adapter;
```

---

## §6 — Source-combination breakdown (included papers)

How included papers distribute across the possible combinations of contributing databases.

| Combination | Count |
|---|---:|
| openalex only | 496 |
| openalex + s2 | 20 |
| dean_provided + s2 | 4 |
| eric only | 0 |
| s2 only | 0 |
| openalex + eric | 0 |
| eric + s2 | 0 |
| openalex + eric + s2 | 0 |
| dean_provided + openalex | 0 |
| dean_provided + eric | 0 |
| **Total included** | **520** |

The four `dean_provided + s2` papers are the dean-curated PDFs whose existing-paper match came from a Semantic-Scholar-only original harvest (these were the Emerald papers OpenAlex did not return at harvest time, even though OpenAlex *does* have them — the OpenAlex DOI lookup we ran during dean-PDF ingestion confirmed they exist in OpenAlex's index but no `openalex` raw_record was created at that step). Conceptually they are dean+OpenAlex+S2 papers; in the `source_apis` audit they show as `dean_provided,s2` because that reflects what is recorded in `paper_sources`.

```sql
WITH per_paper AS (
  SELECT p.paper_id,
         GROUP_CONCAT(DISTINCT rr.adapter ORDER BY rr.adapter) AS combo
  FROM papers p
  JOIN paper_sources ps ON ps.paper_id=p.paper_id
  JOIN raw_records  rr ON rr.raw_id=ps.raw_id
  WHERE p.included=1
  GROUP BY p.paper_id
)
SELECT combo, COUNT(*) FROM per_paper GROUP BY combo;
```

---

## §7 — Quality-tier breakdown

Quality tiers (`high_confidence`, `review_needed`) are assigned at screen time per `rrl/screen/rules.py:decide_quality_tier`. Both tiers are reportable; the `review_needed` tier surfaces — rather than silently drops — papers requiring human judgment (K-12-HE mixed, AI-as-curriculum signal, non-standard work type, publisher in the predatory blocklist, peer-review and DOAJ signals neither of which fired).

### All included papers (n = 520)

| Tier | Count |
|---|---:|
| high_confidence | 52 |
| review_needed | 468 |

### Matrix rows only (included + PDF downloaded; n = 424)

| Tier | Count |
|---|---:|
| high_confidence | 48 |
| review_needed | 376 |

### By era (included, n = 520)

| Tier | post_chatgpt (2023–2026) | pre_chatgpt (2020–2022) |
|---|---:|---:|
| high_confidence | 41 | 11 |
| review_needed | 418 | 50 |
| **Total** | **459** | **61** |

```sql
SELECT quality_tier, era_tag, COUNT(*)
FROM papers WHERE included=1
GROUP BY quality_tier, era_tag;
```

---

## §8 — Download status

PDF retrieval is the last stage of the pipeline. URLs are tried in priority order (`oa_pdf_url` → CORE-by-DOI → CORE-by-title) with magic-byte (`%PDF-`) and minimum-size (10 KB) validation.

| Outcome (included papers) | Count |
|---|---:|
| PDF successfully downloaded | 424 |
| PDF retrieval failed (`oa_link_dead`) | 96 |
| **Total included** | **520** |
| **Success rate** | **81.5%** |

```sql
SELECT pdf_status, COUNT(*) FROM papers WHERE included=1 GROUP BY pdf_status;
```

---

## Notes and follow-ups

1. **ERIC contribution = 0.** Documented in detail in `docs/superpowers/specs/2026-05-18-source-attribution-diagnosis.md`. Of the 16,177 ERIC raw records, 1,087 pass the topic gate, report `peerreviewed='T'`, and fall in the 2020–2026 window — but every one is excluded as `not_oa` because the pipeline does not currently construct ERIC's own `files.eric.ed.gov` PDF URLs from `external_id`. Closing this gap is a methodological follow-up, not a corpus retraction.
2. **work_type='article' allowlist (fixed 2026-05-18).** OpenAlex's newer type taxonomy uses `article` for what used to be `journal-article`; the quality-tier and peer-review allowlists now include both. Without this fix, four dean-curated papers (and any future OpenAlex-typed `article`) would silently land in `review_needed` instead of `high_confidence`.
3. **dean_provided source attribution.** The four `dean_provided + s2` papers were also confirmed present in OpenAlex during ingestion, but no `openalex` raw_record was created at that step. If complete provenance reporting is wanted, the dean-PDF ingest script can be extended to insert an `openalex` raw_record alongside the `dean_provided` one; this is a labelling refinement that does not change which papers are included.
