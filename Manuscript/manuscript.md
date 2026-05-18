# A Systematic Review of AI Adoption in Higher Education, 2020–2026

## Abstract

*[PLACEHOLDER — write last; target 250 words; structured: Background/Objectives/Methods/Results/Conclusions]*

---

## 1. Introduction

The release of ChatGPT in November 2022 made conversational large language models freely usable by anyone with a web browser, and within months it had become the fastest-growing consumer application on record. Higher education was among the first sectors to feel that shift directly: students used the tool to draft essays, faculty rewrote assignments in response, and institutions issued — and then revised — policy in real time. By the start of 2024, surveys were reporting that a majority of undergraduates had used generative AI for coursework at least once, while institutional positions ranged from outright prohibition to formal integration. The pre-2022 literature on artificial intelligence in higher education had largely concerned itself with adaptive learning systems and intelligent tutoring; the post-2022 literature is a different conversation, conducted at a different pace and in a different vocabulary.

This pace is the problem this review addresses. Empirical work on AI in higher education is now appearing faster than any individual reader can synthesize, scattered across education, computing, library science, ethics, and policy journals, and indexed unevenly across the major academic databases. Existing reviews tend to be either narrow (single tool, single discipline, single institution) or broad-but-impressionistic (narrative summaries of selected exemplars). What is missing is a methodical, transparent, and reproducible sweep of the empirical literature across the entire 2020–2026 window — one that distinguishes the pre-ChatGPT baseline from the post-ChatGPT explosion, one that names what *was* searched and what *was not*, and one whose corpus is open enough that other researchers can re-run it on a later date and see what has changed.

This review takes that approach. We harvested 63,304 candidate records from OpenAlex, ERIC, and Semantic Scholar; deduplicated to 62,091 unique papers; and applied a sequence of automated filters (date, language, open-access availability, topic, peer-review status, empirical methodology) followed by quality-tier triage. The result is a screened, downloadable, open-access-only corpus of 424 papers with full PDFs available for reading and extraction. The pipeline that produced it is published alongside this manuscript and is fully reproducible from a single command. We adopt the methodology described by Randles and Finnegan (2023) for the conduct and reporting of this review.

### 1.1 Research questions

This review is organized around four questions:

- **RQ1.** How has the empirical literature on AI/GenAI/LLM adoption in higher education evolved across the pre-ChatGPT (2020–2022) and post-ChatGPT (2023–2026) eras, in volume and in topical focus?
- **RQ2.** What does the empirical evidence say about adoption patterns and reported outcomes among the three principal stakeholder groups — students, faculty, and institutions?
- **RQ3.** What barriers, enablers, and ethical concerns are most frequently reported across the included studies, and how do they cluster?
- **RQ4.** Where are the methodological and geographic gaps in the current open-access evidence base, and what does that imply for future research and policy?

---

## 2. Methods

The conduct, screening, and reporting of this review follow the guidelines of Randles and Finnegan (2023) for systematic reviews, supplemented by the PRISMA 2020 reporting standard for the flow of records through identification, screening, eligibility, and inclusion.

### 2.1 Protocol and registration

*[PLACEHOLDER — note whether registered on PROSPERO; if not, justify and link the publicly versioned design spec at `docs/superpowers/specs/2026-05-14-rrl-pipeline-design.md`]*

### 2.2 Eligibility criteria

Records were eligible for inclusion if they met every one of the following criteria, applied in the order shown by the screening pipeline:

| Criterion | Operationalization |
|---|---|
| **Date** | Publication year between 2020 and 2026 inclusive. Records were tagged `pre_chatgpt` (2020–2022) or `post_chatgpt` (2023–2026) for stratified analysis. |
| **Language** | English. Language was taken from the source record where available; for records without a language tag we ran `langdetect` on the abstract. |
| **Open access with retrievable PDF** | The paper must have been openly accessible *and* a PDF must have been resolvable through OpenAlex's `best_oa_location`, Unpaywall, or (where configured) CORE. Closed-access papers were excluded by design (see §2.3). |
| **Topic match** | Title + abstract + venue text had to contain at least one AI/GenAI/LLM token (e.g. `artificial intelligence`, `generative AI`, `ChatGPT`, `GPT-4`, `large language model`, `LLM`, `Bard`, `Gemini`, `Claude`, `Copilot`) *and* at least one higher-education token (e.g. `higher education`, `university`, `college`, `undergraduate`, `postgraduate`, `faculty`, `instructor`, `tertiary education`). The full lists are in `rrl/config.py`. |
| **Not K-12-only** | Papers whose only educational context was K-12 (kindergarten through grade 12, elementary/middle/secondary/high school) were excluded. Mixed-context papers (both K-12 and higher-ed terms present) were *retained* but flagged for human review. |
| **Peer reviewed** | The work-type / source-type metadata from OpenAlex had to indicate a peer-reviewed venue (`journal-article`, `book-chapter`, `proceedings-article`, or `review`, sourced from a non-repository host). |
| **Empirical** | Records whose title or abstract explicitly identified the work as a literature review, scoping review, meta-analysis, editorial, commentary, opinion, perspective, position paper, conceptual framework, or theoretical framework were excluded. OpenAlex `work_type` values of `editorial`, `letter`, `erratum`, or `paratext` were also excluded. |

Papers satisfying every gate were further triaged into `high_confidence` and `review_needed` tiers. The `review_needed` tier surfaces — rather than silently drops — papers with K-12/HE mixed scope, an AI-as-curriculum reading, a non-standard work type, a publisher on the predatory blocklist, or peer-review/DOAJ signals neither of which fired. Both tiers are reported.

### 2.3 Information sources

We used six external services across two distinct roles: **search databases** (which generate the candidate-record pool) and **enrichment / retrieval services** (which add metadata flags and locate retrievable PDFs once a candidate has been identified).

**Search databases.** Three open scholarly indexes were queried via their public APIs between 14 and 18 May 2026:

- **OpenAlex** (`api.openalex.org`) — primary search source. Provides DOI, abstract (inverted-index encoded), work type, peer-review-relevant source metadata, citation count, and the canonical `best_oa_location` PDF URL. We used the polite pool by supplying a `mailto` parameter.
- **ERIC** (`api.ies.ed.gov/eric/`) — education-specific index intended to surface gray literature and journal content not in OpenAlex's index. The ERIC harvest was rerun on 2026-05-18 after a parser defect was identified and corrected (`docs/superpowers/specs/2026-05-18-source-attribution-diagnosis.md`). With clean parsing in place, ERIC supplied 16,177 raw records with full titles and abstracts, but none reached the included corpus: ERIC records carry no DOI, so the pipeline's Unpaywall-based OA verification cannot run on them, and the screen's `not_oa` gate therefore excludes every one. ERIC's full-text URLs (`https://files.eric.ed.gov/fulltext/<ID>.pdf` for ED-prefix records) are not yet wired into the pipeline; closing that gap is a methodological follow-up (Limitations §4.3).
- **Semantic Scholar** (`api.semanticscholar.org`) — broad CS-leaning index. Contributed 24 included papers (all also found in OpenAlex or supplied by the dean) and abstract enrichment on multi-source rows. No unique included papers.

**Supplementary papers.** We additionally accept dean-curated PDFs, ingested through a separate path (`scripts/ingest_dean_pdfs.py`) that attaches an `adapter='dean_provided'` raw-record to either an existing dedup group or a new paper. Their bibliographic metadata is verified against OpenAlex by DOI at ingest time.

**Metadata enrichment.** **CrossRef** (`api.crossref.org`) is used by the pipeline for fallback metadata lookups when an OpenAlex DOI lookup is inconclusive (e.g., recently-published papers not yet indexed by OpenAlex). In this run CrossRef was configured but not exercised on the harvest path.

**Open-access verification.** **DOAJ** (`doaj.org/api/v3/search/journals/issn:`) supplies the `is_in_doaj` flag, looked up per ISSN. **Unpaywall** (`api.unpaywall.org/v2/`) supplies the authoritative best-OA PDF URL per DOI, and overrides OpenAlex's `oa_pdf_url` when it returns one (Unpaywall is the canonical reference for OA status).

**PDF retrieval.** Primary retrieval uses the URL set by Unpaywall (with OpenAlex's `best_oa_location` as fallback). When both fail, **CORE** (`api.core.ac.uk`) is queried by DOI and then by title. Every downloaded byte stream is validated against the `%PDF-` magic bytes and a 10 KB minimum-size threshold before being accepted.

We did **not** search Scopus, Web of Science, or EBSCO. Those databases require institutional subscriptions and have no free public API; their omission is a deliberate, declared scope restriction (see §4.3).

### 2.4 Search strategy

OpenAlex and Semantic Scholar were queried with a single AI-term OR-list intersected with a single higher-education OR-list, restricted by publication year and language. ERIC was queried with the same OR-lists but restricted to single-word tokens, because ERIC's Solr backend cannot run phrase searches against its default field. The exact term lists, taken verbatim from `rrl/config.py`:

**AI / GenAI terms (16):**

> artificial intelligence, generative AI, generative artificial intelligence, GenAI, ChatGPT, GPT-3, GPT-3.5, GPT-4, GPT-4o, large language model, LLM, LLMs, Bard, Gemini, Claude, Copilot

**Higher-education terms (15):**

> higher education, university, universities, college, colleges, undergraduate, postgraduate, graduate student, tertiary education, faculty, professor, instructor, lecturer, academia

The OpenAlex filter expression (per `rrl/search/openalex.py`):

```
abstract.search:<AI-OR-list>,
abstract.search:<HE-OR-list>,
from_publication_date:2020-01-01,
to_publication_date:2026-12-31,
language:en,
type:journal-article|book-chapter|proceedings-article|review
```

ERIC and Semantic Scholar use the same conceptual query reduced to each API's syntax. The exact query payload sent to every adapter is hashed and persisted in the `search_runs` table for audit. Every per-record fetch is also logged to `logs/harvest-YYYY-MM-DD.jsonl`.

### 2.5 Selection process

Selection ran in two phases:

**Phase 1 — Automated screening.** The pipeline implements the criteria in §2.2 as an ordered chain of decision functions. Each candidate paper passes through date/language/OA gates, then topic regexes built from the term lists in §2.4, then K-12 disambiguation, then peer-review status, then empirical-methodology detection (a regex over title and abstract for review/editorial phrasing, plus an OpenAlex `work_type` blocklist). Every exclusion is recorded with a single canonical reason (`wrong_date`, `non_english`, `not_oa`, `off_topic`, `k12_only`, `not_peer_reviewed`, `non_empirical`); the counts in §3.1 reflect those reasons. Papers passing all gates are tier-assigned to `high_confidence` or `review_needed`; both tiers are included in the matrix.

**Phase 2 — Manual full-text review.** PDFs of all included papers are downloaded in §2.5 and read by the review team. At this point we record per-paper extraction fields and CASP appraisal scores (§2.6, §2.7). Papers found at full-text to violate inclusion criteria not detectable from title and abstract (e.g. K-12 sample retrospectively dominant; review article masquerading as empirical) are downgraded with a reason recorded.

Deduplication was performed before screening, not after: the pipeline groups raw records into canonical papers via a three-step cascade (`DOI` → `OpenAlex work ID` → `normalized title + year + first-author signature`). Records with no resolvable key become singleton groups so they are never silently merged. A `paper_merges` table is used to record any post-hoc manual merges of preprint/journal pairs that share no DOI.

### 2.6 Data extraction

*[PLACEHOLDER — describe extraction fields once finalized. Anticipated minimum set: stakeholder group (student / faculty / institution / mixed), country, study design (survey / experiment / mixed-methods / case study / other), sample size, AI tool studied, outcomes reported, theoretical framework if any, conflict-of-interest declaration.]*

### 2.7 Quality appraisal

*[PLACEHOLDER — CASP checklist (qualitative / cohort / case-control / cross-sectional as appropriate), plus design-specific items. Fill in once full-text review is complete. Report inter-rater agreement.]*

### 2.8 Synthesis approach

*[PLACEHOLDER — narrative synthesis with thematic coding. Themes to be developed inductively from the extracted data; common candidate themes from the prior literature include barriers, enablers, attitudes, ethical concerns, policy responses, and learning outcomes. Refine once extraction is done.]*

---

## 3. Results

### 3.1 Study selection

The PRISMA 2020 flow diagram (Figure 1) will be rendered from `Manuscript/prisma_data.md`, which holds the canonical per-stage counts queried directly from the project database. The numbers below mirror that artefact at the snapshot date (2026-05-18) and will be regenerated from the same SQL queries at submission time.

**Identification.** 63,304 records were identified across four sources: OpenAlex (6,816), ERIC (16,177), Semantic Scholar (40,305), and dean-curated supplementary PDFs (6).

**Deduplication.** A three-step cascade (DOI → OpenAlex work ID → normalised title + year + first-author signature) collapsed the raw records into 62,291 unique canonical papers. 956 papers were found in two or more databases; an additional 57 within-database duplicate raws were removed.

**Screening.** Of 62,291 deduplicated papers, **520 were included** and 61,771 excluded. Exclusion reasons (each paper carries one canonical reason — the first to fire in the screen's filter chain):

| Reason | Count |
|---|---:|
| Not open-access (no retrievable OA PDF) | 37,671 |
| Not peer-reviewed (work-type / source-type signal) | 17,704 |
| Non-English | 4,834 |
| Off-topic (failed AI × HE token gate) | 1,024 |
| Non-empirical (review / editorial / conceptual) | 507 |
| K-12-only context | 31 |
| Wrong publication date (outside 2020–2026) | 0 |

**Retrieval.** Of the 520 included papers, **424 (81.5%) had retrievable PDFs and appear in the analysis matrix**; 96 had advertised OA URLs that were dead at retrieval time and are flagged `oa_link_dead`. The matrix splits as 48 papers in the `high_confidence` tier and 376 in `review_needed`. Era distribution for the 520 included is 459 post-ChatGPT (2023–2026) and 61 pre-ChatGPT (2020–2022).

**Per-database contribution to the included corpus.** OpenAlex was the sole database in 496 of the 520 included papers and the co-source in another 20 (with Semantic Scholar) and 0 (with ERIC). The four `dean_provided` papers in the included set are co-sourced with Semantic Scholar. ERIC contributed zero included papers in this run for the reasons in §2.3.

A complete per-stage breakdown — identification, deduplication, enrichment, screening, per-database contribution, source-combination matrix, quality tiers, and PDF retrieval — is in `Manuscript/prisma_data.md`. Each table in that file is paired with the SQL query that produced it so the numbers can be re-derived against any later database snapshot.

### 3.2 Study characteristics

*[PLACEHOLDER — Table 1 summarizing included studies by country, study design, sample, AI tool studied, stakeholder group. Generated once data extraction (§2.6) is complete.]*

### 3.3 Quality appraisal results

*[PLACEHOLDER — Table 2: CASP score distribution by tier; Figure 2: risk-of-bias visualization. Filled in once §2.7 is complete.]*

### 3.4 Synthesis of findings

*[PLACEHOLDER — organized by themes that emerge from the data. Tentative themes from the prior literature, to be confirmed or revised against extraction: (a) student adoption and academic integrity; (b) faculty practice and assessment redesign; (c) institutional policy and governance; (d) reported learning outcomes; (e) ethical and equity concerns; (f) workforce / labor displacement framing; (g) AI literacy programs. Refine after extraction.]*

---

## 4. Discussion

### 4.1 Summary of evidence

*[PLACEHOLDER]*

### 4.2 Implications for practice and policy

*[PLACEHOLDER]*

### 4.3 Limitations

Several limitations follow from the design of this review and should be read alongside any of its conclusions.

**Open-access only.** By design the corpus contains only papers with a retrievable open-access PDF. Significant closed-access literature in flagship venues — Computers & Education, Studies in Higher Education, Internet and Higher Education, the British Journal of Educational Technology, and others — is therefore *absent* from the analysis. The corpus reported here should be understood as the open-access *slice* of the empirical literature, not the literature in full. A definitive review of the field would supplement this slice with hand-search of those paywalled venues.

**No Scopus, Web of Science, or EBSCO.** These three databases are the conventional backbone of education-systematic-review search strategies and have no free public API; we did not search them. Their omission contributes to the same gap as the OA-only limitation above.

**English only.** A non-trivial volume of empirical work on AI in higher education appears in Mandarin, Spanish, Portuguese, and other languages. Restricting to English misses that work.

**Date range fixed at 2020–2026.** Earlier work on adaptive learning, intelligent tutoring, and conventional educational data mining is excluded by design. This bounds the review's claims to the contemporary GenAI era rather than the history of AI in education.

**Topic boundary is regex-based.** Inclusion and exclusion at the topic level were enforced by keyword regex over title, abstract, and venue. The pipeline's `review_needed` tier exists explicitly to surface borderline cases for human judgment rather than dropping them, but a regex over the term lists in §2.4 will miss papers framed in different vocabulary (e.g. work calling LLMs "foundation models" without naming a specific tool).

**Peer-review signal is uneven.** OpenAlex carries explicit peer-review-relevant metadata and is the basis for the included corpus. Semantic Scholar's API does not expose an equivalent signal; S2-only papers were therefore excluded by the strict peer-review gate even where they may in fact be peer-reviewed. ERIC's `peerreviewed` field is captured in our raw payloads (`T`/`F`) but is not yet read by the pipeline's enrichment step; closing that loop is a follow-up.

**ERIC's contribution is currently zero and is recoverable.** After the ERIC parser was corrected and the harvest was rerun, all 16,177 ERIC records carry full titles, abstracts, and a self-declared peer-review flag — but every record is still excluded by the screen's `not_oa` gate because the pipeline does not currently construct ERIC's own `https://files.eric.ed.gov/fulltext/<ID>.pdf` URLs from `external_id`, and ERIC records carry no DOI for Unpaywall to look up. An audit of the ERIC corpus indicates approximately 1,087 candidate papers would pass the topic and peer-review gates if this OA-URL construction were wired in. Until that step is taken, the included corpus reported here under-represents education-specific gray literature relative to what the search strategy nominally covers. We treat this as a sensitivity-analysis follow-up rather than a retraction; the methodological consequence is a downward bias on grey-literature visibility that we acknowledge explicitly.

**Predatory-venue detection is best-effort.** No comprehensive free machine-readable predatory-venue list exists. We combined DOAJ membership and a short blocklist of widely-acknowledged repeat offenders. Borderline venues land in `review_needed` rather than `high_confidence`, but no automated check can be definitive.

**Deduplication has known gaps.** Preprint/journal pairs published without shared DOIs may both appear in the corpus; the pipeline produces a manual-merge candidate list (`rrl dedup --review`) that reviewers consulted but cannot guarantee is exhaustive.

**No content extraction was automated.** Methods, sample, findings, theoretical framework, and CASP scores are extracted manually during full-text review (§2.6–§2.7). The matrix as published contains only bibliographic and quality-flag columns.

### 4.4 Future research directions

*[PLACEHOLDER]*

---

## 5. Conclusion

*[PLACEHOLDER]*

---

## Declarations

### Funding

*[PLACEHOLDER]*

### Conflicts of interest

*[PLACEHOLDER]*

### Author contributions

*[PLACEHOLDER]*

### Data and code availability

The screening pipeline, including search adapters, deduplication, enrichment, screening rules, and export, is published in the repository accompanying this manuscript. The full screened corpus (`output/rrl_matrix.xlsx`, two sheets — `high_confidence` and `review_needed`) is included alongside the pipeline, as are the per-stage logs (`logs/*.jsonl`). The underlying SQLite database (`data/rrl.sqlite`) is reproducible from a single `rrl all` invocation against the public APIs of OpenAlex, ERIC, Semantic Scholar, DOAJ, and Unpaywall.

---

## References

*[PLACEHOLDER — generate from included papers once finalized. Below are the methodological references already cited in this draft.]*

Randles, R., & Finnegan, A. (2023). Guidelines for writing a systematic review. *Nurse Education Today*, *125*, 105803. https://doi.org/10.1016/j.nedt.2023.105803
