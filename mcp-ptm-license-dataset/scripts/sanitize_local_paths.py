#!/usr/bin/env python3
"""Replace legacy absolute collection paths with repository-relative paths."""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA = PROJECT_ROOT / "data"
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

LEGACY_PREFIXES = {
    "hf": re.compile(
        r"^.*?HuggingFace_Topic_Search[\\/]v1", re.IGNORECASE
    ),
    "github": re.compile(
        r"^.*?D11_GitHub_Topic_Search[\\/]v2_small", re.IGNORECASE
    ),
}


def clean_string(value: str, platform: str) -> str:
    relative = LEGACY_PREFIXES[platform].sub(f"data/{platform}", value)
    return relative.replace("\\", "/")


def clean_json(value, platform: str):
    if isinstance(value, str):
        return clean_string(value, platform)
    if isinstance(value, list):
        return [clean_json(item, platform) for item in value]
    if isinstance(value, dict):
        return {key: clean_json(item, platform) for key, item in value.items()}
    return value


def main() -> None:
    for platform in ("hf", "github"):
        root = DATA / platform
        for path in root.rglob("*.json"):
            if path.name in {"stats.json", "summary.json", "manifest.json"}:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload = clean_json(payload, platform)
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        for path in root.glob("*.csv"):
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
                fieldnames = list(rows[0].keys()) if rows else []
            if not rows:
                continue
            for row in rows:
                for key, value in row.items():
                    if value:
                        row[key] = clean_string(value, platform)
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

    print("Legacy collection roots replaced with data/hf and data/github.")


if __name__ == "__main__":
    main()
