#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
HuggingFace Topic 搜索采集  [v2.4 / 默认全量模式]
==============================================================
v2.4 变更（相对 v2.3）
----------------------
  1) 对 license_spdx ∈ {other, unknown, unspecified} 的模型，
     除常规正文摘录外，额外把 LICENSE 原文完整下载到
     HuggingFace_Topic_Search/v1/license_other_raw/<model_id>/<license_file>。
  2) CSV 新增 license_raw_path 列（相对输出目录的路径）。
  3) stats 新增 license_other_raw_saved / license_other_raw_failed 计数。

v2.2 变更（相对 v2.1）
----------------------
  1) 修复 AttributeError: 'dict' object has no attribute 'headers'。
     原因：search_topic 里调 has_next_page({}, ...) 传了空字典，
     而 has_next_page 期望拿到带 .headers 的 resp 对象。
     修法：
       - _try_get_json() 返回值改为 (items, resp) 二元组
       - search_topic() 三处调用同步解包，把真 resp 传给 has_next_page
       - has_next_page() 加 resp is None / hasattr 防御

v2.1 变更（相对 v2.0）
----------------------
  1) 默认不限总量：DEFAULT_TOTAL_LIMIT 从 30 改为 0。
  2) --total 仍可用。
  3) dry-run 提示更新。

v2.0 变更（相对 v1.9）
----------------------
  1) 全量模式：--total 0 时不再受小上限限制。
  2) topic 列表补全。
  3) 新增 --resume：断点续跑。
  4) 新增 --max-requests：整体请求数硬上限。
  5) --pages 默认 50。
  6) 新增 --no-detail / --no-readme / --no-license-body。
  7) 新增 --shard N/M：分片并行。

v1.9 变更（相对 v1.8）
----------------------
  1) 新增两列：license_name / license_link（来自 cardData）。

v1.8 变更（相对 v1.7）
----------------------
  1) 删除 SPDX 规则匹配逻辑。
  2) 新增 license_body_excerpt 列。
  3) license_cross_check 保持四分类。

v1.7 变更（相对 v1.6）
----------------------
  1) 删除"从文件名推断 SPDX"的逻辑。
  2) 删除 license_spdx_agree 列。

v1.6 变更（相对 v1.5）
----------------------
  1) description 改为从 README.md 正文提取。

v1.5 变更（相对 v1.4）
----------------------
  1) 新增 description 列。

v1.4 变更（相对 v1.3）
----------------------
  1) LICENSE 正文读取默认开启。
  2) 删除 license_body_snippet 列。

v1.3 变更（相对 v1.2）
----------------------
  1) 对 license_has_file=yes 的模型，额外发一次请求拿 LICENSE 正文。

v1.2 变更（相对 v1.1）
----------------------
  1) 新增 is_language_code_false_positive()，过滤语言码误抓。
  2) 可疑记录单独写 lang_code_suspects.csv。

v1.1 变更（相对 v1.0）
----------------------
  1) 新增 probe_sorts()，400 降级重试。
  2) --total 默认值从 10 提到 30。
"""

import argparse
import csv
import json
import os
import re
import socket
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlparse

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
OUT = PROJECT_ROOT / "data" / "hf"
RESUME_FILE = OUT / "_resume.json"

# ★ v2.4: license=other/unknown/unspecified 的模型，LICENSE 原文单独落盘目录
LICENSE_OTHER_RAW_DIR = OUT / "license_other_raw"
LICENSE_OTHER_MAX_BYTES = 1024 * 1024   # 1 MB，正常许可证远小于此，基本不截断
NONASSERTION_LICENSES = {"other", "unknown", "unspecified"}

HF_TOKEN = os.environ.get("HF_TOKEN", "")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36"

ENDPOINT_CANDIDATES = [
    "https://huggingface.co",
    "https://hf-mirror.com",
]

TOPIC_GROUPS = {
    "mcp": [
        {"token": "mcp"},
        {"token": "mcp-server"},
        {"token": "mcp-client"},
        {"token": "model-context-protocol"},
    ],
    "ptm": [
        {"token": "pretrained"},
        {"token": "foundation-model"},
        {"token": "pretraining"},
        {"token": "from-scratch"},
        {"token": "pretrain"},
    ],
}

SORT_STRATEGIES = [
    ("downloads", "desc"),
    ("lastModified", "desc"),
    ("likes", "asc"),
]

# ★ v2.1: 默认不限总量
DEFAULT_TOTAL_LIMIT = 0
DEFAULT_PER_PAGE = 100
# ★ v2.3: 0 = 不限页数（一直翻到没有下一页游标为止）。
#   旧值 50 会让每个 tag x sort 组合最多只取 50 x 100 = 5000 条，
#   看似很大，但配合"不跟随游标"的旧 bug 实际只能拿到 100 条。
#   现在游标修好了，0 才是真正的不限量。
DEFAULT_MAX_PAGES = 0
HF_MAX_LIMIT = 1000

API_WAIT = 1.0 if HF_TOKEN else 1.5
DETAIL_WAIT = 0.4 if HF_TOKEN else 0.8
BODY_WAIT = 0.5 if HF_TOKEN else 1.0
README_WAIT = 0.5 if HF_TOKEN else 1.0
LICENSE_BODY_MAX_BYTES = 200 * 1024
README_BODY_MAX_BYTES = 300 * 1024
DESCRIPTION_MAX_LEN = 800
LICENSE_EXCERPT_MAX_LEN = 2000

LICENSE_NAME_RE = re.compile(r"licen[cs]e", re.IGNORECASE)
LICENSE_MAX_NAMES = 3
DEFAULT_DETAIL_LIMIT = 0
ALLOW_SINGLE_MODEL_FETCH = True

SPDX_KNOWN = {
    "apache-2.0", "mit", "bsd-2-clause", "bsd-3-clause", "bsd-3-clause-clear",
    "bsd-4-clause", "gpl-2.0", "gpl-3.0", "lgpl-2.1", "lgpl-3.0", "agpl-3.0",
    "mpl-2.0", "isc", "unlicense", "cc0-1.0", "cc-by-4.0", "cc-by-sa-4.0",
    "cc-by-nc-4.0", "cc-by-nc-sa-4.0", "cc-by-nd-4.0", "cc-by-nc-nd-4.0",
    "epl-2.0", "eupl-1.2", "artistic-2.0", "zlib", "postgresql", "python-2.0",
    "odbl-1.0", "cddl-1.0", "wtfpl", "beerware", "0bsd", "bsl-1.1",
    "openrail", "openrail++", "bigscience-openrail-m", "creativeml-openrail-m",
    "bigcode-openrail-m", "llama2", "llama3", "llama3.1", "llama3.2", "llama4",
    "gemma", "cc-by-nc-3.0", "ncsa", "ms-pl", "osl-3.0", "apl-1.0",
}
SPDX_NONASSERTION = {"other", "unknown", "unspecified"}

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
LICENSE_NEGATIVE_RE = re.compile(
    r"contributor|(^|[^a-z])cla([^a-z]|$)|copyright|(^|[^a-z])notice([^a-z]|$)"
    r"|third[_-]?party|(^|[^a-z])commercial([^a-z]|$)|enterprise|(^|[^a-z])ee([^a-z]|$)"
    r"|exception|waiver|(^|[^a-z])info([^a-z]|$)|security|(^|[^a-z])todo([^a-z]|$)"
    r"|template|header",
    re.IGNORECASE,
)

# ---- v1.2: 语言码假阳性识别 ----
NON_GENERATIVE_PIPELINE_TAGS = {
    "fill-mask",
    "text-classification",
    "token-classification",
    "language-identification",
    "feature-extraction",
    "sentence-similarity",
    "automatic-speech-recognition",
    "audio-classification",
    "image-classification",
    "tabular-classification",
}
LANG_CODE_TAGS_THRESHOLD = 100
SHORT_TOKEN_TOPICS = {"mcp", "ptm", "mcp-server", "mcp-client"}

CSV_FIELDS = [
    "model_id", "downloads", "search_topic", "search_sort",
    "hf_last_modified", "hf_created_at", "collected_at",
    "tags_count", "pipeline_tag", "description",
    "license_spdx",
    "license_name", "license_link",
    "found_by_count", "hf_url",
    "license_has_api", "license_has_file", "license_file_names",
    "license_file_path", "license_file_source",
    "license_cross_check",
    "license_body_excerpt",
    "license_raw_path",            # ★ v2.4: license=other 的原文落盘相对路径
    "matched_by", "likes", "trending_score", "library_name", "gated",
]

CROSSCHECK_FIELDS = [
    "model_id", "downloads", "likes", "license_spdx",
    "license_name", "license_link",
    "gated",
    "description",
    "license_has_api", "license_has_file", "license_file_names",
    "license_file_path", "license_file_source",
    "license_cross_check",
    "license_body_excerpt",
    "license_raw_path",            # ★ v2.4
    "matched_by",
]

SUSPECT_FIELDS = [
    "model_id", "downloads", "search_topic", "tags_count",
    "pipeline_tag", "license_spdx", "filter_note", "hf_url",
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


# ============================================================
# 端点探测
# ============================================================

def tcp_alive(host, port=443, timeout=6):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def pick_endpoint(explicit=None, verbose=True):
    tried = []
    candidates = []
    if explicit:
        candidates.append(explicit)
    if os.environ.get("HF_ENDPOINT"):
        candidates.append(os.environ["HF_ENDPOINT"])
    candidates += ENDPOINT_CANDIDATES

    seen = set()
    for url in candidates:
        url = url.rstrip("/")
        if url in seen:
            continue
        seen.add(url)
        host = urlparse(url).netloc
        ok = tcp_alive(host)
        tried.append((url, ok))
        if verbose:
            log(f"  [端点探测] {url:<32} TCP443 {'可达' if ok else '不通'}")
        if ok:
            return url, tried
    return None, tried


# ============================================================
# HTTP
# ============================================================

def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})
    if HF_TOKEN:
        s.headers["Authorization"] = f"Bearer {HF_TOKEN}"
    return s


SESSION = None
REQUEST_COUNT = 0

# ---- 配额感知（v2.3 新增）----
# HF 官方 API 的固定窗口配额实测为 500 请求 / 300 秒
# （响应头 ratelimit-policy: "fixed window";"api";q=500;w=300）。
# 不限量采集很容易撞上，所以这里主动读 ratelimit 头：
#   剩余很少时提前慢下来；真被 429 就按窗口重置时间等待。
# 每次调用都按这个秒数重取一次配额，避免复用过期的读数。
RATE_CACHE_TTL = 60.0
_rate_cache = {"checked_at": 0.0, "remaining": None, "reset": None, "limit": None}
_429_retries = 0
MAX_429_RETRIES = 4


def _note_rate(resp):
    """解析响应头，记录剩余配额与窗口重置时刻。"""
    if resp is None or not hasattr(resp, "headers"):
        return
    rl = resp.headers.get("ratelimit") or resp.headers.get("RateLimit") or ""
    pol = (resp.headers.get("ratelimit-policy")
           or resp.headers.get("RateLimit-Policy") or "")
    now = time.time()
    m = re.search(r'r=(\d+)', rl)
    if m:
        _rate_cache["remaining"] = int(m.group(1))
    t = re.search(r't=(\d+)', rl)
    if t:
        _rate_cache["reset"] = now + int(t.group(1))
    q = re.search(r'q=(\d+)', pol)
    if q:
        _rate_cache["limit"] = int(q.group(1))
    if m or q:
        _rate_cache["checked_at"] = now


def _rate_throttle():
    """剩余配额不多时主动降速，避免撞 429。"""
    rem = _rate_cache.get("remaining")
    lim = _rate_cache.get("limit")
    if rem is None or not lim:
        return
    if rem <= 5:
        log(f"    [配额] 剩余 {rem}/{lim}，等待 30s 以放缓请求")
        time.sleep(30)
    elif rem <= 20:
        time.sleep(5)


def _rate_wait_for_reset():
    """429 时按配额窗口重置时间等待，拿不到就用 Retry-After 兜底。"""
    reset = _rate_cache.get("reset")
    if reset:
        wait = int(reset - time.time()) + 2
    else:
        wait = 30
    return max(5, min(wait, 360))


def http_get(url, max_retries=3, timeout=25, stream=False, max_bytes=None):
    global REQUEST_COUNT, _429_retries
    REQUEST_COUNT += 1
    if MAX_REQUESTS and REQUEST_COUNT > MAX_REQUESTS:
        raise RuntimeError(f"已达 --max-requests 上限 {MAX_REQUESTS}，停止")
    _rate_throttle()
    for attempt in range(max_retries):
        try:
            if stream:
                resp = SESSION.get(url, timeout=timeout, stream=True,
                                   allow_redirects=True)
            else:
                resp = SESSION.get(url, timeout=timeout)
            _note_rate(resp)
            if resp.status_code == 429:
                if _429_retries >= MAX_429_RETRIES:
                    log(f"    [限流 429] 已重试 {_429_retries} 次仍被限，放弃本次请求")
                    return resp
                _429_retries += 1
                ra = resp.headers.get("Retry-After")
                wait = int(ra) if (ra and str(ra).isdigit()) else _rate_wait_for_reset()
                log(f"    [限流 429] 第 {_429_retries}/{MAX_429_RETRIES} 次，"
                    f"等待 {wait}s（配额窗口重置）")
                time.sleep(wait)
                continue
            if resp.status_code in (500, 502, 503, 504):
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
            return resp
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                log(f"    [请求失败] {e}")
    return None


def _read_stream_text(resp, max_bytes):
    chunks = []
    total = 0
    truncated = False
    try:
        for chunk in resp.iter_content(chunk_size=8192):
            if not chunk:
                continue
            if total + len(chunk) > max_bytes:
                chunks.append(chunk[:max_bytes - total])
                truncated = True
                break
            chunks.append(chunk)
            total += len(chunk)
            if total >= max_bytes:
                truncated = True
                break
    except Exception:
        return None, total, truncated
    finally:
        try:
            resp.close()
        except Exception:
            pass

    raw = b"".join(chunks)
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc), len(raw), truncated
        except UnicodeDecodeError:
            continue
    return None, len(raw), truncated


# ★ v2.3: 新增 next_cursor_url —— 真正跟随游标翻页
#   HF 的 /api/models 是**游标分页**：响应头 Link: <...&cursor=xxx>; rel="next"。
#   返回的是下一页的完整 URL，必须拿它去请求才能翻页。
#   [!] 两个坑：
#     1) Link 头里的域名是 huggingface.co（官方），而我们可能走 hf-mirror.com，
#        所以必须把域名换回当前端点，否则会绕回被墙的官方域名。
#     2) 旧版只判断"有没有 next 链接"，却始终用同一个 URL 请求，
#        导致每一页都拿到第 1 页的数据 —— 采集量永远卡在 limit 条。
def next_cursor_url(resp, endpoint):
    """从 Link 头解析 rel="next" 的 URL，并把域名换回当前端点。"""
    if resp is None or not hasattr(resp, "headers"):
        return None
    link = resp.headers.get("Link") or resp.headers.get("link") or ""
    if not link:
        return None
    m = re.search(r'<([^>]+)>\s*;\s*rel="next"', link)
    if not m:
        return None
    nxt = m.group(1).strip()
    # 把 Link 里的官方域名换成当前端点，其余参数（含 cursor）原样保留
    if endpoint:
        nxt = re.sub(r'^https?://[^/]+', endpoint.rstrip("/"), nxt)
    return nxt


# ★ v2.2: 加防御，resp 为 None 时按"本页装满"保守判断
# ★ v2.3: 只有拿到真实 next 游标才认为有下一页。
#   Link 头缺失时**不再**用 count >= limit 猜测 —— 那会让脚本在
#   没有下一页时也空转请求，白耗配额（HF 官方配额仅 500 请求/5 分钟）。
def has_next_page(resp, count, limit, endpoint=None):
    if next_cursor_url(resp, endpoint) is not None:
        return True
    if resp is None or not hasattr(resp, "headers"):
        return count >= limit
    return False


# ============================================================
# sort 能力探测
# ============================================================

def probe_sorts(endpoint, token="mcp", verbose=True):
    available = []
    if verbose:
        log("  [sort 探测] 检查当前端点支持的排序组合：")
    for sort_by, direction in SORT_STRATEGIES:
        url = (f"{endpoint}/api/models?limit=1"
               f"&filter={quote(token)}&sort={sort_by}&direction={direction}")
        resp = http_get(url, max_retries=1)
        ok = resp is not None and resp.status_code == 200
        if not ok and resp is not None and resp.status_code == 400:
            url2 = (f"{endpoint}/api/models?limit=1"
                    f"&filter={quote(token)}&sort={sort_by}")
            resp2 = http_get(url2, max_retries=1)
            if resp2 is not None and resp2.status_code == 200:
                ok = True
                if verbose:
                    log(f"    {sort_by}:{direction:<4} → 仅支持不带 direction（已自动降级）")
        if ok:
            available.append((sort_by, direction))
            if verbose and not (resp is not None and resp.status_code == 400):
                log(f"    {sort_by}:{direction:<4} → OK")
        else:
            code = resp.status_code if resp is not None else "None"
            if verbose:
                log(f"    {sort_by}:{direction:<4} → HTTP {code}，剔除")
    if not available:
        if verbose:
            log("    [!] 所有 sort 都探测失败，回退到默认列表（后续靠 400 降级重试）")
        return list(SORT_STRATEGIES)
    return available


# ============================================================
# 标签校验
# ============================================================

def extract_license_from_tags(tags):
    for t in tags or []:
        if isinstance(t, str) and t.lower().startswith("license:"):
            return t.split(":", 1)[1].strip().lower() or None
    return None


def verify_tags(tags, token):
    low = [str(t).lower() for t in (tags or [])]
    tok = token.lower()
    if tok in low:
        return True, "tag"
    for t in low:
        if t.startswith(tok + "-") or t.endswith("-" + tok) or t == tok:
            return True, "tag_variant"
    for t in low:
        if ":" in t and t.split(":", 1)[1] == tok:
            return True, "tag_ns"
    return False, ""


LANGUAGE_CODE_RE = re.compile(r"^[a-z]{2,3}$")


def is_probably_language_code(tag):
    return bool(LANGUAGE_CODE_RE.match(str(tag)))


# ============================================================
# v1.2: 语言码假阳性识别
# ============================================================

def is_language_code_false_positive(rec):
    topic = str(rec.get("search_topic") or "").lower()
    tags_count = rec.get("tags_count") or 0
    pipe = str(rec.get("pipeline_tag") or "").lower()

    if topic not in SHORT_TOKEN_TOPICS:
        return False, ""
    if tags_count <= LANG_CODE_TAGS_THRESHOLD:
        return False, ""
    if pipe not in NON_GENERATIVE_PIPELINE_TAGS:
        return False, ""

    return True, (f"短 token '{topic}' + tags_count={tags_count} + "
                  f"pipeline_tag='{pipe}' → 疑似 ISO 639 语言码误抓")


# ============================================================
# v1.3: LICENSE 正文读取
# ============================================================

def fetch_license_body(model_id, filename):
    meta = {"requests": 1, "error": None, "bytes": 0, "truncated": False}
    url = f"{ENDPOINT}/{quote(model_id)}/resolve/main/{quote(filename)}"
    resp = http_get(url, stream=True, max_bytes=LICENSE_BODY_MAX_BYTES)
    if resp is None or resp.status_code != 200:
        meta["error"] = f"HTTP {resp.status_code if resp is not None else 'None'}"
        return None, meta
    text, nbytes, truncated = _read_stream_text(resp, LICENSE_BODY_MAX_BYTES)
    meta["bytes"] = nbytes
    meta["truncated"] = truncated
    if text is None:
        meta["error"] = "正文编码无法解码"
    return text, meta


# ============================================================
# v2.4: license=other/unknown 的 LICENSE 原文单独下载
# ============================================================

def download_license_raw(model_id, filename):
    """把 LICENSE 文件原样完整下载到 license_other_raw/<model_id>/<filename>。

    与 fetch_license_body 的区别：
      - 不截断（上限调到 1 MB，正常许可证文件远小于此）；
      - 直接落盘为原始文件，保留换行/编码原貌，方便人工核验；
      - 返回落盘路径 + 元数据。
    返回 (saved_path or None, meta)
    """
    meta = {"requests": 1, "error": None, "bytes": 0,
            "truncated": False, "saved_path": None}

    # model_id 形如 "org/name"，直接作为目录层级；对路径分隔符做清洗
    safe_id = model_id.replace("\\", "/").strip("/")
    safe_name = filename.replace("\\", "/").strip("/")
    dest = LICENSE_OTHER_RAW_DIR / safe_id / safe_name
    dest.parent.mkdir(parents=True, exist_ok=True)

    url = f"{ENDPOINT}/{quote(model_id)}/resolve/main/{quote(filename)}"
    resp = http_get(url, stream=True, max_bytes=LICENSE_OTHER_MAX_BYTES)
    if resp is None or resp.status_code != 200:
        meta["error"] = f"HTTP {resp.status_code if resp is not None else 'None'}"
        return None, meta

    text, nbytes, truncated = _read_stream_text(resp, LICENSE_OTHER_MAX_BYTES)
    meta["bytes"] = nbytes
    meta["truncated"] = truncated
    if text is None:
        meta["error"] = "正文编码无法解码"
        return None, meta

    try:
        with open(dest, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    except Exception as e:
        meta["error"] = f"落盘失败: {e}"
        return None, meta

    meta["saved_path"] = str(dest.relative_to(OUT))
    return dest, meta


# ============================================================
# v1.6: README 正文读取 + description 提取
# ============================================================

README_FRONTMATTER_RE = re.compile(r"^\s*---\s*\n.*?\n---\s*\n", re.DOTALL)


def fetch_readme_body(model_id):
    meta = {"requests": 1, "error": None, "bytes": 0, "truncated": False}
    url = f"{ENDPOINT}/{quote(model_id)}/resolve/main/README.md"
    resp = http_get(url, stream=True, max_bytes=README_BODY_MAX_BYTES)
    if resp is None or resp.status_code != 200:
        meta["error"] = f"HTTP {resp.status_code if resp is not None else 'None'}"
        return None, meta
    text, nbytes, truncated = _read_stream_text(resp, README_BODY_MAX_BYTES)
    meta["bytes"] = nbytes
    meta["truncated"] = truncated
    if text is None:
        meta["error"] = "README 编码无法解码"
    return text, meta


def extract_description_from_readme(text, max_len=DESCRIPTION_MAX_LEN):
    if not text:
        return ""

    m = README_FRONTMATTER_RE.match(text)
    body = text[m.end():] if m else text

    paragraphs = re.split(r"\n\s*\n", body)
    for para in paragraphs:
        lines = [ln.strip() for ln in para.splitlines() if ln.strip()]
        if not lines:
            continue

        if all(ln.startswith("#") for ln in lines):
            continue

        kept = []
        for ln in lines:
            if ln.startswith("#"):
                continue
            if ln.startswith("!["):
                continue
            if re.match(r"^\s*\[!\[", ln):
                continue
            if re.match(r"^\s*<img\b", ln, re.IGNORECASE):
                continue
            if re.match(r"^\s*\[[^\]]+\]\([^)]+\)\s*$", ln):
                continue
            if re.match(r"^\s*[|>-]{3,}\s*$", ln):
                continue
            kept.append(ln)

        if not kept:
            continue

        desc = " ".join(kept)
        desc = re.sub(r"\s+", " ", desc).strip()
        if not desc:
            continue
        return desc[:max_len]

    return ""


# ============================================================
# Part 1: 按 tag 搜索模型
# ============================================================

def _build_search_url(token, sort_by, direction, limit, use_search=False,
                      omit_direction=False):
    key = "search" if use_search else "filter"
    parts = [f"{key}={quote(str(token))}", f"limit={min(limit, HF_MAX_LIMIT)}"]
    if sort_by:
        parts.append(f"sort={sort_by}")
    if direction and not omit_direction:
        parts.append(f"direction={direction}")
    return f"{ENDPOINT}/api/models?" + "&".join(parts)


# ★ v2.2: 返回值改为 (items, resp)
def _try_get_json(url, meta):
    resp = http_get(url)
    meta["requests"] += 1
    if resp is None:
        meta["error"] = "HTTP None"
        return None, None
    if resp.status_code != 200:
        meta["error"] = f"HTTP {resp.status_code}"
        return None, resp
    try:
        items = resp.json()
    except Exception as e:
        meta["error"] = f"JSON 解析失败: {e}"
        return None, resp
    if not isinstance(items, list):
        meta["error"] = f"返回不是列表: {type(items).__name__}"
        return None, resp
    return items, resp


def search_topic(token, sort_by, direction, limit, max_pages,
                 budget=None, budget_pages=None, use_search=False):
    """搜一个 (tag, sort) 组合。

    v2.3 关键修复：本函数现在**真正跟随游标翻页**。
      旧版每一页都请求同一个 URL，拿到的是同一批数据，所以无论 --pages 多大，
      最终每个组合最多只有 limit 条。现在改成：
        用首屏 URL 取第一页 -> 从 Link 头拿到 next 游标 URL -> 用它取下一页
      max_pages=None 表示**不限页数**，一直翻到没有 next 游标为止。
    budget = 本组合最多收多少条（None = 不限）
    budget_pages = 本组合最多请求几页（None = 不限）
    """
    models = []
    meta = {"requests": 0, "budget": budget, "budget_hit": False,
            "total_seen": 0, "rejected_by_tag_check": 0, "error": None,
            "cursor_pages": 0, "via": "search" if use_search else "filter",
            "degrade_level": 0, "pages_fetched": 0, "unique_ids": 0,
            "stop_reason": None}

    # 页数上限：budget_pages 与 max_pages 都可能是 None（不限）
    caps = [c for c in (max_pages, budget_pages) if c is not None]
    page_cap = min(caps) if caps else None

    url = _build_search_url(token, sort_by, direction, limit, use_search=use_search)
    page = 0
    seen_ids = set()
    while True:
        page += 1
        if page_cap is not None and page > page_cap:
            meta["stop_reason"] = f"达页数上限 {page_cap}"
            break

        # ★ v2.3: 解包 (items, resp)；首屏用拼好的 URL，之后用游标 URL
        items, resp = _try_get_json(url, meta)

        if items is None and meta.get("error", "").startswith("HTTP 400") and page == 1:
            log(f"    [400 降级 L2] 去掉 direction 重试")
            meta["degrade_level"] = max(meta["degrade_level"], 2)
            url = _build_search_url(token, sort_by, direction, limit,
                                    use_search=use_search, omit_direction=True)
            items, resp = _try_get_json(url, meta)

        if items is None and meta.get("error", "").startswith("HTTP 400") and page == 1:
            log(f"    [400 降级 L3] 改用 sort=lastModified:desc")
            meta["degrade_level"] = max(meta["degrade_level"], 3)
            url = _build_search_url(token, "lastModified", "desc", limit,
                                    use_search=use_search)
            items, resp = _try_get_json(url, meta)

        if items is None:
            meta["stop_reason"] = meta.get("error") or "请求失败"
            break
        if not items:
            meta["stop_reason"] = "本页为空"
            break

        meta["cursor_pages"] += 1
        meta["pages_fetched"] += 1
        new_this_page = 0
        for item in items:
            if budget is not None and len(models) >= budget:
                meta["budget_hit"] = True
                break
            meta["total_seen"] += 1
            tags = item.get("tags") or []
            if not use_search:
                ok, why = verify_tags(tags, token)
                if not ok:
                    meta["rejected_by_tag_check"] += 1
                    continue
            else:
                why = "search"
            mid = item.get("id") or item.get("modelId") or ""
            if not mid:
                continue
            # 同一模型可能在多页重复出现（翻页期间数据变动），这里去重
            if mid in seen_ids:
                continue
            seen_ids.add(mid)
            new_this_page += 1
            models.append({
                "id": mid,
                "model_id": mid,
                "author": item.get("author") or (mid.split("/", 1)[0] if "/" in mid else ""),
                "downloads": item.get("downloads") or 0,
                "likes": item.get("likes") or 0,
                "trending_score": item.get("trendingScore"),
                "private": bool(item.get("private")),
                "gated": item.get("gated", False),
                "tags": tags,
                "pipeline_tag": item.get("pipeline_tag"),
                "library_name": item.get("library_name"),
                "hf_last_modified": item.get("lastModified"),
                "hf_created_at": item.get("createdAt"),
                "search_topic": token,
                "search_sort": f"{sort_by}:{direction}",
                "matched_by": why,
                "license_spdx": extract_license_from_tags(tags),
                "hf_url": f"https://huggingface.co/{mid}",
            })
        if meta["budget_hit"]:
            meta["stop_reason"] = "达本组合条数预算"
            break

        # ★ v2.3: 拿下一页游标；拿不到就是真的到底了
        nxt = next_cursor_url(resp, ENDPOINT)
        if not nxt:
            meta["stop_reason"] = "无下一页游标"
            break
        url = nxt
        # 本页一条新的都没加（全是已见过的），说明游标没推进，避免死循环
        if new_this_page == 0 and meta["pages_fetched"] > 1:
            meta["stop_reason"] = "本页全部重复，游标疑似未推进"
            break
        time.sleep(API_WAIT)
    meta["unique_ids"] = len(seen_ids)
    return models, meta


def build_topic_list(group, custom_topics):
    if custom_topics:
        return [{"token": t} for t in custom_topics]
    if group == "all":
        out = []
        for g in ("mcp", "ptm"):
            out += TOPIC_GROUPS[g]
        return out
    return list(TOPIC_GROUPS.get(group, []))


def run_search(topics, per_page, max_pages, total_limit=None, save_raw=False,
               sorts=None, resume_state=None, shard=None):
    sorts = sorts or SORT_STRATEGIES
    log("=" * 66)
    log("Part 1: HuggingFace 模型搜索（按 tag，客户端精确校验）")
    log(f"  {len(topics)} topics x {len(sorts)} sorts x "
        f"{('最多 %d 页' % max_pages) if max_pages else '不限页数'} x {per_page}/页")
    log(f"  可用排序: {', '.join(f'{a}:{b}' for a, b in sorts)}")
    if total_limit:
        log(f"  ★ 总量上限 {total_limit} 条：按剩余组合动态分配预算，取满即停")
    else:
        log(f"  ★ 全量模式（默认）：不限量，翻页直到端点返回空"
            f"（受 --max-requests 约束）")
    log("=" * 66)

    run_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_models = resume_state.get("all_models", []) if resume_state else []
    combos_meta = resume_state.get("combos_meta", {}) if resume_state else {}
    done_keys = set(resume_state.get("done_keys", [])) if resume_state else set()

    all_combos = []
    for topic in topics:
        for sort_by, direction in sorts:
            all_combos.append((topic["token"], sort_by, direction))
    if shard:
        n, m = shard
        all_combos = [c for i, c in enumerate(all_combos) if i % m == (n - 1)]

    total_combos = len(all_combos)
    log(f"  总组合数: {total_combos}"
        + (f"（shard {shard[0]}/{shard[1]}）" if shard else "")
        + (f"，已完成 {len(done_keys)}，跳过" if done_keys else ""))

    for idx, (token, sort_by, direction) in enumerate(all_combos, 1):
        key = f"{token}|{sort_by}:{direction}"
        if key in done_keys:
            log(f"\n[{idx}/{total_combos}] {key}  已采过，跳过")
            continue

        budget = budget_pages = None
        if total_limit:
            remaining = total_limit - len(all_models)
            if remaining <= 0:
                log(f"\n[完成] 已达总量上限 {total_limit} 条，停止搜索")
                return finish(all_models, combos_meta, topics, per_page,
                              max_pages, total_limit, run_at, True, save_raw,
                              resume_state=resume_state)
            combos_left = total_combos - idx + 1
            per_combo = max(1, -(-remaining // combos_left))
            budget = min(per_combo, remaining)
            budget_pages = max(1, -(-budget // per_page))

        log(f"\n[{idx}/{total_combos}] tag:{token} sort={sort_by}:{direction}"
            + (f" (预算 {budget} 条)" if budget else ""))

        try:
            models, meta = search_topic(token, sort_by, direction, per_page,
                                        max_pages, budget=budget,
                                        budget_pages=budget_pages)
        except RuntimeError as e:
            log(f"  [!] {e}")
            return finish(all_models, combos_meta, topics, per_page, max_pages,
                          total_limit, run_at, False, save_raw,
                          resume_state=resume_state)

        if not models and meta.get("rejected_by_tag_check", 0) > 0:
            log(f"  tag 精确校验拒绝了 {meta['rejected_by_tag_check']} 条，"
                f"改用 search 兜底")
            try:
                m2, meta2 = search_topic(token, sort_by, direction, per_page, 1,
                                         budget=budget, budget_pages=budget_pages,
                                         use_search=True)
            except RuntimeError as e:
                log(f"  [!] {e}")
                return finish(all_models, combos_meta, topics, per_page, max_pages,
                              total_limit, run_at, False, save_raw,
                              resume_state=resume_state)
            meta["fallback_search"] = meta2
            models = m2
            meta["requests"] += meta2["requests"]

        all_models.extend(models)
        combos_meta[key] = meta
        done_keys.add(key)

        if resume_state is not None:
            save_json({
                "date": run_at,
                "all_models": all_models,
                "combos_meta": combos_meta,
                "done_keys": list(done_keys),
            }, "_resume.json")

        flag = ""
        if meta.get("budget_hit"):
            flag += " [达本组合预算]"
        if meta.get("rejected_by_tag_check"):
            flag += f" [tag校验拒绝{meta['rejected_by_tag_check']}]"
        if meta.get("fallback_search"):
            flag += " [search兜底]"
        if meta.get("degrade_level"):
            flag += f" [已降级 L{meta['degrade_level']}]"
        if meta.get("error"):
            flag += f" [{meta['error']}]"
        log(f"  -> {len(models)} 条  累计 {len(all_models)}/"
            f"{total_limit or '不限'}  翻页={meta.get('pages_fetched', 0)}{flag}")

        if total_limit and len(all_models) >= total_limit:
            log(f"\n[完成] 已达总量上限 {total_limit} 条，停止搜索")
            return finish(all_models, combos_meta, topics, per_page, max_pages,
                          total_limit, run_at, True, save_raw,
                          resume_state=resume_state)
        time.sleep(API_WAIT)

    return finish(all_models, combos_meta, topics, per_page, max_pages,
                  total_limit, run_at, False, save_raw,
                  resume_state=resume_state)


# ============================================================
# Part 2: 许可证信息采集
# ============================================================

def _split_license_name(fname):
    stem, dot, ext = fname.rpartition(".")
    if not dot:
        return fname.lower(), ""
    suffix = ("." + ext).lower()
    return stem.lower(), suffix


def license_file_score(path):
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
    if re.search(r"licen[cs]es?$", parent, re.IGNORECASE):
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


def classify_api_license(spdx):
    if not spdx:
        return "no"
    s = str(spdx).strip().lower()
    if s in SPDX_NONASSERTION:
        return "noassertion"
    if s in SPDX_KNOWN:
        return "yes"
    return "noassertion"


def fetch_model_detail(model_id):
    meta = {"requests": 1, "error": None}
    url = f"{ENDPOINT}/api/models/{quote(model_id)}?full=true"
    resp = http_get(url)
    if resp is None or resp.status_code != 200:
        meta["error"] = f"HTTP {resp.status_code if resp is not None else 'None'}"
        return None, meta
    try:
        return resp.json(), meta
    except Exception as e:
        meta["error"] = f"JSON 解析失败: {e}"
        return None, meta


def run_license_crosscheck(records, detail_limit=0, save_raw=False, run_at=None,
                           do_detail=True, do_readme=True, do_license_body=True):
    log()
    log("=" * 66)
    log("Part 2: 许可证信息采集（API license tag × 文件清单 × LICENSE 正文）")
    log(f"  detail={do_detail} readme={do_readme} license_body={do_license_body}")
    log("=" * 66)

    stats = {
        "enabled": True, "repos_scanned": 0, "requests": 0,
        "detail_from_part1": 0, "detail_fetched": 0, "detail_failed": 0,
        "cross_check": {}, "license_file_names_top": {},
        "file_only_examples": [], "api_only_examples": [],
        "license_tag_distribution": {},
        "license_body_fetched": 0, "license_body_failed": 0,
        "license_body_truncated": 0,
        # ★ v2.4
        "license_other_raw_saved": 0, "license_other_raw_failed": 0,
        "readme_fetched": 0, "readme_failed": 0, "readme_truncated": 0,
        "description_filled": 0,
        "license_name_filled": 0, "license_link_filled": 0,
    }
    cross_counter = Counter()
    name_counter = Counter()
    tag_counter = Counter()

    n = len(records)
    for i, rec in enumerate(records, 1):
        mid = rec.get("model_id") or rec.get("id")
        tags = rec.get("tags") or []
        api_spdx = rec.get("license_spdx")
        api_state = classify_api_license(api_spdx)
        tag_counter[api_spdx or "(none)"] += 1

        rec.setdefault("license_name", "")
        rec.setdefault("license_link", "")
        rec.setdefault("license_raw_path", "")   # ★ v2.4

        siblings = rec.get("_siblings")
        if do_detail and siblings is None and (detail_limit == 0 or i <= detail_limit):
            if ALLOW_SINGLE_MODEL_FETCH:
                log(f"  [{i}/{n}] 取文件清单: {mid}")
                detail, dmeta = fetch_model_detail(mid)
                stats["requests"] += dmeta["requests"]
                if detail:
                    siblings = [s.get("rfilename", "") for s in (detail.get("siblings") or [])]
                    stats["detail_fetched"] += 1
                    if detail.get("tags") and len(detail["tags"]) > len(tags):
                        rec["tags"] = detail["tags"]
                        tags = detail["tags"]
                        new_spdx = extract_license_from_tags(tags)
                        if new_spdx and not api_spdx:
                            rec["license_spdx"] = new_spdx
                            api_spdx = new_spdx
                            api_state = classify_api_license(api_spdx)
                    if detail.get("lastModified"):
                        rec["hf_last_modified"] = detail["lastModified"]

                    card = detail.get("cardData") or {}
                    lname = card.get("license_name")
                    llink = card.get("license_link")
                    if lname:
                        rec["license_name"] = str(lname).strip()
                        stats["license_name_filled"] += 1
                    if llink:
                        rec["license_link"] = str(llink).strip()
                        stats["license_link_filled"] += 1
                else:
                    stats["detail_failed"] += 1
                time.sleep(DETAIL_WAIT)
        elif siblings is not None:
            stats["detail_from_part1"] += 1
        siblings = siblings or []

        if do_readme:
            log(f"  [{i}/{n}] 读 README: {mid}")
            readme_text, rmeta = fetch_readme_body(mid)
            stats["requests"] += rmeta["requests"]
            if readme_text:
                stats["readme_fetched"] += 1
                if rmeta.get("truncated"):
                    stats["readme_truncated"] += 1
                desc = extract_description_from_readme(readme_text)
                rec["description"] = desc
                if desc:
                    stats["description_filled"] += 1
            else:
                stats["readme_failed"] += 1
                rec.setdefault("description", "")
            time.sleep(README_WAIT)
        else:
            rec.setdefault("description", "")

        files = [p for p in siblings if LICENSE_NAME_RE.search(p.rsplit("/", 1)[-1])]
        files = sort_license_files(files)

        if api_state == "yes" and files:
            cross = "both"
        elif api_state == "yes":
            cross = "api_only"
        elif files:
            cross = "file_only"
        else:
            cross = "neither"

        body_excerpt = ""
        if do_license_body and files:
            target = files[0]
            log(f"  [{i}/{n}] 读 LICENSE 正文: {mid} :: {target}")
            body_text, bmeta = fetch_license_body(mid, target)
            stats["requests"] += bmeta["requests"]
            if body_text:
                stats["license_body_fetched"] += 1
                if bmeta.get("truncated"):
                    stats["license_body_truncated"] += 1
                excerpt = re.sub(r"\s+", " ", body_text).strip()
                body_excerpt = excerpt[:LICENSE_EXCERPT_MAX_LEN]
            else:
                stats["license_body_failed"] += 1
            time.sleep(BODY_WAIT)

        # ★ v2.4: license 为 other/unknown/unspecified 时，单独完整下载 LICENSE 原文
        if (do_license_body and files
                and str(api_spdx or "").strip().lower() in NONASSERTION_LICENSES):
            target = files[0]
            log(f"  [{i}/{n}] [other] 下载 LICENSE 原文: {mid} :: {target}")
            saved, ometa = download_license_raw(mid, target)
            stats["requests"] += ometa["requests"]
            if saved is not None:
                rec["license_raw_path"] = ometa["saved_path"]
                stats["license_other_raw_saved"] += 1
            else:
                stats["license_other_raw_failed"] += 1
                log(f"      [other] 下载失败: {ometa['error']}")
            time.sleep(BODY_WAIT)

        rec["license_has_api"] = api_state
        rec["license_has_file"] = "yes" if files else "no"
        rec["license_file_names"] = "|".join(f.rsplit("/", 1)[-1]
                                             for f in files[:LICENSE_MAX_NAMES])
        rec["license_file_path"] = (files[0].rsplit("/", 1)[-1] if files else "")
        rec["license_file_source"] = "full" if siblings else "none"
        rec["license_cross_check"] = cross
        rec["license_files"] = files
        rec["license_checked_at"] = run_at
        rec["license_body_excerpt"] = body_excerpt

        stats["repos_scanned"] += 1
        cross_counter[cross] += 1
        for f in files[:LICENSE_MAX_NAMES]:
            name_counter[f.rsplit("/", 1)[-1].lower()] += 1
        if cross == "file_only" and len(stats["file_only_examples"]) < 10:
            stats["file_only_examples"].append({
                "model_id": mid, "file_names": rec["license_file_names"],
                "api_state": api_state})
        if cross == "api_only" and len(stats["api_only_examples"]) < 10:
            stats["api_only_examples"].append({
                "model_id": mid, "api_spdx": api_spdx,
                "files_present": bool(siblings)})

    for k in ("both", "api_only", "file_only", "neither"):
        cross_counter.setdefault(k, 0)

    stats["cross_check"] = dict(cross_counter)
    stats["license_file_names_top"] = dict(name_counter.most_common(15))
    stats["license_tag_distribution"] = dict(tag_counter.most_common(20))

    log()
    log("  许可证采集结果：")
    log(f"    both      API 有 license tag 且仓库里有 license 文件 : "
        f"{stats['cross_check']['both']}")
    log(f"    api_only  仅 API 标注（文件缺失，可疑）             : "
        f"{stats['cross_check']['api_only']}")
    log(f"    file_only 仅文件命中（API 漏标/未识别）             : "
        f"{stats['cross_check']['file_only']}")
    log(f"    neither   两边都没有                                : "
        f"{stats['cross_check']['neither']}")
    log(f"    ★ LICENSE 正文: 成功={stats['license_body_fetched']} "
        f"失败={stats['license_body_failed']} 截断={stats['license_body_truncated']}")
    log(f"    ★ [other] LICENSE 原文单独下载: 成功={stats['license_other_raw_saved']} "
        f"失败={stats['license_other_raw_failed']}")
    log(f"    ★ README: 成功={stats['readme_fetched']} "
        f"失败={stats['readme_failed']} 截断={stats['readme_truncated']}")
    log(f"    ★ description 填充数: {stats['description_filled']}/{n}")
    log(f"    ★ license_name 填充数: {stats['license_name_filled']}/{n}")
    log(f"    ★ license_link 填充数: {stats['license_link_filled']}/{n}")
    log(f"    license tag 分布: {stats['license_tag_distribution']}")

    if save_raw:
        raw = {r.get("model_id"): {
            "tags": r.get("tags"), "license_spdx": r.get("license_spdx"),
            "license_name": r.get("license_name"),
            "license_link": r.get("license_link"),
            "gated": r.get("gated"), "files": r.get("license_files"),
            "search_topic": r.get("search_topic"),
            "search_sort": r.get("search_sort"),
            "matched_by": r.get("matched_by"),
            "license_body_excerpt": r.get("license_body_excerpt"),
            "license_raw_path": r.get("license_raw_path"),   # ★ v2.4
            "description": r.get("description"),
        } for r in records}
        save_json({"note": "许可证信息逐模型明细",
                   "run_at": run_at, "summary": stats, "models": raw},
                  "raw_api_responses", "license_scan.json")
    return stats


# ============================================================
# 去重 / 过滤 / 落盘
# ============================================================

def finish(all_models, combos_meta, topics, per_page, max_pages,
           total_limit, run_at, stopped_early, save_raw, resume_state=None,
           do_detail=True, do_readme=True, do_license_body=True):
    seen = {}
    for r in all_models:
        rid = r["model_id"]
        tag = f"{r['search_topic']}|{r['search_sort']}"
        if rid not in seen:
            seen[rid] = r
            r["_found_by"] = [tag]
        else:
            seen[rid]["_found_by"].append(tag)
            if (r.get("downloads") or 0) > (seen[rid].get("downloads") or 0):
                new = dict(r)
                new["_found_by"] = seen[rid]["_found_by"]
                seen[rid] = new
    unique = sorted(seen.values(), key=lambda x: (x.get("downloads") or 0), reverse=True)

    excluded = {"private": 0, "test_repo": 0, "lang_code_fp": 0}
    suspicious = []
    valid = []
    for r in unique:
        if r.get("private"):
            excluded["private"] += 1
            continue
        if re.search(r"(awesome|testrepo|test-repo|xxx|dummy)", r["model_id"], re.IGNORECASE):
            excluded["test_repo"] += 1
            continue
        r["found_by_count"] = len(r["_found_by"])
        r["collected_at"] = run_at
        r["tags_count"] = len(r.get("tags") or [])

        fp, reason = is_language_code_false_positive(r)
        r["_lang_code_suspect"] = fp
        r["_lang_code_reason"] = reason
        if fp:
            excluded["lang_code_fp"] += 1
            r["filter_note"] = reason
            suspicious.append(r)
            continue

        valid.append(r)

    log()
    log(f"  原始记录: {len(all_models)}")
    log(f"  去重后:   {len(unique)}")
    log(f"  有效:     {len(valid)}  "
        f"(排除 private={excluded['private']} 测试仓库={excluded['test_repo']} "
        f"语言码误抓={excluded['lang_code_fp']})")
    if suspicious:
        log()
        log(f"  [!] 语言码假阳性 {len(suspicious)} 条（已从主表剔除，详见 "
            f"lang_code_suspects.csv）：")
        for s in suspicious[:8]:
            log(f"      - {s['model_id']}  [{s['_lang_code_reason']}]")
        if len(suspicious) > 8:
            log(f"      ... 其余 {len(suspicious) - 8} 条见文件")

    if not valid:
        log()
        log("  [!] 没有任何有效模型。可能原因：")
        log("    1) 该端点没连通（跑 --probe-endpoint 看探测结果）")
        log("    2) 这些 tag 在 HF 上确实不存在")
        log("    3) --total 太小")
        log("    4) 端点不支持当前 sort（看 [sort 探测] 日志）")
        log("    5) 假阳性过滤过严（检查 lang_code_suspects.csv）")
        log("    建议先跑: python %s --probe-endpoint" % Path(__file__).name)
        log("    以及:     python %s --group mcp --total 50" % Path(__file__).name)

    license_summary = run_license_crosscheck(
        valid, detail_limit=DEFAULT_DETAIL_LIMIT,
        save_raw=save_raw, run_at=run_at,
        do_detail=do_detail, do_readme=do_readme,
        do_license_body=do_license_body)

    total_requests = sum(m.get("requests", 0) for m in combos_meta.values())
    total_requests += license_summary.get("requests", 0)

    if save_raw:
        save_json({"note": "原始 API 分页元数据（用于复核分页与命中率）",
                   "run_at": run_at, "endpoint": ENDPOINT,
                   "per_combo": combos_meta},
                  "raw_api_responses", "search_meta.json")

    def clean(r):
        return {k: v for k, v in r.items() if not k.startswith("_")}

    save_json({
        "date": run_at,
        "endpoint": ENDPOINT,
        "source": "huggingface",
        "config": {
            "topics": [t["token"] for t in topics],
            "num_topics": len(topics),
            "sorts": [f"{a}:{b}" for a, b in SORT_STRATEGIES],
            "per_page": per_page, "pages": max_pages,
            "total_limit": total_limit,
            "authenticated": bool(HF_TOKEN),
            "read_license_body": do_license_body,
            "read_readme": do_readme,
            "read_detail": do_detail,
            "spdx_from_filename": False,
            "spdx_from_body": False,
            "read_carddata_license": do_detail,
            "download_other_license_raw": do_license_body,   # ★ v2.4
        },
        "total_raw": len(all_models),
        "total_unique": len(unique),
        "total_valid": len(valid),
        "total_requests": total_requests,
        "stopped_early_by_limit": stopped_early,
        "excluded": excluded,
        "per_combo": combos_meta,
        "license_crosscheck": license_summary,
        "models": [clean(r) for r in valid],
    }, "all_models_v1.json")

    save_json({
        "date": run_at,
        "endpoint": ENDPOINT,
        "total_raw": len(all_models),
        "total_valid": len(valid),
        "total_requests": total_requests,
        "note": "v2.4 默认全量模式。license_spdx 为 API tags 里的 license:xxx；"
                "license_name / license_link 来自 cardData；"
                "license_body_excerpt 为 LICENSE 正文前 N 字符，原样记录。"
                "license_raw_path 为 license=other/unknown/unspecified 时"
                "LICENSE 原文完整落盘的相对路径。"
                "description 来自 README.md 正文。"
                "gated 是访问限制，不是许可证。",
        "license_crosscheck": license_summary,
        "excluded": excluded,
        "topics": [t["token"] for t in topics],
        "stars_range": {
            "max": max((r.get("downloads") or 0) for r in valid) if valid else 0,
            "min": min((r.get("downloads") or 0) for r in valid) if valid else 0,
        },
        "updated_at_range": {
            "newest": max((r.get("hf_last_modified") or "") for r in valid) if valid else "",
            "oldest": min((r.get("hf_last_modified") or "~") for r in valid) if valid else "",
        },
    }, "stats.json")

    write_csv(valid, "hf_dataset.csv")
    write_crosscheck_csv(valid)
    write_timestamps(valid)
    if suspicious:
        write_suspects_csv(suspicious)

    if resume_state is not None and RESUME_FILE.exists():
        try:
            RESUME_FILE.unlink()
            log(f"  已清理断点文件 {RESUME_FILE.name}")
        except Exception:
            pass

    return valid


# ============================================================
# CSV 输出
# ============================================================

def _cell(r, key, desc_limit=None):
    v = r.get(key)
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    v = str(v)
    if key in ("tags", "license_file_names", "description",
               "license_body_excerpt", "license_name", "license_link",
               "license_raw_path"):
        v = re.sub(r"\s+", " ", v).strip()
    return v


def write_csv(records, filename):
    path = Path(OUT, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow({k: _cell(r, k) for k in CSV_FIELDS})
    tmp.replace(path)
    log(f"  已写出 {filename}  ({len(records)} 行, {len(CSV_FIELDS)} 列)")
    return path


def write_crosscheck_csv(records, filename="license_crosscheck.csv"):
    order = {"file_only": 0, "api_only": 1, "both": 2, "neither": 3, "": 4}
    rows = sorted(records,
                  key=lambda r: (order.get(str(r.get("license_cross_check", "")), 9),
                                 -(r.get("downloads") or 0)))
    path = Path(OUT, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CROSSCHECK_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: _cell(r, k) for k in CROSSCHECK_FIELDS})
    tmp.replace(path)
    log(f"  已写出 {filename}  ({len(rows)} 行, 许可证对照表)")
    return path


def write_timestamps(records, filename="timestamps.csv"):
    fields = ["model_id", "hf_last_modified", "hf_created_at", "collected_at"]
    path = Path(OUT, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})
    log(f"  已写出 {filename}  ({len(records)} 行)")
    return path


def write_suspects_csv(records, filename="lang_code_suspects.csv"):
    path = Path(OUT, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUSPECT_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow({k: _cell(r, k) for k in SUSPECT_FIELDS})
    tmp.replace(path)
    log(f"  已写出 {filename}  ({len(records)} 行, 疑似语言码误抓，待人工确认)")
    return path


# ============================================================
# CLI
# ============================================================

def cmd_probe_endpoint():
    log("端点连通性探测（huggingface.co 在国内常被阻断，hf-mirror.com 可用）")
    log()
    url, tried = pick_endpoint(verbose=False)
    for u, ok in tried:
        log(f"  {'[可达]' if ok else '[不通]'}  {u}")
    log()
    if not url:
        log("  没有任何可用端点。检查网络或设置 HF_ENDPOINT。")
        return 1
    log(f"  选用端点: {url}")
    log()
    s = make_session()
    try:
        resp = s.get(f"{url}/api/models?limit=1", timeout=20)
        log(f"  API 探针: HTTP {resp.status_code}")
        if resp.status_code == 200 and isinstance(resp.json(), list):
            log(f"  样例模型: {resp.json()[0].get('id')}")
            log("  → 端点可用，可以正式采集")
            return 0
        log("  → HTTP 通了但返回异常，谨慎使用")
        return 1
    except Exception as e:
        log(f"  API 探针失败: {e}")
        return 1


def cmd_dry_run(topics, per_page, max_pages, total_limit, group, sorts=None,
                do_detail=True, do_readme=True, do_license_body=True,
                shard=None):
    sorts = sorts or SORT_STRATEGIES
    log("Dry-run：不发出任何请求")
    log(f"  目录        {OUT}")
    log(f"  端点        自动探测（候选：{' / '.join(ENDPOINT_CANDIDATES)}）")
    log(f"  认证        {'HF_TOKEN 已设置' if HF_TOKEN else '匿名'}")
    log(f"  topic 组    {group}（{len(topics)} 个 tag）")
    for t in topics:
        log(f"                 - {t['token']}")
    log(f"  排序        {len(sorts)} 种 "
        f"({', '.join(f'{a}:{b}' for a, b in sorts)})")
    log(f"  翻页上限    {('%d 页' % max_pages) if max_pages else '不限（翻到无下一页游标为止）'}"
        f" x {per_page} 条/页")
    n_combos = len(topics) * len(sorts)
    if shard:
        n_combos_shard = sum(1 for i in range(n_combos)
                             if i % shard[1] == (shard[0] - 1))
        log(f"  组合数      {n_combos}（shard {shard[0]}/{shard[1]} → {n_combos_shard}）")
    else:
        log(f"  组合数      {n_combos}")
    log()
    log(f"  ★ 总量上限  {total_limit or '不限（默认全量模式）'} 条（原始记录）")
    if total_limit:
        log(f"  搜索请求    约 {min(n_combos, total_limit or 10**9)} 次（取满即停）")
    elif max_pages:
        log(f"  搜索请求    每组合最多 {max_pages} 页，共约 "
            f"{n_combos * max_pages} 次（受 --max-requests 约束）")
    else:
        log(f"  搜索请求    不限量：每组合翻到无下一页游标为止，最坏情况可能上千次")
        log(f"  [!] HF 官方配额实测为 500 请求 / 5 分钟（响应头 ratelimit-policy）。")
        log(f"      不限量 + Part 2 详情请求很容易撞限流，建议同时给个保险，例如：")
        log(f"      --max-requests 4000        给整体请求数设个硬上限")
        log(f"      --no-detail --no-readme    不取详情/README，省下大部分请求")
    log(f"  [!] 这些是**原始记录**，去重后会更少：同一个热门模型会被多个 tag x sort 命中。")
    log(f"  [!] v1.2 启用语言码假阳性过滤：search_topic 是短 token + ")
    log(f"      tags_count>{LANG_CODE_TAGS_THRESHOLD} + 非生成任务 → 剔除到 "
        f"lang_code_suspects.csv")
    log(f"  [!] Part 2 detail={do_detail} readme={do_readme} "
        f"license_body={do_license_body}")
    log(f"  [!] v2.4 对 license=other/unknown/unspecified 的模型，额外把 LICENSE 原文"
        f"完整下载到 {LICENSE_OTHER_RAW_DIR.name}/<model_id>/ 并写入 license_raw_path")
    log(f"  [!] v2.2 默认全量：不传 --total 就是不限量；")
    log(f"      --total N 限制总量；--resume 断点续跑；")
    log(f"      --max-requests N 限制总请求数；--shard N/M 并行切分")
    log()
    log(f"  输出列（{len(CSV_FIELDS)} 列）:")
    for i, c in enumerate(CSV_FIELDS, 1):
        log(f"                 {i:>2}. {c}")
    log()
    log("  确认后执行: python collect_hf.py")
    return 0


def main():
    global ENDPOINT, SESSION, MAX_REQUESTS

    ap = argparse.ArgumentParser(
        description="HuggingFace Topic 搜索 v2.4（默认全量 + other LICENSE 原文下载）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="只算请求量，不发请求")
    ap.add_argument("--probe-endpoint", action="store_true",
                    help="只探测端点连通性，不发业务请求")
    ap.add_argument("--endpoint", type=str, default=None,
                    help=f"手动指定 API 端点（默认自动探测：{' / '.join(ENDPOINT_CANDIDATES)}）")
    ap.add_argument("--group", choices=["mcp", "ptm", "all"], default="all",
                    help="topic 组：mcp=MCP 生态，ptm=预训练模型，all=两组都搜（默认）")
    ap.add_argument("--total", type=int, default=DEFAULT_TOTAL_LIMIT,
                    help=f"总量上限（原始记录数），默认 {DEFAULT_TOTAL_LIMIT}（不限量）；"
                         f"传 N 则限制为 N 条")
    ap.add_argument("--per-page", type=int, default=DEFAULT_PER_PAGE,
                    help=f"每个请求取多少条（默认 {DEFAULT_PER_PAGE}，上限 {HF_MAX_LIMIT}）")
    ap.add_argument("--pages", type=int, default=DEFAULT_MAX_PAGES,
                    help=f"每个组合最多翻页数。默认 {DEFAULT_MAX_PAGES} = 不限页数，"
                         f"一直翻到没有下一页游标为止；传 N>0 则限制为 N 页")
    ap.add_argument("--topics", type=str, default=None,
                    help='逗号分隔的自定义 tag 列表，覆盖 --group，例如 "mcp,pretrained"')
    ap.add_argument("--no-raw", action="store_true", help="不保存原始 API 元数据")
    ap.add_argument("--from-json", action="store_true",
                    help="不发请求，直接读 all_models_v1.json 重建 CSV")
    ap.add_argument("--skip-sort-probe", action="store_true",
                    help="跳过 sort 能力探测，直接用全部排序策略（调试用）")
    ap.add_argument("--no-lang-filter", action="store_true",
                    help="关闭语言码假阳性过滤（调试用，可疑记录会留在主表）")
    ap.add_argument("--resume", action="store_true",
                    help="从 _resume.json 断点续跑（存在则自动启用）")
    ap.add_argument("--max-requests", type=int, default=0,
                    help="整体请求数硬上限，0 表示不限（默认 0）")
    ap.add_argument("--no-detail", action="store_true",
                    help="跳过 Part 2 的 full=true 详情请求")
    ap.add_argument("--no-readme", action="store_true",
                    help="跳过 Part 2 的 README 正文读取")
    ap.add_argument("--no-license-body", action="store_true",
                    help="跳过 Part 2 的 LICENSE 正文读取（同时不下载 other 原文）")
    ap.add_argument("--shard", type=str, default=None,
                    help="分片：N/M，只跑第 N 份（从 1 开始），例如 1/3")
    args = ap.parse_args()

    if args.probe_endpoint:
        return cmd_probe_endpoint()

    explicit = args.endpoint or os.environ.get("HF_ENDPOINT") or None
    ENDPOINT, tried = pick_endpoint(explicit=explicit)
    if not ENDPOINT:
        log()
        log("  [X] 没有任何可用端点。已尝试：")
        for u, _ in tried:
            log(f"      {u}")
        log("  排查：网络是否可用 / 是否需要设 HF_ENDPOINT / 代理是否生效")
        return 1
    SESSION = make_session()

    MAX_REQUESTS = args.max_requests or 0

    if args.no_lang_filter:
        global SHORT_TOKEN_TOPICS
        SHORT_TOKEN_TOPICS = set()
        log("  [语言码过滤] 已关闭（--no-lang-filter）")

    custom = ([t.strip() for t in args.topics.split(",") if t.strip()]
              if args.topics else None)
    topics = build_topic_list(args.group, custom)
    if not topics:
        log(f"  [X] --group {args.group} 没有对应 topic")
        return 1

    per_page = max(1, min(args.per_page, HF_MAX_LIMIT))
    # ★ v2.3: --pages <= 0（含默认 0）表示不限页数，一路翻到没有下一页游标
    pages = args.pages if (args.pages and args.pages > 0) else None
    total_limit = args.total if args.total and args.total > 0 else None

    shard = None
    if args.shard:
        try:
            n, m = args.shard.split("/")
            shard = (int(n), int(m))
            assert 1 <= shard[0] <= shard[1] and shard[1] >= 1
        except Exception:
            log(f"  [X] --shard 格式错误: {args.shard}（应为 N/M，如 1/3）")
            return 1

    if args.skip_sort_probe:
        sorts = list(SORT_STRATEGIES)
        log("  [sort 探测] 已跳过（--skip-sort-probe）")
    else:
        sorts = probe_sorts(ENDPOINT, token=topics[0]["token"], verbose=True)

    if args.dry_run:
        return cmd_dry_run(topics, per_page, pages, total_limit, args.group,
                           sorts=sorts,
                           do_detail=not args.no_detail,
                           do_readme=not args.no_readme,
                           do_license_body=not args.no_license_body,
                           shard=shard)

    if args.from_json:
        src = OUT / "all_models_v1.json"
        if not src.exists():
            log(f"[--from-json] 找不到 {src}，请先跑一次采集。")
            return 1
        payload = json.loads(src.read_text(encoding="utf-8"))
        valid = payload.get("models", [])
        if not valid:
            log("[--from-json] all_models_v1.json 里没有 models 数据。")
            return 1
        for r in valid:
            if str(r.get("license_has_api") or "") == "":
                r["license_has_api"] = classify_api_license(r.get("license_spdx"))
            r.setdefault("description", "")
            r.setdefault("license_body_excerpt", "")
            r.setdefault("license_name", "")
            r.setdefault("license_link", "")
            r.setdefault("license_raw_path", "")   # ★ v2.4
            for old_key in ("license_body_snippet", "license_spdx_agree",
                            "license_spdx_from_file",
                            "license_spdx_file_source",
                            "license_spdx_agree_body"):
                r.pop(old_key, None)
        log(f"[--from-json] 读入 {len(valid)} 条（采集时间 {payload.get('date')}），"
            f"不发请求，只重建 CSV")
        write_csv(valid, "hf_dataset.csv")
        write_crosscheck_csv(valid)
        write_timestamps(valid)
        return 0

    OUT.mkdir(parents=True, exist_ok=True)

    resume_state = None
    if args.resume or RESUME_FILE.exists():
        if RESUME_FILE.exists():
            try:
                resume_state = json.loads(RESUME_FILE.read_text(encoding="utf-8"))
                log(f"  [断点续跑] 读入 {RESUME_FILE.name}，"
                    f"已完成 {len(resume_state.get('done_keys', []))} 个组合，"
                    f"已采 {len(resume_state.get('all_models', []))} 条原始记录")
            except Exception as e:
                log(f"  [断点续跑] 读入失败: {e}，忽略断点")
                resume_state = None
        else:
            log(f"  [断点续跑] 未找到 {RESUME_FILE.name}，从头开始")
            resume_state = {"all_models": [], "combos_meta": {}, "done_keys": []}

    log()
    log("#" * 66)
    log("# HuggingFace Topic 搜索 v2.4")
    log(f"# 端点:   {ENDPOINT}")
    log(f"# 输出:   {OUT}")
    log(f"# topic 组: {args.group}（{len(topics)} 个 tag）")
    log(f"# 总量上限: {total_limit if total_limit else '不限（默认全量模式）'} 条")
    log(f"# 翻页上限: {pages} 页")
    log(f"# 可用排序: {len(sorts)} 种")
    log(f"# 语言码过滤: {'关闭' if args.no_lang_filter else '开启'}")
    log(f"# Part 2: detail={not args.no_detail} readme={not args.no_readme} "
        f"license_body={not args.no_license_body}")
    log(f"# other LICENSE 原文目录: {LICENSE_OTHER_RAW_DIR}")
    log(f"# 请求硬上限: {MAX_REQUESTS or '不限'}")
    log(f"# 分片: {f'{shard[0]}/{shard[1]}' if shard else '无'}")
    log("#" * 66)

    valid = run_search(topics, per_page, pages, total_limit=total_limit,
                       save_raw=not args.no_raw, sorts=sorts,
                       resume_state=resume_state, shard=shard)

    if not valid:
        log()
        log("  未采到任何有效模型，未写出主表。")
        return 1

    log()
    log("=" * 66)
    log(f"v2.4 完成。输出目录: {OUT}")
    log("  数据集:     hf_dataset.csv")
    log("  许可证对照: license_crosscheck.csv")
    log("  时间对照:   timestamps.csv")
    log("  误抓复核:   lang_code_suspects.csv（若有）")
    log("  明细:       all_models_v1.json / stats.json")
    log(f"  other LICENSE 原文: {LICENSE_OTHER_RAW_DIR}（见 license_raw_path 列）")
    log("=" * 66)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("\n已中断。断点文件 _resume.json 已保留，下次加 --resume 继续。")
        sys.exit(130)
