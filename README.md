# VibeDroid

<p align="center">
  <img src="assets/vibedroid.svg" alt="VibeDroid logo" width="180" />
</p>

VibeDroid is a curated database of Android application projects with evidence of **AI-assisted development** or **vibe coding**.

It is a **reviewed reference dataset** for research and analysis — not an app store, ranking, or benchmark.

## Positioning

VibeDroid tracks projects at the intersection of:

- Android app development
- explicit AI-development evidence
- manual verification

In short: VibeDroid is a **curated observational dataset** for studying how AI-assisted development appears in the Android ecosystem.

## Scope

The master catalog lives in `data/curated/apps.csv`.

An entry is included only when it has:

1. clear **Android evidence**
2. clear or reviewable **AI-development evidence**

## Review Logic

| Condition | Outcome |
| --- | --- |
| Android evidence + AI-development evidence | `verified` |
| Android evidence + incomplete AI-development evidence | `candidate` |
| No Android evidence, or reviewed and excluded | `rejected` |

This keeps released counts conservative: only `verified` entries should be treated as confirmed matches.

## Status Model

- `verified`: Android scope and AI-development evidence are both confirmed
- `candidate`: plausible match, but evidence is still incomplete
- `rejected`: reviewed and excluded from confirmed dataset claims

## What This Database Is

- a manually reviewed Android project catalog
- a structured dataset for research and reporting
- a sourceable record of inclusion decisions

## What This Database Is Not

- not an app marketplace
- not a quality ranking
- not a complete census of all AI-touched Android apps

## Use Cases

- landscape mapping
- framework and tooling analysis
- audit of AI-development claims
- downstream visualizations and reports

## Data Model

The core unit is one reviewed app project / repository identity.

Key fields include:

- `status`
- `classification`
- `repo_url`
- `app_name`
- `platform_target`
- `framework`
- `ai_tools`
- `apk_available`
- `android_evidence`
- `ai_dev_evidence`
- `notes`

Full schema: `docs/SCHEMA.md`

## Repository Layout

- `data/curated/apps.csv`: reviewed master catalog
- `data/raw/2026-11-04_github_candidates.csv`: raw discovery export
- `docs/SCHEMA.md`: schema and verification rules
- `scripts/validate_catalog.py`: catalog validation
- `scripts/summary.py`: summary statistics

## Validation

```bash
python3 scripts/validate_catalog.py data/curated/apps.csv
python3 scripts/summary.py data/curated/apps.csv
```

## Automated GitHub Discovery

GitHub discovery is automated, but verification remains manual. Set a GitHub
token in the shell before searching so the API allows the authenticated rate
limit:

```bash
export GITHUB_TOKEN="github_pat_your_token_here"
python3 scripts/search_github.py --output data/raw/github_candidates.csv
```

The script combines GitHub Repository Search and Code Search. It now:

- runs a broader set of configurable vibe-coding discovery queries across README text, descriptions, and topics
- preserves all matched discovery queries for the same repository
- fetches README content and stores a short evidence snippet plus a source URL
- verifies Android structure for Native Android, Flutter, and React Native repositories
- flags likely tools, tutorials, templates, libraries, and unrelated repositories for exclusion or manual review

Code Search still works as a supplementary discovery signal and still benefits
from `GITHUB_TOKEN`. Discovery matches are not treated as confirmed dataset
entries on their own: the CSV records README evidence, Android validation, and
review status so candidates remain auditable.

To test a query without writing a file:

```bash
python3 scripts/search_github.py --query 'android "vibe coded" in:readme' --dry-run
```

Useful options:

```bash
python3 scripts/search_github.py --max-pages 10 --per-query 100
python3 scripts/search_github.py --no-code-search
python3 scripts/search_github.py --code-query 'filename:CLAUDE.md android'
python3 scripts/search_github.py --raw-json-dir data/raw/github_api
```

Important output fields include:

- `discovery_queries`: all queries that matched a repository
- `vibe_evidence_status`, `vibe_evidence_text`, `vibe_evidence_url`: extracted README evidence
- `android_framework`, `android_validation_status`, `android_evidence`: structural Android checks
- `project_type`, `review_status`, `exclusion_reason`: lightweight filtering decisions

Classification is intentionally conservative. Generic mentions of Claude Code,
Cursor, or Copilot do not count as vibe-coding evidence by themselves, and
ambiguous repositories stay in `manual_review` instead of being silently
discarded.

When `--raw-json-dir` is set, the script also saves the raw GitHub API items for
each query as JSON. This makes it easier to audit search quality, reprocess
results, or compare Repository Search against Code Search without re-running the
API calls.

Create a fine-grained GitHub token with public repository read access. Keep the
token in the shell environment or a local secret manager; do not commit it to
the repository.

## Quality Principles

- conservative verification
- explicit uncertainty
- traceable review decisions
- deduplicated project identity

## Limitations

- not exhaustive
- evidence can change over time
- some AI-assisted projects are not publicly disclosed

## Licensing

- code in `scripts/` is licensed under `LICENSE-CODE`
- data and documentation are licensed under `LICENSE-DATA`

## Remote Setup

Create a private GitHub repository only after `gh auth login` succeeds locally.
