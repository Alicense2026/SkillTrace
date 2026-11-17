#!/usr/bin/env python3
"""Generate SHA256SUMS for every public repository file."""

from __future__ import annotations

import hashlib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "SHA256SUMS"
EXCLUDED_PARTS = {".git", "__pycache__"}


def main() -> None:
    rows = []
    for path in sorted(PROJECT_ROOT.rglob("*")):
        if not path.is_file() or path == OUTPUT:
            continue
        relative = path.relative_to(PROJECT_ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(f"{digest}  {relative.as_posix()}")
    OUTPUT.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} entries.")


if __name__ == "__main__":
    main()
