#!/usr/bin/env python3
"""Validate the packaged manifest, task matrix, results, and license evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=PROJECT_ROOT / "repos",
    )
    args = parser.parse_args()

    skills = load(PROJECT_ROOT / "inputs" / "skills.json")["skills"]
    tasks = load(PROJECT_ROOT / "inputs" / "tasks.json")["tasks"]
    evidence = load(PROJECT_ROOT / "inputs" / "license_evidence.json")["skills"]
    results = load(PROJECT_ROOT / "outputs" / "results.json")

    assert len(skills) == 8, f"expected 8 Skills, found {len(skills)}"
    assert len({s["id"] for s in skills}) == 8, "duplicate Skill ids"
    assert len(tasks) == 12, f"expected 12 tasks, found {len(tasks)}"
    assert Counter(t["condition"] for t in tasks) == {
        "positive": 6,
        "negative_control": 6,
    }
    assert len({t["run_id"] for t in tasks}) == 12, "duplicate run ids"

    for scenario in ("C1", "C2", "C3", "O1", "O2", "O3"):
        subset = [t for t in tasks if t["scenario"] == scenario]
        assert len(subset) == 2, f"{scenario} must have two tasks"
        assert {t["condition"] for t in subset} == {
            "positive",
            "negative_control",
        }

    for task in tasks:
        observed = task["observed"]
        if task["condition"] == "positive":
            assert observed["conflict_detected"] is True
            assert observed["guarded_step"] is True
        else:
            assert observed["conflict_detected"] is False
        assert task["pass"] is True

    by_skill = {s["id"]: s for s in skills}
    for item in evidence:
        skill = by_skill[item["skill_id"]]
        assert skill["commit"] == item["commit"]
        assert skill["repository"] == item["repository"]

    repo_root = args.repos_dir
    checked_files = 0
    if repo_root.exists():
        for item in evidence:
            repo_dir = repo_root / item["skill_id"]
            for file_info in item["files"]:
                path = repo_dir / file_info["path"]
                assert path.is_file(), f"missing evidence file: {path}"
                assert file_sha256(path) == file_info["sha256"], (
                    f"hash mismatch: {path}"
                )
                checked_files += 1

    summary = results["summary"]
    assert summary["overall_passed"] == 12
    assert summary["overall_total"] == 12

    print("PASS")
    print(f"Skills: {len(skills)}")
    print("Tasks: 12 (6 positive, 6 negative controls)")
    print("Expected decisions: 12/12")
    print(
        "License evidence files: "
        + (str(checked_files) if checked_files else "not checked; repos/ is absent")
    )


if __name__ == "__main__":
    main()
