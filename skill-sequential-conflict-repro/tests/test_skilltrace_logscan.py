from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from skilltrace.scanner import scan_log_files


class SkillTraceLogScanTests(unittest.TestCase):
    def test_codex_log_matches_c1(self):
        result = scan_log_files(
            [PROJECT_ROOT / "examples" / "skilltrace" / "sample_codex_c1.jsonl"]
        )
        self.assertEqual(
            [item["id"] for item in result["detected_skills"]],
            ["paper-search-pro", "easy-vibe"],
        )
        self.assertEqual(
            [item["license"] for item in result["detected_skills"]],
            ["Apache-2.0", "CC-BY-NC-SA-4.0"],
        )
        self.assertEqual(result["matched_chains"][0]["scenario"], "C1")

    def test_claude_log_matches_o1(self):
        result = scan_log_files(
            [PROJECT_ROOT / "examples" / "skilltrace" / "sample_claude_o1.json"]
        )
        self.assertEqual(
            [item["id"] for item in result["detected_skills"]],
            ["license-philosopher", "ritual-document"],
        )
        self.assertEqual(
            [item["license"] for item in result["detected_skills"]],
            ["CC-BY-SA-4.0", "Apache-2.0 OR MIT"],
        )
        self.assertEqual(result["matched_chains"][0]["scenario"], "O1")

    def test_generic_text_log_can_be_scanned(self):
        sample = PROJECT_ROOT / "examples" / "skilltrace" / "sample_generic.txt"
        result = scan_log_files([sample], source="generic")
        self.assertEqual(
            [item["id"] for item in result["detected_skills"]],
            ["gzh-design"],
        )


if __name__ == "__main__":
    unittest.main()
