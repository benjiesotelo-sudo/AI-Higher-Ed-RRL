You are appraising a {category} study with the Mixed Methods Appraisal Tool (MMAT, v2018).

{framing}

Rate EACH of the criteria below as yes | no | cant_tell. "cant_tell" means the information is
not reported or is unclear — do not penalize a study for something that is genuinely not
applicable, and do not assume a failing when the text simply does not say.

Criteria to rate:
{criteria_block}

For each criterion give a one-sentence rationale and a source_quote copied VERBATIM from the text.

Output one JSON object PER LINE (JSON Lines), one per criterion, and nothing else:
{{"criterion_id": "...", "rating": "yes|no|cant_tell", "rationale": "one sentence", "source_quote": "a span copied verbatim from the text", "confidence": 0.0}}

--- PAPER TEXT ---
{text}
