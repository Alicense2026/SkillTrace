#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GitHub Topic 搜索采集  [v2.3 / 全量模式 + other 许可证原文下载]
==========================================================
v2.3 变更（相对 v2.2）
----------------------
  1) 改为全量模式：默认 --total 为 0（不限量），--pages 拉满到 10。
  2) 彻底移除单查询页数硬限制，自动顺延直至触及 GitHub 1000 条 API 上限。
  3) 强化 Token 校验：若开启全量模式且未配置 GITHUB_TOKEN，直接拦截退出，
     防止匿名状态下无限等待（匿名核心 API 配额仅 60 次/小时）。

本版**不做 ABC 许可证分级**，只做两件事：
    1) 按 topic 搜 GitHub 仓库 -> 去重 -> 过滤 -> 输出（含每条数据的更新时间）
    2) 许可证"双方法交叉印证"：API 字段（方法一） × 文件名含 license 的文件（方法二）
"""

import argparse
import base64
import csv
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

try:
    from curl_cffi import requests
except ImportError:
    try:
        import requests
    except ImportError:
        sys.exit("缺少依赖: pip install curl_cffi   (或 pip install requests)")


# ============================================================
# 配置
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT = PROJECT_ROOT / "data" / "github"

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_API = os.environ.get("GITHUB_API", "https://api.github.com").rstrip("/")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": UA,
    "Accept": "application/vnd.github.v3+json",
})
if GITHUB_TOKEN:
    SESSION.headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

# ★ 核心 topic：MCP 与 PTM (Pre-Trained Models)
CORE_TOPICS = [
    # MCP
    "mcp in:name,description",
    "mcp-server in:name,description",
    "mcp-client in:name,description",
    "model-context-protocol in:name,description",
    # PTM
    "pretrained in:name,description",
    "foundation-model in:name,description",
    "pretraining in:name,description",
]

SORT_STRATEGIES = [
    ("updated", "desc"),
    ("stars", "desc"),
    ("stars", "asc"),
]

# ★ v2.3: 默认不限总量
DEFAULT_TOTAL_LIMIT = 0
DEFAULT_PER_PAGE = 100
# 100条/页 x 10页 = 1000条，触及单查询上限
DEFAULT_PAGES = 10
MAX_RESULTS_PER_QUERY = 1000

API_WAIT = 2.0 if GITHUB_TOKEN else 7.0

AWESOME_PATTERNS = [r"^awesome[_-]", r"[_-]list$", r"^awesome$"]

# ---- 方法二：文件名含 license 的文件扫描 ----
LICENSE_NAME_RE = re.compile(r"licen[cs]e", re.IGNORECASE)

LICENSE_WAIT = 0.5 if GITHUB_TOKEN else 3.0
LICENSE_CONTENT_MAX_BYTES = 64 * 1024
LICENSE_OTHER_MAX_BYTES = 1024 * 1024
NONASSERTION_LICENSES = {"other", "noassertion", ""}

LICENSE_MAX_CONTENT_FILES = 2
LICENSE_MAX_NAMES = 3
LICENSE_QUOTA_STOP_WAIT = 120

DEFAULT_LICENSE_SCAN = "auto"
DEFAULT_LICENSE_CONTENT = True
DEFAULT_LICENSE_TEXT = True
LICENSE_TEXT_DIR = "license_files_v2"
LICENSE_OTHER_RAW_DIR = "license_other_raw"

SPDX_PATTERNS = (
    ("MIT", (r"\bmit\s+license\b", r"\bpermission is hereby granted\b")),
    ("Apache-2.0", (r"\bapache\s+license\b.*version 2", r"\bapache-2\.0\b")),
    ("GPL-3.0", (r"\bgnu general public license\b.*version 3", r"\bgpl-3\.0\b")),
    ("GPL-2.0", (r"\bgnu general public license\b.*version 2", r"\bgpl-2\.0\b")),
    ("AGPL-3.0", (r"\bgnu affero general public license\b", r"\bagpl-3\.0\b")),
    ("BSD-3-Clause", (r"\bbsd 3-clause\b",)),
    ("BSD-2-Clause", (r"\bbsd 2-clause\b",)),
    ("MPL-2.0", (r"\bmozilla public license\b.*version 2", r"\bmpl-2\.0\b")),
    ("Unlicense", (r"\bthis is free and unencumbered software\b",)),
    ("CC0-1.0", (r"\bcc0\b.*1\.0", r"\bcreative commons zero\b")),
    ("ISC", (r"\bisc license\b",)),
    ("LGPL-3.0", (r"\bgnu lesser general public license\b", r"\blgpl-3\.0\b")),
)

SPDX_ALIASES = {
    "GPL-3.0-ONLY": "GPL-3.0", "GPL-3.0-OR-LATER": "GPL-3.0",
    "GPL-2.0-ONLY": "GPL-2.0", "GPL-2.0-OR-LATER": "GPL-2.0",
    "LGPL-3.0-ONLY": "LGPL-3.0", "LGPL-3.0-OR-LATER": "LGPL-3.0",
    "AGPL-3.0-ONLY": "AGPL-3.0", "AGPL-3.0-OR-LATER": "AGPL-3.0",
    "THE UNLICENSE": "UNLICENSE",
}

CSV_FIELDS = [
    "full_name", "stars", "search_topic", "search_sort",
    "github_updated_at", "github_created_at", "collected_at",
    "description",
    "language", "license_spdx", "found_by_count", "html_url",
    "license_has_api", "license_has_file", "license_file_names",
    "license_file_path", "license_file_source", "license_file_spdx",
    "license_cross_check", "license_spdx_agree",
]

CROSSCHECK_FIELDS = [
    "full_name", "license_spdx", "license_has_api", "license_has_file",
    "license_file_names", "license_file_path", "license_file_source",
    "license_file_spdx", "license_cross_check", "license_spdx_agree",
    "stars", "html_url",
]

DEFAULT_DESC_LIMIT = None


def log(msg=""):
    print(msg, flush=True)


def save_json(data, *path_parts):
    p = Path(OUT, *path_parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(p)


def http_get(url, max_retries=3, accept=None):
    """带退避的 GET。"""
    for attempt in range(max_retries):
        try:
            headers = {}
            if accept:
                headers["Accept"] = accept
            resp = SESSION.get(url, timeout=20, headers=headers)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 30))
                log(f"    [限流 429] 等待 {wait}s")
                time.sleep(wait)
                continue
            if resp.status_code == 403:
                if "rate limit" in resp.text.lower():
                    reset = resp.headers.get("X-RateLimit-Reset")
                    if reset and reset.isdigit():
                        wait = max(int(reset) - int(time.time()) + 1, 5)
                    else:
                        wait = 60
                    log(f"    [限流 403] 等待 {wait}s 直到配额重置")
                    time.sleep(min(wait, 300))
                    continue
                return resp
            return resp
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                log(f"    [请求失败] {e}")
    return None


# ============================================================
# Part 1: Topic 搜索
# ============================================================

def search_topic(topic, sort_by, order, per_page, max_pages,
                 budget=None, budget_pages=None):
    repos = []
    meta = {"requests": 0, "truncated": False, "incomplete": False,
            "total_count": None, "budget": budget, "budget_hit": False}
    
    # 如果不限总量，默认把页数拉满
    if max_pages is None:
        max_pages = MAX_RESULTS_PER_QUERY // per_page

    page_cap = max_pages if budget_pages is None else min(max_pages, budget_pages)
    for page in range(1, page_cap + 1):
        if page * per_page > MAX_RESULTS_PER_QUERY:
            meta["truncated"] = True
            break
        url = (f"{GITHUB_API}/search/repositories?q={quote(topic)}"
               f"&sort={sort_by}&order={order}"
               f"&per_page={per_page}&page={page}")
        resp = http_get(url)
        meta["requests"] += 1
        if resp is None or resp.status_code != 200:
            meta["error"] = f"HTTP {resp.status_code if resp is not None else 'None'}"
            break

        data = resp.json()
        if meta["total_count"] is None:
            meta["total_count"] = data.get("total_count")
        if data.get("incomplete_results"):
            meta["incomplete"] = True

        items = data.get("items", [])
        if not items:
            break

        for item in items:
            if budget is not None and len(repos) >= budget:
                meta["budget_hit"] = True
                break
            lic = item.get("license")
            repos.append({
                "id": item["id"],
                "full_name": item["full_name"],
                "owner": item["owner"]["login"] if item.get("owner") else "",
                "name": item["name"],
                "stars": item["stargazers_count"],
                "language": item.get("language"),
                "description": item.get("description", ""),
                "html_url": item["html_url"],
                "topics": item.get("topics", []),
                "fork": item["fork"],
                "archived": item.get("archived", False),
                "license_spdx": lic["spdx_id"] if lic else None,
                "license_key": lic["key"] if lic else None,
                "github_updated_at": item.get("updated_at"),
                "github_created_at": item.get("created_at"),
                "search_topic": topic,
                "search_sort": f"{sort_by}:{order}",
            })
        if meta["budget_hit"]:
            break
        if len(items) < per_page:
            break
        time.sleep(API_WAIT)
    return repos, meta


def run_search(topics, per_page, max_pages, total_limit=None, save_raw=False,
               desc_limit=None, license_scan=DEFAULT_LICENSE_SCAN,
               license_content=DEFAULT_LICENSE_CONTENT,
               license_text=DEFAULT_LICENSE_TEXT, license_force=False):
    log("=" * 66)
    log("Part 1: GitHub Topic 搜索")
    log(f"  {len(topics)} topics x {len(SORT_STRATEGIES)} sorts x "
        f"{max_pages if max_pages else '极值'} pages x {per_page}/page")
    if total_limit:
        log(f"  ★ 总量上限 {total_limit} 条：取满即停")
    else:
        log(f"  ★ 全量模式：不限量，翻至触及 API 1000 条上限")
    log("=" * 66)

    run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_repos = []
    combos_meta = {}
    total_combos = len(topics) * len(SORT_STRATEGIES)
    combo = 0

    for topic in topics:
        for sort_by, order in SORT_STRATEGIES:
            combo += 1
            key = f"{topic}|{sort_by}:{order}"

            budget = budget_pages = None
            if total_limit:
                remaining = total_limit - len(all_repos)
                if remaining <= 0:
                    log(f"\n[完成] 已达总量上限 {total_limit} 条，停止搜索")
                    return finish(all_repos, combos_meta, topics, per_page,
                                  max_pages, total_limit, run_at, True, save_raw,
                                  desc_limit, license_scan, license_content,
                                  license_text, license_force)
                combos_left = total_combos - combo + 1
                per_combo = max(1, -(-remaining // combos_left))
                budget = min(per_combo, remaining)
                budget_pages = max(1, -(-budget // per_page))

            log(f"\n[{combo}/{total_combos}] topic:{topic} sort={sort_by}:{order}"
                + (f" (预算 {budget} 条 / {budget_pages} 页)" if budget else ""))
            repos, meta = search_topic(topic, sort_by, order, per_page, max_pages,
                                       budget=budget, budget_pages=budget_pages)
            all_repos.extend(repos)
            combos_meta[key] = meta

            flag = ""
            if meta.get("truncated"):
                flag += " [触及1000条上限]"
            if meta.get("incomplete"):
                flag += " [API返回incomplete]"
            if meta.get("budget_hit"):
                flag += " [达本组合预算]"
            if meta.get("error"):
                flag += f" [{meta['error']}]"
            log(f"  -> {len(repos)} 条 (total_count={meta.get('total_count')})"
                f"  累计 {len(all_repos)}/{total_limit or '不限'}{flag}")

            if total_limit and len(all_repos) >= total_limit:
                log(f"\n[完成] 已达总量上限 {total_limit} 条，停止搜索")
                return finish(all_repos, combos_meta, topics, per_page,
                              max_pages, total_limit, run_at, True, save_raw,
                              desc_limit, license_scan, license_content,
                              license_text, license_force)
            time.sleep(API_WAIT)

    return finish(all_repos, combos_meta, topics, per_page, max_pages,
                  total_limit, run_at, False, save_raw, desc_limit,
                  license_scan, license_content, license_text, license_force)


def finish(all_repos, combos_meta, topics, per_page, max_pages,
           total_limit, run_at, stopped_early, save_raw, desc_limit=None,
           license_scan=DEFAULT_LICENSE_SCAN,
           license_content=DEFAULT_LICENSE_CONTENT,
           license_text=DEFAULT_LICENSE_TEXT, license_force=False):
    seen = {}
    for r in all_repos:
        rid = r["id"]
        tag = f"{r['search_topic']}|{r['search_sort']}"
        if rid not in seen:
            seen[rid] = r
            r["_found_by"] = [tag]
        else:
            seen[rid]["_found_by"].append(tag)
            if r["stars"] > seen[rid]["stars"]:
                new = dict(r)
                new["_found_by"] = seen[rid]["_found_by"]
                seen[rid] = new
    unique = sorted(seen.values(), key=lambda x: x["stars"], reverse=True)

    excluded = {"fork": 0, "archived": 0, "awesome_list": 0}
    valid = []
    for r in unique:
        if r["fork"]:
            excluded["fork"] += 1
            continue
        if r["archived"]:
            excluded["archived"] += 1
            continue
        if any(re.search(p, r["name"].lower()) for p in AWESOME_PATTERNS):
            excluded["awesome_list"] += 1
            continue
        r["found_by_count"] = len(r["_found_by"])
        r["collected_at"] = run_at
        valid.append(r)

    log()
    log(f"  原始记录: {len(all_repos)}")
    log(f"  去重后:   {len(unique)}")
    log(f"  有效:     {len(valid)}  "
        f"(排除 fork={excluded['fork']} archived={excluded['archived']} "
        f"awesome={excluded['awesome_list']})")

    license_summary = run_license_crosscheck(
        valid, mode=license_scan, content=license_content, save_text=license_text,
        save_raw=save_raw, run_at=run_at, force_quota=license_force)

    total_requests = sum(m["requests"] for m in combos_meta.values())

    if save_raw:
        save_json({"note": "原始 API 响应快照（用于复核分页与总数）",
                   "run_at": run_at, "per_combo": combos_meta},
                  "raw_api_responses", "search_meta.json")

    save_json({
        "date": run_at,
        "config": {
            "topics": topics, "num_topics": len(topics),
            "sorts": [f"{a}:{b}" for a, b in SORT_STRATEGIES],
            "per_page": per_page, "pages": max_pages,
            "total_limit": total_limit,
            "authenticated": bool(GITHUB_TOKEN),
            "license_scan": license_scan,
            "license_content_sniff": bool(license_content),
            "license_text_archived": bool(license_text),
        },
        "total_raw": len(all_repos),
        "total_unique": len(unique),
        "total_valid": len(valid),
        "total_requests": total_requests,
        "stopped_early_by_limit": stopped_early,
        "excluded": excluded,
        "per_combo": combos_meta,
        "license_crosscheck": license_summary,
        "repos": valid,
    }, "all_repos_v2.json")

    save_json({
        "date": run_at,
        "total_raw": len(all_repos),
        "total_valid": len(valid),
        "total_requests": total_requests,
        "level_distribution": None,
        "note": "全量模式。license_spdx 为 API 原值（方法一）；"
                "license_has_file 等为文件名扫描（方法二）；"
                "license_cross_check 为交叉印证。",
        "license_crosscheck": license_summary,
        "topics": topics,
        "excluded": excluded,
        "stars_range": {
            "max": max((r["stars"] for r in valid), default=None),
            "min": min((r["stars"] for r in valid), default=None),
        },
        "updated_at_range": {
            "newest": max((r["github_updated_at"] or "" for r in valid), default=None),
            "oldest": min((r["github_updated_at"] or "" for r in valid), default=None),
        },
    }, "stats.json")

    write_csv(valid, "github_dataset.csv", desc_limit=desc_limit)
    write_crosscheck_csv(valid, "license_crosscheck.csv")
    write_timestamps(valid, "timestamps.csv")

    log(f"  搜索请求总数: {total_requests}")
    return valid


# ============================================================
# Part 2: 许可证双方法交叉印证
# ============================================================

def identify_spdx_from_text(text):
    head = re.sub(r"\s+", " ", (text or "")[:1500].lower())
    for spdx, pats in SPDX_PATTERNS:
        for p in pats:
            if re.search(p, head):
                return spdx
    return "Other"


def _norm_spdx(value):
    s = str(value or "").strip().upper()
    return SPDX_ALIASES.get(s, s)


def _api_has_license(rec):
    spdx = str(rec.get("license_spdx") or "").strip()
    if not spdx:
        return "no"
    if spdx.upper() in ("NOASSERTION", "OTHER"):
        return "noassertion"
    return "yes"


def _license_path_match(path, fname):
    if LICENSE_NAME_RE.search(fname):
        return "name"
    for seg in str(path).split("/")[:-1]:
        if LICENSE_NAME_RE.search(seg):
            return "dir"
    return ""


LICENSE_NEGATIVE_RE = re.compile(
    r"contributor|(^|[^a-z])cla([^a-z]|$)|copyright|(^|[^a-z])notice([^a-z]|$)"
    r"|third[_-]?party|(^|[^a-z])commercial([^a-z]|$)|enterprise|(^|[^a-z])ee([^a-z]|$)"
    r"|exception|waiver|(^|[^a-z])info([^a-z]|$)|security|(^|[^a-z])todo([^a-z]|$)"
    r"|template|header",
    re.IGNORECASE,
)

LICENSE_STEM_SCORES = (
    ("license", 100), ("licence", 99), ("copying", 90), ("unlicense", 85),
    ("copyright", 10), ("notice", 5),
)

LICENSE_EXT_SCORE = {
    "": 8, ".md": 6, ".markdown": 6, ".txt": 5, ".rst": 3,
    ".html": 1, ".htm": 1,
}

LICENSE_SUFFIX_KEEP_RE = re.compile(r"^\.(lesser|lib)$", re.IGNORECASE)
LICENSE_SUFFIX_DROP_RE = re.compile(
    r"^\.(apache2?|mit|bsd|gplv?[23]|agplv?3|lgplv?[23]|isc|mpl2?|cc0|0bsd|unlicense"
    r"|license|licence|txt|md|markdown|rst|html?)$",
    re.IGNORECASE,
)

def _split_license_name(fname):
    stem, dot, ext = fname.rpartition(".")
    if not dot:
        return fname.lower(), ""
    suffix = ("." + ext).lower()
    if LICENSE_SUFFIX_KEEP_RE.match(suffix):
        return stem.lower(), suffix
    return stem.lower(), suffix

def license_file_score(item):
    path = str(item.get("path") or item.get("name") or "")
    fname = path.rsplit("/", 1)[-1]
    low_name = fname.lower()
    low_stem, suffix = _split_license_name(fname)

    if LICENSE_NEGATIVE_RE.search(low_name):
        return -1000

    score = 0
    for token, pts in LICENSE_STEM_SCORES:
        if low_stem == token or low_stem.startswith(token):
            score = max(score, pts)
    if score == 0:
        return -500

    if LICENSE_SUFFIX_KEEP_RE.match(suffix):
        score -= 40

    score -= path.count("/") * 20

    parent = path.rsplit("/", 1)[0] if "/" in path else ""
    if item.get("matched_by") == "dir" or re.search(r"licen[cs]es?$", parent, re.IGNORECASE):
        score += 15

    if not LICENSE_SUFFIX_KEEP_RE.match(suffix):
        if suffix and not LICENSE_SUFFIX_DROP_RE.match(suffix):
            score -= 25
        else:
            score += LICENSE_EXT_SCORE.get(suffix, 0)

    if re.search(r"[-_](mit|apache|gpl|bsd|isc|mpl|agpl|lgpl|cc0|unlicense)", low_stem):
        score -= 30

    score -= max(0, len(low_stem) - len("license")) * 3

    return score

def sort_license_files(files):
    if not files:
        return files
    return sorted(files, key=license_file_score, reverse=True)


def _entry_meta(entry, via):
    return {
        "name": entry.get("name", ""),
        "path": entry.get("path", entry.get("name", "")),
        "size": entry.get("size"),
        "sha": entry.get("sha"),
        "download_url": entry.get("download_url"),
        "html_url": entry.get("html_url"),
        "via": via,
    }


def _decode_entry_text(entry, max_bytes=LICENSE_CONTENT_MAX_BYTES):
    if entry.get("encoding") != "base64" or not entry.get("content"):
        return None
    size = entry.get("size") or 0
    if size and size > max_bytes:
        return None
    try:
        raw = base64.b64decode(entry["content"])
    except Exception:
        return None
    return raw.decode("utf-8", errors="replace")


def _fetch_license_text(owner, repo, item, meta, api_spdx=None):
    """
    抓取正文。
    如果 api_spdx 为 other/空，则读取上限放宽至 1MB 并落盘到 license_other_raw。
    """
    is_other = str(api_spdx or "").strip().lower() in NONASSERTION_LICENSES
    max_bytes = LICENSE_OTHER_MAX_BYTES if is_other else LICENSE_CONTENT_MAX_BYTES

    size = item.get("size") or 0
    if size and size > max_bytes:
        return None, None

    path = item.get("path") or item.get("name", "")
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{quote(path)}"
    
    resp = http_get(url, accept="application/vnd.github.raw")
    meta["requests"] = meta.get("requests", 0) + 1
    meta["content_requests"] = meta.get("content_requests", 0) + 1
    
    if resp is not None and resp.status_code == 200:
        text = resp.text
        if text:
            if is_other:
                safe_owner = owner.replace("/", "_").strip("_")
                safe_repo = repo.replace("/", "_").strip("_")
                safe_name = item.get("name", "LICENSE").replace("/", "_").strip("_")
                target_dir = Path(OUT) / LICENSE_OTHER_RAW_DIR / safe_owner / safe_repo
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / safe_name
                try:
                    target.write_text(text, encoding="utf-8")
                    item["other_raw_saved"] = str(target.relative_to(OUT))
                except Exception as e:
                    log(f"    [error] 落盘 other license 失败: {e}")
            return text, "api"

    return None, None


def list_license_files(owner, repo, mode="auto", want_content=True, api_spdx=None):
    meta = {"requests": 0, "source": "none", "error": None, "tree_truncated": False,
            "content_requests": 0, "raw_requests": 0}

    def _take_contents():
        url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/"
        resp = http_get(url)
        meta["requests"] += 1
        if resp is None or resp.status_code != 200:
            return []
        entries = resp.json()
        if isinstance(entries, dict):
            entries = [entries]
        out = []
        for e in entries:
            if e.get("type") != "file":
                continue
            matched = _license_path_match(e.get("path", e.get("name", "")), e.get("name", ""))
            if not matched:
                continue
            item = _entry_meta(e, "contents")
            item["matched_by"] = matched
            out.append(item)
        return out

    def _take_tree():
        url = f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"
        resp = http_get(url)
        meta["requests"] += 1
        if resp is None or resp.status_code != 200:
            return []
        data = resp.json()
        meta["tree_truncated"] = bool(data.get("truncated"))
        out = []
        for e in data.get("tree", []):
            if e.get("type") != "blob":
                continue
            path = e.get("path", "")
            fname = path.rsplit("/", 1)[-1]
            matched = _license_path_match(path, fname)
            if not matched:
                continue
            out.append({"name": fname, "path": path, "size": e.get("size"),
                        "sha": e.get("sha"), "download_url": None,
                        "html_url": None, "via": "tree", "matched_by": matched})
        return out

    files = []
    if mode in ("auto", "contents"):
        files = _take_contents()
        if files:
            meta["source"] = "contents"
    if not files and mode in ("auto", "tree"):
        files = _take_tree()
        if files:
            meta["source"] = "tree"

    files = sort_license_files(files)

    if want_content and files:
        for item in files[:LICENSE_MAX_CONTENT_FILES]:
            text, how = _fetch_license_text(owner, repo, item, meta, api_spdx=api_spdx)
            if text:
                item["_text"] = text
                item["text_source"] = how
                item["spdx_from_file"] = identify_spdx_from_text(text)
    return files, meta


def core_quota_state():
    try:
        resp = http_get(f"{GITHUB_API}/rate_limit")
        if resp is None or resp.status_code != 200:
            return None
        core = (resp.json().get("resources") or {}).get("core") or {}
        reset = core.get("reset")
        return {
            "remaining": core.get("remaining"),
            "limit": core.get("limit"),
            "reset_in": max(0, int(reset) - int(time.time()) + 1) if reset else None,
        }
    except Exception:
        return None


def annotate_license_skipped(records, reason):
    for r in records:
        r["license_has_api"] = _api_has_license(r)
        for k in ("license_has_file", "license_file_names", "license_file_path",
                  "license_file_source", "license_file_spdx",
                  "license_cross_check", "license_spdx_agree"):
            r[k] = ""
    return {"enabled": False, "reason": reason,
            "note": "方法二本次未执行：license_file_* / license_cross_check 等列为空，"
                    "license_spdx 仍是 API 原值（方法一）"}


def annotate_license_off(records):
    return annotate_license_skipped(records, "--license-scan off")


def run_license_crosscheck(records, mode=DEFAULT_LICENSE_SCAN, content=True,
                           save_text=True, save_raw=False, run_at=None,
                           force_quota=False):
    if not records:
        return {"enabled": False, "reason": "无有效仓库"}

    if mode == "off":
        log()
        log("Part 2: 许可证双方法交叉印证  ——  已由 --license-scan off 关闭")
        return annotate_license_off(records)

    log()
    log("=" * 66)
    log(f"Part 2: 许可证双方法交叉印证（API 字段 × 文件名匹配）  "
        f"{len(records)} 个仓库")
    log(f"  扫描模式: {mode}   正文识别: {'开' if content else '关'}   "
        f"原文留档: {'开' if save_text else '关'}")
    log("=" * 66)

    quota = core_quota_state()
    if quota:
        log(f"  核心 API 配额: 剩余 {quota.get('remaining')}/{quota.get('limit')}"
            + (f"，{quota['reset_in']}s 后重置" if quota.get("reset_in") is not None else ""))
    if (quota and not force_quota and quota.get("remaining") is not None
            and quota["remaining"] <= 0
            and (quota.get("reset_in") or 0) > LICENSE_QUOTA_STOP_WAIT):
        log(f"  ⚠ 核心 API 配额已用尽且 {quota['reset_in']}s 后才会重置，"
            f"本次跳过方法二（不干等）")
        summary = annotate_license_skipped(records, "core_api_quota_exhausted")
        summary["quota"] = quota
        return summary

    cross_counter = Counter()
    agree_counter = Counter()
    name_counter = Counter()
    stats = {
        "enabled": True, "mode": mode, "content_sniff": bool(content),
        "text_archived": bool(save_text), "repos_scanned": 0,
        "requests": 0, "content_requests": 0, "raw_requests": 0, "errors": 0,
        "quota_before": quota,
        "cross_check": {}, "spdx_agree": {}, "license_file_names_top": {},
        "mismatch_examples": [], "api_only_examples": [], "file_only_examples": [],
        "other_raw_saved": 0,
    }
    raw_payload = {}
    text_dir = Path(OUT, LICENSE_TEXT_DIR)
    total = len(records)

    for i, rec in enumerate(records, 1):
        owner, name = rec.get("owner", ""), rec.get("name", "")
        api_state = _api_has_license(rec)
        api_spdx = rec.get("license_spdx")
        
        files, meta = list_license_files(owner, name, mode=mode,
                                         want_content=content, api_spdx=api_spdx)
        
        stats["repos_scanned"] += 1
        stats["requests"] += meta.get("requests", 0)
        stats["content_requests"] += meta.get("content_requests", 0)
        stats["raw_requests"] += meta.get("raw_requests", 0)
        if meta.get("error"):
            stats["errors"] += 1

        file_spdx = ""
        read_any_text = False
        for f in files:
            if "spdx_from_file" in f:
                read_any_text = True
            if f.get("other_raw_saved"):
                stats["other_raw_saved"] += 1
                
            spdx = f.get("spdx_from_file") or ""
            if spdx and (not file_spdx or file_spdx == "Other"):
                file_spdx = spdx
            if save_text and f.get("_text"):
                safe = re.sub(r"[^A-Za-z0-9._-]", "_", f.get("name", ""))[:60]
                target = text_dir / f"{owner}_{name}_{safe}"[:180]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f["_text"], encoding="utf-8")
                f["text_saved"] = str(target)
            f.pop("_text", None)

        if api_state == "yes" and files:
            cross = "both"
        elif api_state == "yes":
            cross = "api_only"
        elif files:
            cross = "file_only"
        else:
            cross = "neither"

        agree = ""
        if files and content and read_any_text:
            if not file_spdx or file_spdx == "Other":
                agree = "file_unknown"
            elif api_state == "yes":
                agree = ("match" if _norm_spdx(file_spdx)
                         == _norm_spdx(rec.get("license_spdx")) else "mismatch")
            else:
                agree = "api_absent"

        rec["license_has_api"] = api_state
        rec["license_has_file"] = "yes" if files else "no"
        rec["license_file_names"] = "|".join(
            f["name"] for f in files[:LICENSE_MAX_NAMES])
        rec["license_file_path"] = files[0]["path"] if files else ""
        rec["license_file_source"] = meta.get("source", "none") if files else ""
        rec["license_file_spdx"] = file_spdx
        rec["license_cross_check"] = cross
        rec["license_spdx_agree"] = agree
        rec["license_files"] = files
        rec["license_scan_meta"] = meta
        rec["license_checked_at"] = run_at

        cross_counter[cross] += 1
        agree_counter[agree or "n/a"] += 1
        for f in files[:LICENSE_MAX_NAMES]:
            name_counter[f["name"].lower()] += 1
        if cross == "api_only" and len(stats["api_only_examples"]) < 10:
            stats["api_only_examples"].append({
                "full_name": rec.get("full_name"),
                "api_spdx": rec.get("license_spdx"),
                "file_names": rec["license_file_names"],
                "scan": meta.get("source"),
            })
        if cross == "file_only" and len(stats["file_only_examples"]) < 10:
            stats["file_only_examples"].append({
                "full_name": rec.get("full_name"),
                "file_names": rec["license_file_names"],
                "file_spdx": file_spdx,
                "scan": meta.get("source"),
            })
        if agree == "mismatch" and len(stats["mismatch_examples"]) < 10:
            stats["mismatch_examples"].append({
                "full_name": rec.get("full_name"),
                "api_spdx": rec.get("license_spdx"),
                "file_spdx": file_spdx,
                "file_names": rec["license_file_names"],
            })

        if save_raw:
            raw_payload[rec.get("full_name", f"#{i}")] = {
                "api_spdx": rec.get("license_spdx"),
                "api_state": api_state,
                "cross_check": cross,
                "spdx_agree": agree,
                "meta": meta,
                "files": files,
            }

        if i % 25 == 0 or i == total:
            log(f"  [{i}/{total}] both={cross_counter['both']} "
                f"api_only={cross_counter['api_only']} "
                f"file_only={cross_counter['file_only']} "
                f"neither={cross_counter['neither']}  "
                f"请求={stats['requests']}")
        last = (i == total)
        if not last and meta.get("requests"):
            time.sleep(LICENSE_WAIT)

    stats["cross_check"] = dict(cross_counter)
    stats["spdx_agree"] = dict(agree_counter)
    stats["license_file_names_top"] = dict(name_counter.most_common(15))

    for k in ("both", "api_only", "file_only", "neither"):
        stats["cross_check"].setdefault(k, 0)
    for k in ("match", "mismatch", "file_unknown", "api_absent", "n/a"):
        stats["spdx_agree"].setdefault(k, 0)

    log()
    log("  交叉印证结果（方法一 API 字段  ×  方法二 文件名匹配）:")
    log(f"    both      API 有标注 且 有 license 文件 : {stats['cross_check']['both']}")
    log(f"    api_only  仅 API 标注（文件缺失，可疑）: {stats['cross_check']['api_only']}")
    log(f"    file_only 仅文件命中（API 漏检/未识别）: {stats['cross_check']['file_only']}")
    log(f"    neither   两边都没有                  : {stats['cross_check']['neither']}")
    if content:
        log(f"    SPDX 对撞: match={stats['spdx_agree']['match']} "
            f"mismatch={stats['spdx_agree']['mismatch']} "
            f"file_unknown={stats['spdx_agree']['file_unknown']} "
            f"api_absent={stats['spdx_agree']['api_absent']}")
    log(f"    ★ 下载 other 原文: {stats['other_raw_saved']} 份")
    log(f"    额外核心 API 请求: {stats['requests']}"
        f"（其中抓正文 {stats['content_requests']}）"
        f"   raw 兜底请求: {stats['raw_requests']}   失败: {stats['errors']}")
    
    if save_raw:
        save_json({"note": "方法二（文件名含 license 的文件）逐仓库扫描明细",
                   "run_at": run_at, "mode": mode,
                   "summary": stats, "repos": raw_payload},
                  "raw_api_responses", "license_scan.json")
    return stats


def _cell(r, key, desc_limit=None):
    v = r.get(key)
    if v is None:
        return ""
    v = str(v)
    if key == "description":
        v = re.sub(r"\s+", " ", v).strip()
        if desc_limit:
            v = v[:desc_limit]
    return v


def write_csv(records, filename, desc_limit=None):
    path = Path(OUT, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow({k: _cell(r, k, desc_limit) for k in CSV_FIELDS})
    tmp.replace(path)
    log(f"  已写出 {filename}  ({len(records)} 行, {len(CSV_FIELDS)} 列"
        + (f", description 截断到 {desc_limit}" if desc_limit else ", description 不截断")
        + f", 含 {len(CSV_FIELDS) - 12} 个许可证双方法列)")
    return path


def write_crosscheck_csv(records, filename="license_crosscheck.csv"):
    order = {"file_only": 0, "api_only": 1, "both": 2, "neither": 3, "": 4}
    rows = sorted(records,
                  key=lambda r: (order.get(str(r.get("license_cross_check", "")), 9),
                                 -(r.get("stars") or 0)))
    path = Path(OUT, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CROSSCHECK_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: _cell(r, k) for k in CROSSCHECK_FIELDS})
    tmp.replace(path)
    log(f"  已写出 {filename}  ({len(rows)} 行, 许可证双方法对照表)")
    return path


def write_timestamps(records, filename):
    fields = ["full_name", "github_updated_at", "github_created_at", "collected_at"]
    path = Path(OUT, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})
    log(f"  已写出 {filename}  ({len(records)} 行)")
    return path


# ============================================================
# CLI
# ============================================================

def cmd_dry_run(topics, per_page, max_pages, total_limit, license_scan):
    combos = len(topics) * len(SORT_STRATEGIES)
    requests_est = combos * max_pages if not total_limit else min(combos, total_limit)

    log("Dry-run：不发出任何请求")
    log(f"  目录        {OUT}")
    log(f"  认证        {'GITHUB_TOKEN 已设置' if GITHUB_TOKEN else '匿名（搜索 10 次/分钟，核心 API 60 次/小时）'}")
    log(f"  topics      {len(topics)} 个")
    log(f"  排序        {len(SORT_STRATEGIES)} 种")
    log(f"  翻页上限    {max_pages} 页 x {per_page} 条/页")
    log(f"  组合数      {combos}")
    log()
    log(f"  ★ 总量上限  {total_limit if total_limit else '不限'} 条")
    log(f"  搜索请求    约 {requests_est} 次"
        f"（最小耗时约 {requests_est*API_WAIT/60:.1f} 分钟）")
    log()
    log(f"  许可证方法一: API 字段 license_spdx")
    if license_scan == "off":
        log(f"  许可证方法二: 已关闭（--license-scan off）")
    else:
        n = total_limit or "去重后有效仓库数"
        log(f"  许可证方法二: 文件名含 license/licence 的文件扫描，mode={license_scan}")
        log(f"                开跑前会查 /rate_limit，并额外下载 other/空 的许可证原文")
    log()
    log("  确认后执行: python scripts/collect_github.py")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="GitHub Topic 搜索 v2.3（全量模式 + other 原文下载）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="只算请求量，不发请求")
    ap.add_argument("--total", type=int, default=DEFAULT_TOTAL_LIMIT,
                    help=f"总量上限（原始记录数），默认 {DEFAULT_TOTAL_LIMIT}（不限量）")
    ap.add_argument("--per-page", type=int, default=DEFAULT_PER_PAGE,
                    help=f"每页条数（默认 {DEFAULT_PER_PAGE}，上限 100）")
    ap.add_argument("--pages", type=int, default=DEFAULT_PAGES,
                    help=f"每个 query 最多翻页数（默认 {DEFAULT_PAGES}，填0则自动顺延至1000条上限）")
    ap.add_argument("--topics", type=str, default=None,
                    help="逗号分隔的自定义 topic 列表（覆盖默认列表）")
    ap.add_argument("--no-raw", action="store_true", help="不保存原始 API 响应元数据")
    ap.add_argument("--from-json", action="store_true",
                    help="不发请求，直接读 all_repos_v2.json 重建 CSV")
    ap.add_argument("--desc-limit", type=int, default=DEFAULT_DESC_LIMIT,
                    help="description 截断长度；默认不截断（0 也表示不截断）")
    ap.add_argument("--license-scan", choices=["auto", "contents", "tree", "off"],
                    default=DEFAULT_LICENSE_SCAN,
                    help="方法二扫描方式，默认 auto")
    ap.add_argument("--no-license-content", dest="license_content",
                    action="store_false",
                    help="不解析正文（只按文件名交叉印证）")
    ap.add_argument("--no-license-text", dest="license_text", action="store_false",
                    help="不留档命中文件的原文")
    ap.add_argument("--license-force", dest="license_force", action="store_true",
                    help="忽略核心 API 配额预检")
    ap.set_defaults(license_content=DEFAULT_LICENSE_CONTENT,
                    license_text=DEFAULT_LICENSE_TEXT,
                    license_force=False)
    args = ap.parse_args()

    if args.from_json:
        src = OUT / "all_repos_v2.json"
        if not src.exists():
            log(f"[--from-json] 找不到 {src}，请先跑一次采集。")
            return 1
        payload = json.loads(src.read_text(encoding="utf-8"))
        valid = payload.get("repos", [])
        if not valid:
            log("[--from-json] all_repos_v2.json 里没有 repos 数据。")
            return 1
        desc_limit = args.desc_limit if args.desc_limit and args.desc_limit > 0 else None
        log(f"[--from-json] 读入 {len(valid)} 条，不发请求，只重建 CSV")
        for r in valid:
            if str(r.get("license_has_api") or "") == "":
                r["license_has_api"] = _api_has_license(r)
        write_csv(valid, "github_dataset.csv", desc_limit=desc_limit)
        write_crosscheck_csv(valid, "license_crosscheck.csv")
        write_timestamps(valid, "timestamps.csv")
        return 0

    topics = ([t.strip() for t in args.topics.split(",") if t.strip()]
              if args.topics else list(CORE_TOPICS))
    per_page = max(1, min(args.per_page, 100))
    # 如果传0或者None，则置为None，让 search_topic 自动满额
    pages = args.pages if (args.pages and args.pages > 0) else None
    
    # 如果不限总量，强制提醒 Token 要求
    if not args.total and not GITHUB_TOKEN:
        log("  [X] 配置错误：在不限总量的情况下，必须配置环境变量 GITHUB_TOKEN。")
        log("      否则匿名状态下搜索 API 只有 10 次/分钟，核心 API 只有 60 次/小时，")
        log("      下载许可证将耗时几十小时甚至被反复限流中断。")
        return 1

    total_limit = args.total if args.total and args.total > 0 else None
    desc_limit = args.desc_limit if args.desc_limit and args.desc_limit > 0 else None

    if args.dry_run:
        return cmd_dry_run(topics, per_page, pages or 10, total_limit, args.license_scan)

    OUT.mkdir(parents=True, exist_ok=True)

    log()
    log("#" * 66)
    log("# GitHub Topic 搜索 v2.3（全量模式 + other 原文）")
    log(f"# 输出: {OUT}")
    log(f"# 总量上限: {total_limit if total_limit else '不限（全量）'}")
    log(f"# description: {'不截断' if not desc_limit else f'截断到 {desc_limit} 字符'}")
    log("#" * 66)

    repos = run_search(topics, per_page, pages, total_limit=total_limit,
                       save_raw=not args.no_raw, desc_limit=desc_limit,
                       license_scan=args.license_scan,
                       license_content=args.license_content,
                       license_text=args.license_text,
                       license_force=args.license_force)

    if not repos:
        log("\n  未搜到任何仓库。请检查网络与 GITHUB_TOKEN。")
        return 1

    log()
    log("=" * 66)
    log(f"完成。输出目录: {OUT}")
    log("  数据集:     github_dataset.csv")
    log("  许可证对照: license_crosscheck.csv")
    log("  时间对照:   timestamps.csv")
    log("  明细:       all_repos_v2.json / stats.json")
    log(f"  other 原文: {LICENSE_OTHER_RAW_DIR}/")
    log("=" * 66)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("\n已中断。")
        sys.exit(130)
