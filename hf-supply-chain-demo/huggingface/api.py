# -*- coding: utf-8 -*-
"""Hugging Face Hub 的 HTTP 接口封装。

三个设计要点：

1. 直接用 requests，不走 huggingface_hub。
   它默认把模型卡缓存写到 ~/.cache/huggingface，受限环境里那个目录常常不可写；
   而这些元数据本来就是简单的 REST 接口，直接请求更轻、更可控。

2. 带重试。huggingface.co 偶尔会 SSL 断开（UNEXPECTED_EOF），
   单次失败不代表模型不存在，所以默认重试 3 次。

3. 带本地磁盘缓存（默认 .cache/hf/）。
   一个 demo 往往要反复跑同一个仓库，缓存既能避免重复请求被限流，
   也让网络抖动时的结果保持稳定、可复现。
   缓存只记录"服务器明确返回的结果"（200 / 404），
   网络失败不会被当成"模型不存在"写进缓存。

需要访问私有/受限模型时，在 .env 里配 HF_TOKEN。
"""

from __future__ import annotations

import json
import os
import re
import time

import requests

HF_BASE = os.getenv("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
API_MODELS = HF_BASE + "/api/models"
TIMEOUT = 40

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_ROOT = os.getenv("HF_DEMO_CACHE_DIR", os.path.join(_PROJECT_ROOT, ".cache", "hf"))

_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)

_cache_enabled = True

# 运行情况统计，方便在结果末尾提示"这次是不是网络出了问题"
HEALTH = {"network_failures": 0, "cache_hits": 0, "live_requests": 0}


def set_cache_enabled(flag):
    global _cache_enabled
    _cache_enabled = bool(flag)


def reset_health():
    HEALTH.update(network_failures=0, cache_hits=0, live_requests=0)


# --------------------------------------------------------------------------
# 缓存
# --------------------------------------------------------------------------

def _cache_path(kind, key, suffix=".json"):
    safe = re.sub(r"[^\w.\-]+", "__", str(key))[:150]
    return os.path.join(CACHE_ROOT, kind, safe + suffix)


def _cache_load(path):
    if not _cache_enabled or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def _cache_save(path, payload):
    if not _cache_enabled:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
    except Exception:
        pass


# --------------------------------------------------------------------------
# 带重试 / 缓存的 GET
# --------------------------------------------------------------------------

def _headers(json_response=True):
    head = {"User-Agent": "hf-supply-chain-demo"}
    head["Accept"] = "application/json" if json_response else "*/*"
    token = os.getenv("HF_TOKEN")
    if token:
        head["Authorization"] = "Bearer %s" % token
    return head


def _get(url, *, cache_kind, cache_key, as_text=False, params=None, retries=3):
    """返回 (status_code, payload)。

    status_code 为 None 表示网络层面失败（重试后仍然失败），
    payload 在 as_text 模式下是字符串，否则是解析好的 JSON。
    """
    path = _cache_path(cache_kind, cache_key)
    cached = _cache_load(path)
    if cached is not None:
        HEALTH["cache_hits"] += 1
        return cached.get("status"), cached.get("payload")

    last_error = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=_headers(not as_text), params=params,
                                timeout=TIMEOUT)
        except Exception as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(1.0 * (attempt + 1))
            continue

        HEALTH["live_requests"] += 1
        if resp.status_code == 200:
            payload = resp.text if as_text else _safe_json(resp)
            if not as_text and payload is None:
                return None, None            # 返回体坏掉：当网络问题处理，不写缓存
            _cache_save(path, {"status": 200, "payload": payload})
            return 200, payload
        if resp.status_code == 404:
            _cache_save(path, {"status": 404, "payload": None})
            return 404, None
        if resp.status_code in (401, 403):   # 需要 token / 被限流：不重试
            return resp.status_code, None
        last_error = "HTTP %s" % resp.status_code
        if attempt < retries - 1:
            time.sleep(1.0 * (attempt + 1))

    HEALTH["network_failures"] += 1
    if last_error is not None:
        return None, None
    return None, None


def _safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return None


# --------------------------------------------------------------------------
# 模型信息
# --------------------------------------------------------------------------

def _normalize_license(value):
    if isinstance(value, (list, tuple)):
        names = [str(v).strip() for v in value if str(v).strip()]
        return ", ".join(names) if names else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def readme_front_matter_license(readme):
    """从 README 顶部的 YAML front-matter 里抠出 license 字段。"""
    if not readme:
        return None
    match = _FRONT_MATTER_RE.match(readme.lstrip("\ufeff"))
    if not match:
        return None
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        if key.strip().lower() in ("license", "license_name"):
            return _normalize_license(value.strip().strip("'\""))
    return None


def get_model_info(model_id):
    """查询模型是否存在及其元信息；返回 dict，或 None（不存在/查询失败）。"""
    if not model_id:
        return None
    status, data = _get("%s/%s" % (API_MODELS, model_id),
                        cache_kind="model_info", cache_key=model_id)
    if status != 200 or not isinstance(data, dict) or not data.get("id"):
        return None

    info = {
        "model": data.get("modelId") or data.get("id"),
        "url": "%s/%s" % (HF_BASE, data.get("id")),
        "downloads": data.get("downloads"),
        "likes": data.get("likes"),
        "pipeline_tag": data.get("pipeline_tag"),
        "gated": data.get("gated"),
        "author": data.get("author"),
        "license": None,
        "license_source": "unknown",
    }

    card = data.get("cardData") or {}
    name = _normalize_license(card.get("license")) or _normalize_license(card.get("license_name"))
    if name:
        info["license"] = name
        info["license_source"] = "model-card"
        return info

    for tag in data.get("tags") or []:
        if isinstance(tag, str) and tag.lower().startswith("license:"):
            info["license"] = tag.split(":", 1)[1].strip()
            info["license_source"] = "model-tags"
            return info

    return info


def get_readme(model_id):
    """下载模型卡的 README.md 原文（找不到返回 None）。"""
    if not model_id:
        return None
    for revision in ("main", "refs%2Fpr%2F1"):
        status, text = _get("%s/%s/raw/%s/README.md" % (HF_BASE, model_id, revision),
                            cache_kind="readme", cache_key="%s@%s" % (model_id, revision),
                            as_text=True, retries=2)
        if status == 200 and text and text.strip():
            return text
        if status == 404:
            continue
        if status is None:
            return None                       # 网络问题，别继续瞎试
    return None


def search_models(keyword, limit=15):
    """按关键词搜索 HF 模型，按下载量倒序，返回 [{id, downloads, ...}]。"""
    if not keyword:
        return []
    params = {"search": keyword, "limit": limit, "sort": "downloads", "direction": -1}
    status, data = _get(API_MODELS, cache_kind="search",
                        cache_key="%s_%d" % (keyword, limit), params=params, retries=2)
    if status != 200 or not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict) and item.get("id")]


# --------------------------------------------------------------------------
# 模型许可证
# --------------------------------------------------------------------------

def detect_license_with_llm(model_id, readme):
    """模型卡没有 license 字段时，让 DeepSeek 读 README 猜一个。"""
    from llm import chat_json

    data = chat_json(
        "下面是 Hugging Face 模型 %s 的模型卡 README。\n"
        "请判断该模型使用的许可证（SPDX 名字，如 apache-2.0 / mit / cc-by-nc-4.0）。\n"
        '只输出 JSON：{"license": "apache-2.0", "confidence": "high|low", "reason": "一句话理由"}\n'
        'README 里没有许可证信息时 license 填 "unknown"。\n\n'
        "README：\n%s" % (model_id, (readme or "")[:6000])
    )
    if not isinstance(data, dict):
        return None
    value = str(data.get("license") or "").strip()
    if not value or value.lower() in ("unknown", "none", "null"):
        return None
    return value


def get_model_license(model_id, info=None, readme=None, use_llm=True):
    """返回 (许可证名字, 来源)。优先级：模型卡 -> tags -> README front-matter -> 大模型。"""
    info = info if info is not None else get_model_info(model_id)
    if info and info.get("license"):
        return info["license"], info.get("license_source") or "model-card"

    if readme is None:
        readme = get_readme(model_id)
    name = readme_front_matter_license(readme)
    if name:
        return name, "readme-front-matter"

    if use_llm and readme:
        guess = detect_license_with_llm(model_id, readme)
        if guess:
            return guess, "llm-from-readme"

    return "unknown", "unknown"
