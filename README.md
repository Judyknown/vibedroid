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
