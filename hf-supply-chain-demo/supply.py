# -*- coding: utf-8 -*-
"""供应链编排：一个 GitHub 仓库 → 若干条「仓库 → AI 资产」的 9 列记录。

数据流：
    astscan 召回（AST / 常量传播 / 配置信号）
        ↓ 候选引用点
    大模型判定（哪些是真正在用、属于 model / dataset / tool）
        ↓ 保留下来的候选
    registries 解析（Hugging Face / MCP 注册中心 / 社区站 / GitHub 兜底）
        ↓ 带 URL 和许可证的资产
    integration 判定（代码层面集成 or 远程服务调用；集成的话有没有改过）
        ↓
    9 列输出行
"""

from __future__ import annotations

import re

import astscan
import integration
import registries

SYSTEM = "你是 AI 供应链分析专家，只输出 JSON，不要解释。"

DEFAULT_MAX_ARTIFACTS = 12
DEFAULT_MAX_CANDIDATES = 50
DEFAULT_DIGEST_CHARS = 45_000

_PROVIDER_PREFIX = None


def _provider_prefix():
    global _PROVIDER_PREFIX
    if _PROVIDER_PREFIX is None:
        import re
        _PROVIDER_PREFIX = re.compile(
            r"^(claude|gpt|gemini|deepseek|glm|qwen|llama|mistral|o[1-4]|palm|"
            r"command|mixtral|phi|gemma|yi|baichuan|ernie)", re.I)
    return _PROVIDER_PREFIX


def _rank_candidate(cand):
    """给候选打分，用于挑出最值得送进大模型的一批（以及兜底时的优先级）。

    权重刻意让"长得像 AI 资产"的证据（服务商前缀、org/name）压过
    "仅仅是被 AST 抓到的某个 model= 参数"——后者在设计工具里全是布局变量。
    """
    score = 0.0
    origin = cand.get("origin")
    if origin == "config":
        score += 100            # vendored 源码 / 子模块：一定是"在用"
    elif origin == "ast":
        score += 25             # 真语法分析命中，但要看参数像不像模型
    elif origin == "const-propagation":
        score += 15
    elif origin == "llm-extra":
        score += 30

    name = cand.get("name") or ""
    if _provider_prefix().match(name):
        score += 25             # 知名服务商模型名
    if "/" in name:
        score += 15             # org/name 形态
    if re.search(r"\d", name) and re.search(r"[-.]\d", name):
        score += 10             # 带版本号的更像模型（gpt-5.6 / claude-sonnet-4-6）
    if cand.get("partial"):
        score -= 10             # 只匹配到前缀

    path = (cand.get("file") or "").lower()
    if "test" in path or "/tests/" in path or "_test" in path or "mock" in path:
        score -= 35             # 测试里的假模型名
    if path.endswith(".md"):
        score -= 15             # 文档里的举例
    if "templates/" in path or "/assets/" in path:
        score -= 25             # 模板 / 资源文件里的设计变量

    if cand.get("arg") == "literal":
        score -= 10
    return score


def _shortlist(candidates, limit=DEFAULT_MAX_CANDIDATES):
    """按名字去重 + 打分排序，取前 limit 个送大模型。"""
    best = {}
    for cand in candidates:
        key = (cand.get("name") or "").lower()
        if not key:
            continue
        rank = _rank_candidate(cand)
        if key not in best or rank > best[key][0]:
            best[key] = (rank, cand)
    ordered = sorted(best.values(), key=lambda row: -row[0])
    return [cand for _rank, cand in ordered[:limit]]


# --------------------------------------------------------------------------
# 候选整理
# --------------------------------------------------------------------------

def _config_candidates(index, signals=None):
    """从 vendor / 子模块 / MCP 配置里直接产出候选。

    这些不是代码调用，但确实是被集成/被使用的资产：
      * vendored 目录、子模块 → tool（附带源码，可能构成代码层面集成）
      * MCP 配置块里登记的 server → tool（外部服务，属于远程调用）
    """
    # 同一个 vendor 目录可能同时被 .gitmodules 和目录扫描各记一次，
    # 按路径去重，并优先保留带 upstream 的那条
    by_path = {}
    for entry in index:
        key = entry["path"].lower().rstrip("/")
        current = by_path.get(key)
        if current is None or (entry.get("upstream") and not current.get("upstream")):
            by_path[key] = entry

    out = []
    for entry in by_path.values():
        name = entry["path"].rstrip("/").split("/")[-1]
        if entry.get("upstream"):
            repo = entry["upstream"].rstrip("/").split("/")[-1]
            if repo and len(repo) > 2:
                name = repo.replace(".git", "")
        note = entry.get("note") or ""
        file_ = entry.get("file") or ""
        line_ = entry.get("line") or 0
        code = entry.get("snippet") or note
        if not code:
            code = "%s（本地 vendored 目录，上游来源未知）" % entry["path"]
        out.append({
            "name": name,
            "kind_hint": astscan.KIND_TOOL,
            "file": file_ or (entry["path"] + "/"),
            "line": line_,
            "code": astscan._squash(code, 300),
            "api": entry["source"],
            "language": "",
            "origin": "config",
            "partial": False,
            "arg": "",
            "hint_url": entry.get("upstream") or "",
            "declared_in": "%s:%s" % (file_ or entry["path"], line_ or "?"),
        })

    # MCP 配置文件里登记的 server（真正的"外部工具"用法）
    for server in (signals or {}).get("mcp_servers") or []:
        name = server.get("name") or ""
        if not name:
            continue
        out.append({
            "name": name,
            "kind_hint": astscan.KIND_TOOL,
            "file": server.get("file") or "",
            "line": server.get("line") or 0,
            "code": astscan._squash(server.get("snippet") or name, 300),
            "api": "mcp-config",
            "language": "",
            "origin": "config",
            "partial": False,
            "arg": "",
            "hint_url": "",
            "declared_in": "%s:%s" % (server.get("file") or "?", server.get("line") or "?"),
        })
    return out


def _dedupe(candidates):
    seen, out = set(), []
    for item in candidates:
        key = (item["name"].lower(), item.get("file") or "", item.get("line") or 0)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


# --------------------------------------------------------------------------
# 大模型判定
# --------------------------------------------------------------------------

def _llm_judge(scan, repo_name, candidates, digest_chars=DEFAULT_DIGEST_CHARS):
    """让大模型判断：哪些候选是真的在用、以及属于 model / dataset / tool。"""
    from llm import chat_json

    compact = [{"name": c["name"], "kind_hint": c["kind_hint"], "file": c["file"],
                "line": c["line"], "origin": c["origin"]}
               for c in candidates[:DEFAULT_MAX_CANDIDATES]]

    prompt = """分析下面这个 GitHub 仓库，找出它真正使用的 AI 资产。

三类资产：
- model   模型（预训练模型、托管模型服务，如 gpt-4o / claude-sonnet-4 / nari-labs/Dia-1.6B）
- dataset 数据集（如 squad、wikipedia、某公司开源语料）
- tool    工具（MCP 服务器、Agent Skill、CLI 工具、SDK，如 @modelcontextprotocol/server-github）

判定标准：
1) 只有代码或配置里真实引用/加载/调用的才算（含 vendored 源码、子模块、MCP 配置里登记的服务）。
2) 必须排除：
   - 测试用例里的假数据（如 "gpt-test"、"claude-a"、mock 值）
   - 纯粹的 UI 文案、i18n 词条、图标名、注释里的举例
   - 变量名、路径、文件名、颜色值、版本号
3) 拿不准就标 uncertain，不要硬判 real。

【仓库】%s

【代码摘要】
%s

【候选（含噪声）】
%s

只输出 JSON：
{"items": [{"name": "必须与候选里的 name 完全一致", "kind": "model|dataset|tool",
            "verdict": "real|not_ai|uncertain", "reason": "简短理由"}],
 "extra_items": [{"name": "代码里确实在用、但候选漏掉的资产", "kind": "model|dataset|tool", "reason": "..."}]}
""" % (repo_name or "(未知)", scan["digest"][:digest_chars],
       __import__("json").dumps(compact, ensure_ascii=False))

    data = chat_json(prompt, system=SYSTEM)
    return data if isinstance(data, dict) else None


def _merge_judgement(candidates, judged, use_llm, repo_path=""):
    """把大模型的判定和确定性候选合并。证据永远取确定性候选里的那份。"""
    verdicts, extras = {}, []
    if judged:
        for item in judged.get("items") or []:
            if isinstance(item, dict) and item.get("name"):
                verdicts[str(item["name"]).strip()] = item
        for item in judged.get("extra_items") or []:
            if isinstance(item, dict) and item.get("name"):
                extras.append(item)

    kept = []
    for cand in candidates:
        info = verdicts.get(cand["name"])
        if info:
            verdict = str(info.get("verdict") or "uncertain").lower()
            if verdict == "not_ai":
                continue
            kind = str(info.get("kind") or "").strip().lower()
            reason = info.get("reason") or ""
            verdict = "real" if verdict == "real" else "uncertain"
        elif judged is None:
            # 大模型不可用：退回到确定性规则。只保留"质量够"的候选，
            # 宁可少报，也不要灌一堆噪声进表格。
            if cand["origin"] == "config":
                verdict = "real"
            elif cand["origin"] in ("ast", "const-propagation"):
                score = _rank_candidate(cand)
                if score < 25:
                    continue
                verdict = "uncertain"
            else:
                continue
            kind = cand["kind_hint"]
            reason = "确定性规则命中（大模型不可用，未经复核）"
        else:
            # 大模型给出了判定，但没提到这个候选：只保留配置来源这种确定性事实
            if cand["origin"] != "config":
                continue
            verdict = "real"
            kind = cand["kind_hint"]
            reason = "来自仓库内的 vendored 源码 / 子模块声明"

        if kind not in registries.KINDS:
            kind = cand["kind_hint"]
        kept.append(dict(cand, verdict=verdict, kind=kind, reason=reason))

    # 大模型补充的资产：必须能回到仓库里定位到真实行号，否则不收
    # （这条约束保证第 9 列的证据永远是可核查的，而不是大模型的一面之词）
    known = {c["name"].lower() for c in kept}
    for item in extras:
        name = str(item["name"]).strip()
        if not name or name.lower() in known:
            continue
        located = astscan.locate(repo_path, name) if repo_path else None
        if not located:
            continue
        kind = str(item.get("kind") or "model").strip().lower()
        if kind not in registries.KINDS:
            kind = "model"
        kept.append({
            "name": name, "kind_hint": kind,
            "file": located["file"], "line": located["line"], "code": located["code"],
            "api": "llm-extra", "language": "", "origin": "llm-extra",
            "partial": False, "arg": "", "verdict": "uncertain",
            "kind": kind, "reason": item.get("reason") or "大模型补充，已在仓库中定位到出现位置",
        })
        known.add(name.lower())
    return kept


scan_text_cache = ""


# --------------------------------------------------------------------------
# 解析与证据
# --------------------------------------------------------------------------

def _resolve(cand, use_llm=True):
    """候选 → Artifact。有上游 URL 的直接按 URL 解析，避免搜错。"""
    hint_url = cand.get("hint_url")
    if hint_url:
        artifact = registries.resolve_url_literal(hint_url)
        if artifact:
            artifact["resolved_via"] = "config-upstream"
            artifact["kind"] = cand.get("kind") or registries.KIND_TOOL
            return artifact
        license_name, source = registries.github_license_from_url(hint_url)
        return registries.make_artifact(
            cand["name"], cand.get("kind") or registries.KIND_TOOL, "github",
            hint_url, license_name, source, 0.95, cand["name"],
            {"note": "来自仓库内的 vendored 目录 / 子模块声明"})

    return registries.resolve_artifact(
        cand["name"], kind_hint=cand.get("kind"), context=cand.get("code", ""),
        use_llm=use_llm)


def _level(artifact, cand):
    """证据等级：强 / 中 / 弱。判据是"名字在证据行里能不能看到"。"""
    if not artifact:
        return "弱"
    name = (artifact.get("name") or "").lower()
    raw = (cand.get("name") or "").lower()
    code = (cand.get("code") or "").lower()
    mentions = bool(name and name in code) or bool(raw and raw in code)

    origin = cand.get("origin")
    via = artifact.get("resolved_via")

    if origin == "config":
        return "强" if (mentions or cand.get("line")) else "中"
    if origin == "ast":
        if mentions:
            return "强" if via in ("hf-model", "hf-dataset", "config-upstream") else "中"
        return "中"
    if origin in ("const-propagation", "regex", "llm-extra"):
        if mentions:
            return "中"
    if artifact.get("score", 0) >= 0.95:
        return "中"
    return "弱"


LEVEL_LABEL = {"强": "已确认（强）", "中": "待复核（中）", "弱": "待人工复核（弱）"}


def _evidence_text(artifact, cand, level, integ):
    """生成第 9 列：把"哪个文件第几行、原文写了什么"放在最前面，方便人工核对。"""
    parts = []
    is_config = cand.get("origin") == "config"

    file_ = (cand.get("file") or "").strip()
    line_ = cand.get("line") or 0
    if file_ and line_:
        location = "%s:%d" % (file_, line_)
    else:
        location = file_ or "?"
    parts.append("%s: %s" % ("集成声明位置" if is_config else "调用位置", location))

    code = astscan._squash(cand.get("code") or "", 320)
    parts.append("%s: %s" % ("声明原文" if is_config else "调用原文",
                             code or "（该资产来自配置声明，没有单行代码）"))

    parts.append("证据等级: %s" % LEVEL_LABEL.get(level, level))

    if artifact:
        parts.append("解析: %s → %s" % (artifact.get("registry") or "?",
                                        artifact.get("resolved_via") or "?"))
        source = artifact.get("license_source")
        if source and source != "unknown":
            parts.append("许可证来源: %s" % source)

    if integ:
        source_note = (integ.get("evidence") or {}).get("source_note")
        if source_note:
            parts.append("源码情况: %s" % source_note)
        usage = (integ.get("evidence") or {}).get("usage")
        if usage:
            parts.append("代码引用位置: %s:%s" % (usage.get("file"), usage.get("line")))
            parts.append("引用原文: %s" % astscan._squash(usage.get("code") or "", 240))
        parts.append("集成判定: %s" % (integ.get("detail") or ""))

    if cand.get("reason"):
        parts.append("判定理由: %s" % cand["reason"])
    return " ｜ ".join(part for part in parts if part)


# --------------------------------------------------------------------------
# 对外入口
# --------------------------------------------------------------------------

def analyze(repo_path, repo_name, repo_url, github_license, use_llm=True,
            max_artifacts=DEFAULT_MAX_ARTIFACTS, quiet=False):
    """返回 (rows, details)。rows 是 9 列的行。"""
    global scan_text_cache

    scan = astscan.scan(repo_path, repo_name=repo_name)
    scan_text_cache = scan.get("search_text", "")
    index = integration.build_index(scan["signals"])

    candidates = _dedupe(scan["candidates"] + _config_candidates(index, scan["signals"]))
    shortlist = _shortlist(candidates)
    if not quiet:
        print("  扫描: %d 个文件, %d 个候选引用点, %d 个本地代码集成资产 → 送去判定 %d 个"
              % (scan["files_scanned"], len(scan["candidates"]), len(index), len(shortlist)))

    judged = _llm_judge(scan, repo_name, shortlist) if use_llm else None
    kept = _merge_judgement(shortlist, judged, use_llm, repo_path=repo_path)
    if not quiet:
        print("  判定后保留: %d 个候选" % len(kept))

    rows, details = [], []
    used, used_urls = set(), set()
    attempts = 0
    for cand in kept:
        if len(rows) >= max_artifacts:
            break
        if attempts >= max_artifacts * 3:      # 解析尝试上限，防止一路空手而归
            break
        attempts += 1
        artifact = _resolve(cand, use_llm=use_llm)
        if not artifact:
            continue
        key = (artifact.get("name", "").lower(), artifact.get("kind"))
        url_key = (artifact.get("url") or "").lower().rstrip("/")
        if key in used or (url_key and url_key in used_urls):
            continue
        used.add(key)
        if url_key:
            used_urls.add(url_key)

        entry = integration.match_entry(artifact.get("name", ""), index) or \
            integration.match_entry(cand.get("name", ""), index)
        integ = integration.analyze(artifact, entry, repo_path, use_llm=use_llm)

        level = _level(artifact, cand)
        rows.append({
            "github_repo": repo_name,
            "github_url": repo_url,
            "github_license": github_license,
            "artifact_name": artifact.get("name"),
            "artifact_url": artifact.get("url") or "",
            "artifact_license": artifact.get("license") or "unknown",
            "artifact_kind": artifact.get("kind"),
            "integration": integ["type"],
            "modified": ("\\" if integ["type"] == "远程服务调用"
                         else integ.get("modified_label") or "无法确定"),
            "evidence": _evidence_text(artifact, cand, level, integ),
            "_level": level,
        })
        details.append({
            "repo_url": repo_url,
            "candidate": cand,
            "artifact": artifact,
            "integration": integ,
            "level": level,
        })

    return rows, details, scan
