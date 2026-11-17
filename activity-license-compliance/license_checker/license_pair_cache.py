"""Reusable SQLite cache for license-license symbolic comparisons only."""
import hashlib
import json
import sqlite3
from pathlib import Path

CACHE_ALGORITHM = "asc-pair-cache-v1"


def stable_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def comparison_key(upstream, downstream, scope_shared):
    """Key on normalized ASC terms and rule provenance, excluding case identities."""
    def term(rule):
        triple = rule["triple"]
        source = rule.get("source", {})
        return {
            "triple": {
                "A": triple["A"],
                "S": {"artifact": "$LICENSED_OBJECT", "kind": triple["S"]["kind"]},
                "C": triple["C"],
            },
            "license": source.get("license"),
            "license_version": source.get("license_version"),
            "clause_id": source.get("clause_id"),
            "rule_version": source.get("rule_version"),
            "mapping_quality": rule.get("mapping_quality"),
            "coverage": rule.get("coverage"),
        }
    identity = {"algorithm": CACHE_ALGORITHM, "upstream": term(upstream),
                "downstream": term(downstream), "scope_shared": scope_shared}
    return hashlib.sha256(stable_json(identity).encode("utf-8")).hexdigest()


class LicensePairCache:
    """SQLite cache. Behavior/fact checking and obligation status are never cached."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS comparisons (cache_key TEXT PRIMARY KEY, result_json TEXT NOT NULL)")

    def _connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def get(self, key):
        with self._connect() as db:
            row = db.execute("SELECT result_json FROM comparisons WHERE cache_key=?", (key,)).fetchone()
        if row is None:
            self.misses += 1
            return None
        try:
            result = json.loads(row[0])
            if not isinstance(result, dict):
                raise ValueError("Cached comparison is not an object")
        except (json.JSONDecodeError, ValueError):
            with self._connect() as db:
                db.execute("DELETE FROM comparisons WHERE cache_key=?", (key,))
            self.misses += 1
            return None
        self.hits += 1
        return result

    def put(self, key, result):
        encoded = stable_json(result)
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO comparisons(cache_key,result_json) VALUES (?,?)", (key, encoded))

    def stats(self):
        with self._connect() as db:
            size = db.execute("SELECT COUNT(*) FROM comparisons").fetchone()[0]
        return {"path": str(self.path), "hits": self.hits, "misses": self.misses,
                "entries": size, "algorithm": CACHE_ALGORITHM}
