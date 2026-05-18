# Progress log

Running log of session-level work on the AI in Higher Ed RRL project. Newest at the top.

---

## 2026-05-18 — Diagnosis, dean corpus, manuscript scaffold

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

### Task 2 — Add 6 dean-provided PDFs (commit `d95227f`)

**Input:** 6 PDFs in `pdfs/From Dean/` (since deleted), all 2026 Emerald journal articles.

**Per-PDF outcome:**

| PDF | DOI | Paper ID | Outcome | Screening result |
|---|---|---|---|---|
| Fernandes 2025 (framework proposal) | 10.1108/ijem-08-2024-0441 | `03aa44aa607b0e73` | duplicate of S2-only paper | **included → high_confidence** |
| Lago 2026 (literature review) | 10.1108/lfet-08-2025-0100 | `41f5b0c950550505` | **new paper inserted** | excluded → non_empirical (title is "literature review") |
| Lawrence 2026 (stakeholder perceptions) | 10.1108/jarhe-10-2025-0872 | `8ab99685bf611427` | duplicate of S2-only paper | **included → high_confidence** |
| Mittal 2026 (bibliometric analysis) | 10.1108/aiie-04-2025-0076 | `786b0581c04bbb7a` | duplicate of S2-only paper | **included → high_confidence** |
| Soomro 2026 (faculty empowerment) | 10.1108/lfet-06-2025-0077 | `281df417f101e592` | duplicate of S2-only paper | **included → high_confidence** |
| Toha 2025 (sustainability) | 10.1108/ijem-12-2024-0773 | `83fc40cc33332056` | duplicate of S2-only paper | excluded → non_empirical (full title is "a systematic literature review") |

5 of 6 were duplicates of papers originally harvested by S2 alone and excluded as `not_oa`. With the dean copy + dean-trust override (`is_oa=1`, `is_peer_reviewed=1`), 4 of those flipped to `high_confidence`. The 2 exclusions (Lago, Toha) are both literature reviews and were correctly rejected by the empirical-only methodology gate even with dean trust applied.

**Pipeline state after Task 2:**
- raw_records: 63,298 → **63,304**
- papers (deduped): 62,090 → **62,091** (+1 new)
- included: 516 → **520** (+4)
- matrix: 420 → **424** (+4 with PDFs)
- high_confidence tier: 44 → **48** (+4)

PDFs moved to `pdfs/<year>/<paper_id>.pdf`. `pdfs/From Dean/` folder deleted. `source_apis` correctly shows `dean_provided,s2` on the 4 newly-included rows.

**Scripts (one-shot, in `scripts/`, not part of CLI):**
- `ingest_dean_pdfs.py` — extract + dedup + insert + initial enrich + screen
- `rescreen_dean_pdfs.py` — apply dean-trust overrides and re-evaluate
- `enrich_dean_dup_flags.py` — populate `work_type` / `publisher` / `citation_count` / `is_in_doaj` on the 5 duplicates

### Task 3 — Manuscript scaffold (commit `3412c2c`)

- `Manuscript/` folder created.
- `Manuscript/references/Randles_Finnegan_2023_SR_guidelines.pdf` — moved + renamed from `/Users/benjie/Documents/Manuscript/main.pdf`.
- `Manuscript/manuscript.md` — IMRaD structure per Randles & Finnegan (2023). 215 lines.
  - **Drafted now:** §1 Introduction (incl. 4 RQs), §2.2 Eligibility, §2.3 Information sources, §2.4 Search strategy (term lists pulled verbatim from `rrl/config.py`), §2.5 Selection process, §3.1 Study selection (PRISMA flow with live counts), §4.3 Limitations.
  - **Placeholders:** Abstract (write last), §2.1 Protocol/registration (PROSPERO decision), §2.6 Data extraction, §2.7 Quality appraisal, §2.8 Synthesis, §3.2–§3.4 Results body, §4.1, §4.2, §4.4 Discussion, §5 Conclusion, Declarations.
- `Manuscript/README.md` — what's drafted vs. placeholder, update order, target-journal TBD.

---

## Open items for the next session

1. **Decide on ERIC re-harvest.** Now that `rrl/search/eric.py` is fixed, a clean ERIC re-run could meaningfully expand the corpus with education-specific gray literature. Cost: multi-hour pipeline rerun (`rrl harvest --only eric → rrl dedup → rrl enrich → rrl screen → rrl export`). Until this runs, the methods section should keep the honest disclosure currently in `Manuscript/manuscript.md §2.3`.
2. **Investigate `work_type='article'` in OpenAlex.** The 6 dean papers came back with `work_type='article'` rather than `'journal-article'`. The current `decide_quality_tier` allowlist (`{"journal-article", "proceedings-article", "review"}`) would route any future `'article'`-typed paper to `review_needed`. OpenAlex may have changed its type taxonomy; worth confirming and adding `'article'` to the allowlist if so.
3. **PROSPERO registration decision** (manuscript §2.1).
4. **Data-extraction template** to finalize before reading 424 PDFs (manuscript §2.6).
5. **Target journal** to lock in (`Manuscript/README.md`).

## How to run anything from this session again

```bash
# Reproduce ingestion of dean PDFs (idempotent; no-op if the From Dean folder is empty)
python scripts/ingest_dean_pdfs.py

# Re-apply dean-trust screening overrides
python scripts/rescreen_dean_pdfs.py

# Refresh enrichment flags on dean duplicates
python scripts/enrich_dean_dup_flags.py

# Refresh the matrix after any of the above
rrl export
```
