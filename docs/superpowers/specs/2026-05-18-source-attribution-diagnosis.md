# Source Attribution Diagnosis (2026-05-18)

## Question

`output/rrl_matrix.xlsx` appears to show OpenAlex as the source for every paper, even though the pipeline harvested from three databases (OpenAlex, ERIC, Semantic Scholar). Two hypotheses:

- **Possibility A:** Other adapters didn't contribute unique included papers.
- **Possibility B:** Dedup collapsed multi-source rows; matrix shows only canonical priority source.

## Verdict

**Possibility A is correct.** The matrix code (`rrl/output/matrix.py:36`) already aggregates all adapters per paper via `SELECT DISTINCT rr.adapter`. The exported xlsx already contains `openalex,s2` for the multi-source papers. The original observation was incomplete — 16 of 420 rows in `rrl_matrix.xlsx` do show both sources.

But the deeper finding is that **ERIC is silently broken** at the parser layer and contributed zero records to the included corpus.

## Evidence

### Source-combination breakdown for included papers (n=516)

| found_in | papers |
|---|---|
| openalex | 496 |
| openalex,s2 | 20 |
| eric | 0 |
| s2 (only) | 0 |
| all three | 0 |

### Source-combination breakdown for matrix rows (included + downloaded, n=420)

| found_in | papers |
|---|---|
| openalex | 404 |
| openalex,s2 | 16 |

Existing xlsx confirms this exact split — the matrix is correctly reporting both sources.

### Adapter contributions

| adapter | total_raws | raws_with_doi | distinct_title_norm | raws_in_included_papers |
|---|---|---|---|---|
| eric | 16,177 | 0 | **32** | 0 |
| openalex | 6,816 | 6,783 | 6,630 | 516 |
| s2 | 40,305 | 39,104 | 39,882 | 20 |

The `32` distinct ERIC title-norms across 16,177 records is the smoking gun.

### ERIC parser bug

Sample of ERIC `raw_records` rows:

```
raw_id  title  title_norm  first_author
45620   2      2           (empty)
49521   R      r           heimer
48156   E      e           marshall
48157   A      (empty)     quinn
48093   T      t           sun
```

Titles are single characters. Verified against `raw_payload`:

```python
title field type: str
title value: '2019-2020 Florida Adult Education Assessment Technical Assistance Paper'
description type: str
publisher type: str
language type: list
author type: list
```

ERIC's API returns `title`, `description`, `publisher` as **strings**, but the parser at `rrl/search/eric.py:57-70` assumes lists and indexes `[0]`:

```python
title_list = d.get("title") or [""]
return RawRecord(
    title=title_list[0] if title_list else "",          # str[0] = first character
    abstract=desc_list[0] if desc_list else None,        # same problem
    venue=(d.get("publisher") or [None])[0],             # same problem
    language="en" if (d.get("language") or ["English"])[0].lower()...  # OK: language IS a list
    ...
)
```

The `or [""]` fallback only fires when the field is empty — when ERIC returns a real string, `str[0]` silently yields the first character. `author` and `language` happen to come back as lists from ERIC, so those parse correctly.

### Effect on dedup

Every ERIC record has either a 1-character title (or empty) and no DOI:
- DOI cascade misses (no DOIs).
- OpenAlex-ID cascade misses (ERIC payload has no OpenAlex ID).
- Signature key (`title_norm|year|first_author`) is built from a 1-char title → essentially every ERIC row becomes its own singleton group, or collides bogusly with other ERIC rows that happen to start with the same letter.

Result: 15,941 papers got created from ERIC raws, all with garbage titles, none of which pass the topic regex during screening. ERIC's intended role (education-specific gray literature OpenAlex misses) is completely absent from the corpus.

### Field contributions for the 20 multi-source openalex+s2 papers

Titles agree in length across the two adapters in every case (same paper, identical title). Abstracts vary: S2 supplies an abstract that OpenAlex lacks in roughly half the cases, and vice versa. So S2's real contribution to the corpus is **abstract enrichment** for shared papers, not unique-paper coverage.

## What this means for the methods section

The pipeline harvested from three databases but the **effective** corpus came from one:

- **OpenAlex:** 516/516 included papers (100%).
- **S2:** found 20 of those same papers (~3.9%); contributed abstract enrichment but no unique included papers.
- **ERIC:** broken parser → 0 papers in the included corpus.

A methods section written today should report this honestly: "Harvest configured for OpenAlex, ERIC, and Semantic Scholar; in this run, ERIC records were unusable due to a parser defect (since corrected) and Semantic Scholar contributed no unique included papers after deduplication; OpenAlex was the de facto sole source."

## Recommended next steps

1. **Do not "fix" matrix.py** — it is working correctly.
2. **Fix `rrl/search/eric.py`** — handle both string and list field types from ERIC. Three lines (title, abstract, publisher).
3. **Re-harvest ERIC** after the fix (`rrl harvest --only eric`), then `rrl dedup`, `rrl enrich`, `rrl screen`, `rrl export`. ERIC's gray-lit niche may meaningfully expand the corpus.
4. **Decide before Task 2:** does the user want the ERIC re-harvest run now (multi-hour), or proceed with Task 2 against the OpenAlex-only corpus and re-harvest ERIC later?
