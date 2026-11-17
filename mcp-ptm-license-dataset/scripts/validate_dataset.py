#!/usr/bin/env python3
"""Validate packaged counts, identifiers, hashes, archive integrity, and token hygiene."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA = PROJECT_ROOT / "data"
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    hf = read_csv(DATA / "hf" / "hf_dataset.csv")
    gh = read_csv(DATA / "github" / "github_dataset.csv")
    assert len(hf) == 6394, f"HF rows: {len(hf)}"
    assert len(gh) == 16296, f"GitHub rows: {len(gh)}"
    assert len({row["model_id"] for row in hf}) == len(hf)
    assert len({row["full_name"] for row in gh}) == len(gh)
    assert len(read_csv(DATA / "hf" / "license_crosscheck.csv")) == len(hf)
    assert len(read_csv(DATA / "github" / "license_crosscheck.csv")) == len(gh)

    summary = json.loads((DATA / "summary.json").read_text(encoding="utf-8"))
    assert summary["huggingface"]["categories"] == {"MCP": 262, "PTM": 6132}
    assert summary["github"]["categories"] == {"MCP": 9778, "PTM": 6518}

    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = PROJECT_ROOT / item["path"]
        assert path.is_file(), f"missing file: {path}"
        assert path.stat().st_size == item["bytes"], f"size mismatch: {path}"
        assert file_sha256(path) == item["sha256"], f"hash mismatch: {path}"

    archive = DATA / "github" / "license_evidence.zip"
    with zipfile.ZipFile(archive) as handle:
        names = handle.namelist()
        assert names, "empty GitHub license evidence archive"
        assert handle.testzip() is None, "corrupt ZIP entry"

    github_script = (PROJECT_ROOT / "scripts" / "collect_github.py").read_text(
        encoding="utf-8"
    )
    assert not re.search(r'GITHUB_TOKEN\s*=\s*"', github_script), (
        "hard-coded GitHub token"
    )
    assert 'os.environ.get("GITHUB_TOKEN"' in github_script

    secret_pattern = re.compile(rb"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}")
    local_path_pattern = re.compile(rb"[A-Za-z]:\\\\Users\\\\")
    text_suffixes = {".py", ".md", ".json", ".csv", ".txt", ".yml", ".yaml"}
    for path in PROJECT_ROOT.rglob("*"):
        if path.is_file() and path.suffix.lower() in text_suffixes:
            content = path.read_bytes()
            assert not secret_pattern.search(content), (
                f"credential-like token found: {path}"
            )
            assert not local_path_pattern.search(content), (
                f"legacy absolute user path found: {path}"
            )

    print("PASS")
    print("HF: 6394 records (MCP 262, PTM 6132)")
    print("GitHub: 16296 records (MCP 9778, PTM 6518)")
    print(f"Manifest files: {len(manifest['files'])}")
    print(f"GitHub evidence entries: {len(names)}")


if __name__ == "__main__":
    main()
