# VibeDroid catalog schema

The master catalog is `data/curated/apps.csv`.

## Verification rules

A row can be marked `verified` only if both conditions are met:

1. **Android-specific evidence**: the repository clearly targets Android, for example via native Android code, Android app screenshots, Android install instructions, Android APK/release artifacts, or Android-specific README language.
2. **AI-development evidence**: the repository explicitly states that AI tools were used to build the app, or includes equivalent first-party evidence such as README claims, install notes, badges, or repository docs that the app was vibe coded or AI assisted.

Rows that mention AI as a product feature rather than as a development method should not be upgraded to `verified` on that basis alone.

## Columns

- `id`: stable row identifier
- `status`: one of `verified`, `candidate`, `rejected`
- `classification`: one of `vibe_coded`, `ai_assisted`, `unclear`, `not_a_match`
- `repo_url`: canonical repository URL
- `app_name`: project or app name
- `platform_target`: Android scope such as `android`, `android_auto`, `android_tv`, or `android+ios`
- `framework`: main stack or framework
- `ai_tools`: semicolon-separated list of named AI tools if explicitly evidenced
- `apk_available`: `yes`, `no`, or `unknown`
- `created_year`: repository creation year when confirmed
- `android_evidence`: concise evidence for Android specificity
- `ai_dev_evidence`: concise evidence for AI-assisted development classification
- `discovery_source`: where the candidate came from
- `discovery_query`: search query or collection method
- `discovery_date`: ISO date when discovered
- `last_checked`: ISO date when manually reviewed
- `notes`: free-form review notes

## Deduplication

Deduplicate in two stages:

1. Canonical repository URL
   - normalize `https`
   - lowercase hostname
   - strip trailing slash
   - strip `.git`
   - treat `www.github.com` as `github.com`
2. Unmistakably identical project identity
   - same Android app published under renamed or mirrored repositories
   - same project maintained in a moved repository

Do not deduplicate unrelated forks or templates unless project identity is unmistakably identical.

## Status meanings

- `verified`: include in summaries and released dataset counts
- `candidate`: reviewed but not yet strong enough for verified counts
- `rejected`: reviewed and excluded from dataset claims
