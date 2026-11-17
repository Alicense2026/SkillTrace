# -*- coding: utf-8 -*-
"""多注册中心适配层：把仓库里出现的名字，解析成有 URL 和许可证的「AI 资产」。

支持三类资产（kind）：
  model    —— 模型权重 / 推理服务
  dataset  —— 数据集
  tool     —— MCP 服务器、Agent Skill、CLI 工具、SDK

注册中心覆盖（按可用性排序）：
  1. Hugging Face   模型 / 数据集，官方 JSON API，最可靠
  2. MCP 官方注册中心  registry.modelcontextprotocol.io，公开 JSON API
  3. mcp.so / agentskills.io / skillsmp  没有公开 JSON 接口，
     只在仓库里出现它们的具体 URL 时去抓页面标题和许可证（尽力而为）
  4. GitHub          通用兜底：按名字搜仓库，许可证从 /license 接口或 LICENSE 正文识别

解析顺序遵循"先精确、后搜索、最后大模型裁决"，每个环节都可降级，
任何一步网络失败都不会让整条流水线崩掉。
"""

from __future__ import annotations

import json
import os
import re
import time
from difflib import SequenceMatcher

import requests

from github.api import get_json as github_get_json
from github.license import detect_from_text
from huggingface.api import get_model_info, get_model_license, get_readme, search_models

KIND_MODEL = "model"
KIND_DATASET = "dataset"
KIND_TOOL = "tool"
KINDS = (KIND_MODEL, KIND_DATASET, KIND_TOOL)

# 托管/API 模型没有"源码仓库"，它的"仓库"就是服务商的模型目录页。
# 名字不带 "/" 且命中这些前缀时，按服务商目录解析，而不是去 Hugging Face 上
# 找一个同名但毫不相干的个人仓库（实测 claude-sonnet-5 会被跑到 oroboros-labs 名下）。
PROVIDER_CATALOG = [
    (re.compile(r"^(claude|anthropic|opus|sonnet|haiku)", re.I), "anthropic", "Anthropic",
     "https://docs.anthropic.com/en/docs/about-claude/models"),
    (re.compile(r"^(gpt|chatgpt|o[1-4]\b|davinci|curie|babbage|text-embedding|dall-e|whisper|sora)", re.I),
     "openai", "OpenAI", "https://platform.openai.com/docs/models"),
    (re.compile(r"^(gemini|palm|imagen|veo|learnlm)", re.I), "google", "Google",
     "https://ai.google.dev/gemini-api/docs/models"),
    (re.compile(r"^deepseek", re.I), "deepseek", "DeepSeek",
     "https://api-docs.deepseek.com/quick_start/pricing"),
    (re.compile(r"^(glm|chatglm)", re.I), "zhipu", "Zhipu AI",
     "https://open.bigmodel.cn/dev/api"),
    (re.compile(r"^(qwen|qwq)", re.I), "alibaba", "Alibaba Cloud",
     "https://help.aliyun.com/zh/model-studio/models"),
    (re.compile(r"^(mistral|mixtral|codestral|pixtral)", re.I), "mistral", "Mistral AI",
     "https://docs.mistral.ai/getting-started/models/"),
    (re.compile(r"^(llama|meta-llama)", re.I), "meta", "Meta",
     "https://www.llama.com/models/"),
    (re.compile(r"^(command|cohere|embed-english|rerank)", re.I), "cohere", "Cohere",
     "https://docs.cohere.com/docs/models"),
    (re.compile(r"^(ernie|wenxin)", re.I), "baidu", "Baidu",
     "https://cloud.baidu.com/doc/WENXINWORKSHOP/index.html"),
    (re.compile(r"^(moonshot|kimi)", re.I), "moonshot", "Moonshot AI",
     "https://platform.moonshot.cn/docs"),
]

HF_BASE = os.getenv("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
MCP_REGISTRY = "https://registry.modelcontextprotocol.io/v0/servers"
# skillsmp 的公开 JSON 接口（实测可用，不需要 key）。
# 官方文档在 /docs/api，v1 端点 /api/v1/skills/search?q= 需要 query 且会限流，
# 这里优先用更稳的 /api/skills?search=。
SKILLSMP_API = "https://skillsmp.com/api/skills"
TIMEOUT = int(os.getenv("REGISTRY_TIMEOUT", "30"))

_CACHE_ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".cache", "reg")
_cache_enabled = True
HEALTH = {"live": 0, "cache_hits": 0, "failures": 0}


def set_cache_enabled(flag):
    global _cache_enabled
    _cache_enabled = bool(flag)


def reset_health():
    HEALTH.update(live=0, cache_hits=0, failures=0)


# --------------------------------------------------------------------------
# 通用 HTTP（带缓存 + 重试）
# --------------------------------------------------------------------------

def _cache_path(kind, key):
    safe = re.sub(r"[^\w.\-]+", "__", str(key))[:140]
    return os.path.join(_CACHE_ROOT, kind, safe + ".json")


def _http_json(url, cache_kind, cache_key, params=None, retries=3, as_text=False):
    """返回 (status, payload)。status=None 表示网络失败（不写缓存）。

    重试次数可用 REGISTRY_RETRIES 覆盖：被注册中心限流时，默认的 3 次重试
    会让每个候选耗掉近 90 秒，一个仓库几十个候选就卡十几分钟。
    """
    retries = max(1, int(os.getenv("REGISTRY_RETRIES", retries)))
    path = _cache_path(cache_kind, cache_key)
    if _cache_enabled and os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as handle:
                cached = json.load(handle)
            HEALTH["cache_hits"] += 1
            return cached.get("status"), cached.get("payload")
        except Exception:
            pass

    last = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=TIMEOUT,
                                headers={"User-Agent": "hf-supply-chain-demo",
                                         "Accept": "*/*" if as_text else "application/json"})
        except Exception as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(1.0 * (attempt + 1))
            continue
        HEALTH["live"] += 1
        if resp.status_code in (200, 404):
            if as_text:
                payload = resp.text
            else:
                try:
                    payload = resp.json()
                except Exception:
                    payload = None
            if _cache_enabled:
                try:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "w", encoding="utf-8") as handle:
                        json.dump({"status": resp.status_code, "payload": payload},
                                  handle, ensure_ascii=False)
                except Exception:
                    pass
            return resp.status_code, payload
        if resp.status_code in (401, 403):
            return resp.status_code, None
        last = "HTTP %s" % resp.status_code
        if attempt < retries - 1:
            time.sleep(1.0 * (attempt + 1))

    HEALTH["failures"] += 1
    return None, None


def make_artifact(name, kind, registry, url, license_name="unknown",
                  license_source="unknown", score=1.0, raw_name=None, extra=None):
    return {
        "name": name,
        "kind": kind,
        "registry": registry,
        "url": url,
        "license": license_name or "unknown",
        "license_source": license_source or "unknown",
        "score": round(float(score), 3),
        "raw_name": raw_name or name,
        "extra": extra or {},
    }


# --------------------------------------------------------------------------
# 服务商模型目录（托管/API 模型走这条）
# --------------------------------------------------------------------------

def resolve_provider_model(raw):
    """名字像某家的托管模型时，解析到该服务商的模型目录页。

    这类模型没有可拉取的开源仓库，许可证通常是服务商条款而不是开源许可证，
    所以许可证记为 proprietary（来源 provider-terms）。
    """
    if not raw or "/" in raw:          # 带 org/ 的按 Hugging Face / GitHub 走
        return None
    for pattern, provider, display, url in PROVIDER_CATALOG:
        if pattern.match(raw):
            return make_artifact(
                raw, KIND_MODEL, "provider-catalog", url,
                "proprietary", "provider-terms", 0.9, raw,
                {"provider": provider, "provider_name": display,
                 "note": "托管模型，无开源源码仓库；许可证为服务商条款"})
    return None


# --------------------------------------------------------------------------
# Hugging Face：模型
# --------------------------------------------------------------------------

def resolve_hf_model(raw):
    info = get_model_info(raw)
    method, score = "exact", 1.0
    if not info:
        candidates = search_models(raw, limit=15)
        if raw.split("/")[-1] != raw:
            candidates += search_models(raw.split("/")[-1], limit=15)
        best, best_score = None, 0.0
        for item in candidates:
            mid = item["id"]
            if mid.lower() == raw.lower():
                score_val = 1.0
            elif mid.split("/")[-1].lower() == raw.lower():
                score_val = 0.97
            else:
                score_val = SequenceMatcher(None, raw.lower(), mid.lower()).ratio() * 0.85
            if score_val > best_score:
                best, best_score = mid, score_val
        if not best or best_score < 0.60:
            return None
        info = get_model_info(best)
        method, score = "search", best_score
        if not info:
            return None

    readme = get_readme(info["model"])
    license_name, license_source = get_model_license(
        info["model"], info=info, readme=readme, use_llm=True)
    return make_artifact(info["model"], KIND_MODEL, "huggingface", info["url"],
                         license_name, license_source, score, raw,
                         {"match": method, "downloads": info.get("downloads")})


# --------------------------------------------------------------------------
# Hugging Face：数据集
# --------------------------------------------------------------------------

def hf_dataset_info(name):
    status, data = _http_json("%s/api/datasets/%s" % (HF_BASE, name),
                              "hf_dataset", name)
    if status != 200 or not isinstance(data, dict):
        return None
    card = data.get("cardData") or {}
    license_name = card.get("license")
    if isinstance(license_name, list):
        license_name = ", ".join(str(x) for x in license_name)
    source = "dataset-card"
    if not license_name:
        for tag in data.get("tags") or []:
            if isinstance(tag, str) and tag.lower().startswith("license:"):
                license_name = tag.split(":", 1)[1]
                source = "dataset-tags"
                break
    return {
        "id": data.get("id") or name,
        "url": "%s/datasets/%s" % (HF_BASE, data.get("id") or name),
        "license": license_name or "unknown",
        "license_source": source if license_name else "unknown",
        "downloads": data.get("downloads"),
    }


def hf_dataset_search(keyword, limit=15):
    status, data = _http_json("%s/api/datasets" % HF_BASE, "hf_dataset_search",
                              "%s_%d" % (keyword, limit),
                              params={"search": keyword, "limit": limit,
                                      "sort": "downloads", "direction": -1},
                              retries=2)
    if status != 200 or not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict) and item.get("id")]


def resolve_hf_dataset(raw):
    info = hf_dataset_info(raw)
    score, method = 1.0, "exact"
    if not info:
        best, best_score = None, 0.0
        for item in hf_dataset_search(raw, limit=15):
            did = item["id"]
            name = did.split("/")[-1].lower()
            if name == raw.lower():
                score_val = 0.97
            else:
                score_val = SequenceMatcher(None, raw.lower(), name).ratio() * 0.85
            if score_val > best_score:
                best, best_score = did, score_val
        if not best or best_score < 0.60:
            return None
        info = hf_dataset_info(best)
        score, method = best_score, "search"
        if not info:
            return None
    return make_artifact(info["id"], KIND_DATASET, "huggingface", info["url"],
                         info["license"], info["license_source"], score, raw,
                         {"match": method, "downloads": info.get("downloads")})


# --------------------------------------------------------------------------
# skillsmp（Agent Skills 市场，有公开 JSON 接口）
# --------------------------------------------------------------------------

# 通用库/品牌名不适合拿去技能市场匹配："
# transformers" 会命中某个人的 skills/transformers 目录，"openai" 会命中
# openai-whisper-api —— 这类匹配全是噪声，直接跳过 skillsmp 这一级。
GENERIC_LIBRARY_NAMES = {
    "openai", "anthropic", "google", "gemini", "claude", "langchain", "llama-index",
    "llamaindex", "transformers", "sentence-transformers", "sentence_transformers",
    "huggingface-hub", "huggingface", "torch", "pytorch", "tensorflow", "onnxruntime",
    "onnx", "vllm", "ollama", "mistral", "cohere", "replicate", "mcp", "markitdown",
}


def skillsmp_search(keyword, limit=10):
    status, data = _http_json(SKILLSMP_API, "skillsmp", "%s_%d" % (keyword, limit),
                              params={"search": keyword, "limit": limit,
                                      "sortBy": "stars"}, retries=2)
    if status != 200 or not isinstance(data, dict):
        return []
    return [item for item in (data.get("skills") or [])
            if isinstance(item, dict) and item.get("name")]


def resolve_skillsmp(raw):
    """技能市场：按名字查 Skill，URL 用它的 GitHub 源，许可证从 GitHub 取。

    只接受"名字完全一致"的匹配。降级成包含/相似匹配会大量误配——
    实测 "openai" 会命中 openai-whisper-api、"transformers" 会命中某个人的
    skills/transformers 目录。
    """
    if not raw or raw.strip().lower() in GENERIC_LIBRARY_NAMES:
        return None

    hits = skillsmp_search(raw, limit=10)
    if not hits:
        return None

    target = raw.lower()
    short = target.split("/")[-1]
    best, best_score = None, 0.0
    for hit in hits:
        name = str(hit.get("name") or "").lower()
        author = str(hit.get("author") or "").lower()
        full = "%s/%s" % (author, name) if author else name
        if name == short or full == target:
            score = 1.0
        elif full.endswith("/" + target) or name == target:
            score = 0.95
        else:
            score = 0.0
        if score > best_score:
            best, best_score = hit, score
    if not best or best_score < 0.95:
        return None

    github_url = best.get("githubUrl") or ""
    owner = best.get("author") or ""
    name = best.get("name") or ""
    display = ("%s/%s" % (owner, name)) if owner else name
    url = github_url or ("https://skillsmp.com/skills/%s" % (best.get("id") or name))
    if github_url:
        license_name, license_source = github_license_from_url(github_url)
    else:
        license_name, license_source = "unknown", "unknown"

    return make_artifact(display, KIND_TOOL, "skillsmp", url,
                         license_name, license_source, best_score, raw,
                         {"description": best.get("description"),
                          "stars": best.get("stars"),
                          "github": github_url,
                          "path": best.get("path")})


# --------------------------------------------------------------------------
# MCP 官方注册中心
# --------------------------------------------------------------------------

def mcp_registry_search(keyword, limit=10):
    status, data = _http_json(MCP_REGISTRY, "mcp_search", "%s_%d" % (keyword, limit),
                              params={"search": keyword, "limit": limit}, retries=2)
    if status != 200 or not isinstance(data, dict):
        return []
    out = []
    for entry in data.get("servers") or []:
        server = entry.get("server") or {}
        if not server.get("name"):
            continue
        out.append({
            "name": server.get("name"),
            "description": server.get("description") or "",
            "repo": (server.get("repository") or {}).get("url") or "",
            "version": server.get("version"),
            "website": server.get("websiteUrl") or server.get("homepage") or "",
        })
    return out


def resolve_mcp_server(raw):
    hits = mcp_registry_search(raw, limit=10)
    if not hits:
        short = raw.split("/")[-1]
        if short != raw:
            hits = mcp_registry_search(short, limit=10)
    if not hits:
        return None

    target = raw.lower()
    best, best_score = None, 0.0
    for hit in hits:
        full = str(hit["name"]).lower()
        short = full.split("/")[-1]
        if full == target:
            score = 1.0
        elif short == target or short == target.split("/")[-1]:
            score = 0.95
        elif target in full:
            score = 0.80
        else:
            score = SequenceMatcher(None, target, short).ratio() * 0.7
        if score > best_score:
            best, best_score = hit, score
    # MCP 注册中心里同名/近名的服务很多，松匹配会把完全无关的服务配上来，
    # 所以这里要求"短名完全一致"级别的分数
    if not best or best_score < 0.85:
        return None

    url = best["repo"] or best["website"] or ("%s/%s" % (MCP_REGISTRY, best["name"]))
    license_name, license_source = github_license_from_url(best["repo"])
    return make_artifact(best["name"], KIND_TOOL, "mcp-registry", url,
                         license_name, license_source, best_score, raw,
                         {"description": best["description"],
                          "version": best.get("version")})


# --------------------------------------------------------------------------
# 社区站（mcp.so / agentskills.io / skillsmp）：尽力而为
# --------------------------------------------------------------------------

COMMUNITY_HOSTS = {
    "mcp.so": "mcp.so",
    "agentskills.io": "agentskills.io",
    "skillsmp.com": "skillsmp.com",
    "claudeskills.dev": "claudeskills.dev",
}

_LICENSE_WORDS = re.compile(
    r"\b(MIT|Apache[- ]2\.0|GPL[- ]?[23]\.0|AGPL[- ]?3\.0|LGPL[- ]?3\.0|BSD[- ]?3[- ]Clause|"
    r"BSD[- ]?2[- ]Clause|MPL[- ]?2\.0|ISC|Unlicense|CC0[- ]?1\.0|CC[- ]BY[- ]?4\.0)\b", re.I)

# 页面里这些仓库是"导航/awesome 列表"性质的，不是该资产自己的源码仓库
_REPO_NOISE = {
    "chatmcp/mcp-directory", "modelcontextprotocol/servers", "punkpeye/awesome-mcp-servers",
    "modelcontextprotocol/python-sdk", "modelcontextprotocol/typescript-sdk",
}
_GITHUB_REPO_RE = re.compile(r"https://github\.com/([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+)")


def _extract_repo_from_page(html):
    """从社区站页面里抽出该资产自己的 GitHub 仓库（页面是 SSR 的，链接就在 HTML 里）。"""
    found = []
    for match in _GITHUB_REPO_RE.finditer(html or ""):
        owner = match.group(1)
        repo = re.sub(r"\.git$", "", match.group(2))
        if repo in ("", "blob", "tree", "issues", "pull"):
            continue
        full = "%s/%s" % (owner, repo)
        if full.lower() in _REPO_NOISE:
            continue
        if full not in found:
            found.append(full)
        if len(found) >= 5:
            break
    return found


def _page_title(html):
    match = re.search(r"<title>(.*?)</title>", html or "", re.S | re.I)
    if not match:
        return ""
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    title = re.sub(r"\s*[|｜]\s*(MCP\.so|SkillsMP|agentskills\.io).*$", "", title, flags=re.I)
    title = re.sub(r"\s*[:\-–—]\s*(Tools|Setup|Config).*$", "", title, flags=re.I)
    return title[:120]


def resolve_community_url(url):
    """仓库里直接写了社区站的具体 URL 时：抓页面拿名字、GitHub 仓库、许可证。

    实测 mcp.so 的 /servers/<slug> 页是服务端渲染的，HTML 里带
    `https://github.com/owner/repo`，所以"只给一个 URL"也能反查到源码仓库，
    再用 GitHub 的许可证接口拿到权威许可证名。
    """
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    site = COMMUNITY_HOSTS.get(host, host)
    status, html = _http_json(url, "community", url, as_text=True, retries=2)
    if status != 200 or not html:
        return None

    title = _page_title(html)
    repos = _extract_repo_from_page(html)
    slug = url.rstrip("/").split("/")[-1]

    license_name, license_source = "unknown", "unknown"
    if repos:
        # 有源码仓库就以 GitHub 为准（比页面上的文字可靠）
        license_name, license_source = github_license_from_url("https://github.com/" + repos[0])
    if license_name == "unknown":
        found = _LICENSE_WORDS.search(html)
        if found:
            license_name, license_source = found.group(1), "page-scan"

    name = repos[0] if repos else (title or slug)
    target_url = ("https://github.com/" + repos[0]) if repos else url
    return make_artifact(name, KIND_TOOL, site, target_url,
                         license_name, license_source, 0.9, url,
                         {"title": title, "listing": url,
                          "repo_candidates": repos,
                          "resolved_via": "page → github" if repos else "page"})


# --------------------------------------------------------------------------
# GitHub：通用兜底 + 许可证识别
# --------------------------------------------------------------------------

_LICENSE_FILES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "LICENSE-MIT",
                  "LICENSE-APACHE")


def github_license_from_url(repo_url):
    """从 GitHub 仓库地址拿许可证名字。先走 API，再回退抓 LICENSE 正文。"""
    if not repo_url:
        return "unknown", "unknown"
    match = re.search(r"github\.com[/:]([^/\s]+)/([^/\s#?]+)", repo_url)
    if not match:
        return "unknown", "unknown"
    owner, repo = match.group(1), re.sub(r"\.git$", "", match.group(2))
    full = "%s/%s" % (owner, repo)

    data = github_get_json("/repos/%s/license" % full)
    if data:
        lic = data.get("license") or {}
        spdx = lic.get("spdx_id")
        if spdx and spdx != "NOASSERTION":
            return spdx, "github-api"

    for name in _LICENSE_FILES:
        for branch in ("HEAD", "main", "master"):
            raw = "https://raw.githubusercontent.com/%s/%s/%s" % (full, branch, name)
            status, text = _http_json(raw, "gh_license", "%s_%s_%s" % (full, branch, name),
                                      as_text=True, retries=1)
            if status == 200 and text:
                detected = detect_from_text(text)
                if detected:
                    return detected, "license-file"
    return "unknown", "unknown"


def github_search(keyword, limit=8):
    data = github_get_json("/search/repositories?q=%s&sort=stars&per_page=%d"
                           % (requests.utils.quote(keyword), limit))
    if not data or not isinstance(data, dict):
        return []
    out = []
    for item in data.get("items") or []:
        out.append({
            "full_name": item.get("full_name"),
            "url": item.get("html_url"),
            "description": item.get("description") or "",
            "stars": item.get("stargazers_count") or 0,
            "license": ((item.get("license") or {}).get("spdx_id") or "unknown"),
        })
    return out


def resolve_github(raw_name, kind):
    """通用兜底：按名字搜 GitHub 仓库，命中后取许可证。"""
    hits = github_search(raw_name, limit=8)
    if not hits:
        return None
    short = raw_name.split("/")[-1].lower()
    best, best_score = None, 0.0
    for hit in hits:
        full = (hit["full_name"] or "").lower()
        name = full.split("/")[-1]
        if full == raw_name.lower():
            score = 1.0
        elif name == short:
            score = 0.93
        elif short in name:
            score = 0.78
        else:
            score = SequenceMatcher(None, short, name).ratio() * 0.7
        if score > best_score:
            best, best_score = hit, score
    if not best or best_score < 0.85:
        return None
    license_name = best["license"]
    source = "github-api"
    if not license_name or license_name in ("unknown", "NOASSERTION"):
        license_name, source = github_license_from_url(best["url"])
    return make_artifact(best["full_name"], kind, "github", best["url"],
                         license_name, source, best_score, raw_name,
                         {"description": best.get("description"),
                          "stars": best.get("stars")})


# --------------------------------------------------------------------------
# 统一解析入口
# --------------------------------------------------------------------------

_LLM_SYSTEM = "你是 AI 供应链分析专家，只输出 JSON，不要解释。"


def classify_kind(raw, url="", context=""):
    """猜这个名字属于 model / dataset / tool（先规则，再大模型）。"""
    low = (raw or "").lower()

    if url:
        host = re.sub(r"^https?://", "", url).split("/")[0].lower()
        if host in COMMUNITY_HOSTS:
            return KIND_TOOL
    if "dataset" in low or low.startswith("hf-dataset"):
        return KIND_DATASET
    if re.search(r"^@[\w.\-]+/", low):                  # npm 作用域包 → 工具
        return KIND_TOOL
    if re.search(r"(mcp|skill|agent|server|tool|cli)$", low):
        return KIND_TOOL
    if re.search(r"(claude|gpt|gemini|deepseek|glm|qwen|llama|mistral|ollama)[\w.\-]*$", low):
        return KIND_MODEL

    from llm import chat_json
    data = chat_json(
        "判断下面这个名字属于哪一类 AI 资产：model（模型）、dataset（数据集）、tool（工具/MCP 服务/Skill/CLI）。\n"
        "名字：%r\n出现的上下文（可能为空）：%s\n"
        '只输出 JSON：{"kind": "model|dataset|tool", "reason": "一句话"}'
        % (raw, (context or "")[:600]), system=_LLM_SYSTEM)
    if isinstance(data, dict):
        kind = str(data.get("kind") or "").strip().lower()
        if kind in KINDS:
            return kind
    return KIND_MODEL


def resolve_artifact(raw, kind_hint=None, context="", use_llm=True):
    """把一个原始名字解析成 Artifact；找不到返回 None。"""
    if not raw or len(raw) < 2:
        return None
    raw = raw.strip()
    kind = kind_hint or classify_kind(raw, context=context)

    attempts = []
    if kind == KIND_MODEL:
        # 先看是不是托管服务商的 API 模型（这类没有开源源码仓库）
        attempts.append(("provider-catalog", lambda: resolve_provider_model(raw)))
        attempts.append(("hf-model", lambda: resolve_hf_model(raw)))
        # 带 "/" 的名字是"org/model"形式的模型 ID，不是仓库名。
        # 这种绝不能拿去 GitHub 搜仓库：实测 openai/gpt-4o-mini 会被配到
        # 一个毫不相干的个人项目（wifiuk/OpenAI-GPT-4o-Mini-TTS-...）。
        if "/" not in raw:
            attempts.append(("github", lambda: resolve_github(raw, kind)))
    elif kind == KIND_DATASET:
        attempts = [("hf-dataset", lambda: resolve_hf_dataset(raw)),
                    ("github", lambda: resolve_github(raw, kind))]
    else:
        attempts = [("mcp-registry", lambda: resolve_mcp_server(raw)),
                    ("skillsmp", lambda: resolve_skillsmp(raw)),
                    ("github", lambda: resolve_github(raw, kind))]

    for label, func in attempts:
        try:
            artifact = func()
        except Exception:
            artifact = None
        if artifact:
            artifact["resolved_via"] = label
            artifact["kind"] = kind
            return artifact
    return None


def resolve_url_literal(url):
    """仓库里出现的 URL：判断是不是某个社区的资产页，能抓就抓。"""
    if not url or not url.startswith("http"):
        return None
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    if host in COMMUNITY_HOSTS:
        return resolve_community_url(url)
    if host in ("huggingface.co", "hf.co"):
        parts = url.split("huggingface.co/")[-1].split("?")[0].strip("/")
        if parts.startswith("datasets/"):
            return resolve_hf_dataset(parts[len("datasets/"):])
        pieces = parts.split("/")
        if len(pieces) >= 2:
            return resolve_hf_model("/".join(pieces[:2]))
    if host == "github.com":
        pieces = [p for p in url.split("github.com/")[-1].split("/") if p]
        if len(pieces) >= 2:
            full = "%s/%s" % (pieces[0], pieces[1])
            license_name, source = github_license_from_url("https://github.com/" + full)
            return make_artifact(full, KIND_TOOL, "github",
                                 "https://github.com/" + full,
                                 license_name, source, 0.9, url)
    return None
