from startup_scout.categorize import categorize
from startup_scout.models import RawStartup


def test_ai_saas_detected():
    s = RawStartup(source="x", name="Acme AI", url="", description="An LLM-powered copilot for support teams")
    assert categorize(s) == "AI SaaS"


def test_cyber_security_detected():
    s = RawStartup(source="x", name="SecureIt", url="", description="Vulnerability scanning and pentest automation")
    assert categorize(s) == "Cyber Security"


def test_education_detected():
    s = RawStartup(source="x", name="LearnFast", url="", description="Online courses and tutoring for students")
    assert categorize(s) == "Education"


def test_unknown_falls_back_to_other():
    s = RawStartup(source="x", name="Mystery", url="", description="")
    assert categorize(s) == "Other"


def test_own_description_beats_generic_source_tag():
    # Regression test: a YC-style generic industry tag ("Developer Tools")
    # should not out-vote a clear signal in the company's own description.
    s = RawStartup(
        source="y_combinator",
        name="Klarify",
        url="",
        description="AI Agent for Therapists",
        tags=["y_combinator", "Developer Tools"],
    )
    assert categorize(s) == "AI SaaS"
