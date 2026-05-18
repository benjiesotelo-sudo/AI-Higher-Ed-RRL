# Manuscript

Working folder for the journal-article draft of the systematic review on AI / GenAI / LLM adoption in higher education, 2020–2026.

## Contents

| Path | What it is |
|---|---|
| `manuscript.md` | The article draft. IMRaD structure (Intro / Methods / Results / Discussion + Abstract, Conclusion, Declarations, References). Sections marked **DRAFT** in the source have content; sections marked **PLACEHOLDER** are intentionally empty and named with what's needed to fill them. |
| `references/` | Methodology references used for writing this review. The systematic-review guidelines we follow are `Randles_Finnegan_2023_SR_guidelines.pdf` (Randles & Finnegan, 2023, *Nurse Education Today*). |

## What's already drafted vs. waiting

| Section | State | Source of content |
|---|---|---|
| §1 Introduction (incl. 1.1 RQs) | **drafted** | Context, scope, RQs framed from the topic and date range |
| §2.1 Protocol and registration | placeholder | needs PROSPERO decision |
| §2.2 Eligibility criteria | **drafted** | mirrors `rrl/screen/rules.py` |
| §2.3 Information sources | **drafted** | mirrors `rrl/search/*.py` and `rrl/enrich/*.py`; honest about ERIC and S2 |
| §2.4 Search strategy | **drafted** | term lists pulled verbatim from `rrl/config.py` |
| §2.5 Selection process | **drafted** | mirrors `rrl/screen/runner.py` and `rrl/dedup/grouping.py` |
| §2.6 Data extraction | placeholder | fill after extraction fields are finalized |
| §2.7 Quality appraisal | placeholder | fill after CASP appraisal is done |
| §2.8 Synthesis approach | placeholder | fill after themes emerge from extraction |
| §3.1 Study selection (PRISMA flow) | **drafted** | numbers pulled from the live SQLite DB at draft time |
| §3.2–3.4 Results | placeholder | fill after extraction and synthesis |
| §4.1, §4.2, §4.4 Discussion | placeholder | fill last |
| §4.3 Limitations | **drafted** | all known limits enumerated |
| §5 Conclusion | placeholder | fill last |
| Abstract | placeholder | write last, as per Randles & Finnegan |

## How to update as the review progresses

Update sections in the rough order they're listed in the section table above. As a rule:

- **Numbers in §3.1 and §2.3 can drift** — they were taken from a snapshot. Before submission, re-run `sqlite3 data/rrl.sqlite "<counts query>"` and refresh.
- **Term lists in §2.4 can drift** if `rrl/config.py` changes — keep them verbatim from the source.
- **Citations** — when you start filling in §3.2 onwards, cite included papers by paper_id from the matrix and replace with full APA at the end. Do not hand-curate the reference list until §3 is locked.
- **Section reorders** — the journal we target may want Limitations before Conclusion or merged with Discussion. Adjust at submission, not before.

## Target journal

*[TBD — candidates to consider include* Computers & Education*,* British Journal of Educational Technology*,* Internet and Higher Education*,* The Internet and Higher Education*,* Studies in Higher Education*,* Higher Education Research & Development*. Word-count target depends on the choice — most are 6,000–8,000 words excluding references.]*

## Methodology reference

We follow Randles, R., & Finnegan, A. (2023). Guidelines for writing a systematic review. *Nurse Education Today*, *125*, 105803. https://doi.org/10.1016/j.nedt.2023.105803. PDF at `references/Randles_Finnegan_2023_SR_guidelines.pdf`. Cite this in §2 (Methods) wherever methodological choices are stated.

## Related artifacts elsewhere in this repo

- `output/rrl_matrix.xlsx` — the corpus (two sheets: `high_confidence`, `review_needed`).
- `output/run_manifest.json` — pipeline version, query hash, per-stage counts, SHA-256 of the xlsx.
- `pdfs/<year>/<paper_id>.pdf` — the actual papers, foldered by publication year.
- `logs/*.jsonl` — every search query, every dedup decision, every screening rejection, every PDF attempt.
- `docs/superpowers/specs/2026-05-14-rrl-pipeline-design.md` — full pipeline design spec.
- `docs/superpowers/specs/2026-05-18-source-attribution-diagnosis.md` — the ERIC-parser-bug and source-attribution diagnosis cited in §2.3 and §4.3.
