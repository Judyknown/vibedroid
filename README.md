# VibeDroid

A database of AI-assisted and vibe-coded Android applications.

## Scope

VibeDroid tracks Android-specific application projects that show evidence of AI-assisted development or explicit vibe-coding. The master catalog lives in `data/curated/apps.csv`.

This repo currently focuses on:
- Android-specific repositories
- explicit AI-development evidence where available
- reproducible collection notes and raw candidate lists
- conservative verification rules

## Status model

- `verified`: Android evidence and AI-development evidence both confirmed
- `candidate`: plausible match, but one or more criteria still need confirmation
- `rejected`: reviewed and excluded from the verified catalog

## Key files

- `docs/SCHEMA.md`
- `docs/HAUKE_REVIEW.md`
- `data/curated/apps.csv`
- `data/raw/2026-11-04_github_candidates.csv`
- `scripts/validate_catalog.py`
- `scripts/summary.py`

## Validation

```bash
python3 scripts/validate_catalog.py data/curated/apps.csv
python3 scripts/summary.py data/curated/apps.csv
```

## Licensing

This repository contains:
- original code in `scripts/`
- original documentation in `docs/`
- an original manually reviewed catalog in `data/`

Code is licensed under `LICENSE-CODE`.
Data and documentation are licensed under `LICENSE-DATA`.

## Remote setup

A private GitHub repo should be created only after `gh auth login` succeeds locally.
