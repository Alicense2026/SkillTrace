# -*- coding: utf-8 -*-
"""判断一个 AI 资产是「代码层面集成」还是「远程服务调用」，
以及代码层面集成时有没有被改动过。

判定依据（全部来自确定性事实，大模型只做最后的定性）：

代码层面集成（唯一判据：**源码真的出现在仓库里**）：
  - 仓库里有与该资产**同名**的 vendor / third_party / external 目录，且目录内有源码文件
  - 该资产以 git 子模块形式引入且子模块内容已随仓库提交

远程服务调用（以下都不算代码层面集成）：
  - 代码里通过 SDK / HTTP 客户端调用服务端点（client、api_key、base_url 等模式）
  - 只有 import / go.mod / package.json 之类的依赖声明，源码需构建时另取
  - .gitmodules 里只登记了 URL，子模块目录为空（zip 包不含子模块内容）
  - 配置表里只出现服务商名称、base_url、模型名（如 provider 列表）
  - 名字是托管服务商的模型名（claude-* / gpt-* / gemini-* / deepseek ...），仓库里没有它的源码

注意：匹配按**完全同名**进行。仓库里 vendored 的是「某服务商的客户端 SDK 或工具」，
不等于「该服务商的模型源码在仓库里」，两者不能混为一谈。

是否修改（仅代码层面集成）：
  1. 先看上游来源注释有没有自述改动（Vendored from ... Trimmed / Removed / Patched）
  2. 再拿本地目录和上游仓库的文件清单做比对，统计 新增 / 缺失 / 体积变化 的文件
  3. 把这两类事实交给大模型定性：这算不算"真的改过"
"""

from __future__ import annotations

import os
import re

import requests

import astscan
from github.api import get_json

_MOD_WORDS = re.compile(
    r"\b(trimmed|trim|removed?|stripped?|patched?|modified|modif\w+|fork(?:ed)?|"
    r"adapted|changed|hacked|customi[sz]ed|vendored\s+with\s+changes)\b", re.I)

REMOTE_HINTS = re.compile(
    r"(base_url|api_key|apiKey|endpoint|Authorization|Bearer|x-api-key|"
    r"chat\.completions|messages\.create|generate_content|/v1/|anthropic|openai)", re.I)

SYSTEM = "你是软件供应链分析专家，只输出 JSON，不要解释。"

# 判定"仓库里有没有它的源码"时认的源码后缀
SOURCE_EXTS = (".rs", ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go",
               ".java", ".kt", ".scala", ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp",
               ".cs", ".rb", ".php", ".swift", ".m", ".mm", ".lua", ".zig", ".dart")

# 清单/文档类文件，不算"源码"
MANIFEST_NAMES = {"cargo.toml", "package.json", "pyproject.toml", "setup.py",
                  "setup.cfg", "makefile", "readme.md", "readme", "license",
                  "license.md", "license.txt", "copying", ".gitignore"}


def inventory_sources(directory, sample_limit=3):
    """清点某个目录下的**源码文件**（不是清单、不是文档）。

    这是"代码层面集成"的唯一硬判据：仓库里必须真的躺着它的源码。
    """
    result = {"count": 0, "samples": [], "scanned_dir": bool(os.path.isdir(directory))}
    if not result["scanned_dir"]:
        return result
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in (".git", "target", "node_modules", "dist")]
        for name in files:
            low = name.lower()
            if low in MANIFEST_NAMES:
                continue
            if os.path.splitext(low)[1] not in SOURCE_EXTS:
                continue
            result["count"] += 1
            if len(result["samples"]) < sample_limit:
                result["samples"].append(
                    os.path.relpath(os.path.join(root, name), directory).replace("\\", "/"))
    return result


def _norm(text):
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _strip_suffixes(name):
    return re.sub(r"[-_](sdk|rs|py|js|go|ts|client|api)$", "", name, flags=re.I)


def build_index(signals):
    """把子模块 / vendor 目录整理成"本地代码集成的资产"索引。"""
    entries = []
    for item in signals.get("gitmodules") or []:
        entries.append({"path": item["path"], "upstream": item.get("url") or "",
                        "note": item.get("snippet") or "",
                        "file": item.get("file") or "", "line": item.get("line") or 0,
                        "snippet": item.get("snippet") or "",
                        "source": "git-submodule"})
    for item in signals.get("vendored") or []:
        entries.append({"path": item["path"], "upstream": item.get("upstream") or "",
                        "note": item.get("note") or "",
                        "file": item.get("file") or "", "line": item.get("line") or 0,
                        "snippet": item.get("snippet") or "",
                        "package": item.get("package") or "",
                        "source": "vendor-dir"})

    for entry in entries:
        names = set()
        base = entry["path"].rstrip("/").split("/")[-1]
        names.add(_norm(base))
        names.add(_norm(_strip_suffixes(base)))
        if entry["upstream"]:
            repo = re.sub(r"\.git$", "", entry["upstream"].rstrip("/").split("/")[-1])
            names.add(_norm(repo))
            names.add(_norm(_strip_suffixes(repo)))
        entry["names"] = {n for n in names if n}
        entry["deps"] = entry["source"]
    return entries


def _usage_names(artifact, entry):
    """给 locate_usage 的候选名字：包名 > 上游仓库名 > 目录名。"""
    names = [entry.get("package") or "", artifact.get("name") or "",
             entry["path"].rstrip("/").split("/")[-1]]
    return [name for name in names if name]


def artifact_token(name):
    """比对用的主体标识：仓库型取 repo 段（owner/repo → repo），裸名原样返回。"""
    raw = (name or "").strip()
    if "/" in raw:
        raw = raw.rstrip("/").split("/")[-1]
    return re.sub(r"\.git$", "", raw, flags=re.I)


def match_entry(artifact_name, index):
    """名字能不能对上某个本地代码集成的资产。

    只接受**完全同名**。历史上这里有一段子串兜底，结果把
    「deepseek」（模型）配到了「vendor/dsh」（上游 deepseek-harness），
    于是模型被标成"代码层面集成"——源码其实不在仓库里。
    """
    target = _norm(_strip_suffixes(artifact_token(artifact_name)))
    if not target:
        return None
    for entry in index:
        if target in entry["names"]:
            return entry
    return None


# --------------------------------------------------------------------------
# 上游比对
# --------------------------------------------------------------------------

def _local_files(directory, limit=4000):
    """本地目录的文件清单：{相对路径: 大小}。"""
    out = {}
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in (".git", "target", "node_modules")]
        for name in files:
            path = os.path.join(root, name)
            rel = os.path.relpath(path, directory).replace("\\", "/")
            try:
                out[rel] = os.path.getsize(path)
            except OSError:
                continue
            if len(out) >= limit:
                return out
    return out


def _upstream_tree(upstream_url):
    """从 GitHub 拿上游仓库的文件清单：{相对路径: 大小}。"""
    match = re.search(r"github\.com[/:]([^/\s]+)/([^/\s#?]+)", upstream_url or "")
    if not match:
        return None, ""
    owner, repo = match.group(1), re.sub(r"\.git$", "", match.group(2))
    full = "%s/%s" % (owner, repo)
    data = get_json("/repos/%s" % full)
    branch = (data or {}).get("default_branch") or "main"
    tree = get_json("/repos/%s/git/trees/%s?recursive=1" % (full, branch))
    if not tree or "tree" not in tree:
        return None, full
    files = {node["path"]: node.get("size") or 0
             for node in tree["tree"] if node.get("type") == "blob"}
    return files, full


def compare_with_upstream(repo_path, entry):
    """本地 vendored 目录 vs 上游仓库：统计差异。"""
    local_dir = os.path.join(repo_path, entry["path"])
    if not os.path.isdir(local_dir):
        return None
    local = _local_files(local_dir)
    if not local:
        # 子模块目录在 zip 源码包里是空的，这时候"没有差异"其实是"没有可比对的东西"，
        # 绝不能当成"未修改"
        return {"empty": True, "upstream": entry.get("upstream") or "",
                "local_files": 0,
                "reason": "该目录是 git 子模块且未被拉取（下载的 zip 源码包不含子模块内容）"}
    upstream, full_name = _upstream_tree(entry.get("upstream"))
    if not upstream:
        return {"upstream": entry.get("upstream") or "",
                "upstream_name": full_name,
                "error": "拿不到上游文件清单（API 限流或地址无效）",
                "local_files": len(local)}

    only_local = sorted(set(local) - set(upstream))
    only_upstream = sorted(set(upstream) - set(local))
    changed = [p for p in (set(local) & set(upstream))
               if upstream[p] and local[p] and abs(upstream[p] - local[p]) > 64]
    return {
        "upstream": entry.get("upstream") or "",
        "upstream_name": full_name,
        "local_files": len(local),
        "upstream_files": len(upstream),
        "added": only_local[:20],
        "added_count": len(only_local),
        "removed": only_upstream[:20],
        "removed_count": len(only_upstream),
        "changed": sorted(changed)[:20],
        "changed_count": len(changed),
    }


# --------------------------------------------------------------------------
# 判决
# --------------------------------------------------------------------------

def _llm_judge_modified(artifact_name, entry, diff, note):
    from llm import chat_json

    payload = {
        "资产": artifact_name,
        "本地路径": entry["path"],
        "上游仓库": entry.get("upstream") or "",
        "上游来源注释": note[:600],
        "文件比对": {
            "本地文件数": (diff or {}).get("local_files"),
            "上游文件数": (diff or {}).get("upstream_files"),
            "本地多出的文件（示例）": (diff or {}).get("added"),
            "本地缺少的文件（示例）": (diff or {}).get("removed"),
            "体积有变化的文件（示例）": (diff or {}).get("changed"),
        },
    }
    data = chat_json(
        "下面是一个仓库把上游开源项目的源码直接放进自己仓库（vendored）的情况。\n"
        "请判断：这份源码相对上游是否被【实质性修改】过（不是排版/换行这类无关差异）。\n"
        "判断要点：本地多出/缺少的文件、体积明显变化的文件、上游来源注释里自述的改动。\n\n"
        "信息：\n%s\n\n"
        '只输出 JSON：{"modified": true, "reason": "一句话理由", "confidence": "high|low"}'
        % __import__("json").dumps(payload, ensure_ascii=False, indent=2),
        system=SYSTEM)
    if isinstance(data, dict):
        return bool(data.get("modified")), str(data.get("reason") or ""), str(data.get("confidence") or "")
    return None, "", ""


def analyze(artifact, entry, repo_path, use_llm=True):
    """返回集成方式分析结果。

    判据（按需求）：只有当**目标仓库里确实存在该资产的源码文件**时，才算
    「代码层面集成」。仅仅在 .gitmodules 里有一行 URL、或目录是空的（子模块未拉取），
    都不构成代码层面集成。
    """
    if not entry:
        usage = astscan.locate_usage(repo_path, [artifact.get("name") or ""])
        hint = ""
        if usage:
            hint = ("；代码中以引用/配置方式使用它（%s:%s），但源码不在仓库内"
                    % (usage.get("file"), usage.get("line")))
        return {
            "type": "远程服务调用",
            "modified": None,
            "modified_label": "\\",
            "detail": ("仓库里没有该资产的源码（未发现同名 vendor/third_party 目录或子模块）"
                       + hint + "，按远程服务调用处理"),
            "evidence": {"usage": usage},
        }

    sources = inventory_sources(os.path.join(repo_path, entry["path"]))
    if not sources["count"]:
        reason = "目录为空（子模块未拉取）" if sources["scanned_dir"] else "目录不存在"
        return {
            "type": "远程服务调用",
            "modified": None,
            "modified_label": "\\",
            "confidence": "high",
            "detail": ("仓库内未找到该资产的源码（%s：%s，仅见 %s 的声明），"
                       "不构成代码层面集成，按远程服务调用处理"
                       % (entry["path"], reason, entry["source"])),
            "evidence": {
                "path": entry["path"],
                "source": entry["source"],
                "upstream": entry.get("upstream") or "",
                "note": (entry.get("note") or "")[:400],
                "sources": sources,
                "source_note": "仓库内未找到源码（%s），只有声明" % reason,
                "usage": astscan.locate_usage(repo_path, _usage_names(artifact, entry)),
            },
        }

    note = entry.get("note") or ""
    diff = compare_with_upstream(repo_path, entry)

    if diff and diff.get("empty"):
        usage = astscan.locate_usage(repo_path, _usage_names(artifact, entry))
        return {
            "type": "代码层面集成",
            "modified": None,
            "modified_label": "无法确定",
            "confidence": "low",
            "detail": ("代码层面集成（%s，上游 %s）；无法判断是否修改：%s"
                       % (entry["path"], entry.get("upstream") or "未知",
                          diff.get("reason") or "本地没有可比对的源码")),
            "evidence": {"path": entry["path"], "source": entry["source"],
                         "upstream": entry.get("upstream") or "",
                         "note": note[:400],
                         "usage": usage,
                         "diff": {"local_files": 0, "empty": True,
                                  "reason": diff.get("reason")}},
        }

    # 1) 注释自述
    note_hit = ""
    found = _MOD_WORDS.search(note)
    if found:
        note_hit = found.group(0)

    # 2) 文件差异
    diff_signal = False
    if diff and not diff.get("error"):
        if diff.get("added_count") or diff.get("removed_count") or diff.get("changed_count"):
            diff_signal = True

    modified, reason, confidence = None, "", ""
    if note_hit or diff_signal:
        modified, reason, confidence = True, "", "high"
        parts = []
        if note_hit:
            parts.append("上游来源注释自述改过（出现 “%s”）" % note_hit)
        if diff and not diff.get("error") and diff_signal:
            parts.append("与上游比对：本地多 %d 个文件、少 %d 个文件、%d 个文件体积变化"
                         % (diff.get("added_count", 0), diff.get("removed_count", 0),
                            diff.get("changed_count", 0)))
        reason = "；".join(parts)
    elif diff and not diff.get("error"):
        modified, reason, confidence = False, "与上游文件清单一致（无新增/缺失/体积变化）", "high"
    else:
        modified, reason, confidence = None, (diff or {}).get("error") or "缺少可比对的上游信息", "low"

    # 3) 大模型定性（只在有事实可依据时才问）
    llm_reason = ""
    if use_llm and (note or (diff and not diff.get("error"))):
        judged, llm_reason, _conf = _llm_judge_modified(artifact.get("name", ""), entry, diff, note)
        if judged is not None:
            modified = judged
            confidence = "high" if confidence != "low" else confidence
        if llm_reason:
            reason = (reason + "；" if reason else "") + "大模型判定：" + llm_reason

    label = "是" if modified is True else ("否" if modified is False else "无法确定")
    detail = "代码层面集成（%s，上游 %s）；是否修改：%s。%s" % (
        entry["path"], entry.get("upstream") or "未知", label, reason)

    # 补一条"代码里实际引用它"的位置，人工核对时最有用
    usage = astscan.locate_usage(repo_path, _usage_names(artifact, entry))

    return {
        "type": "代码层面集成",
        "modified": modified,
        "modified_label": label,
        "confidence": confidence,
        "detail": detail,
        "evidence": {
            "path": entry["path"],
            "source": entry["source"],
            "upstream": entry.get("upstream") or "",
            "note": note[:400],
            "sources": sources,
            "source_note": ("仓库内找到 %d 个源码文件（如 %s）"
                            % (sources["count"],
                               "、".join(sources["samples"][:2]) or "—")),
            "usage": usage,
            "diff": {k: v for k, v in (diff or {}).items()
                     if k in ("local_files", "upstream_files", "added_count",
                              "removed_count", "changed_count", "added", "removed",
                              "changed", "error", "upstream_name")},
        },
    }


def looks_remote(code_text):
    """调用点上下文是否像在调远程服务。"""
    return bool(REMOTE_HINTS.search(code_text or ""))
