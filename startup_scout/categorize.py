"""Rule-based categorization.

A lightweight keyword scorer is enough here (and cheap/deterministic,
unlike an LLM call) because the category taxonomy is small and mostly
about routing into Varun's stated interest areas. If this needs to get
smarter later, swap the scoring body for an LLM call behind the same
`categorize()` signature - callers don't need to change.
"""
from __future__ import annotations

from startup_scout.models import RawStartup

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "AI SaaS": ["ai", "artificial intelligence", "llm", "machine learning", "genai", "copilot", "agent"],
    "Cyber Security": ["security", "cyber", "infosec", "encryption", "privacy", "vulnerability", "pentest", "compliance"],
    "Education": ["learning", "course", "education", "edtech", "training", "tutor", "student"],
    "Automation": ["automation", "workflow", "no-code", "low-code", "zapier", "rpa"],
    "Developer Tools": ["developer", "api", "sdk", "devtools", "cli", "framework", "open source", "github"],
    "B2B Software": ["b2b", "enterprise", "saas", "crm", "erp"],
    "Productivity": ["productivity", "notes", "calendar", "task", "todo", "collaboration"],
    "Digital Products": ["ebook", "template", "digital product", "notion template"],
    "Fintech": ["fintech", "payments", "banking", "invoice", "accounting", "finance"],
    "Healthtech": ["health", "medical", "fitness", "wellness", "clinic"],
}

DEFAULT_CATEGORY = "Other"


def categorize(startup: RawStartup) -> str:
    text = " ".join(
        [startup.name, startup.description, " ".join(startup.tags)]
    ).lower()

    best_category = DEFAULT_CATEGORY
    best_score = 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score = score
            best_category = category
    return best_category
