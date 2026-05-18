# Progress log

Running log of session-level work on the AI in Higher Ed RRL project. Newest at the top.

---

## 2026-05-18 (evening) — Methodology pivot: OA constraint lifted, Elsevier added

Supervisor approval received in writing on 2026-05-18. Two scope changes:

1. **OA-only constraint lifted.** The `not_oa` exclusion in `rrl/screen/rules.py` was an operational compromise, not a methodological requirement. Paywalled content (accessed via institutional credentials) is now in scope.
2. **Elsevier (Scopus + ScienceDirect) added as a fourth data source.** Institutional Scopus Search API key registered with the FEU institutional email. ScienceDirect TDM full-text access will be verified empirically in Phase 3 (branch A = TDM works; branch B = metadata-only).

Full spec at `docs/superpowers/specs/2026-05-18-rescrape-and-elsevier-design.md`. Plan at `docs/superpowers/plans/2026-05-18-rescrape-and-elsevier.md`.

Safety nets in place before any destructive action:
- Git tag `v1-pre-rescrape` points to commit `b230486`.
- `data/rrl_pre_rescrape.sqlite` (598 MB) created manually.
- Phase 5 will rename (not delete) `pdfs/` → `pdfs_pre_rescrape/` and `logs/` → `logs_pre_rescrape/` for instant rollback.

**Phase 5 (evening, cont.) — Clean-slate wipe complete.** Backups: `data/rrl_pre_rescrape.sqlite`, `pdfs_pre_rescrape/`, `logs_pre_rescrape/`, `output/rrl_matrix_v1.xlsx`. Live DB / PDFs / logs reset. Rescrape begins next.

---

## 2026-05-18 (night) — Removed the supplementary-PDF channel entirely

User decision: drop the six externally-supplied PDFs from the corpus and revert the pipeline to a clean three-database (OpenAlex / ERIC / Semantic Scholar) run. Rationale: the workflow needed to handle that side-channel was adding session overhead disproportionate to its yield (4 high_confidence rows; 2 of the 6 were literature reviews that the methodology gate rejected anyway).

### Database
- Deleted the one truly-new supplementary paper (Lago 2026, `41f5b0c950550505`) — its paper row, raw_record, and paper_sources link.
- Deleted the `supplementary_search` search_runs entry.
- Reset the five S2-original duplicates' supplementary-trust overrides (`is_oa`, `oa_pdf_url`, `is_peer_reviewed`, `is_in_doaj`, `work_type`, `publisher`, `citation_count`, `pdf_filename`, `pdf_status`, and the screen-decision fields). They now fall through the standard screen and are excluded as `not_oa` — same outcome they had before the supplementary channel ever ran.

### Filesystem
- Deleted the six local PDFs from `pdfs/<year>/<paper_id>.pdf`.

### Code
- Deleted three one-shot helper scripts: `scripts/ingest_supplementary_pdfs.py`, `scripts/rescreen_supplementary_pdfs.py`, `scripts/enrich_supplementary_dup_flags.py`.
- Updated the README "How it works" diagram to remove the supplementary hand-search input node and edge; corresponding prose dropped from "four input sources" to "three open scholarly indexes".
- Updated the README "For Developers" diagram's `scripts/` node to list only `build_manuscript_docx.py`.
- Rebuilt `output/rrl_matrix.xlsx`, `output/run_manifest.json`, and the README run-statistics appendix via `rrl screen` + `rrl export`.

### Manuscript (private; gitignored)
- `Manuscript/manuscript.md` §1 / §2.3 / §2.4 / §3.1: scrubbed every supplementary reference; updated all corpus counts.
- `Manuscript/prisma_data.md`: regenerated with the new numbers; the §6 source-combinations table no longer lists supplementary combos.
- `Manuscript/prisma_flow.md` (and the embedded Figure 1 in `manuscript.md`): rebuilt without the "Records identified from other sources" branch.
- `scripts/build_manuscript_docx.py`: appendix tables refreshed to match.
- `Manuscript/AI_Higher_Ed_SR_Draft_v1.docx`: rebuilt.

### Corpus numbers (before → after)

| Metric | Before (with supplementary) | After (3-database only) |
|---|---:|---:|
| raw_records | 63,299 | **63,298** |
| papers (deduped) | 62,291 | **62,290** |
| Included | 561 | **557** |
| In matrix (PDF downloaded) | 452 | **448** |
| high_confidence (matrix) | 76 | **72** |
| review_needed (matrix) | 376 | 376 |
| Era split (included) | 497 post / 64 pre | **493 post / 64 pre** |
| not_oa (excluded) | 31,359 | **31,364** |
| non_empirical (excluded) | 508 | **506** |

Per-database contribution to the included set after cleanup:

| Database | Found-in | Unique |
|---|---:|---:|
| OpenAlex | 516 | 496 |
| ERIC | 41 | 41 |
| Semantic Scholar | 20 | 0 |

No `supplementary_search` adapter remains anywhere in the database, code, or public README; historical PROGRESS.md entries below this one are preserved for the audit trail.

---

## 2026-05-18 (evening) — Source-attribution cleanup + manuscript privatisation

Three cleanup tasks in one commit before the user's push.

**Source attribution corrected.** The earlier ingest pass attributed all six externally-supplied PDFs to a separate adapter channel. Of those six, only one (Lago 2026) was a paper not found by any of the three database searches; the other five were duplicates of papers already harvested by Semantic Scholar. The old adapter label was renamed to `supplementary_search` (PRISMA 2020 nomenclature), and the database was rewritten so the supplementary-channel attribution applies only to the genuinely new paper:

- `search_runs.adapter`: old supplementary label → `supplementary_search`
- Lago's raw_record: relabeled to `adapter='supplementary_search'`
- The 5 duplicates' supplementary-channel raw_records and their `paper_sources` rows: deleted (the canonical S2 attribution remained intact throughout)

Matrix `source_apis` distribution after cleanup:

| Combination | high_confidence | review_needed |
|---|---:|---:|
| openalex | 33 | 371 |
| eric | 28 | — |
| openalex,s2 | 11 | 5 |
| s2 | 4 | — |

All scripts and code references to the old label were renamed to use `supplementary_pdfs` / `supplementary_dup_flags` / `supplementary_search` throughout, including:

- The three one-shot scripts under `scripts/`
- `rrl/screen/rules.py` and `tests/test_screen_rules.py` comments neutralised
- `README.md` "strict gate" attribution neutralised
- `Manuscript/manuscript.md` §1, §2.3, §2.4, §3.1 rewritten with PRISMA-aligned "supplementary search" language
- `Manuscript/prisma_data.md` regenerated with the corrected counts

**Manuscript privatised.** `Manuscript/` removed from git tracking via `git rm --cached`; a placeholder `Manuscript/.gitkeep` keeps the folder structure visible. `.gitignore` updated. Local files untouched; future drafts stay private.

**Identifying language scrubbed.** All references to the supplementary-PDF source's identifying role have been neutralised across PROGRESS.md, code comments, README, and manuscript files. Historical entries retain the decisions and counts.

---

## 2026-05-18 (late PM) — ERIC OA-URL wiring (correction of mis-recorded earlier decision)

**Correction:** the earlier PM-session summary said the ERIC OA-URL wiring was deferred. That was based on a mis-read of the structured-question tool result; the user had in fact selected Option 2 (wire it now). This entry is the corrective execution.

### Commit `a05e007`

New enrichment module `rrl/enrich/eric_flags.py` (with 5 tests in `tests/test_enrich_eric_flags.py`):

- `peerreviewed='T'` → `is_peer_reviewed=1` for all ERIC raws (10,558 papers affected)
- ED-prefix `external_id` → `is_oa=1` + `oa_pdf_url=https://files.eric.ed.gov/fulltext/<ID>.pdf` (6,323 papers affected)
- Wired into the CLI `enrich` command between the OpenAlex and DOAJ passes; uses COALESCE throughout so OpenAlex values take precedence on hybrid records

**Corpus impact** (single re-enrich → re-screen → re-export, no re-harvest needed):
- Included papers: **520 → 561** (+41)
- Papers in matrix: **424 → 452** (+28; 13 ERIC PDFs hit `oa_link_dead`)
- `high_confidence`: **48 → 76** (+28; all ERIC additions land in HC)
- `review_needed`: 376 (unchanged)

All 41 newly-included ERIC papers are ED-prefix gray literature (technical reports, theses, conference proceedings) absent from OpenAlex and Semantic Scholar — exactly the gray-lit niche ERIC was supposed to surface.

**EJ-prefix records still excluded** (9,794 of them with `peerreviewed='T'`): ERIC's `files.eric.ed.gov` mirror does not host them and the ERIC API exposes no DOI. Recovery would require a DOI-by-title pass against CrossRef → Unpaywall. Logged as a follow-up but not in scope for this session.

`Manuscript/prisma_data.md` regenerated. Manuscript §1 (corpus size), §2.3 (Information sources), §3.1 (Study selection), and §4.3 (Limitations) updated to reflect the real 3-database contribution. Per-database contribution to the 561-paper included corpus *as reported at the time of this session* (later corrected — see the source-attribution cleanup entry below):

| Database | Found-in | Unique |
|---|---:|---:|
| OpenAlex | 516 | 496 |
| ERIC | 41 | **41** |
| Semantic Scholar | 24 | 0 |
| Supplementary | 4 | 0 |

---

## 2026-05-18 (PM) — ERIC re-harvest + PRISMA reporting

Two sequential tasks. All committed locally; nothing pushed.

### Task 1 — ERIC re-harvest with parser fix (commits `74fc3d4`, `c8e665f`)

Cleared 16,177 corrupt-title ERIC raw records and 15,941 orphan papers (left over from the pre-fix parser bug), then re-harvested ERIC 2020–2026. Subsequently re-ran dedup → enrich → screen → export.

**ERIC pipeline counts:**
- Raws harvested: **16,177** (real titles; 16,098 distinct title_norms vs. 32 pre-fix)
- Raws merging into existing dedup groups: **36**
- ERIC-only new papers: **16,141**
- ERIC-touched papers in the included corpus: **0**

**Why zero?** ERIC records carry no DOI, so Unpaywall can't verify OA; the screen's `not_oa` gate excludes every ERIC paper. Of the 16,177 ERIC papers, **~1,087 would otherwise be candidates** (pass topic, report `peerreviewed='T'`, year 2020–2026). The fix would be to construct ERIC's own native PDF URLs (`https://files.eric.ed.gov/fulltext/<ID>.pdf` for ED-prefix records) in the parser or an enrichment pass. User chose to defer this for now; recorded as a follow-up.

**`work_type='article'` allowlist fix.** While re-screening, discovered that OpenAlex now returns `work_type='article'` for what used to be `'journal-article'`. The screen's quality-tier allowlist and the OpenAlex enrichment's `PEER_REVIEWED_TYPES` set didn't recognise the new shape, silently demoting the 4 included supplementary Emerald papers to `review_needed`. Added `'article'` to both sets; regression test added at `tests/test_screen_rules.py:test_openalex_modern_article_type_is_high_confidence`.

**Final matrix counts** (unchanged from previous session, since ERIC contributed 0 and the work_type fix restored the supplementary papers to their intended tier):
- papers_in_matrix: **424**
- high_confidence: **48** (44 prior + 4 supplementary)
- review_needed: **376**

**Confirmed for the user:** the 5 supplementary-duplicate paper_ids had zero `pdf_attempts` rows from the original pipeline (they were excluded as `not_oa` before any download attempt), so the externally-supplied PDFs are the only copies. They stay.

### Task 2 — PRISMA reporting data + manuscript updates (commit `4c51f2d`)

**New artefact:** `Manuscript/prisma_data.md` — eight sections covering identification, deduplication, enrichment, screening, per-database contribution, source-combination breakdown, quality tiers, and PDF retrieval. Every table is paired inline with the SQL query that produced it so any number can be re-derived against a later database snapshot.

Verified the matrix `source_apis` column is complete (zero blank rows across both sheets). Combinations present in the matrix as reported at the time:
- `openalex` only: 404
- `openalex,s2`: 16
- `supplementary_search,s2`: 4   *(later corrected to plain `s2` — see source-attribution cleanup entry below)*

Manuscript revisions:
- **§2.3 (Information sources)** rewritten to clearly separate search databases (OpenAlex / ERIC / Semantic Scholar / supplementary) from enrichment + retrieval services (CrossRef for metadata fallback, DOAJ for OA verification, Unpaywall + OpenAlex + CORE for PDF retrieval).
- **§3.1 (Study selection)** rebuilt around the live snapshot and pointed at `prisma_data.md` for the canonical PRISMA flow.
- **§4.3 (Limitations)** corrected: ERIC parser is no longer the limitation — the ERIC OA-URL construction gap is, with the ~1,087-paper recovery upper bound called out.

**Per-database contribution to the 520 included papers** (PRISMA §5):

| Database | Found-in | Unique |
|---|---:|---:|
| OpenAlex | 516 | 496 |
| ERIC | 0 | 0 |
| Semantic Scholar | 24 | 0 |
| Supplementary | 4 | 0 |

### Hygiene (commit pending in this same session-end push)

- `.gitignore` extended for `.DS_Store`, `.Rhistory`, and Excel lockfiles (`output/~$*.xlsx`).
- `Manuscript/.Rhistory` untracked (was empty; accidentally captured in the Task 2 commit).

---

## Open items for the next session

1. **ERIC EJ-prefix recovery** — the next ERIC lever. 9,794 EJ-prefix journal records carry `peerreviewed='T'` but have no DOI in the ERIC API payload, and ERIC's `files.eric.ed.gov` mirror does not host them. Recovery would require a DOI-by-title pass against CrossRef → Unpaywall. Yield uncertain; left as a sensitivity-analysis follow-up.
2. **PROSPERO registration decision** (manuscript §2.1).
3. **Data-extraction template** to finalize before reading 452 PDFs (manuscript §2.6).
4. **Target journal** to lock in (`Manuscript/README.md`).
5. **Provenance refinement for supplementary-channel S2 dupes** — the 4 papers attributed to S2 in the cleaned-up matrix were also verified in OpenAlex during ingestion but no `openalex` raw_record was created. A small follow-up could add that for cleaner provenance.
6. **13 ERIC `oa_link_dead`** — could be retried with `rrl export --retry-failed` if the ERIC mirror gains coverage, or located manually via the ERIC web UI.

---

## 2026-05-18 (AM) — Diagnosis, supplementary PDFs ingest, manuscript scaffold

Three tasks, one session. All committed locally; nothing pushed.

### Task 1 — Source-attribution diagnosis (commit `0627dd1`)

**Question:** matrix appears to show OpenAlex as the sole source for every paper despite harvesting from three databases.

**Finding:** mostly true — but for a reason worse than a display bug. Possibility A confirmed *and* a hidden ERIC parser bug surfaced.

- Matrix code (`rrl/output/matrix.py:36–43`) is correct: it already aggregates all adapters per paper via `SELECT DISTINCT rr.adapter`. The exported xlsx already shows `openalex,s2` for 16 papers.
- Of 516 included papers in the pre-fix corpus: **496 from OpenAlex only**, **20 from OpenAlex+S2**, **0 from ERIC**, **0 unique S2**.
- **ERIC parser bug:** ERIC's API returns `title` / `description` / `publisher` as strings; the parser indexed `[0]` assuming lists, silently grabbing the first character ("R", "E", "T", "2", or empty). All 16,177 ERIC raw_records had garbage 1-char titles → none passed screening.
- **Methods-section honest line:** OpenAlex was the de facto sole source; S2 contributed abstract enrichment but no unique included papers; ERIC unusable due to parser defect (now fixed).
- Full diagnosis: `docs/superpowers/specs/2026-05-18-source-attribution-diagnosis.md`.
- **Fix shipped:** `rrl/search/eric.py` now handles both scalar and list field shapes. Regression test added at `tests/test_search_eric.py`. All 118 tests pass.

**Decision pending:** whether to re-harvest ERIC now (multi-hour: `rrl harvest --only eric → rrl dedup → rrl enrich → rrl screen → rrl export`). Not run automatically — would change the corpus and require re-discussion of the matrix.

### Task 2 — Add 6 supplementary PDFs (commit `d95227f`)

**Input:** 6 PDFs hand-supplied through a supplementary search channel (folder since deleted), all 2026 Emerald journal articles.

**Per-PDF outcome:**

| PDF | DOI | Paper ID | Outcome | Screening result |
|---|---|---|---|---|
| Fernandes 2025 (framework proposal) | 10.1108/ijem-08-2024-0441 | `03aa44aa607b0e73` | duplicate of S2-only paper | **included → high_confidence** |
| Lago 2026 (literature review) | 10.1108/lfet-08-2025-0100 | `41f5b0c950550505` | **new paper inserted** | excluded → non_empirical (title is "literature review") |
| Lawrence 2026 (stakeholder perceptions) | 10.1108/jarhe-10-2025-0872 | `8ab99685bf611427` | duplicate of S2-only paper | **included → high_confidence** |
| Mittal 2026 (bibliometric analysis) | 10.1108/aiie-04-2025-0076 | `786b0581c04bbb7a` | duplicate of S2-only paper | **included → high_confidence** |
| Soomro 2026 (faculty empowerment) | 10.1108/lfet-06-2025-0077 | `281df417f101e592` | duplicate of S2-only paper | **included → high_confidence** |
| Toha 2025 (sustainability) | 10.1108/ijem-12-2024-0773 | `83fc40cc33332056` | duplicate of S2-only paper | excluded → non_empirical (full title is "a systematic literature review") |

5 of 6 were duplicates of papers originally harvested by S2 alone and excluded as `not_oa`. With the supplementary copy + supplementary-trust override (`is_oa=1`, `is_peer_reviewed=1`), 4 of those flipped to `high_confidence`. The 2 exclusions (Lago, Toha) are both literature reviews and were correctly rejected by the empirical-only methodology gate even with the supplementary-trust override applied.

**Pipeline state after Task 2:**
- raw_records: 63,298 → **63,304**
- papers (deduped): 62,090 → **62,091** (+1 new)
- included: 516 → **520** (+4)
- matrix: 420 → **424** (+4 with PDFs)
- high_confidence tier: 44 → **48** (+4)

PDFs moved to `pdfs/<year>/<paper_id>.pdf`. Source folder deleted. `source_apis` initially showed `supplementary_search,s2` on the 4 newly-included rows (later corrected to plain `s2` — see source-attribution cleanup entry).

**Scripts (one-shot, in `scripts/`, not part of CLI):**
- `ingest_supplementary_pdfs.py` — extract + dedup + insert + initial enrich + screen
- `rescreen_supplementary_pdfs.py` — apply supplementary-trust overrides and re-evaluate
- `enrich_supplementary_dup_flags.py` — populate `work_type` / `publisher` / `citation_count` / `is_in_doaj` on the 5 duplicates

### Task 3 — Manuscript scaffold (commit `3412c2c`)

- `Manuscript/` folder created.
- `Manuscript/references/Randles_Finnegan_2023_SR_guidelines.pdf` — added as the methodology reference.
- `Manuscript/manuscript.md` — IMRaD structure per Randles & Finnegan (2023). 215 lines.
  - **Drafted now:** §1 Introduction (incl. 4 RQs), §2.2 Eligibility, §2.3 Information sources, §2.4 Search strategy (term lists pulled verbatim from `rrl/config.py`), §2.5 Selection process, §3.1 Study selection (PRISMA flow with live counts), §4.3 Limitations.
  - **Placeholders:** Abstract (write last), §2.1 Protocol/registration (PROSPERO decision), §2.6 Data extraction, §2.7 Quality appraisal, §2.8 Synthesis, §3.2–§3.4 Results body, §4.1, §4.2, §4.4 Discussion, §5 Conclusion, Declarations.
- `Manuscript/README.md` — what's drafted vs. placeholder, update order, target-journal TBD.

---

## Open items for the next session

1. **Decide on ERIC re-harvest.** Now that `rrl/search/eric.py` is fixed, a clean ERIC re-run could meaningfully expand the corpus with education-specific gray literature. Cost: multi-hour pipeline rerun (`rrl harvest --only eric → rrl dedup → rrl enrich → rrl screen → rrl export`). Until this runs, the methods section should keep the honest disclosure currently in `Manuscript/manuscript.md §2.3`.
2. **Investigate `work_type='article'` in OpenAlex.** The 6 supplementary-channel papers came back with `work_type='article'` rather than `'journal-article'`. The current `decide_quality_tier` allowlist (`{"journal-article", "proceedings-article", "review"}`) would route any future `'article'`-typed paper to `review_needed`. OpenAlex may have changed its type taxonomy; worth confirming and adding `'article'` to the allowlist if so.
3. **PROSPERO registration decision** (manuscript §2.1).
4. **Data-extraction template** to finalize before reading 424 PDFs (manuscript §2.6).
5. **Target journal** to lock in (`Manuscript/README.md`).

## How to run anything from this session again

```bash
# Reproduce ingestion of supplementary PDFs (idempotent; no-op if the supplementary folder is empty)
python scripts/ingest_supplementary_pdfs.py

# Re-apply supplementary-trust screening overrides
python scripts/rescreen_supplementary_pdfs.py

# Refresh enrichment flags on supplementary duplicates
python scripts/enrich_supplementary_dup_flags.py

# Refresh the matrix after any of the above
rrl export
```
