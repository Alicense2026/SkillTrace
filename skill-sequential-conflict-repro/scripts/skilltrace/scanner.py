"""Detect the experiment Skills and their licenses in agent execution logs."""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable

from .event_schema import get_normalizer


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SKILLS = PROJECT_ROOT / "inputs" / "skills.json"
DEFAULT_TASKS = PROJECT_ROOT / "inputs" / "tasks.json"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sniff_source(raw: dict[str, Any]) -> str:
    if "tool_input" in raw or "tool_response" in raw:
        return "claude_code"
    event_type = str(raw.get("type", ""))
    if "item" in raw or event_type.startswith(("thread.", "turn.", "item.")):
        return "codex"
    if raw.get("source") in {"codex", "claude_code", "openclaw"}:
        return str(raw["source"])
    return "generic"


def _wrapper_events(payload: Any) -> list[Any] | None:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("events", "messages", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return None


def load_log_events(path: Path, source: str = "auto") -> tuple[list[dict], list[str]]:
    """Load JSON, JSONL, or generic text logs into normalized events."""
    text = path.read_text(encoding="utf-8", errors="replace")
    payloads: list[Any]
    errors: list[str] = []

    try:
        payload = json.loads(text)
        wrapped = _wrapper_events(payload)
        payloads = wrapped if wrapped is not None else [payload]
    except json.JSONDecodeError:
        payloads = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payloads.append(json.loads(line))
            except json.JSONDecodeError:
                payloads.append({"raw_text": line})
                if path.suffix.lower() in {".json", ".jsonl"}:
                    errors.append(f"{path}:{line_no}: non-JSON log line")

    normalized_events: list[dict] = []
    for index, payload in enumerate(payloads):
        raw = payload if isinstance(payload, dict) else {"value": payload}
        selected_source = source
        if source == "auto":
            selected_source = _sniff_source(raw)

        if selected_source == "generic":
            normalized = {
                "event_type": "generic_log",
                "tool_name": "",
                "timestamp": str(raw.get("timestamp", "")),
                "source": "generic",
                "metadata": raw,
            }
        else:
            normalized = get_normalizer(selected_source).normalize(raw)

        searchable = json.dumps(
            {"raw": raw, "normalized": normalized},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        normalized_events.append(
            {
                "index": index,
                "file": path.as_posix(),
                "source": selected_source,
                "raw": raw,
                "normalized": normalized,
                "searchable": searchable,
            }
        )
    return normalized_events, errors


def _load_skills(path: Path) -> list[dict]:
    return list(_load_json(path).get("skills", []))


def _skill_patterns(skill: dict) -> list[str]:
    skill_path = Path(skill["skill_path"])
    values = {
        skill["id"],
        skill["name"],
        skill["repository"],
    }
    if len(skill_path.parts) >= 3:
        values.add(skill["skill_path"])
    patterns = [
        str(value).lower()
        for value in values
        if value and str(value).lower() != "skill.md"
    ]
    return sorted(patterns, key=len, reverse=True)


def _match_skills(events: Iterable[dict], skills: list[dict]) -> list[dict]:
    matches: OrderedDict[str, dict] = OrderedDict()
    for event in events:
        text = event["searchable"].lower()
        for skill in skills:
            if skill["id"] in matches:
                continue
            for pattern in _skill_patterns(skill):
                if pattern not in text:
                    continue
                position = text.find(pattern)
                excerpt = event["searchable"][
                    max(0, position - 80) : position + len(pattern) + 120
                ]
                matches[skill["id"]] = {
                    "id": skill["id"],
                    "name": skill["name"],
                    "license": skill["license"],
                    "repository": skill["repository"],
                    "commit": skill["commit"],
                    "first_event": event["index"],
                    "source_file": event["file"],
                    "matched_text": pattern,
                    "evidence": excerpt,
                }
                break
    return list(matches.values())


def _known_chains(tasks_path: Path, detected: list[dict]) -> list[dict]:
    tasks = _load_json(tasks_path).get("tasks", [])
    detected_names = [item["name"] for item in detected]
    scenarios: OrderedDict[str, dict] = OrderedDict()
    for task in tasks:
        if task["scenario"] in scenarios:
            continue
        scenarios[task["scenario"]] = task

    result = []
    for scenario, task in scenarios.items():
        order = task["call_order"]
        positions = []
        cursor = 0
        for name in order:
            try:
                index = detected_names.index(name, cursor)
            except ValueError:
                positions = []
                break
            positions.append(index)
            cursor = index + 1
        if len(positions) == len(order):
            result.append(
                {
                    "scenario": scenario,
                    "conflict_type": (
                        "commercial_use"
                        if scenario.startswith("C")
                        else "output_content"
                    ),
                    "call_order": order,
                    "detected_order": [detected[index]["id"] for index in positions],
                }
            )
    return result


def scan_log_files(
    log_paths: Iterable[str | Path],
    *,
    source: str = "auto",
    skills_path: str | Path = DEFAULT_SKILLS,
    tasks_path: str | Path = DEFAULT_TASKS,
) -> dict:
    """Scan one or more agent logs and return detected Skill/license evidence."""
    skills = _load_skills(Path(skills_path))
    all_events: list[dict] = []
    errors: list[str] = []
    file_summaries = []

    for raw_path in log_paths:
        path = Path(raw_path)
        events, file_errors = load_log_events(path, source=source)
        for index, event in enumerate(events):
            event["index"] = len(all_events) + index
        all_events.extend(events)
        errors.extend(file_errors)
        file_summaries.append(
            {
                "path": path.as_posix(),
                "events": len(events),
            }
        )

    detected = _match_skills(all_events, skills)
    chains = _known_chains(Path(tasks_path), detected)
    return {
        "files": file_summaries,
        "events": len(all_events),
        "detected_skills": detected,
        "license_sequence": [
            {"id": item["id"], "license": item["license"]} for item in detected
        ],
        "matched_chains": chains,
        "errors": errors,
    }


def render_text(result: dict) -> str:
    lines = [
        f"Files: {len(result['files'])}",
        f"Events: {result['events']}",
        f"Detected Skills: {len(result['detected_skills'])}",
    ]
    for index, skill in enumerate(result["detected_skills"], start=1):
        lines.append(
            f"{index}. {skill['id']} | {skill['license']} | "
            f"first event {skill['first_event']} | matched {skill['matched_text']}"
        )
    if result["matched_chains"]:
        lines.append("Matched chains:")
        for chain in result["matched_chains"]:
            lines.append(
                f"- {chain['scenario']} ({chain['conflict_type']}): "
                + " -> ".join(chain["detected_order"])
            )
    else:
        lines.append("Matched chains: none")
    if result["errors"]:
        lines.append(f"Parse warnings: {len(result['errors'])}")
    return "\n".join(lines)
