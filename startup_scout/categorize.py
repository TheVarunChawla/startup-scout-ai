"""Rule-based categorization.

A lightweight keyword scorer is enough here (and cheap/deterministic,
unlike an LLM call) because the category taxonomy is small and mostly
about routing into Varun's stated interest areas. If this needs to get
smarter later, swap the scoring body for an LLM call behind the same
`categorize()` signature - callers don't need to change.

The startup's own name + description count 3x more than its tags when
scoring. Some sources (like Y Combinator) attach their own generic
industry tags (e.g. "Developer Tools") to a company; those tags are
still a useful signal, but a real content match in the company's own
description should win over an incidental tag match.
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

# How much more the startup's own name/description counts than its tags.
PRIMARY_TEXT_WEIGHT = 3


def categorize(startup: RawStartup) -> str:
    primary_text = " ".join([startup.name, startup.description]).lower()
    tag_text = " ".join(startup.tags).lower()

    best_category = DEFAULT_CATEGORY
    best_score = 0.0
    for category, keywords in CATEGORY_KEYWORDS.items():
        primary_score = sum(1 for kw in keywords if kw in primary_text)
        tag_score = sum(1 for kw in keywords if kw in tag_text)
        score = primary_score * PRIMARY_TEXT_WEIGHT + tag_score
        if score > best_score:
            best_score = score
            best_category = category
    return best_category
