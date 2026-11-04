#!/usr/bin/env python3
import csv
import sys
from pathlib import Path
from urllib.parse import urlparse

REQUIRED_COLUMNS = [
    "id",
    "status",
    "classification",
    "repo_url",
    "app_name",
    "platform_target",
    "framework",
    "ai_tools",
    "apk_available",
    "created_year",
    "android_evidence",
    "ai_dev_evidence",
    "discovery_source",
    "discovery_query",
    "discovery_date",
    "last_checked",
    "notes",
]
ALLOWED_STATUS = {"verified", "candidate", "rejected"}
ALLOWED_CLASSIFICATION = {"vibe_coded", "ai_assisted", "unclear", "not_a_match"}
ALLOWED_APK = {"yes", "no", "unknown", ""}


def canonicalize_repo_url(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    if host == "www.github.com":
        host = "github.com"
    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return f"https://{host}{path}"


def is_valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python3 scripts/validate_catalog.py data/curated/apps.csv")
        return 2

    csv_path = Path(sys.argv[1])
    if not csv_path.exists():
        print(f"error: file not found: {csv_path}")
        return 2

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
        if missing:
            print("error: missing required columns:", ", ".join(missing))
            return 1

        seen_urls = {}
        errors = []
        row_count = 0
        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            row_id = row.get("id", "").strip() or f"row-{row_number}"
            status = row.get("status", "").strip()
            classification = row.get("classification", "").strip()
            repo_url = row.get("repo_url", "").strip()
            apk_available = row.get("apk_available", "").strip()
            created_year = row.get("created_year", "").strip()

            if status not in ALLOWED_STATUS:
                errors.append(f"line {row_number} {row_id}: invalid status '{status}'")
            if classification not in ALLOWED_CLASSIFICATION:
                errors.append(f"line {row_number} {row_id}: invalid classification '{classification}'")
            if apk_available not in ALLOWED_APK:
                errors.append(f"line {row_number} {row_id}: invalid apk_available '{apk_available}'")
            if not repo_url or not is_valid_http_url(repo_url):
                errors.append(f"line {row_number} {row_id}: invalid repo_url '{repo_url}'")
            else:
                canonical = canonicalize_repo_url(repo_url)
                previous = seen_urls.get(canonical)
                if previous:
                    errors.append(
                        f"line {row_number} {row_id}: duplicate repo_url canonicalized to {canonical} (already used by {previous})"
                    )
                else:
                    seen_urls[canonical] = row_id

            if created_year:
                if not (created_year.isdigit() and len(created_year) == 4):
                    errors.append(f"line {row_number} {row_id}: invalid created_year '{created_year}'")

        if errors:
            print(f"validation failed for {csv_path} with {len(errors)} error(s):")
            for error in errors:
                print(f"- {error}")
            return 1

    print(f"validation ok: {csv_path} ({row_count} rows)")
    print(f"unique canonical repo URLs: {row_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
