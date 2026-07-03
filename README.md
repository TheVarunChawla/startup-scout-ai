# Startup Scout AI

An AI technical co-founder that discovers startup ideas from around the world, analyzes them, ranks them against a personal founder profile, and produces a daily top-5 opportunity report.

This is not a scraper. Collection is the first of ten pipeline stages — the point of the project is the analysis, scoring, and ranking that turn raw listings into a decision-ready daily briefing.

## How it works

```
connectors (collect) -> dedupe -> categorize -> AI analysis -> personal scoring
   -> SQLite persistence -> trend analysis -> Markdown report
```

Every stage is an independently testable module under `startup_scout/`. The pipeline (`startup_scout/pipeline.py`) only wires them together — it contains no business logic itself, so a new connector, a new scoring criterion, or a new report section can be added without touching the others.

## Directory structure

```
startup-scout-ai/
├── main.py                    # CLI entrypoint (run pipeline / record feedback)
├── config/
│   ├── config.yaml             # connectors, scoring weights, report/db settings
│   └── profile.yaml            # Varun's founder profile (skills, interests, constraints)
├── startup_scout/
│   ├── models.py                # RawStartup / Analysis / ScoredStartup dataclasses
│   ├── config.py                 # YAML config loader
│   ├── db.py                     # SQLite persistence (history + feedback)
│   ├── dedupe.py                 # cross-source deduplication
│   ├── categorize.py             # keyword-based categorization
│   ├── analysis.py               # AI analysis (heuristic fallback + optional LLM)
│   ├── scoring.py                 # 0-100 personal-fit scoring
│   ├── trends.py                  # category growth trend detection
│   ├── memory.py                  # learns from liked/rejected feedback
│   ├── report.py                  # Markdown daily report generator
│   ├── pipeline.py                # orchestrates all of the above
│   └── connectors/
│       ├── base.py                # BaseConnector interface
│       ├── hacker_news.py         # real: Algolia HN Search API (no key needed)
│       ├── product_hunt.py        # real: Product Hunt GraphQL API (needs a token)
│       └── stubs.py               # documented placeholders for restricted sources
├── tests/                      # pytest unit tests for every module above
├── data/                        # startup_scout.db (SQLite, gitignored)
├── reports/                     # daily YYYY-MM-DD.md reports (committed by CI)
└── .github/workflows/daily.yml  # scheduled daily run
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt
cp .env.example .env   # fill in tokens if you have them (optional — see below)
```

## Running it

```bash
python main.py run
```

This collects from every `enabled: true` connector in `config/config.yaml`, dedupes, analyzes, scores against `config/profile.yaml`, persists to `data/startup_scout.db`, and writes `reports/<today>.md`.

Record feedback so future runs learn your preferences:

```bash
python main.py feedback <startup_id> --like
python main.py feedback <startup_id> --reject --note "not a fit, too capital intensive"
```

`<startup_id>` is the id shown in the report / database (a stable hash of source+name+url).

## Configuration

Nothing about *what* to score or *how much* to weight it is hardcoded — it all comes from YAML:

- `config/profile.yaml` — skills, interests, avoid-list, investment cap, team-size and time preferences.
- `config/config.yaml` — which connectors are enabled and their settings, the 10 scoring weights (must sum to 100), report output settings, and the analysis mode (`heuristic` or `llm`).

## Connector status

| Connector | Status | Why |
|---|---|---|
| Hacker News | **Live** | Free Algolia HN Search API, no key required. Filters out Ask HN/Tell HN/Poll discussion threads and major news-site domains so only startup listings come through. |
| Product Hunt | **Live**, needs credential | Free GraphQL API v2, requires `PRODUCT_HUNT_TOKEN` env var. Runs and returns `[]` with a warning if unset — never breaks the pipeline. |
| Y Combinator directory | Stub | No public export/API |
| YC Requests for Startups | Stub | Static page, would need scraping |
| Wellfound, Indie Hackers, F6S, OpenVC, Seedtable, BetaList | Stub | No public API, most ToS-restrict scraping |
| Crunchbase | Stub | API exists but requires a paid license |
| Reddit | Stub | Needs a free OAuth app registration (5-minute setup, then it's a real connector) |
| GitHub Trending | Stub | No official API — scraping is common practice but flagged here as a policy decision |
| TechCrunch | Stub | Has a public RSS feed — this is the easiest one to make real |
| AI / startup newsletters | Stub | Needs per-newsletter RSS/email parsing config. |

Every stub is a `StubConnector` instance (see `startup_scout/connectors/stubs.py`) that implements the same `BaseConnector` interface, logs why it's not live, and returns `[]`. Turning one on later means writing one connector class and flipping `enabled: true` in `config.yaml` — nothing else in the pipeline changes.

## Scoring methodology

Each startup gets ten 0–10 sub-scores (skills match, interests match, low investment, India readiness, AI potential, ease of execution, revenue potential, competition, scalability, long-term opportunity), each weighted per `config.yaml` and summed to a 0–100 score. A bounded memory adjustment (±10 points) is then applied based on how you've historically rated startups in that category — enough to visibly shift rankings without letting feedback overwhelm the base profile fit.

## AI analysis modes

- **`heuristic`** (default): fast, free, deterministic rule-of-thumb estimates for every analysis field (problem, business model, MVP cost/time, India suitability, etc). Zero external dependency — this is what CI and tests run against, and what you get with no API key configured.
- **`llm`**: calls the Anthropic API with a structured prompt and parses the JSON response into the same fields. Requires `ANTHROPIC_API_KEY`. Falls back to heuristic automatically if the call fails, so a flaky API never breaks the daily run.

Switch modes via `analysis.mode` in `config.yaml`.

## Automation (GitHub Actions)

`.github/workflows/daily.yml` runs `python main.py run` every day and commits the new report + database back to the repo. Add these as repo secrets if you want the live connectors/LLM mode to actually run in CI:

- `PRODUCT_HUNT_TOKEN`
- `ANTHROPIC_API_KEY` (only needed if `analysis.mode: llm`)

## Testing

```bash
pytest
```

Covers deduplication, categorization, scoring, the Hacker News connector (network calls mocked), SQLite persistence, and report generation.

## Roadmap

1. TechCrunch RSS connector (real implementation is straightforward — see stub notes).
2. Reddit connector via PRAW + OAuth app.
3. GitHub Trending connector (decide scraping policy first).
4. LLM-mode analysis by default once cost/latency is validated on a full daily batch.
5. Smarter memory model (e.g. embeddings-based similarity to liked startups, not just category ratio).
6. Web dashboard over the SQLite history for browsing past reports and trends.

## Design decisions worth knowing about

- **Heuristic-first analysis.** The pipeline must run end-to-end with zero paid API calls (important for CI and for day one before you've wired up an LLM key). LLM analysis is opt-in and degrades gracefully.
- **Config-driven scoring weights.** Your priorities will shift as you use this — the weights live in YAML specifically so tuning them doesn't require touching `scoring.py`.
- **Stub connectors are real classes, not TODO comments.** They implement `BaseConnector`, get instantiated by the same registry as live connectors, and log a structured reason — so "add a connector" is always the same mechanical step.
- **SQLite, not a heavier ORM.** The schema is small and stable; plain `sqlite3` keeps the project dependency-light and the data inspectable with any SQLite browser.
- **Feedback adjustment is capped and transparent** (category like-ratio × cap), not a black-box model — you can see exactly why a score moved.
