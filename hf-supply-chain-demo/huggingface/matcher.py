# -*- coding: utf-8 -*-
"""调用方法比对：把 GitHub 仓库的调用代码，和 HF 模型卡 README 里的官方示例做对照。

思路（对应需求里的"如果一致就把它作为确认真正调用的证据"）：
  1. 从模型卡 README 里抽出所有官方调用示例（代码块）
  2. 看 GitHub 代码里的 【完整模型 ID】 是否也出现在模型卡 / 示例里
  3. 看两边用的是不是同一个调用 API（from_pretrained / SentenceTransformer / pipeline ...）
  4. 证据等级：
       强(strong)：完整模型ID + 调用API 两边都能对上
       中(medium)：代码里明确出现完整模型ID，但模型卡示例不是完全一致的写法
       弱(weak)  ：只匹配到模糊模型名，需要人工复核
  5. 可选：让 DeepSeek 再复核一遍"这两段用法是不是同一个模型/同一套 API"，
     大模型说"不一致"时会下调等级。
"""

from __future__ import annotations

import re

CODE_BLOCK_RE = re.compile(r"```[a-zA-Z0-9_+\-]*[ \t]*\r?\n(.*?)```", re.S)
USAGE_HINT_RE = re.compile(
    r"from_pretrained|SentenceTransformer|CrossEncoder|pipeline\s*\(|AutoModel|"
    r"AutoProcessor|AutoTokenizer|hf_hub_download|snapshot_download|\.generate\s*\("
)

SYSTEM_PROMPT = "你是 AI 供应链与开源许可证分析专家，只输出 JSON。"

LEVEL_LABEL = {"strong": "已确认(强)", "medium": "已确认(中)", "weak": "待人工复核(弱)"}


def extract_usage_snippets(readme, limit=10):
    """从模型卡 README 里抽出官方调用示例。"""
    if not readme:
        return []
    blocks = [block.strip() for block in CODE_BLOCK_RE.findall(readme)]
    usage = [block for block in blocks if USAGE_HINT_RE.search(block)]
    if not usage:
        usage = [line.strip() for line in readme.splitlines() if USAGE_HINT_RE.search(line)]
    return [item for item in usage if item][:limit]


def _llm_compare(model_id, github_code, hf_usage):
    from llm import chat_json

    if not github_code or not hf_usage:
        return None
    return chat_json(
        "下面是同一个 Hugging Face 模型的两段使用信息。\n\n"
        "【A. GitHub 仓库里的调用代码】\n%s\n\n"
        "【B. Hugging Face 模型卡 README 里的官方示例】\n%s\n\n"
        "模型: %s\n\n"
        "请判断 A 与 B 是否在用同一个库 / 同一种方式加载同一个模型。\n"
        '只输出 JSON：{"consistent": true, "reason": "一句话理由", "matched_api": "两边一致的调用方式"}'
        % (github_code[:1200], hf_usage[:1200], model_id),
        system=SYSTEM_PROMPT,
    )


def _aliases(model_id, original=None):
    """模型可能有别名：``distilbert/foo`` 与 ``foo`` 要都算命中。"""
    names = set()
    for value in (model_id, original):
        if not value:
            continue
        value = str(value).strip().lower()
        names.add(value)
        names.add(value.split("/")[-1])
    return {name for name in names if name}


def _pick_snippet(snippets, aliases, api_base):
    """挑最合适的官方示例：同时含模型名和调用API > 只含模型名 > 只含API > 第一个。"""
    def has_alias(text):
        low = text.lower()
        return any(alias in low for alias in aliases)

    for snippet in snippets:
        if has_alias(snippet) and api_base and api_base in snippet:
            return snippet
    for snippet in snippets:
        if has_alias(snippet):
            return snippet
    for snippet in snippets:
        if api_base and api_base in snippet:
            return snippet
    return snippets[0] if snippets else ""


def compare_usage(model_id, candidate, readme, use_llm=True, original=None):
    """返回 {"confirmed", "level", "reason", "hf_usage", "github_call", ...}"""
    candidate = candidate or {}
    code = candidate.get("code") or ""
    api = candidate.get("api") or ""
    api_base = api.split(".")[-1] if api else ""
    api_class = api.split(".")[0] if "." in api else ""

    names = _aliases(model_id, original)
    lower_code = code.lower()
    lower_readme = (readme or "").lower()

    id_in_code = any(name in lower_code for name in names)
    id_in_readme = bool(readme) and any(name in lower_readme for name in names)

    snippets = extract_usage_snippets(readme)
    best_snippet = _pick_snippet(snippets, names, api_base)

    # API 在【所有】官方示例里找，避免因为挑错片段而误判
    if snippets:
        api_in_readme = bool(api_base) and any(api_base in snippet for snippet in snippets)
        class_in_readme = bool(api_class) and any(api_class in snippet for snippet in snippets)
    else:
        api_in_readme = bool(api_base) and api_base in lower_readme
        class_in_readme = bool(api_class) and api_class in lower_readme

    if id_in_code and id_in_readme and (api_in_readme or class_in_readme):
        level = "strong"
        reason = "仓库代码里的完整模型ID与调用API，都能在 HF 模型卡官方示例里找到一致写法"
    elif id_in_code and (id_in_readme or api_in_readme or class_in_readme):
        level = "medium"
        reason = "仓库代码里明确出现了完整模型ID，但模型卡示例不是完全一致的写法"
    elif id_in_code:
        level = "medium" if not readme else "weak"
        reason = "仓库代码里明确了模型ID；HF 模型卡没有可直接对照的调用示例"
    else:
        level = "weak"
        reason = "只匹配到模糊模型名，未能在仓库代码里定位到完整模型ID"

    llm_reason = ""
    if use_llm:
        verdict = _llm_compare(model_id, code, best_snippet)
        if isinstance(verdict, dict):
            llm_reason = str(verdict.get("reason") or "")
            if verdict.get("consistent") is False and level != "strong":
                level = "weak"
                reason = "大模型复核认为调用方式不一致：%s" % llm_reason
            elif verdict.get("consistent") is True:
                matched_api = str(verdict.get("matched_api") or "").strip()
                reason = "%s；大模型复核一致%s" % (
                    reason, ("（%s）" % matched_api) if matched_api else "")

    return {
        "confirmed": level in ("strong", "medium"),
        "level": level,
        "reason": reason,
        "llm_reason": llm_reason,
        "id_in_code": id_in_code,
        "id_in_readme": id_in_readme,
        "api_in_readme": api_in_readme,
        "github_call": "%s:%s %s" % (candidate.get("file") or "?", candidate.get("line") or "?", code),
        "hf_usage": _focus_snippet(best_snippet, model_id, api_base) if best_snippet else "",
    }


def _squash(text, limit=260):
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


def _focus_snippet(snippet, model_id, api_base):
    """从一整块官方示例里，只挑出"加载这个模型"的那一行（外加最近的 import 行）。

    模型卡 README 的代码块往往很长（还带推理、写文件等），
    表格里只保留最相关的一两行，读起来才清晰。
    """
    lines = [line.rstrip() for line in (snippet or "").splitlines()]
    index = None
    for position, line in enumerate(lines):
        if model_id and model_id.lower() in line.lower():
            index = position
            break
    if index is None:
        for position, line in enumerate(lines):
            if api_base and api_base in line:
                index = position
                break
    if index is None:
        return _squash(snippet, 200)

    picked = []
    for position in range(index - 1, -1, -1):
        if lines[position].strip().startswith(("import ", "from ")):
            picked.append(lines[position])
            break
    picked.append(lines[index])
    return _squash("\n".join(picked), 240)


def format_evidence(model_id, candidate, comparison):
    """生成表格第 7 列的文本。"""
    candidate = candidate or {}
    comparison = comparison or {}
    tag = LEVEL_LABEL.get(comparison.get("level"), "待人工复核(弱)")

    where = "%s:%s" % (candidate.get("file") or "?", candidate.get("line") or "?")
    parts = ["[%s] %s %s" % (tag, where, _squash(candidate.get("code") or "", 300))]
    if comparison.get("hf_usage"):
        parts.append("HF模型卡官方用法: %s" % comparison["hf_usage"])
    if comparison.get("reason"):
        parts.append(comparison["reason"])
    return " ｜ ".join(part for part in parts if part.strip())
