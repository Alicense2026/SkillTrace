# -*- coding: utf-8 -*-
"""把代码里出现的模型字符串，解析成 Hugging Face 上真实存在的模型 id。

三种手段，逐级兜底：
  1. 直接命中：字符串本身就是完整的 HF id
  2. 搜索 + 打分：在 HF 上搜同名模型，按"名字相似度 + 下载量"排序
  3. 大模型裁决：前几名分数接近时，让 DeepSeek 结合调用代码选出真正的那个
"""

from __future__ import annotations

from difflib import SequenceMatcher

from huggingface.api import get_model_info, search_models

ACCEPT_THRESHOLD = 0.60      # 低于这个分数认为"没找到对应模型"
AMBIGUOUS_GAP = 0.06         # 前几名分差小于它就算有歧义，交给大模型

SYSTEM_PROMPT = "你是 Hugging Face 模型检索专家，只输出 JSON。"


def _similarity(left, right):
    return SequenceMatcher(None, left.lower(), right.lower()).ratio()


def score_candidate(query, model_id, downloads=None):
    """给一个候选 HF id 打分（0~1）。"""
    q = (query or "").lower().strip()
    m = (model_id or "").lower()
    if not q or not m:
        return 0.0

    if q == m:
        base = 1.0
    elif m.split("/")[-1] == q:
        base = 0.97
    elif q.split("/")[-1] == m.split("/")[-1]:
        base = 0.93
    elif q in m or m in q:
        base = 0.78
    else:
        base = _similarity(q, m) * 0.8

    if downloads:
        base += min(downloads / 2_000_000.0, 0.04)   # 热门模型略微加权
    return round(min(base, 1.0), 3)


def _llm_pick(candidate, context, options):
    from llm import chat_json

    listing = "\n".join("%d. %s" % (i + 1, opt) for i, opt in enumerate(options))
    data = chat_json(
        "一段 GitHub 仓库代码里出现了模型名 %r，它在 Hugging Face 上可能对应下面几个仓库：\n%s\n\n"
        "调用代码：\n%s\n\n"
        "请判断代码真正加载的是哪一个。\n"
        '只输出 JSON：{"model": "完整id", "reason": "一句话理由"}\n'
        '如果都无法确定，model 填空字符串。'
        % (candidate, listing, (context or "")[:1200]),
        system=SYSTEM_PROMPT,
    )
    if not isinstance(data, dict):
        return None
    chosen = str(data.get("model") or "").strip()
    return chosen if chosen in options else None


def resolve_model(candidate, context="", use_llm=True):
    """返回 {"model", "score", "method", "info"}；找不到返回 None。"""
    if not candidate:
        return None

    # 1) 直接命中
    info = get_model_info(candidate)
    if info:
        return {"model": info["model"], "score": 1.0, "method": "exact", "info": info}

    # 2) 搜索
    pool = {}
    keywords = {candidate, candidate.split("/")[-1]}
    for keyword in keywords:
        for item in search_models(keyword, limit=15):
            pool[item["id"]] = item
    if not pool:
        return None

    scored = sorted(
        ((score_candidate(candidate, mid, item.get("downloads")), mid, item)
         for mid, item in pool.items()),
        key=lambda row: -row[0],
    )
    best_score, best_id, _ = scored[0]
    if best_score < ACCEPT_THRESHOLD:
        return None

    method = "search"
    close = [row[1] for row in scored if row[0] >= best_score - AMBIGUOUS_GAP]
    if use_llm and len(close) > 1:
        chosen = _llm_pick(candidate, context, close[:5])
        if chosen:
            for score, mid, item in scored:
                if mid == chosen:
                    best_score, best_id, method = score, mid, "search+llm"
                    break

    return {
        "model": best_id,
        "score": best_score,
        "method": method,
        "info": get_model_info(best_id),
    }
