from rrl.config import (
    AI_TERMS, HE_TERMS, K12_TERMS,
    YEAR_MIN, YEAR_MAX,
    PREDATORY_BLOCKLIST, ACADEMIC_PRESS_ALLOWLIST,
    RATE_PLANS, Settings,
)

def test_term_lists_nonempty():
    assert len(AI_TERMS) >= 10
    assert len(HE_TERMS) >= 10
    assert len(K12_TERMS) >= 5
    assert "ChatGPT" in AI_TERMS
    assert "higher education" in HE_TERMS
    assert "AI" not in AI_TERMS  # bare AI excluded — too noisy

def test_year_range():
    assert YEAR_MIN == 2020
    assert YEAR_MAX == 2026

def test_blocklist_and_allowlist():
    assert len(PREDATORY_BLOCKLIST) >= 5
    assert len(ACADEMIC_PRESS_ALLOWLIST) >= 8
    assert "Springer" in ACADEMIC_PRESS_ALLOWLIST

def test_rate_plans_for_required_adapters():
    for adapter in ("openalex", "eric", "s2", "crossref", "core", "doaj", "unpaywall"):
        assert adapter in RATE_PLANS
        assert RATE_PLANS[adapter]["requests_per_second"] > 0

def test_settings_requires_openalex_email(monkeypatch):
    monkeypatch.delenv("OPENALEX_EMAIL", raising=False)
    try:
        Settings.from_env()
    except RuntimeError as e:
        assert "OPENALEX_EMAIL" in str(e)
    else:
        raise AssertionError("expected RuntimeError")

def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("OPENALEX_EMAIL", "test@example.com")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "abc123")
    s = Settings.from_env()
    assert s.openalex_email == "test@example.com"
    assert s.s2_api_key == "abc123"
    assert s.core_api_key is None


def test_settings_from_env_loads_elsevier_key(monkeypatch):
    monkeypatch.setenv("OPENALEX_EMAIL", "user@example.com")
    monkeypatch.setenv("ELSEVIER_API_KEY", "fake-elsevier-key")
    monkeypatch.delenv("ELSEVIER_INSTTOKEN", raising=False)
    from rrl.config import Settings
    s = Settings.from_env()
    assert s.elsevier_api_key == "fake-elsevier-key"
    assert s.elsevier_insttoken is None


def test_settings_from_env_elsevier_key_optional(monkeypatch):
    monkeypatch.setenv("OPENALEX_EMAIL", "user@example.com")
    monkeypatch.delenv("ELSEVIER_API_KEY", raising=False)
    monkeypatch.delenv("ELSEVIER_INSTTOKEN", raising=False)
    from rrl.config import Settings
    s = Settings.from_env()
    assert s.elsevier_api_key is None
    assert s.elsevier_insttoken is None


def test_settings_from_env_loads_elsevier_insttoken(monkeypatch):
    monkeypatch.setenv("OPENALEX_EMAIL", "user@example.com")
    monkeypatch.setenv("ELSEVIER_API_KEY", "fake-key")
    monkeypatch.setenv("ELSEVIER_INSTTOKEN", "fake-token")
    from rrl.config import Settings
    s = Settings.from_env()
    assert s.elsevier_insttoken == "fake-token"
