#!/usr/bin/env python3
import csv
import sys
from collections import Counter
from pathlib import Path


def split_values(value: str):
    return [item.strip() for item in value.split(";") if item.strip()]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python3 scripts/summary.py data/curated/apps.csv")
        return 2

    csv_path = Path(sys.argv[1])
    if not csv_path.exists():
        print(f"error: file not found: {csv_path}")
        return 2

    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    verified = [row for row in rows if row.get("status", "").strip() == "verified"]

    year_counts = Counter()
    ai_tool_counts = Counter()
    framework_counts = Counter()
    apk_counts = Counter()

    for row in verified:
        year = row.get("created_year", "").strip()
        if year:
            year_counts[year] += 1
        for tool in split_values(row.get("ai_tools", "")):
            ai_tool_counts[tool] += 1
        for framework in split_values(row.get("framework", "")):
            framework_counts[framework] += 1
        apk = row.get("apk_available", "").strip() or "unknown"
        apk_counts[apk] += 1

    print(f"reviewed_rows: {len(rows)}")
    print(f"verified_rows: {len(verified)}")
    print("creation_years:")
    for year, count in sorted(year_counts.items()):
        print(f"  {year}: {count}")
    print("ai_tools:")
    for tool, count in ai_tool_counts.most_common():
        print(f"  {tool}: {count}")
    print("frameworks:")
    for framework, count in framework_counts.most_common():
        print(f"  {framework}: {count}")
    print("apk_availability:")
    for label in ["yes", "no", "unknown"]:
        print(f"  {label}: {apk_counts.get(label, 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
