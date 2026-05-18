"""Configuration: term lists, blocklists, rate plans, env-loaded settings."""
from __future__ import annotations
import os
from dataclasses import dataclass

AI_TERMS = [
    "artificial intelligence",
    "generative AI", "generative artificial intelligence", "GenAI",
    "ChatGPT", "GPT-3", "GPT-3.5", "GPT-4", "GPT-4o",
    "large language model", "LLM", "LLMs",
    "Bard", "Gemini", "Claude", "Copilot",
]

HE_TERMS = [
    "higher education", "university", "universities",
    "college", "colleges", "undergraduate", "postgraduate",
    "graduate student", "tertiary education",
    "faculty", "professor", "instructor", "lecturer", "academia",
]

K12_TERMS = [
    "K-12", "K12", "kindergarten",
    "elementary school", "primary school",
    "secondary school", "high school", "middle school",
]

YEAR_MIN = 2020
YEAR_MAX = 2026

PREDATORY_BLOCKLIST = {
    "OMICS International", "OMICS Publishing Group", "Bentham Open",
    "Bentham Science Publishers", "SCIRP", "Scientific Research Publishing",
    "Hindawi Limited", "Academic Journals", "International Journal of Advanced Research",
    "IISTE", "International Institute for Science, Technology and Education",
}

ACADEMIC_PRESS_ALLOWLIST = {
    "Springer", "Springer Nature", "Routledge", "Cambridge University Press",
    "Oxford University Press", "MIT Press", "Elsevier", "Wiley",
    "Palgrave Macmillan", "Taylor & Francis", "Sage", "SAGE Publications",
}

RATE_PLANS: dict[str, dict] = {
    "openalex":   {"requests_per_second": 10, "per_page": 200},
    "eric":       {"requests_per_second": 1,  "per_page": 2000},
    "s2":         {"requests_per_second": 1,  "per_page": 100, "with_key_rps": 5},
    "scopus":     {"requests_per_second": 6,  "per_page": 25},
    "crossref":   {"requests_per_second": 50, "per_page": 100},
    "core":       {"requests_per_second": 0.17, "per_page": 100},  # 10/min
    "doaj":       {"requests_per_second": 2,  "per_page": 1},
    "unpaywall":  {"requests_per_second": 10, "per_page": 1},
}

@dataclass(frozen=True)
class Settings:
    openalex_email: str
    s2_api_key: str | None
    core_api_key: str | None
    elsevier_api_key: str | None = None
    elsevier_insttoken: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        email = os.environ.get("OPENALEX_EMAIL", "").strip()
        if not email:
            raise RuntimeError(
                "OPENALEX_EMAIL is required (used in User-Agent for OpenAlex and as the "
                "email param for Unpaywall). Set it in .env."
            )
        if email == "your-email@example.com":
            raise RuntimeError(
                "OPENALEX_EMAIL is still the .env.example placeholder. "
                "Edit .env and set it to a real email address."
            )
        s2 = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip() or None
        core = os.environ.get("CORE_API_KEY", "").strip() or None
        elsevier = os.environ.get("ELSEVIER_API_KEY", "").strip() or None
        elsevier_inst = os.environ.get("ELSEVIER_INSTTOKEN", "").strip() or None
        return cls(
            openalex_email=email,
            s2_api_key=s2,
            core_api_key=core,
            elsevier_api_key=elsevier,
            elsevier_insttoken=elsevier_inst,
        )
