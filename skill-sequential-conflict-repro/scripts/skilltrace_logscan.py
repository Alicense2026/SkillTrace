#!/usr/bin/env python3
"""Extract Skill invocation and license evidence from agent execution logs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from skilltrace.scanner import (  # noqa: E402
    DEFAULT_SKILLS,
    DEFAULT_TASKS,
    render_text,
    scan_log_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Extract Skill invocation order, license evidence, and known conflict "
            "chains from Codex/Claude JSONL or generic text logs."
        )
    )
    parser.add_argument("logs", nargs="+", help="JSON, JSONL, or text log files")
    parser.add_argument(
        "--source",
        choices=["auto", "codex", "claude_code", "openclaw", "generic"],
        default="auto",
    )
    parser.add_argument("--skills", default=str(DEFAULT_SKILLS))
    parser.add_argument("--tasks", default=str(DEFAULT_TASKS))
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    parser.add_argument("--output", help="write the result to this path")
    args = parser.parse_args()

    result = scan_log_files(
        args.logs,
        source=args.source,
        skills_path=args.skills,
        tasks_path=args.tasks,
    )
    if args.json or args.output:
        rendered = json.dumps(
            result,
            ensure_ascii=False,
            indent=2 if args.pretty else None,
        )
    else:
        rendered = render_text(result)

    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        print(args.output)
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
