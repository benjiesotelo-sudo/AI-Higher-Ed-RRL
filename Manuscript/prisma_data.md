# PRISMA 2020 Reporting Data

Source: `data/rrl.sqlite` snapshot as of **2026-05-18 (post-ERIC OA wiring)**. All counts are pulled directly from SQL queries against the canonical database (queries are documented inline below for reproducibility); none rely on log files. The PRISMA 2020 flow diagram (Figure 1 in the manuscript) is intended to be rendered from this file.

---

## §1 — Identification

Total records identified from electronic database searches and supplementary sources, before any deduplication.

| Source | Records | Notes |
|---|---:|---|
| OpenAlex | 6,816 | Primary source. Polite-pool API; 2020–2026 publication window; English; types `journal-article \| book-chapter \| proceedings-article \| review`. |
| ERIC | 16,177 | Education-specific index. Re-harvested 2026-05-18 with the corrected scalar/list parser. ERIC `peerreviewed='T'` and ED-prefix native PDF URL (`https://files.eric.ed.gov/fulltext/<ID>.pdf`) are mapped to `is_peer_reviewed=1` and `is_oa=1 + oa_pdf_url` via the `enrich_from_eric_payloads` pass. |
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

After dedup, every paper was passed through four enrichment passes:
- **OpenAlex flag lift** (`rrl/enrich/openalex_flags.py`) — derives `is_oa`, `oa_status`, `oa_pdf_url`, `work_type`, `publisher`, `citation_count`, `is_peer_reviewed` from cached OpenAlex `raw_payload`s. Only fires for papers with an OpenAlex source.
- **ERIC flag lift** (`rrl/enrich/eric_flags.py`) — for ERIC-sourced papers, maps `peerreviewed='T'` → `is_peer_reviewed=1`, and for ED-prefix records sets `is_oa=1` and `oa_pdf_url=https://files.eric.ed.gov/fulltext/<ID>.pdf`. Uses COALESCE so OpenAlex values (run first) take precedence on hybrid records.
- **DOAJ verification** — `is_in_doaj` looked up by ISSN.
- **Unpaywall lookup** — authoritative best-OA PDF URL by DOI. Overrides OpenAlex (but not ERIC's ED URL) if it has one.

| Field set | Papers | Notes |
|---|---:|---|
| Has at least one OpenAlex raw (flag lift eligible) | 6,815 | Of 62,291. |
| Has at least one ERIC raw (flag lift eligible) | 16,141 | The ERIC-only and ERIC-overlap papers. |
| `doaj_checked_at` populated | 62,291 | Every paper checked exactly once. |
| `unpaywall_checked_at` populated | 44,937 | Only papers with a DOI; ERIC records have none. |
| `is_in_doaj = 1` | 403 | Journals indexed in the Directory of Open Access Journals. |
| `is_peer_reviewed = 1` | 17,224 | OpenAlex work-type signal + ERIC `peerreviewed='T'` + dean-curation override on 6 papers. |
| Open access with retrievable PDF URL (`is_oa=1 AND oa_pdf_url IS NOT NULL`) | 27,480 | The pool from which §4's `not_oa` exclusion is the complement. Includes 6,323 ED-prefix ERIC papers newly attached to `files.eric.ed.gov` URLs. |

```sql
SELECT COUNT(*) FROM papers WHERE doaj_checked_at IS NOT NULL;
SELECT COUNT(*) FROM papers WHERE unpaywall_checked_at IS NOT NULL;
SELECT COUNT(*) FROM papers WHERE is_oa=1 AND oa_pdf_url IS NOT NULL;
SELECT COUNT(*) FROM papers WHERE is_peer_reviewed=1;
```

---

## §4 — Screening (exclusion reasons)

Screening rules in `rrl/screen/rules.py`. Filters apply in order; each excluded paper is tagged with one canonical reason (the first one to fire).

| Exclusion reason | Count |
|---|---:|
| `not_oa` (no retrievable OA PDF URL) | 31,359 |
| `not_peer_reviewed` (work type / source-type signal / `peerreviewed=F`) | 17,779 |
| `non_english` | 4,834 |
| `off_topic` (failed AI × HE token gate) | 7,215 |
| `non_empirical` (review / editorial / conceptual phrasing) | 508 |
| `k12_only` (K-12 terms present, no HE terms) | 35 |
| `wrong_date` (outside 2020–2026) | 0 |
| **Total excluded** | **61,730** |
| **Total included** | **561** |

The `off_topic` count rose from 1,024 to 7,215 with this run because ED-prefix ERIC records (mostly gray-lit reports on K-12 or general adult-education topics) now clear the `not_oa` gate and are evaluated against the AI × HE topic regex; most are off-topic for this review and fall here. This is the intended behaviour — they are being correctly *categorised as off-topic* rather than incorrectly *excluded as inaccessible*.

```sql
SELECT exclusion_reason, COUNT(*) FROM papers WHERE included=0 GROUP BY exclusion_reason;
```

---

## §5 — Per-database contribution to included papers

For each database, how many included papers were found in it, and how many were found *only* in it.

| Database | Found in (included papers) | Unique to this database |
|---|---:|---:|
| OpenAlex | 516 | 496 |
| ERIC | 41 | 41 |
| Semantic Scholar | 24 | 0 |
| Dean-provided | 4 | 0 |

Every ERIC-included paper in this run is also ERIC-unique: the 41 ERIC papers are ED-prefix gray literature (technical reports, conference proceedings, theses) that OpenAlex and Semantic Scholar do not index. OpenAlex remains the single largest contributor (96% of included papers excluding ERIC's 41). Semantic Scholar continues to overlap entirely with other sources (20 with OpenAlex; 4 with dean-provided).

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
| eric only | 41 |
| openalex + s2 | 20 |
| dean_provided + s2 | 4 |
| s2 only | 0 |
| openalex + eric | 0 |
| eric + s2 | 0 |
| openalex + eric + s2 | 0 |
| dean_provided + openalex | 0 |
| dean_provided + eric | 0 |
| **Total included** | **561** |

The four `dean_provided + s2` papers are the dean-curated Emerald PDFs whose existing-paper match came from a Semantic-Scholar-only original harvest; they were also verified against OpenAlex at ingest time but no `openalex` raw_record was created at that step (see notes §3 in this file). The 41 ERIC-only included papers are exclusively ED-prefix gray literature; EJ-prefix journal records do not pass the `not_oa` gate under the current ED-only OA-URL mapping.

```sql
WITH per_paper AS (
  SELECT p.paper_id,
         (SELECT GROUP_CONCAT(a, ',') FROM (
            SELECT DISTINCT rr.adapter AS a
            FROM paper_sources ps2 JOIN raw_records rr ON rr.raw_id=ps2.raw_id
            WHERE ps2.paper_id=p.paper_id ORDER BY rr.adapter
         )) AS combo
  FROM papers p WHERE p.included=1
)
SELECT combo, COUNT(*) FROM per_paper GROUP BY combo;
```

---

## §7 — Quality-tier breakdown

Quality tiers (`high_confidence`, `review_needed`) are assigned at screen time per `rrl/screen/rules.py:decide_quality_tier`. Both tiers are reportable; the `review_needed` tier surfaces — rather than silently drops — papers requiring human judgment.

### All included papers (n = 561)

| Tier | Count |
|---|---:|
| high_confidence | 93 |
| review_needed | 468 |

### Matrix rows only (included + PDF downloaded; n = 452)

| Tier | Count |
|---|---:|
| high_confidence | 76 |
| review_needed | 376 |

### By era (included, n = 561)

| Tier | post_chatgpt (2023–2026) | pre_chatgpt (2020–2022) |
|---|---:|---:|
| high_confidence | 79 | 14 |
| review_needed | 418 | 50 |
| **Total** | **497** | **64** |

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
| PDF successfully downloaded | 452 |
| PDF retrieval failed (`oa_link_dead`) | 109 |
| **Total included** | **561** |
| **Success rate** | **80.6%** |

Of the 41 newly-included ERIC papers, 28 downloaded successfully and 13 hit `oa_link_dead` (ERIC's `files.eric.ed.gov` mirror does not host every ED-prefix record). The 13 dead links are flagged for human review or alternative retrieval.

```sql
SELECT pdf_status, COUNT(*) FROM papers WHERE included=1 GROUP BY pdf_status;
```

---

## Notes and follow-ups

1. **ERIC EJ-prefix records remain `not_oa`.** ERIC's `files.eric.ed.gov` mirror does not host journal-article (`EJ`) records, and the ERIC API does not expose DOIs in its payloads. A future pass could attempt to recover DOIs for EJ papers via title + author + ISSN search against CrossRef, then run them through Unpaywall — but the recovery rate is uncertain and the work was out of scope for this run. The 9,794 EJ papers with `peerreviewed='T'` are the principal addressable population.
2. **13 ERIC ED `oa_link_dead`.** These could be retried with `rrl export --retry-failed` if the ERIC mirror gains coverage of those records, or manually located via the ERIC web UI.
3. **dean_provided source attribution.** The four `dean_provided + s2` papers were also confirmed present in OpenAlex during ingestion, but no `openalex` raw_record was created at that step. If complete provenance reporting is wanted, the dean-PDF ingest script can be extended to insert an `openalex` raw_record alongside the `dean_provided` one; this is a labelling refinement that does not change which papers are included.
