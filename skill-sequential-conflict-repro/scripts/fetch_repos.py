#!/usr/bin/env python3
"""Fetch every Skill repository at the commit recorded in inputs/skills.json."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_git(git: str, cwd: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        [git, "-C", str(cwd), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and proc.returncode:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {cwd}\n"
            f"{proc.stdout}\n{proc.stderr}"
        )
    return proc.stdout.strip()


def ensure_repo(skill: dict, repos_dir: Path, git: str) -> None:
    target = repos_dir / skill["id"]
    target.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{skill['repository']}.git"

    if not (target / ".git").exists():
        run_git(git, target, "init", "-q")
        run_git(git, target, "remote", "add", "origin", url)
    else:
        status = run_git(git, target, "status", "--porcelain")
        if status:
            raise RuntimeError(f"refusing to update dirty checkout: {target}")
        remotes = run_git(git, target, "remote").splitlines()
        if "origin" in remotes:
            run_git(git, target, "remote", "set-url", "origin", url)
        else:
            run_git(git, target, "remote", "add", "origin", url)

    run_git(
        git,
        target,
        "fetch",
        "-q",
        "--depth",
        "1",
        "origin",
        skill["commit"],
    )
    run_git(git, target, "checkout", "-q", "--detach", "FETCH_HEAD")
    head = run_git(git, target, "rev-parse", "HEAD")
    if head != skill["commit"]:
        raise RuntimeError(
            f"commit mismatch for {skill['id']}: expected {skill['commit']}, got {head}"
        )
    print(f"{skill['id']}: {head}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skills",
        type=Path,
        default=PROJECT_ROOT / "inputs" / "skills.json",
    )
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=PROJECT_ROOT / "repos",
    )
    parser.add_argument("--git", default="git")
    args = parser.parse_args()

    payload = json.loads(args.skills.read_text(encoding="utf-8"))
    args.repos_dir.mkdir(parents=True, exist_ok=True)
    for skill in payload["skills"]:
        ensure_repo(skill, args.repos_dir, args.git)


if __name__ == "__main__":
    main()
