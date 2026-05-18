# Methodology pivot — Clean rescrape with Elsevier/Scopus, OA constraint lifted

**Spec date:** 2026-05-18
**Supervisor approval:** received in writing, 2026-05-18
**Author:** benjie (with Claude as design collaborator)
**Status:** approved by user; awaiting implementation plan

---

## 1. Background

The AI in Higher Ed RRL pipeline currently harvests from three open scholarly indexes (OpenAlex, ERIC, Semantic Scholar), screens for open-access full-text availability, and produces a `pdfs/<year>/<id>.pdf` corpus plus a two-sheet `output/rrl_matrix.xlsx`. The current included corpus is 557 papers / 448 PDFs.

Two supervisor-approved methodology changes drive a clean rescrape:

1. **OA-only constraint lifted.** Paywalled content is in scope. The `not_oa` exclusion (`rrl/screen/rules.py:108-109`) was an operational compromise, not a methodological requirement; the supervisor confirms removing it for the v2 corpus.
2. **Elsevier (Scopus + ScienceDirect) added as a fourth data source.** Author has an institutional Scopus Search API key registered with the FEU email. ScienceDirect TDM full-text access via the same key is the single biggest unknown (see §5.3.1).

The previous matrix appeared to attribute every paper to OpenAlex alone. Diagnosis (`docs/superpowers/specs/2026-05-18-source-attribution-diagnosis.md`) traced this to an ERIC parser bug that has since been fixed — `matrix.py:_source_apis` already aggregates all contributing adapters correctly. The clean rescrape will demonstrate this with all four sources contributing.

## 2. Goals and non-goals

### In scope

- Add `rrl/search/scopus.py` adapter following the `SearchAdapter` Protocol pattern.
- Add ScienceDirect full-text fallback to `rrl/output/pdf.py`, gated on Elsevier DOI prefix and successful TDM probe.
- Remove the `not_oa` screening exclusion; surface `pdf_status` in the matrix instead of filtering on it.
- Wipe the DB, PDFs, logs, and run manifest. Re-run the full pipeline from scratch with all four databases.
- Verify and document multi-source attribution.
- Regenerate the manuscript (v2 alongside v1), PRISMA artifacts, and README.
- Audit and clean accumulated cruft in `scripts/`, `docs/`, `Manuscript/`, `output/`, `logs/`, root.

### Out of scope

- Changes to the `AI_TERMS` / `HE_TERMS` lists. Term-list changes alter the eligibility frame and require their own protocol amendment.
- Re-architecting the dedup, enrichment, or screening modules beyond the targeted edits described here.
- A retry-loop for `pdf_status='not_retrievable'` papers (worklist for a future manual-retrieval pass via interlibrary loan; documented but not automated here).
- PROSPERO registration, data-extraction template, target-journal selection — all carry forward as separate open items.

## 3. High-level phase order

| Phase | Outcome | Est. wall-clock |
|---|---|---:|
| 1. Documentation | PROGRESS.md entry + tag verification | 15 min |
| 2. Project cleanup | Pruned cruft, archived superseded specs | 30 min |
| 3. Elsevier integration | Scopus adapter + ScienceDirect fallback (or branch B fallback-less) + TDD | 4–6 h |
| 4. Screening updates | OA gate removed; matrix shows pdf_status | 1–2 h |
| 5. Clean-slate wipe | DB/PDFs/logs/manifest reset; backups preserved | 15 min |
| 6. Pipeline rescrape | Harvest → dedup → enrich → screen → export | 6–10 h |
| 7. Attribution verification | SQL audit + 5-row spot check | 30 min |
| 8. Artifact regeneration | Manuscript v2, PRISMA, README, PROGRESS | 2–3 h |
| **Total** | | **14–22 h** spread over multiple sessions |

Stop-and-confirm gate at every phase boundary. Commits per phase (descriptive messages). User pushes manually.

---

## 4. Phase 1 — Documentation prerequisites

1. Verify `git tag --verify v1-pre-rescrape` resolves to the current HEAD commit (`b230486`).
2. Append a new entry to the top of `PROGRESS.md`:
   - Date: 2026-05-18
   - Supervisor-approval line (written approval received)
   - Two-change summary (OA lifted, Elsevier added)
   - Pointer to this spec file
3. Commit: `docs(progress): log methodology pivot — OA lifted, Elsevier added`.

## 5. Phase 2 — Project cleanup (before any new code)

User-approved inventory and actions:

### `scripts/`
- `build_manuscript_docx.py` — **keep**. Only remaining script; still active.
- (Supplementary-PDF helpers removed in commit `b230486`; nothing further to prune.)

### `tests/`
- Run `pytest` first. Remove only tests that fail because their target code no longer exists. No blind deletions.

### `docs/superpowers/specs/`
- `2026-05-14-rrl-pipeline-design.md` — **keep** (canonical pipeline spec).
- `2026-05-18-source-attribution-diagnosis.md` — **archive** to `docs/archive/specs/`. The diagnosis is fully resolved in code; preserved as historical record.
- `2026-05-18-rescrape-and-elsevier-design.md` (this file) — **keep** (canonical for the rescrape).

### `docs/superpowers/plans/`
- `2026-05-14-rrl-pipeline.md` — **archive** to `docs/archive/plans/`. Original-build plan, fully executed.

### `Manuscript/`
- `AI_Higher_Ed_SR_Draft_v1.docx` — **keep** (frozen v1 with 3-database results).
- `AI_Higher_Ed_SR_Draft_v1_pre_rescrape.docx` — **keep through Phase 8**; delete after v2 is signed off.
- `AI_Higher_Ed_SR_Draft_v1_pre_scope_change.docx` — **delete** (redundant; identical bytes to `_pre_rescrape`).
- `~$_Higher_Ed_SR_Draft_v1.docx` — **delete** (Word lockfile).
- `.DS_Store`, `.Rhistory` — **delete**.

### `output/`
- `rrl_matrix.xlsx` — **rename** to `rrl_matrix_v1.xlsx` in Phase 5; keep until then.
- `rrl_matrix_pre_rescrape.xlsx` — **delete** (byte-identical to `rrl_matrix.xlsx`).
- `rrl_matrix_pre_scope_change.xlsx` — **delete** (byte-identical).
- `~$rrl_matrix.xlsx` — **delete** (Excel lockfile).
- `run_manifest.json` — touched in Phase 5.

### `logs/`
- `mv logs logs_pre_rescrape` in Phase 5. All 12 files preserved as archive; new `logs/` created empty.

### Root
- `.DS_Store` — **delete**.

### `PROGRESS.md`
- Per user instruction: historical entries kept verbatim. Only the bottom "Open items" section is rewritten, and a new top entry is appended in Phase 1.

### `README.md`
- No changes in Phase 2. Updated in Phase 8 (4-source diagram, scope wording, regenerated stats appendix).

### `.gitignore`
- Already comprehensive. No change needed.

### Commit
`chore: phase-2 project cleanup (archive specs, prune backups)`

---

## 6. Phase 3 — Elsevier integration

### 6.1 Step 1 — TDM probe (blocking)

`scripts/probe_sciencedirect.py` — single-DOI smoke test, no DB writes. Pseudocode:

```python
import os, requests, sys
key = os.environ["ELSEVIER_API_KEY"]
doi = "10.1016/j.caeai.2023.100132"   # known Elsevier OA paper
r = requests.get(
    f"https://api.elsevier.com/content/article/doi/{doi}",
    headers={"X-ELS-APIKey": key, "Accept": "application/pdf"},
    timeout=30,
)
ok = r.status_code == 200 and r.content.startswith(b"%PDF-")
print(f"status={r.status_code} content-type={r.headers.get('Content-Type')} "
      f"bytes={len(r.content)} pdf_magic={'yes' if r.content.startswith(b'%PDF-') else 'no'}")
sys.exit(0 if ok else 1)
```

Report result to user. Branch:

- **Branch A — TDM works (200 + `%PDF-`):** proceed with ScienceDirect fallback (§6.4) and the matching test (§6.6).
- **Branch B — TDM denied (401/403/non-PDF):** drop the ScienceDirect fallback entirely. Scopus stays as a metadata source; included Elsevier papers without OA URLs end up `pdf_status='not_retrievable'`. Skip §6.4 and §6.6. Update §5.3 of the manuscript to acknowledge the limitation.

### 6.2 Step 2 — Scopus adapter

`rrl/search/scopus.py`. Implements the `SearchAdapter` Protocol; structurally mirrors `rrl/search/openalex.py`.

**Query (verbatim — no term-list changes):**

```
( TITLE-ABS-KEY("artificial intelligence" OR "generative AI" OR "generative artificial intelligence"
              OR "GenAI" OR "ChatGPT" OR "GPT-3" OR "GPT-3.5" OR "GPT-4" OR "GPT-4o"
              OR "large language model" OR "LLM" OR "LLMs"
              OR "Bard" OR "Gemini" OR "Claude" OR "Copilot") )
AND
( TITLE-ABS-KEY("higher education" OR "university" OR "universities"
              OR "college" OR "colleges" OR "undergraduate" OR "postgraduate"
              OR "graduate student" OR "tertiary education"
              OR "faculty" OR "professor" OR "instructor" OR "lecturer" OR "academia") )
AND PUBYEAR > 2019 AND PUBYEAR < 2027
AND LANGUAGE(english)
AND ( DOCTYPE(ar) OR DOCTYPE(cp) OR DOCTYPE(re) OR DOCTYPE(ch) )
```

DOCTYPE codes: `ar`=article, `cp`=conference paper, `re`=review, `ch`=book chapter — matches existing OpenAlex `WORK_TYPES`. Reviews stay in (methodology gate rejects them at screen).

**HTTP:**
- Base: `https://api.elsevier.com/content/search/scopus`
- Headers: `X-ELS-APIKey: <key>`, `Accept: application/json`, optional `X-ELS-Insttoken: <token>`
- Params: `query=<above>`, `view=COMPLETE` (for inline abstract — confirm institutional-tier availability; fallback is per-record Abstract Retrieval if `COMPLETE` is denied), `count=25`, `cursor=*` (paginate via `response['search-results']['cursor']['@next']`)
- Rate: throttle to 6 req/s (institutional cap is 9; leaves headroom for enrichment & retries).

**`_parse(entry)`:**
- `external_id` = `entry['dc:identifier']` (e.g., `SCOPUS_ID:85179234567`)
- `doi` = `normalize_doi(entry.get('prism:doi'))`
- `title` = `entry.get('dc:title') or ""`
- `authors` = list of `{family, given, orcid: None}` parsed from `entry.get('author', [])`
- `year` = parse from `entry.get('prism:coverDate')` (YYYY-MM-DD)
- `venue` = `entry.get('prism:publicationName')`
- `abstract` = `entry.get('dc:description')` (present only with `view=COMPLETE`; if missing here we'll need a follow-up Abstract Retrieval call — design that as a fallback path inside `_parse`)
- `language` = `entry.get('language')` (often null; default `None`)
- `raw_payload` = the full entry dict

### 6.3 Step 3 — Plumbing

`rrl/config.py`:
- Add `RATE_PLANS["scopus"] = {"requests_per_second": 6, "per_page": 25}`
- Extend `Settings` with `elsevier_api_key: str | None = None` and `elsevier_insttoken: str | None = None`. Both load from env via `Settings.from_env`. Neither is required to start; missing key disables Scopus harvesting (warn, don't fail).

`rrl/harvest.py`:
- Extend `ADAPTERS` tuple: `("openalex", "eric", "s2", "scopus")`
- Extend `_build_adapter`: `if name == "scopus": return ScopusAdapter(session=rls, api_key=settings.elsevier_api_key, inst_token=settings.elsevier_insttoken)`
- If `settings.elsevier_api_key is None` and `"scopus"` is selected (explicitly or via "all"), log a warning and skip.

`.env.example`:
- Add `ELSEVIER_API_KEY=` placeholder.
- Add commented `# ELSEVIER_INSTTOKEN=` line with a one-sentence comment.

### 6.4 Step 4 — ScienceDirect PDF fallback (branch A only)

Edit `rrl/output/pdf.py`:

1. Refactor `_try_url` to accept an optional `headers` dict (default empty), so per-source auth headers can flow through without polluting the session.
2. In `download_pdfs`, after the CORE-by-title URL append, add:

```python
if doi and elsevier_api_key and doi.startswith("10.1016/"):
    urls.append((
        "sciencedirect",
        f"https://api.elsevier.com/content/article/doi/{doi}",
        {"X-ELS-APIKey": elsevier_api_key, "Accept": "application/pdf"},
    ))
```

3. Update the URL-tuple unpack at the loop site to handle the new `(source, url, headers)` shape (keep backward compat by allowing 2-tuples or normalizing earlier appends to 3-tuples).
4. Magic-byte validation (`validate_pdf_bytes`) unchanged.
5. `pdf_attempts` rows now also get logged for `source='sciencedirect'`.

`rrl/output/runner.py` and the CLI wiring need to pass `elsevier_api_key` into `download_pdfs` from `Settings` (parallel to how `core_api_key` flows today).

The Elsevier-DOI prefix check is conservative: papers with non-`10.1016/` DOIs (T&F, Wiley, Sage, etc.) appear in Scopus too but are not retrievable via ScienceDirect. They flow naturally to `pdf_status='not_retrievable'`.

### 6.5 Step 5 — Scopus citation enrichment (lightweight)

`rrl/enrich/scopus_citations.py`:
- For papers with `doi IS NOT NULL AND citation_count IS NULL`, GET `https://api.elsevier.com/content/abstract/doi/{doi}` (Abstract Retrieval API), extract `citationcount` field, update `papers.citation_count`.
- Skips silently if no `ELSEVIER_API_KEY`.
- Throttled to 6 req/s; tracks a `scopus_checked_at` column (added via `ALTER TABLE papers ADD COLUMN scopus_checked_at TEXT` in `db.py:init_schema`'s migration block, like the existing `unpaywall_checked_at` / `doaj_checked_at` pattern).
- New `rrl enrich --scopus` CLI flag.

### 6.6 Step 6 — Test-driven development

New / modified tests, all using the existing `responses` library mock pattern:

- `tests/test_search_scopus.py` — happy path (one page, multiple pages via cursor), DOI normalization, missing-abstract handling (with and without `view=COMPLETE`), error paths (401, 429, malformed JSON).
- `tests/test_output_pdf.py` — extend with ScienceDirect cases: 200 + PDF → `outcome='ok'`; 403 → `outcome='http_error'`; non-PDF body → `outcome='not_pdf'`. Verify the header is sent.
- `tests/test_enrich_scopus_citations.py` — mock Abstract Retrieval; verify `citation_count` update and `scopus_checked_at` timestamp.
- `tests/test_config.py` — `ELSEVIER_API_KEY` and `ELSEVIER_INSTTOKEN` both optional; absence doesn't raise.
- `tests/test_harvest.py` — adapter-dispatch fixture recognizes `"scopus"`; missing key logs a warning and skips without failing.

Per TDD: red → green → refactor for each. All existing 118 tests must continue to pass.

### 6.7 Commit
`feat(elsevier): add Scopus adapter + ScienceDirect TDM fallback` (or `... + Scopus metadata-only (branch B)`).

---

## 7. Phase 4 — Screening updates

### 7.1 Code change (tiny)

`rrl/screen/rules.py:108-109` — delete:

```python
if not p.get("is_oa") or not p.get("oa_pdf_url"):
    return {"included": 0, "exclusion_reason": "not_oa"}
```

`is_oa` and `oa_pdf_url` continue to populate from Unpaywall + OpenAlex enrichment. They remain visible in the matrix and are useful as a diagnostic signal — they just don't gate inclusion.

### 7.2 Matrix update

`rrl/output/matrix.py`:
- Drop `AND pdf_status = 'downloaded'` from `QUERY`. New filter: `WHERE included = 1 AND paper_id NOT IN (SELECT loser_id FROM paper_merges) AND quality_tier = ?`.
- Add `pdf_status` to `MATRIX_COLUMNS` (between `pdf_filename` and `source_apis`).
- Reviewer filters by `pdf_status` in Excel to focus on the "readable" subset.

### 7.3 PDF status taxonomy

`pdf_status` values after this change:
- `downloaded` — file exists at `pdfs/<year>/<paper_id>.pdf` and validated as PDF.
- `not_retrievable` — included paper; tried every applicable source; none worked. **New value, replaces `oa_link_dead`** as the broader bucket. Old `oa_link_dead` retired; migration trivial (`UPDATE papers SET pdf_status='not_retrievable' WHERE pdf_status='oa_link_dead'`) — but since we're wiping the DB in Phase 5, no migration needed.
- `merged_to_winner` — unchanged.
- `NULL` — never attempted (e.g., excluded paper).

### 7.4 Test updates

- `tests/test_screen_rules.py` — remove all `not_oa` exclusion cases; add cases verifying a paywalled paper with full topic+peer-review+empirical signals returns `included=1`.
- `tests/test_output_matrix.py` — assert `pdf_status` column present; assert papers with `pdf_status='not_retrievable'` appear with empty `pdf_filename`.

### 7.5 Commit
`refactor(screen): lift OA-only exclusion; surface pdf_status in matrix`

---

## 8. Phase 5 — Clean-slate wipe

### 8.1 Pre-flight checks (all must pass)

```bash
git tag --verify v1-pre-rescrape                              # tag exists
git rev-parse v1-pre-rescrape | grep $(git rev-parse HEAD)    # tag = current commit
sha256sum data/rrl.sqlite data/rrl_pre_rescrape.sqlite        # identical bytes
```

Abort and report to user if any check fails.

### 8.2 Wipe (rename-don't-delete for instant rollback)

```bash
mv pdfs pdfs_pre_rescrape
mv logs logs_pre_rescrape
mv output/rrl_matrix.xlsx output/rrl_matrix_v1.xlsx
rm output/run_manifest.json
rm data/rrl.sqlite                # backup at data/rrl_pre_rescrape.sqlite preserved
mkdir pdfs logs
```

`metadata/download_log.csv` doesn't exist in this codebase (download attempts are persisted in the `pdf_attempts` SQLite table). Document this in the commit message so future-me doesn't search for it.

### 8.3 Rollback (if Phase 6 fails)

```bash
mv pdfs pdfs_failed && mv pdfs_pre_rescrape pdfs
mv logs logs_failed && mv logs_pre_rescrape logs
cp data/rrl_pre_rescrape.sqlite data/rrl.sqlite
git checkout v1-pre-rescrape    # if code regressed
```

### 8.4 Commit
`chore: phase-5 clean-slate wipe (backups preserved)`

---

## 9. Phase 6 — Full pipeline rescrape

### 9.1 Commands (sequential)

```bash
rrl harvest                # all 4 adapters; per-adapter try/except already catches failures
rrl dedup
rrl enrich --openalex
rrl enrich --eric
rrl enrich --doaj
rrl enrich --unpaywall
rrl enrich --scopus        # new; no-op without ELSEVIER_API_KEY
rrl screen                 # updated rules
rrl export                 # matrix + PDF downloads (with ScienceDirect if branch A)
```

### 9.2 Checkpoint strategy

- Commit after `rrl harvest` completes: `data: phase-6a — raw harvest from 4 databases (n=<N>)`.
- Commit after `rrl export` completes: `data: phase-6b — full rescrape complete (corpus=<M> / matrix=<K>)`.

If anything explodes mid-pipeline, the SQLite state is recoverable from journal + the harvest CLI's `--only <adapter>` lets us resume per-source without re-harvesting the others.

### 9.3 Operational notes

- Scopus quota: 200–600 requests estimated; comfortably under the 20k/week institutional budget.
- PDF retrieval: ~12k HTTP requests estimated for ~3k included papers × 4 attempts each; ~2–3 hours.
- Storage: 500–1,500 PDFs estimated, 0.7–2 GB.

---

## 10. Phase 7 — Multi-source attribution verification

### 10.1 SQL audit

```sql
WITH paper_adapters AS (
  SELECT ps.paper_id,
         GROUP_CONCAT(DISTINCT rr.adapter) AS source_apis
  FROM raw_records rr
  JOIN paper_sources ps ON ps.raw_id = rr.raw_id
  JOIN papers p ON p.paper_id = ps.paper_id
  WHERE p.included = 1
  GROUP BY ps.paper_id
)
SELECT source_apis, COUNT(*) AS n
FROM paper_adapters
GROUP BY source_apis
ORDER BY n DESC;
```

SQLite's `GROUP_CONCAT(DISTINCT ...)` doesn't order alphabetically; the matrix.py code does Python-side `sorted(...)` for the user-facing column. For the audit pass criteria the unsorted-set form is sufficient (we care about combinations and counts, not display order).

### 10.2 Pass criteria

- No row with `source_apis IS NULL` or empty.
- At least one row showing `scopus` alone (Scopus contributes unique discoveries).
- At least one row showing a multi-source combination including Scopus (e.g., `openalex,scopus` or `openalex,s2,scopus`).
- All four adapters represented in at least one paper's `source_apis`.

### 10.3 Spot check

Pick 5 random `included=1` papers. For each, query their `raw_records` directly and confirm the matrix's `source_apis` string matches. Report results to user.

### 10.4 README addendum

In Phase 8, add a one-paragraph note to README.md explaining the `source_apis` column: comma-separated list of all databases that independently returned the paper; alphabetically sorted; non-empty for every included row.

---

## 11. Phase 8 — Manuscript, README, PROGRESS regeneration

### 11.1 `Manuscript/manuscript.md` (section-targeted edits)

| § | Change |
|---|---|
| 2.2 Eligibility | Drop OA constraint. Add "subscription content accessed via institutional credentials" clause. |
| 2.3 Information sources | Add Scopus as fourth source. Describe its complementary coverage (Elsevier, T&F, Wiley, Sage education journals). Document ScienceDirect TDM as a full-text retrieval channel (or note its unavailability — branch B). |
| 2.4 Search strategy | Append the Scopus query string verbatim. Add one paragraph documenting the methodology pivot (date, supervisor approval, rationale). |
| 2.5 Selection process | Mention `not_retrievable` as a distinct PRISMA bucket from "excluded". |
| 3.1 Study selection | Regenerate all counts from the new DB. |
| 4.3 Limitations | Remove the OA-only limitation. Add: subscription-tier publisher skew (Elsevier overrepresented); ScienceDirect TDM access constraints if branch A, residual non-retrievability if branch B; reviewer was unable to read `not_retrievable` papers without interlibrary loan. |

### 11.2 `Manuscript/prisma_data.md`

Regenerate fully from new DB. Include:
- Per-database raw-record counts.
- Per-database contribution to the included set (found-in + unique).
- Source-combinations table (multi-source attribution from §10).

### 11.3 `Manuscript/prisma_flow.md` + embedded Figure 1

Rebuild the Mermaid PRISMA diagram with four "Records identified" boxes (one per database) feeding into dedup, then through screening to the final included set. Mirror the same diagram inside `manuscript.md` for self-contained rendering.

### 11.4 `Manuscript/AI_Higher_Ed_SR_Draft_v2.docx`

`scripts/build_manuscript_docx.py` minor change: emit `AI_Higher_Ed_SR_Draft_v2.docx` (preserving v1). Either: (a) hardcode v2, (b) take a `--version` arg. Option (b) preferred for repeat use.

### 11.5 `README.md`

- "How it works" Mermaid: 4 source nodes + (branch A only) ScienceDirect fallback edge from the PDF-retrieval node.
- Scope wording: replace "three open scholarly indexes" with "four scholarly indexes (three open + one institutional-subscription)".
- Test count if it changed.
- Auto-generated run-stats appendix regenerated via existing markers in `rrl/output/readme.py`.

### 11.6 `PROGRESS.md`

- New top entry: "2026-05-18 — Methodology pivot: lifted OA-only constraint, added Elsevier/Scopus". Includes corpus deltas (before → after), supervisor approval, links to this spec.
- Rewrite "Open items" section. Drop items resolved by this rescrape (ERIC re-harvest decision, work_type='article' investigation already done). Carry forward: PROSPERO registration decision, data-extraction template, target journal, EJ-prefix ERIC recovery (if still relevant), `not_retrievable` worklist for ILL.

### 11.7 Commit
`docs(manuscript,readme): v2 with 4-database corpus + methodology pivot`

---

## 12. Cross-cutting concerns

### 12.1 Backup inventory

| Asset | Backup mechanism | When created |
|---|---|---|
| Code (pre-rescrape) | Git tag `v1-pre-rescrape` | Already done by user |
| Database | `data/rrl_pre_rescrape.sqlite` (598 MB) | Already done by user |
| PDFs | `pdfs_pre_rescrape/` (rename) | Phase 5 |
| Logs | `logs_pre_rescrape/` (rename) | Phase 5 |
| Matrix v1 | `output/rrl_matrix_v1.xlsx` (rename) | Phase 5 |
| Manuscript v1 | `Manuscript/AI_Higher_Ed_SR_Draft_v1.docx` | Already frozen |

### 12.2 Rollback decision tree

| Failure mode | Action |
|---|---|
| Phase 3 tests fail | Fix in-place; tests gate further work. |
| Phase 6 mid-harvest failure | Use `rrl harvest --only <adapter>` to resume. State is per-adapter in `search_runs`. |
| Phase 6 catastrophic DB corruption | `cp data/rrl_pre_rescrape.sqlite data/rrl.sqlite` and restart Phase 6 from the top. |
| New corpus has methodological problems discovered post-Phase 6 | Restore PDFs/logs from `_pre_rescrape/`, restore DB, `git checkout v1-pre-rescrape`, return to v1 state. |
| ScienceDirect TDM denied (branch B) | Spec already supports this branch; just skip §6.4 and §6.6 ScienceDirect tests; manuscript §4.3 acknowledges. |

### 12.3 Authorization & destructive-action protocol

- Phase 2 deletions: shown in this spec; user has approved.
- Phase 5 wipe: pre-flight checks must pass first; user re-confirms before `rm data/rrl.sqlite`.
- No `git push`. No `git reset --hard`. No `--no-verify`. No `git rebase`.
- One commit per phase boundary. Auto mode within a phase OK; pause at phase boundary.

### 12.4 Open questions / decision log

- **TDM access:** answered by Phase 3 Step 1. Branch A or B determined empirically.
- **`view=COMPLETE` access:** answered at first Scopus query in Phase 6. If denied, fall back to per-record Abstract Retrieval (adds latency but doesn't block).
- **Reviews in DOCTYPE filter:** kept in (`re`), excluded at screen — matches OpenAlex behavior.

---

## 13. Acceptance criteria

The rescrape is considered complete when:

1. All four databases (`openalex`, `eric`, `s2`, `scopus`) are represented in at least one paper's `source_apis` in the v2 matrix.
2. `rrl/screen/rules.py` contains no `not_oa` exclusion path.
3. The v2 matrix (`output/rrl_matrix.xlsx`) contains a visible `pdf_status` column and includes `not_retrievable` rows.
4. `Manuscript/AI_Higher_Ed_SR_Draft_v2.docx` exists alongside v1 with all §2 and §3.1 sections regenerated from the new corpus.
5. `Manuscript/prisma_flow.md` shows four "Records identified" branches.
6. `README.md` shows the 4-source Mermaid diagram and updated scope wording.
7. `PROGRESS.md` has a top entry documenting the pivot, and an updated "Open items" section.
8. All tests in `tests/` pass (existing 118 + new Scopus/ScienceDirect tests).
9. Git log shows one commit per phase boundary; no force pushes; no skipped hooks.
10. Backup assets (`data/rrl_pre_rescrape.sqlite`, `pdfs_pre_rescrape/`, `logs_pre_rescrape/`, `output/rrl_matrix_v1.xlsx`, `Manuscript/AI_Higher_Ed_SR_Draft_v1.docx`) are intact.
