#!/usr/bin/env python3
"""Export the packaged first-decision records as a readable Markdown log."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASKS_PATH = PROJECT_ROOT / "inputs" / "tasks.json"
OUTPUT_PATH = PROJECT_ROOT / "transcripts" / "run_outputs.md"


def main() -> None:
    data = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    lines = [
        "# First-decision run log",
        "",
        "This file is generated from `inputs/tasks.json`. It records the first Agent "
        "decision for the single-run replay, before any retry or correction.",
        "",
    ]
    for task in data["tasks"]:
        observed = task["observed"]
        lines.extend(
            [
                f"## {task['run_id']}",
                "",
                f"- Condition: `{task['condition']}`",
                f"- Skill order: {' -> '.join(task['call_order'])}",
                f"- Prompt: {task['prompt']}",
                f"- First decision: `{observed['decision']}`",
                f"- Conflict detected: `{str(observed['conflict_detected']).lower()}`",
                f"- Guarded step: `{str(observed.get('guarded_step', False)).lower()}`",
                "",
                observed["response"],
                "",
                "Evidence:",
                "",
            ]
        )
        lines.extend(f"- {item}" for item in task["evidence"])
        lines.extend(["", f"Result: **{'PASS' if task['pass'] else 'FAIL'}**", ""])

    OUTPUT_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
