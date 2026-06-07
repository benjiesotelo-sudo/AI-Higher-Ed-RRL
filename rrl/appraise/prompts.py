"""MMAT prompt instrument: criterion guidance + render helpers (deterministic, no model)."""
from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).parent / "prompts"

CRITERION_GUIDANCE = {
    "S1": "Are there clear research questions?",
    "S2": "Do the collected data allow the research questions to be addressed?",
    "1.1": "Is the qualitative approach appropriate to answer the research question?",
    "1.2": "Are the qualitative data-collection methods adequate to address the question?",
    "1.3": "Are the findings adequately derived from the data?",
    "1.4": "Is the interpretation of results sufficiently substantiated by data?",
    "1.5": "Is there coherence between qualitative data sources, collection, analysis, interpretation?",
    "2.1": "Is randomization appropriately performed?",
    "2.2": "Are the groups comparable at baseline?",
    "2.3": "Are there complete outcome data?",
    "2.4": "Are outcome assessors blinded to the intervention provided? NOTE: the assessor may be "
           "the participant (patient-reported outcome / PRO), the provider, or a third party — do "
           "NOT auto-fail a PRO study merely because the participant knows the assignment.",
    "2.5": "Did the participants adhere to the assigned intervention?",
    "3.1": "Are the participants representative of the target population?",
    "3.2": "Are measurements appropriate regarding both the outcome and the exposure/intervention?",
    "3.3": "Are there complete outcome data?",
    "3.4": "Are the confounders accounted for in the design and analysis?",
    "3.5": "During the study period, was the intervention/exposure administered as intended?",
    "4.1": "Is the sampling strategy relevant to address the research question?",
    "4.2": "Is the sample representative of the target population?",
    "4.3": "Are the measurements appropriate?",
    "4.4": "Is the risk of nonresponse bias low?",
    "4.5": "Is the statistical analysis appropriate to answer the research question?",
    "5.1": "Is there an adequate rationale for using a mixed-methods design?",
    "5.2": "Are the different components of the study effectively integrated to answer the question?",
    "5.3": "Are the outputs of the integration of components adequately interpreted?",
    "5.4": "Are divergences and inconsistencies between components addressed? NOTE: rate YES if "
           "there is no divergence between the quantitative and qualitative results.",
    "5.5": "(COMPUTED — do not rate) Do the components adhere to their tradition's quality criteria? "
           "Derived deterministically from the component ratings.",
}

BUCKET_GUIDANCE = {
    "qualitative": "qualitative (phenomenology, ethnography, grounded theory, case study, etc.).",
    "rct": "quantitative randomized controlled trial.",
    "quant_nonrandomized": "quantitative non-randomized (cohort, case-control, quasi-experiment).",
    "quant_descriptive": "quantitative descriptive (survey, prevalence, single-group).",
    "mixed_methods": "mixed methods — at least one qualitative AND one quantitative strand, each "
                     "conducted rigorously and INTEGRATED via a mixed-methods design (use the "
                     "integration test, NOT whichever strand happens to be larger).",
    "not_assessable": "not assessable by MMAT — non-empirical (review / theoretical / editorial), "
                      "economic evaluation, or diagnostic-accuracy study.",
}

_FRAMING = {
    1: "Work criterion by criterion: for each, first locate the relevant evidence in the text, "
       "then decide the rating.",
    2: "First summarize the study's design and methods in your own words, then rate each criterion "
       "from that summary.",
}


def load_template(name: str) -> str:
    return (_DIR / name).read_text()


def render_classify(text: str, pass_n: int) -> str:
    buckets = "\n".join(f"   - {b}: {g}" for b, g in BUCKET_GUIDANCE.items())
    return load_template("classify.md").format(
        framing=_FRAMING[pass_n], bucket_guidance=buckets, text=text)


def render_rate(category: str, criteria: list[str], text: str, pass_n: int) -> str:
    block = "\n".join(f"   - {c}: {CRITERION_GUIDANCE[c]}" for c in criteria)
    return load_template("rate.md").format(
        framing=_FRAMING[pass_n], category=category, criteria_block=block, text=text)
