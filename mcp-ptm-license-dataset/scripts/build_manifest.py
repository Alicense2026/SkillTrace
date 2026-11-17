#!/usr/bin/env python3
"""Build dataset summary and SHA-256 manifest from the packaged result files."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA = PROJECT_ROOT / "data"
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def category(topic: str) -> str:
    value = topic.lower().split(" in:name,description", 1)[0].strip()
    if value.startswith("mcp") or value == "model-context-protocol":
        return "MCP"
    return "PTM"


def dataset_summary(path: Path, id_field: str) -> dict:
    rows = read_csv(path)
    categories = Counter(category(row.get("search_topic", "")) for row in rows)
    topics = Counter(row.get("search_topic", "") for row in rows)
    return {
        "file": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "records": len(rows),
        "unique_ids": len({row.get(id_field, "") for row in rows}),
        "id_field": id_field,
        "categories": dict(sorted(categories.items())),
        "topics": dict(sorted(topics.items())),
        "columns": list(rows[0].keys()) if rows else [],
    }


def main() -> None:
    hf_csv = DATA / "hf" / "hf_dataset.csv"
    gh_csv = DATA / "github" / "github_dataset.csv"
    hf_stats = json.loads((DATA / "hf" / "stats.json").read_text(encoding="utf-8"))
    gh_stats = json.loads(
        (DATA / "github" / "stats.json").read_text(encoding="utf-8")
    )

    summary = {
        "collection_dates": {
            "huggingface": hf_stats.get("date"),
            "github": gh_stats.get("date"),
        },
        "huggingface": dataset_summary(hf_csv, "model_id"),
        "github": dataset_summary(gh_csv, "full_name"),
        "license_crosscheck": {
            "huggingface": hf_stats.get("license_crosscheck", {}).get(
                "cross_check", {}
            ),
            "github": gh_stats.get("license_crosscheck", {}).get(
                "cross_check", {}
            ),
        },
    }
    (DATA / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    files = sorted(path for path in DATA.rglob("*") if path.is_file())
    manifest = {
        "algorithm": "sha256",
        "files": [
            {
                "path": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in files
            if path.name not in {"manifest.json", "summary.json"}
        ],
    }
    (DATA / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"HF={summary['huggingface']['records']} "
        f"GitHub={summary['github']['records']} "
        f"files={len(manifest['files'])}"
    )


if __name__ == "__main__":
    main()
