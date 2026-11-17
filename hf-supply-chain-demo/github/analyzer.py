# -*- coding: utf-8 -*-
"""扫描 GitHub 仓库代码，找出"可能被调用的 Hugging Face 模型"，并给出可核查的证据。

分两层，互相校验：
  第 1 层（确定性）：正则从源码里捞出所有"加载模型"的调用点，
                     证据 = 真实的 文件:行号 + 那一行代码。
  第 2 层（语义）：把代码摘要 + 候选列表丢给 DeepSeek 判断哪些是真调用、哪些是噪声。

设计要点：第 7 列需要的"证据"永远来自第 1 层的真实代码行，
大模型只负责"判断/过滤"，不能凭空编造证据行。
"""

from __future__ import annotations

import json
import os
import re

# --------------------------------------------------------------------------
# 扫描范围
# --------------------------------------------------------------------------

SKIP_DIRS = {
    ".git", ".github", "node_modules", "venv", ".venv", "__pycache__", "dist",
    "build", ".mypy_cache", ".pytest_cache", "site-packages", ".idea", ".vscode",
    ".eggs", "*.egg-info", "wandb", ".next", "target", ".gradle", ".tox",
}

SCAN_EXTENSIONS = {
    ".py", ".pyi", ".ipynb", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt",
    ".scala", ".go", ".rs", ".rb", ".php", ".c", ".cc", ".cpp", ".h", ".hpp",
    ".cs", ".sh", ".bash", ".ps1", ".bat", ".yaml", ".yml", ".toml", ".cfg",
    ".ini", ".md", ".rst", ".txt", ".json",
}

SKIP_FILES = {
    "package-lock.json", "yarn.lock", "poetry.lock", "pipfile.lock",
    "cargo.lock", "composer.lock", "go.sum",
}

MAX_FILE_BYTES = 1_000_000
MAX_FILES = 5000

# 会出现在"模型加载"上下文里的关键词（用来挑出要放进摘要的文件）
HF_SIGNAL_WORDS = (
    "from_pretrained", "transformers", "sentence_transformers", "sentence-transformers",
    "huggingface", "hf_hub", "AutoModel", "AutoTokenizer", "AutoProcessor", "pipeline(",
    "diffusers", "peft", "SentenceTransformer", "CrossEncoder", "load_dataset",
)


# --------------------------------------------------------------------------
# 第 1 层：正则捞调用点
# --------------------------------------------------------------------------
# (标签, 正则, 模型名所在组, 调用方法所在组或 None, 置信度)

QUOTE = r"(?:[frbFRB]{0,2})?[\"']"
PATTERNS = [
    ("X.from_pretrained",
     re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*from_pretrained\s*\(\s*" + QUOTE + r"([^\"'\n]{2,200})[\"']"),
     2, 1, "high"),
    ("from_pretrained",
     re.compile(r"\.from_pretrained\s*\(\s*" + QUOTE + r"([^\"'\n]{2,200})[\"']"),
     1, None, "high"),
    ("SentenceTransformer",
     re.compile(r"\bSentenceTransformer\s*\(\s*" + QUOTE + r"([^\"'\n]{2,200})[\"']"),
     1, None, "high"),
    ("CrossEncoder",
     re.compile(r"\bCrossEncoder\s*\(\s*" + QUOTE + r"([^\"'\n]{2,200})[\"']"),
     1, None, "high"),
    ("pipeline",
     re.compile(r"\bpipeline\s*\([^)]{0,300}?model\s*=\s*" + QUOTE + r"([^\"'\n]{2,200})[\"']"),
     1, None, "high"),
    ("hf_hub_download",
     re.compile(r"\b(?:snapshot_download|hf_hub_download|hf_hub_url)\s*\([^)]{0,300}?repo_id\s*=\s*" + QUOTE + r"([^\"'\n]{2,200})[\"']"),
     1, None, "high"),
    ("model_name_or_path",
     re.compile(r"\b(?:model_name_or_path|model_id|model_checkpoint|pretrained_model_name_or_path|MODEL_NAME|MODEL_ID|MODEL_PATH|repo_id)\s*[:=]\s*" + QUOTE + r"([A-Za-z0-9_][\w.\-]*/[\w.\-]+)[\"']"),
     1, None, "high"),
    ("字符串字面量",
     re.compile(r"[\"']([A-Za-z0-9_][\w.\-]*/[\w.\-]+)[\"']"),
     1, None, "low"),
]

# 明显不是 HF 模型的字符串
BAD_EXTS = (".py", ".json", ".txt", ".bin", ".pt", ".pth", ".safetensors", ".onnx",
            ".gguf", ".yaml", ".yml", ".md", ".zip", ".tar", ".gz", ".csv", ".tsv",
            ".png", ".jpg", ".jpeg", ".svg", ".html", ".css", ".js", ".lock", ".toml")

BAD_VALUES = {
    "utf-8", "utf8", "text/plain", "application/json", "iso-8859-1", "ascii",
    "true", "false", "none", "null", "main", "master", "head", "cpu", "cuda", "mps",
}

API_MODEL_RE = re.compile(
    r"^(gpt-|chatgpt|claude-|gemini-|o1-|o3-|o4-|text-davinci|text-curie|text-babbage|"
    r"text-ada|davinci|deepseek-(chat|reasoner|coder|v\d)|glm-|qwen-(max|plus|turbo|flash)|"
    r"moonshot-|abab|command-|ernie|mistral-(large|medium|small)|llama-?[23]-\d+b-instruct$)",
    re.I)


def _squash(text, limit=320):
    """把多行调用压成一行，方便放进表格。"""
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _extract_call(text, open_index, limit=320):
    """从 ( 开始做括号配对，取出完整的一次调用。"""
    depth = 0
    quote = None
    index = open_index
    length = len(text)
    while index < length:
        char = text[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
        else:
            if char in "\"'":
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return _squash(text[open_index:index + 1], limit)
        index += 1
    return _squash(text[open_index:min(length, open_index + limit)], limit)


def _is_model_like(value):
    if not value or len(value) < 2 or len(value) > 200:
        return False
    if any(ch in value for ch in " \t\n\\"):
        return False
    low = value.lower()
    if low in BAD_VALUES:
        return False
    if "://" in value or value.startswith((".", "/", "~", "$", "{")):
        return False
    if low.endswith(BAD_EXTS):
        return False
    if not re.match(r"^[A-Za-z0-9_]", value):
        return False
    if API_MODEL_RE.match(low) and "/" not in low:
        return False
    return True


def _is_doc_file(rel_path):
    return os.path.splitext(rel_path)[1].lower() in (".md", ".rst", ".txt")


def extract_candidates(files):
    """files: [(相对路径, 正文)] -> 候选调用点列表（已去重）。"""
    found = {}
    for rel_path, text in files:
        for label, regex, model_group, api_group, confidence in PATTERNS:
            for match in regex.finditer(text):
                value = (match.group(model_group) or "").strip()
                if not _is_model_like(value):
                    continue

                line_no = text.count("\n", 0, match.start()) + 1
                # 证据 = 从这一行开头到这次调用结束的完整语句
                line_start = text.rfind("\n", 0, match.start()) + 1
                paren = text.find("(", match.start())
                if paren != -1 and paren - match.start() < 120:
                    code = _squash(text[line_start:paren] + _extract_call(text, paren), 340)
                else:
                    line_end = text.find("\n", match.start())
                    line_end = line_end if line_end != -1 else len(text)
                    code = _squash(text[line_start:line_end], 340)

                if api_group is not None:
                    api = "%s.from_pretrained" % match.group(api_group)
                else:
                    api = label

                key = (value, rel_path, line_no)
                candidate = {
                    "model": value,
                    "file": rel_path,
                    "line": line_no,
                    "api": api,
                    "code": code,
                    "pattern": label,
                    "confidence": confidence,
                }
                # 同一个位置只保留置信度更高的那条
                if key not in found or found[key]["confidence"] == "low":
                    found[key] = candidate
    return list(found.values())


# --------------------------------------------------------------------------
# 代码摘要（给大模型看）
# --------------------------------------------------------------------------

DEP_FILES = ("requirements.txt", "requirements-dev.txt", "pyproject.toml",
             "setup.py", "environment.yml", "environment.yaml", "pipfile",
             "package.json", "conda.yaml")


def _build_digest(repo_name, files, candidates, budget=60_000):
    by_rel = dict(files)
    parts = []
    used = 0

    def add(title, body, cap):
        nonlocal used
        if not body:
            return
        body = body[:cap]
        if used + len(body) > budget:
            body = body[:max(0, budget - used)]
        if not body:
            return
        parts.append("\n===== %s =====\n%s" % (title, body))
        used += len(body)

    add("依赖文件", "\n\n".join(
        "--- %s ---\n%s" % (rel, by_rel[rel][:3000])
        for rel in by_rel if os.path.basename(rel).lower() in DEP_FILES), 12_000)

    for rel in by_rel:
        if os.path.basename(rel).lower().startswith("readme"):
            add("README(%s)" % rel, by_rel[rel], 8_000)
            break

    # 有 HF 信号的文件优先，其次是有候选调用点的文件
    scored = []
    for rel, text in by_rel.items():
        if os.path.basename(rel).lower().startswith("readme"):
            continue
        score = sum(1 for word in HF_SIGNAL_WORDS if word in text)
        if any(c["file"] == rel for c in candidates):
            score += 5
        if score:
            scored.append((score, rel, text))
    scored.sort(key=lambda item: -item[0])

    for score, rel, text in scored[:40]:
        add("文件 %s" % rel, text, 4000)

    header = ("仓库: %s\n扫描到的文件数: %d\n候选调用点数: %d\n"
              % (repo_name or "(未知)", len(files), len(candidates)))
    return header + "".join(parts)


def scan_repo(repo_path, repo_name=""):
    """扫描仓库，返回 {digest, candidates, files_scanned, search_text}。"""
    files = []
    for root, dirs, names in os.walk(repo_path):
        dirs[:] = [d for d in dirs
                   if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        for name in names:
            if len(files) >= MAX_FILES:
                break
            if name.lower() in SKIP_FILES:
                continue
            ext = os.path.splitext(name)[1].lower()
            if ext not in SCAN_EXTENSIONS:
                continue
            path = os.path.join(root, name)
            try:
                if os.path.getsize(path) > MAX_FILE_BYTES:
                    continue
                with open(path, encoding="utf-8", errors="ignore") as handle:
                    text = handle.read()
            except OSError:
                continue
            if not text.strip():
                continue
            files.append((os.path.relpath(path, repo_path).replace("\\", "/"), text))

    candidates = extract_candidates(files)
    digest = _build_digest(repo_name, files, candidates)
    search_text = "\n".join(text for _, text in files)[:800_000]

    return {
        "digest": digest,
        "candidates": candidates,
        "files_scanned": len(files),
        "search_text": search_text,
    }


def read_code(repo_path):
    """兼容旧接口：返回给大模型看的代码摘要。"""
    return scan_repo(repo_path)["digest"]


# --------------------------------------------------------------------------
# 第 2 层：DeepSeek 语义过滤
# --------------------------------------------------------------------------

SYSTEM_PROMPT = "你是 AI 供应链分析专家，只输出 JSON，不要任何解释文字。"


def _llm_filter(scan, repo_name):
    from llm import chat_json

    candidates = scan["candidates"]
    compact = [{"model": c["model"], "file": c["file"], "line": c["line"],
                "api": c["api"]} for c in candidates[:80]]

    prompt = """分析下面这个 GitHub 仓库，找出它【真正调用/加载】的 Hugging Face 模型。

判断标准：
1) 只有代码里真实出现"加载模型"的调用才算，例如：
   AutoModel.from_pretrained("bert-base-uncased")
   pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")
   SentenceTransformer("all-MiniLM-L6-v2")
   Dia.from_pretrained("nari-labs/Dia-1.6B-0626")
   hf_hub_download(repo_id="...")
2) 必须排除：
   - 云 API 模型（gpt-4、claude-3、gemini、deepseek-chat 等），它们不在 Hugging Face 上
   - 数据集名、变量名、本地路径、文件名、配置键名
   - 只在文档/注释里顺带提到、代码里并没有真正加载的

【仓库】%s

【代码摘要】
%s

【正则已经捞出的候选（含噪声）】
%s

只输出 JSON：
{"models": [{"model": "必须与候选列表里的 model 完全一致", "verdict": "hf_model|not_model|uncertain", "reason": "简短理由"}],
 "extra_models": [{"model": "代码里确实调用、但候选列表漏掉的 HF 模型名", "reason": "简短理由"}]}
""" % (repo_name or "(未知)", scan["digest"], json.dumps(compact, ensure_ascii=False))

    data = chat_json(prompt, system=SYSTEM_PROMPT)
    if not isinstance(data, dict):
        return None
    return data


def _merge(candidates, llm_result, search_text):
    verdicts = {}
    extras = []
    if llm_result:
        for item in llm_result.get("models") or []:
            if isinstance(item, dict) and item.get("model"):
                verdicts[str(item["model"]).strip()] = item
        for item in llm_result.get("extra_models") or []:
            if isinstance(item, dict) and item.get("model"):
                extras.append(item)

    kept = []
    for candidate in candidates:
        info = verdicts.get(candidate["model"])
        if info:
            verdict = str(info.get("verdict") or "uncertain").lower()
            reason = info.get("reason") or ""
            if verdict == "not_model":
                continue
        else:
            verdict = "hf_model" if candidate["confidence"] == "high" else "uncertain"
            reason = "正则命中，未经大模型复核"

        # 文档里的调用证据弱一些
        if _is_doc_file(candidate["file"]) and candidate["confidence"] == "high":
            candidate = dict(candidate, confidence="medium")

        kept.append(dict(candidate, llm_verdict=verdict, llm_reason=reason))

    # 大模型补充的模型必须能在仓库原文里找到，防止编造
    known = {c["model"].lower() for c in kept}
    for item in extras:
        model = str(item["model"]).strip()
        if not model or model.lower() in known or not _is_model_like(model):
            continue
        if model not in search_text and model.split("/")[-1] not in search_text:
            continue
        kept.append({
            "model": model, "file": "", "line": 0, "api": "大模型补充",
            "code": "（大模型指出代码里调用了该模型，但未定位到确切行号，建议人工复核）",
            "pattern": "llm-extra", "confidence": "low",
            "llm_verdict": "hf_model", "llm_reason": item.get("reason") or "",
        })
        known.add(model.lower())

    # 去重：同一个模型保留信息量最大的那条证据
    def rank(item):
        order = {"high": 0, "medium": 1, "low": 2}
        return (order.get(item["confidence"], 3), _is_doc_file(item["file"]), not item["file"])

    best = {}
    for item in kept:
        key = item["model"].lower()
        if key not in best or rank(item) < rank(best[key]):
            best[key] = item
    result = sorted(best.values(), key=rank)
    return result


def find_models(scan, repo_name="", use_llm=True):
    """输入 scan_repo() 的结果，返回被确认/待确认的模型调用列表。"""
    if not scan.get("candidates"):
        return []
    llm_result = _llm_filter(scan, repo_name) if use_llm else None
    return _merge(scan["candidates"], llm_result, scan.get("search_text", ""))


def analyze_repo(repo_path, repo_name="", use_llm=True):
    """一步到位：扫描 + 语义分析。"""
    scan = scan_repo(repo_path, repo_name=repo_name)
    return find_models(scan, repo_name=repo_name, use_llm=use_llm), scan
