# -*- coding: utf-8 -*-
"""召回层：从仓库代码里找出「AI 资产（model / dataset / tool）」的引用点。

两条路径：
  1. Python 文件 —— 用标准库 ast 做真语法分析：
     收集字符串常量、支持 + 拼接 / f-string / 变量引用传播，再定位需要参数的调用。
  2. 其他语言（Rust / TS / JS / Go ...）—— 用正则 + 常量传播：
     先收集 `NAME = "..."` 这类赋值，再在调用行里把标识符替换回字面量。
     这是纯正则做不到的部分——本项目要解决的"动态拼接 / 配置里的名字"。

除了调用点，还额外收集"配置信号"：
  .gitmodules 子模块、vendor 目录的上游注释、MCP 配置块、skills 目录、依赖清单。
  这些是判断「代码层面集成 vs 远程调用」以及 tool 类资产的主要依据。
"""

from __future__ import annotations

import ast
import os
import re
import warnings

KIND_MODEL = "model"
KIND_DATASET = "dataset"
KIND_TOOL = "tool"

SKIP_DIRS = {
    ".git", ".github", "node_modules", "target", "dist", "build", "__pycache__",
    ".venv", "venv", ".mypy_cache", ".pytest_cache", ".next", ".cache",
    "site-packages", ".idea", ".vscode", "assets", "static", "public",
}

# 扫描调用点时跳过 vendor（里面是上游源码，噪声大）；vendor 单独用于集成分析
SCAN_SKIP_DIRS = SKIP_DIRS | {"vendor", "third_party", "external", ".cargo"}

LANG_BY_EXT = {
    ".py": "python", ".rs": "rust", ".ts": "ts", ".tsx": "ts", ".js": "js",
    ".jsx": "js", ".go": "go", ".java": "java", ".kt": "kotlin", ".rb": "ruby",
    ".php": "php", ".cs": "csharp", ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp",
}

MAX_FILE_BYTES = 800_000
MAX_FILES = 6000

# 参数名 → 资产类型
MODEL_ARGS = {"model", "model_id", "model_name", "model_name_or_path", "engine",
              "deployment", "deployment_name", "pretrained_model_name_or_path",
              "repo_id", "checkpoint", "model_path"}
DATASET_ARGS = {"dataset", "dataset_name", "dataset_id", "data_files", "data_path",
                "dataset_path", "dataset_config_name"}
TOOL_ARGS = {"server", "server_name", "tool", "tool_name", "skill", "skill_name",
             "package", "package_name", "command"}

CALL_HINTS = {
    "from_pretrained": KIND_MODEL, "SentenceTransformer": KIND_MODEL,
    "CrossEncoder": KIND_MODEL, "pipeline": KIND_MODEL,
    "load_dataset": KIND_DATASET, "load_from_disk": KIND_DATASET,
    "snapshot_download": KIND_MODEL, "hf_hub_download": KIND_MODEL,
}

QUOTE = r"(?:[frbFRB]{0,2})?[\"']"

# ---------------------------------------------------------------- 垃圾值过滤

BAD_EXTS = (".py", ".json", ".jsonl", ".txt", ".bin", ".pt", ".pth", ".safetensors", ".onnx",
            ".gguf", ".yaml", ".yml", ".md", ".zip", ".tar", ".gz", ".csv", ".tsv",
            ".png", ".jpg", ".jpeg", ".svg", ".html", ".css", ".js", ".lock",
            ".toml", ".rs", ".ts", ".exe", ".dll", ".so", ".dylib", ".wasm",
            ".jsonc", ".sql", ".log", ".op", ".bak", ".tmp")

BAD_VALUES = {
    "utf-8", "utf8", "text/plain", "application/json", "true", "false", "none",
    "null", "main", "master", "head", "cpu", "cuda", "mps", "auto", "default",
    "localhost", "127.0.0.1",
}


def is_artifact_like(value):
    """粗筛：像不像一个 AI 资产的标识符。"""
    if not value or not isinstance(value, str):
        return False
    value = value.strip()
    if len(value) < 3 or len(value) > 160:
        return False
    if any(ch in value for ch in " \t\n\\"):
        return False
    low = value.lower()
    if low in BAD_VALUES:
        return False
    if "://" in value or ":" in value:
        return False
    if value.startswith((".", "/", "~", "$", "{", "%", "@@")):
        return False
    if low.endswith(BAD_EXTS):
        return False
    if not re.match(r"^[A-Za-z0-9_@]", value):
        return False
    if re.fullmatch(r"[\d.\-]+", value):        # 纯版本号
        return False
    return True


# 布局 / 结构性取值，绝不是 AI 资产
LAYOUT_WORDS = {
    "left", "right", "top", "bottom", "center", "middle", "table", "row", "column",
    "grid", "flex", "block", "inline", "none", "auto", "name", "family", "chain",
    "type", "kind", "value", "key", "id", "text", "title", "label", "default",
    "primary", "secondary", "horizontal", "vertical", "fill", "fill_container",
    "hug", "fixed", "wrap", "nowrap", "start", "end", "space_between",
}

# 路径形态：构建产物、资源目录、源码目录都不可能是模型名
PATHISH_RE = re.compile(
    r"(^|/)(target|debug|release|assets?|src|scripts?|docs?|tests?|fixtures?|"
    r"templates?|node_modules|packages|out|dist|build|\.cargo)/", re.I)

_PROVIDER_PREFIX = re.compile(
    r"^(claude|gpt|gemini|deepseek|glm|qwen|llama|mistral|o[1-4]|palm|command|"
    r"mixtral|phi|gemma|yi|baichuan|ernie|stable-?diffusion|whisper|flux|sdxl)", re.I)

# 设计系统里的尺寸/字号变量，长得像模型名但不是
DESIGN_TOKEN_RE = re.compile(
    r"^(display|title|body|heading|caption|label|headline|subtitle|corner|icon|color|"
    r"spacing|radius|shadow|font|text|bg|fg|border|padding|margin|gap|size|weight)[-_]?[a-z0-9]*$",
    re.I)


def plausible_asset(value, kind=KIND_MODEL):
    """比 is_artifact_like 更严格的"像不像 AI 资产"判断，用来压噪声。"""
    if not is_artifact_like(value):
        return False
    low = value.lower()
    if low in LAYOUT_WORDS:
        return False
    if PATHISH_RE.search(value):
        return False
    if value.count("/") > 1:
        return False
    if DESIGN_TOKEN_RE.match(value):        # display-l / title-2 / body-m 这类设计变量
        return False
    if re.search(r"\.[a-z]{2,4}$", low) and not re.search(r"\.\d", low):
        return False                        # file.ext 形态（bake.op / scores.jsonl）
    if _PROVIDER_PREFIX.match(value):
        return True
    if value.startswith("@") and "/" in value:          # npm 作用域包
        return True
    if low.endswith(("-mcp", "_mcp", "-sdk", "-skill", "-server", "-agent")):
        return True
    if "/" in value:                                    # org/name
        left, right = value.split("/", 1)
        return (bool(re.match(r"^[A-Za-z0-9_.\-]{2,40}$", left))
                and bool(re.match(r"^[A-Za-z0-9_.\-]{2,60}$", right)))
    if kind == KIND_DATASET:
        return len(value) >= 3
    if kind == KIND_TOOL:
        return len(value) >= 3 and bool(re.search(r"[-_.]", value))
    return len(value) >= 6 and bool(re.search(r"[-.]", value))


# ---------------------------------------------------------------- 通用工具

def _squash(text, limit=340):
    return re.sub(r"\s+", " ", text or "").strip()[:limit]


def extract_call_span(text, open_index, limit=340):
    """从 ( 开始做括号配对（跳过字符串内括号），取出完整调用。"""
    depth, quote, index = 0, None, open_index
    while index < len(text):
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
    return _squash(text[open_index:open_index + limit], limit)


def _line_of(text, position):
    return text.count("\n", 0, position) + 1


# ---------------------------------------------------------------- Python AST

class _PyConsts(ast.NodeVisitor):
    """收集模块级 / 函数级的字符串常量（含 + 拼接、只含常量的 f-string）。"""

    def __init__(self):
        self.values = {}

    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Name):
                value, partial = _py_eval(node.value, self.values)
                if value:
                    self.values[target.id] = (value, partial)
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        if isinstance(node.target, ast.Name) and node.value is not None:
            value, partial = _py_eval(node.value, self.values)
            if value:
                self.values[node.target.id] = (value, partial)
        self.generic_visit(node)


def _py_eval(node, consts):
    """返回 (字符串值, 是否只匹配到前缀)。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value, False
    if isinstance(node, ast.Name):
        return consts.get(node.id, (None, False))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, lp = _py_eval(node.left, consts)
        right, rp = _py_eval(node.right, consts)
        if left and right:
            return left + right, lp or rp
        if left:
            return left, True
        return None, False
    if isinstance(node, ast.JoinedStr):
        prefix = ""
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                prefix += part.value
            else:
                return (prefix, True) if prefix else (None, False)
        return prefix, False
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        # "{}".format(...) / os.path.join(...) 之类：尽量取第一个常量
        if node.args:
            return _py_eval(node.args[0], consts)
    return None, False


def _call_name(node):
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _collect_python(rel_path, text):
    """用 AST 找出调用点。"""
    out = []
    try:
        # 被测仓库的代码里常有非法转义序列（"\d" 之类），ast.parse 会抛 SyntaxWarning
        # 刷满终端。这些与我们的分析无关，直接静音。
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            warnings.simplefilter("ignore", DeprecationWarning)
            tree = ast.parse(text)
    except SyntaxError:
        return out

    consts = {}
    collector = _PyConsts()
    collector.visit(tree)
    consts = collector.values

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if not name:
            continue

        picked = []          # [(value, kind, arg_label, partial)]
        for arg in node.args:
            value, partial = _py_eval(arg, consts)
            kind = CALL_HINTS.get(name, KIND_MODEL)
            if value and plausible_asset(value, kind):
                picked.append((value, kind, "positional", partial))
                break
        for kw in node.keywords:
            if not kw.arg:
                continue
            value, partial = _py_eval(kw.value, consts)
            if not value:
                continue
            if kw.arg in MODEL_ARGS:
                kind = KIND_DATASET if kw.arg in DATASET_ARGS else KIND_MODEL
            elif kw.arg in DATASET_ARGS:
                kind = KIND_DATASET
            elif kw.arg in TOOL_ARGS:
                kind = KIND_TOOL
            else:
                continue
            if not plausible_asset(value, kind):
                continue
            picked.append((value, kind, kw.arg, partial))
            break

        if not picked:
            continue

        line = _line_of(text, node.lineno and 0) if False else node.lineno
        start = text.find(name, 0)
        # 用 lineno/col_offset 精确定位调用文本
        lines = text.splitlines()
        if 1 <= node.lineno <= len(lines):
            prefix = lines[node.lineno - 1]
            call_text = _squash(prefix, 300)
        else:
            call_text = name + "(...)"

        for value, kind, arg_label, partial in picked:
            out.append({
                "name": value,
                "kind_hint": kind,
                "file": rel_path,
                "line": node.lineno,
                "code": call_text,
                "api": name,
                "language": "python",
                "origin": "ast",
                "partial": bool(partial),
                "arg": arg_label,
            })
    return out


# ---------------------------------------------------------------- 其他语言

ASSIGN_PATTERNS = [
    # Rust: let mut x = String::from("...") / let x = "..." / const X: &str = "..."
    re.compile(r"\b(?:let\s+(?:mut\s+)?|const\s+|static\s+)([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=]+)?=\s*(?:String::from\()?" + QUOTE + r"([^\"'\n]{2,200})[\"']"),
    # TS/JS: const x = "..." / let x: string = '...'
    re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*" + QUOTE + r"([^\"'\n]{2,200})[\"']"),
    # Go: x := "..."
    re.compile(r"\b([A-Za-z_][\w]*)\s*:=\s*" + QUOTE + r"([^\"'\n]{2,200})[\"']"),
    # 配置键值: MODEL = "..." / model: "..."
    re.compile(r"\b([A-Za-z_][\w]*)\s*[:=]\s*" + QUOTE + r"([^\"'\n]{2,200})[\"']"),
]

CALL_PATTERNS = [
    # model = "..." / .model("...") / model: "..."
    (re.compile(r"\bmodel(?:_id|_name)?\s*[:=]\s*" + QUOTE + r"([^\"'\n]{2,200})[\"']"), KIND_MODEL),
    (re.compile(r"\.model\(\s*" + QUOTE + r"([^\"'\n]{2,200})[\"']"), KIND_MODEL),
    (re.compile(r"\bfrom_pretrained\(\s*" + QUOTE + r"([^\"'\n]{2,200})[\"']"), KIND_MODEL),
    (re.compile(r"\b(?:repo_id|snapshot_download|hf_hub_download)\s*\(?\s*[:=]?\s*" + QUOTE + r"([^\"'\n]{2,200})[\"']"), KIND_MODEL),
    (re.compile(r"\b(?:dataset|dataset_name|data_path)\s*[:=]\s*" + QUOTE + r"([^\"'\n]{2,200})[\"']"), KIND_DATASET),
    (re.compile(r"\b(?:server|server_name|tool|tool_name|skill|skill_name|package)\s*[:=]\s*" + QUOTE + r"([^\"'\n]{2,200})[\"']"), KIND_TOOL),
]

# 形如 "org/name" 的裸字面量（低置信，靠大模型过滤）
LITERAL_RE = re.compile(r"[\"']([A-Za-z0-9_][\w.\-]*/[\w.\-]+)[\"']")

# 裸字面量只有落在"像在说 AI 资产"的上下文里才值得收集，否则一个前端仓库
# 会产出几万条 i18n key 之类的噪声
AI_CONTEXT_RE = re.compile(
    r"(model|dataset|repo_id|from_pretrained|pretrained|hf_hub|sentence_transformers|"
    r"provider|anthropic|openai|claude|gpt|gemini|deepseek|glm|qwen|llama|ollama|"
    r"mistral|mcp|skill|agent|huggingface|inference|embedding|tokeniz)", re.I)


def _collect_generic(rel_path, text, language):
    out = []
    consts = {}
    for pattern in ASSIGN_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(2).strip()
            if is_artifact_like(value):
                consts.setdefault(match.group(1), (value, match.start()))

    seen = set()
    for pattern, kind in CALL_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1).strip()
            if not plausible_asset(value, kind):
                continue
            line = _line_of(text, match.start())
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            code = _squash(text[line_start:line_end if line_end != -1 else len(text)], 300)
            key = (value, line)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "name": value, "kind_hint": kind, "file": rel_path, "line": line,
                "code": code, "api": pattern.pattern[:24], "language": language,
                "origin": "regex", "partial": False, "arg": "regex",
            })

    # 用常量表回头补一遍：调用点里出现的是变量名时，替换成字面量。
    # 证据优先指向【常量定义行】（那一行真的含有名字），再注明引用位置，
    # 否则会出现"证据行里没有名字"的尴尬情况。
    for var, (value, def_pos) in consts.items():
        if var not in text:            # 先做便宜的字符串判断，避免逐个编译正则
            continue
        def_line = _line_of(text, def_pos)
        def_start = text.rfind("\n", 0, def_pos) + 1
        def_end = text.find("\n", def_pos)
        def_code = _squash(text[def_start:def_end if def_end != -1 else len(text)], 300)
        use_re = re.compile(r"\b" + re.escape(var) + r"\b")
        for match in use_re.finditer(text):
            line = _line_of(text, match.start())
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            code = _squash(text[line_start:line_end if line_end != -1 else len(text)], 300)
            if not re.search(r"(model|dataset|repo|server|tool|skill|package|provider)", code, re.I):
                continue
            if not plausible_asset(value, KIND_MODEL):
                continue
            key = (value, def_line)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "name": value, "kind_hint": KIND_MODEL, "file": rel_path,
                "line": def_line,
                "code": "%s（引用处 第%d行）" % (def_code, line),
                "api": "const-propagation", "language": language,
                "origin": "const-propagation", "partial": False, "arg": var,
                "used_at": "%s:%d" % (rel_path, line),
            })

    # 低置信的裸字面量：只有上下文像"在调用 AI 资产"时才收集，否则噪声太大
    for match in LITERAL_RE.finditer(text):
        value = match.group(1).strip()
        if not plausible_asset(value, KIND_MODEL):
            continue
        if any(value == known for known, _pos in consts.values()):
            continue
        line = _line_of(text, match.start())
        key = (value, line)
        if key in seen:
            continue
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        context_line = text[line_start:line_end if line_end != -1 else len(text)]
        if not AI_CONTEXT_RE.search(context_line):
            continue
        seen.add(key)
        out.append({
            "name": value, "kind_hint": KIND_MODEL, "file": rel_path, "line": line,
            "code": _squash(context_line, 300),
            "api": "literal", "language": language, "origin": "regex",
            "partial": False, "arg": "literal",
        })
    return out


# ---------------------------------------------------------------- 配置信号

MCP_KEY_RE = re.compile(r"\"?mcpServers\"?\s*:\s*\{", re.I)
PKG_NAME_RE = re.compile(r"[\"'](@[a-z0-9\-_.]+/[a-z0-9\-_.]+|[a-z0-9\-_.]+-mcp[a-z0-9\-_.]*)[\"']", re.I)


def collect_config_signals(repo_path):
    """收集子模块、vendor 上游来源、MCP 配置、skills 目录、依赖清单。"""
    signals = {
        "gitmodules": [],      # [{path, url}]
        "vendored": [],        # [{path, upstream, note, files}]
        "mcp_servers": [],     # [{name, file, line}]
        "skills": [],          # [{name, path}]
        "ai_dependencies": [], # [{name, file}]
        "references": [],      # 配置里出现的 org/name 字符串
    }

    gm = os.path.join(repo_path, ".gitmodules")
    if os.path.isfile(gm):
        try:
            text = open(gm, encoding="utf-8", errors="ignore").read()
            current = {}
            for lineno, raw in enumerate(text.splitlines(), 1):
                stripped = raw.strip()
                if stripped.startswith("[submodule"):
                    current = {}
                elif "=" in stripped:
                    key, _, value = stripped.partition("=")
                    key, value = key.strip(), value.strip()
                    current[key] = value
                    if key == "url" and current.get("path"):
                        # 记下声明所在的文件与行号，这样证据列能给出可核对的位置
                        signals["gitmodules"].append({
                            "path": current["path"],
                            "url": value,
                            "file": ".gitmodules",
                            "line": lineno,
                            "snippet": _squash(raw, 200),
                        })
        except OSError:
            pass

    # vendor/<name>/Cargo.toml 或 package.json 里的上游注释
    for base in ("vendor", "third_party", "external", "deps"):
        root = os.path.join(repo_path, base)
        if not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root)):
            sub = os.path.join(root, entry)
            if not os.path.isdir(sub):
                continue
            provenance = _read_provenance(sub, base + "/" + entry)
            signals["vendored"].append({
                "path": "%s/%s" % (base, entry),
                "upstream": provenance["upstream"],
                "note": provenance["note"],
                "file": provenance["file"],
                "line": provenance["line"],
                "snippet": provenance["snippet"],
                "package": _read_package_name(sub),
                "files": _count_files(sub),
            })

    # skills 目录
    for dirpath, dirnames, filenames in os.walk(repo_path):
        rel = os.path.relpath(dirpath, repo_path).replace("\\", "/")
        if rel.count("/") > 6:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        if os.path.basename(dirpath) == "skills":
            for entry in sorted(os.listdir(dirpath))[:80]:
                if os.path.isdir(os.path.join(dirpath, entry)):
                    signals["skills"].append({"name": entry, "path": "%s/%s" % (rel, entry)})
                elif entry.endswith(".md"):
                    signals["skills"].append(
                        {"name": os.path.splitext(entry)[0], "path": "%s/%s" % (rel, entry)})

    # MCP 配置文件
    for name in ("mcp.json", ".mcp.json", "mcp_config.json", "claude_desktop_config.json",
                 "opencode.json", "settings.json"):
        for dirpath, dirnames, filenames in os.walk(repo_path):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            if name in filenames:
                path = os.path.join(dirpath, name)
                try:
                    text = open(path, encoding="utf-8", errors="ignore").read()
                except OSError:
                    continue
                if MCP_KEY_RE.search(text):
                    for match in PKG_NAME_RE.finditer(text):
                        line_no = _line_of(text, match.start())
                        line_start = text.rfind("\n", 0, match.start()) + 1
                        line_end = text.find("\n", match.start())
                        signals["mcp_servers"].append({
                            "name": match.group(1),
                            "file": os.path.relpath(path, repo_path).replace("\\", "/"),
                            "line": line_no,
                            "snippet": _squash(
                                text[line_start:line_end if line_end != -1 else len(text)], 200),
                        })

    # 依赖清单里的 AI SDK
    ai_dep_re = re.compile(
        r"[\"']?([@\w.\-/]*(?:openai|anthropic|claude|gemini|google-generativeai|"
        r"ollama|mistral|cohere|replicate|langchain|llama[-_]index|huggingface|"
        r"transformers|mcp)[\w.\-/]*)", re.I)
    for manifest in ("package.json", "Cargo.toml", "requirements.txt", "pyproject.toml"):
        for dirpath, dirnames, filenames in os.walk(repo_path):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            if manifest in filenames:
                path = os.path.join(dirpath, manifest)
                try:
                    text = open(path, encoding="utf-8", errors="ignore").read()
                except OSError:
                    continue
                for match in ai_dep_re.finditer(text):
                    name = match.group(1).strip("/\"'")
                    if len(name) > 3:
                        signals["ai_dependencies"].append({
                            "name": name,
                            "file": os.path.relpath(path, repo_path).replace("\\", "/")})

    # 去重
    for key in ("gitmodules", "mcp_servers", "skills", "ai_dependencies", "vendored"):
        seen, unique = set(), []
        for item in signals[key]:
            marker = item.get("name") or item.get("path")
            if marker in seen:
                continue
            seen.add(marker)
            unique.append(item)
        signals[key] = unique
    return signals


def _read_provenance(directory, rel_dir=""):
    """读 vendor 目录里的来源注释（Vendored from ...）。

    返回 file/line/snippet，这样证据列可以给到"哪个文件第几行写了什么"。
    """
    result = {"note": "", "upstream": "", "file": "", "line": 0, "snippet": ""}
    for name in ("Cargo.toml", "package.json", "README.md", "README", "LICENSE"):
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()[:4000]
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines()[:60], 1):
            if not result["note"] and re.search(
                    r"(vendor|fork|copy|upstream|based on|from https)", line, re.I):
                result["note"] = _squash(line, 300)
                result["snippet"] = _squash(line, 300)
                result["file"] = ("%s/%s" % (rel_dir, name)) if rel_dir else name
                result["line"] = lineno
            if not result["upstream"]:
                found = re.search(r"https?://github\.com/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+", line)
                if found:
                    result["upstream"] = found.group(0)
        if result["note"] and result["upstream"]:
            break
    return result


def _count_files(directory, limit=4000):
    count = 0
    for _root, _dirs, files in os.walk(directory):
        count += len(files)
        if count >= limit:
            return limit
    return count


# ---------------------------------------------------------------- 主入口

def scan(repo_path, repo_name=""):
    """扫描仓库，返回 candidates / signals / digest。"""
    files = []
    for dirpath, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [d for d in dirnames if d not in SCAN_SKIP_DIRS]
        for name in filenames:
            if len(files) >= MAX_FILES:
                break
            ext = os.path.splitext(name)[1].lower()
            if ext not in LANG_BY_EXT:
                continue
            path = os.path.join(dirpath, name)
            try:
                if os.path.getsize(path) > MAX_FILE_BYTES:
                    continue
                text = open(path, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            if not text.strip():
                continue
            files.append((os.path.relpath(path, repo_path).replace("\\", "/"), text, LANG_BY_EXT[ext]))

    candidates = []
    for rel, text, language in files:
        if language == "python":
            candidates.extend(_collect_python(rel, text))
        else:
            # 大仓库的性能闸门：整篇都不沾 AI 词汇的文件直接跳过
            if not AI_CONTEXT_RE.search(text):
                continue
            candidates.extend(_collect_generic(rel, text, language))

    # 去重：(名字, 文件, 行号)
    seen, unique = set(), []
    for item in candidates:
        key = (item["name"].lower(), item["file"], item["line"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    signals = collect_config_signals(repo_path)
    search_text = "\n".join(text for _, text, _ in files)[:900_000]

    return {
        "candidates": unique,
        "signals": signals,
        "files_scanned": len(files),
        "search_text": search_text,
        "digest": _build_digest(repo_name, files, unique, signals),
    }


def locate(repo_path, name, limit_files=1500):
    """按名字回仓库里定位真实行号，用于给"大模型补充的资产"补上可核查的证据。"""
    if not name or len(name) < 3:
        return None
    needle = name.lower()
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [d for d in dirnames if d not in SCAN_SKIP_DIRS]
        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in LANG_BY_EXT:
                continue
            scanned += 1
            if scanned > limit_files:
                return None
            path = os.path.join(dirpath, filename)
            try:
                if os.path.getsize(path) > MAX_FILE_BYTES:
                    continue
                text = open(path, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            position = text.lower().find(needle)
            if position == -1:
                continue
            line = _line_of(text, position)
            line_start = text.rfind("\n", 0, position) + 1
            line_end = text.find("\n", position)
            return {
                "file": os.path.relpath(path, repo_path).replace("\\", "/"),
                "line": line,
                "code": _squash(text[line_start:line_end if line_end != -1 else len(text)], 300),
            }
    return None


_COMMENT_PREFIXES = ("//", "#", "/*", "*", "<!--", "--")


def _is_comment_line(line):
    stripped = line.lstrip()
    return not stripped or stripped.startswith(_COMMENT_PREFIXES)


def _use_patterns(variant):
    """只认真正的"引用语句"，不认注释/文档里顺带提到的词。"""
    escaped = re.escape(variant)
    return [
        re.compile(r"^\s*(?:pub\s+)?use\s+" + escaped + r"\b"),
        re.compile(r"\buse\s+" + escaped + r"\b"),
        re.compile(r"^\s*extern\s+crate\s+" + escaped + r"\b"),
        re.compile(r"\b" + escaped + r"::"),
        re.compile(r"^\s*from\s+" + escaped + r"(?:\s+|\.)"),
        re.compile(r"^\s*import\s+" + escaped + r"\b"),
        re.compile(r"(?:from|require\s*\()\s*['\"]" + escaped + r"['\"/]"),
    ]


_USAGE_LINE_RE = re.compile(r"\b(use|import|from|require|extern\s+crate|#include)\b")
_USAGE_INDEX = {}


def _usage_index(repo_path, limit_files=3000):
    """单遍扫出仓库里所有"引用类"代码行，供 locate_usage 复用。

    之前每个资产都整仓扫一遍，openpencil 上要 4×3500 个文件，慢到 4 分钟；
    这里扫一遍缓存起来，后续按名字匹配就行。
    """
    key = os.path.abspath(repo_path)
    if key in _USAGE_INDEX:
        return _USAGE_INDEX[key]

    rows = []
    scanned = 0
    manifests = {"cargo.toml", "package.json", "pyproject.toml",
                 "requirements.txt", "cargo.lock"}
    for dirpath, dirnames, filenames in os.walk(repo_path):
        dirnames[:] = [d for d in dirnames if d not in SCAN_SKIP_DIRS]
        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in LANG_BY_EXT or filename.lower() in manifests:
                continue
            path = os.path.join(dirpath, filename)
            try:
                if os.path.getsize(path) > MAX_FILE_BYTES:
                    continue
                text = open(path, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            scanned += 1
            if scanned > limit_files:
                _USAGE_INDEX[key] = rows
                return rows
            rel = os.path.relpath(path, repo_path).replace("\\", "/")
            for lineno, line in enumerate(text.splitlines(), 1):
                if len(line) > 400 or not _USAGE_LINE_RE.search(line):
                    continue
                if _is_comment_line(line):
                    continue
                rows.append((rel, lineno, line.strip()))
    _USAGE_INDEX[key] = rows
    return rows


def locate_usage(repo_path, names, limit_files=2500):
    """在仓库源码里找"实际引用某个库/包"的第一处位置。

    只认 `use x::` / `from x import` / `require('x')` 这类真实引用，
    并且跳过注释行——否则会在文档注释里撞到同名词，给出误导性证据。
    """
    variants = set()
    for name in names:
        if not name:
            continue
        text = str(name).strip()
        if text.endswith(".git"):
            text = text[:-4]
        for part in text.split("/"):
            part = part.strip()
            if len(part) < 5:            # 太短的名字（jian/agent）到处都能撞上，放弃
                continue
            variants.add(part)
            variants.add(part.replace("-", "_"))
            variants.add(part.replace("_", "-"))
    variants = sorted(v for v in variants if len(v) >= 5)
    if not variants:
        return None

    patterns = [(variant, _use_patterns(variant)) for variant in variants]
    for rel, lineno, line in _usage_index(repo_path, limit_files):
        for variant, variant_patterns in patterns:
            if any(pattern.search(line) for pattern in variant_patterns):
                return {"file": rel, "line": lineno, "code": _squash(line, 300),
                        "matched": variant}
    return None


def _read_package_name(directory):
    """从 vendored 目录自己的清单里读包名（比目录名更准）。"""
    cargo = os.path.join(directory, "Cargo.toml")
    if os.path.isfile(cargo):
        try:
            text = open(cargo, encoding="utf-8", errors="ignore").read()[:4000]
            match = re.search(r"^\s*name\s*=\s*\"([^\"]+)\"", text, re.M)
            if match:
                return match.group(1)
        except OSError:
            pass
    pkg = os.path.join(directory, "package.json")
    if os.path.isfile(pkg):
        try:
            text = open(pkg, encoding="utf-8", errors="ignore").read()[:4000]
            match = re.search(r"\"name\"\s*:\s*\"([^\"]+)\"", text)
            if match:
                return match.group(1)
        except OSError:
            pass
    return ""


def _build_digest(repo_name, files, candidates, signals, budget=70_000):
    """给大模型看的摘要：代码片段 + 配置信号。"""
    by_rel = {rel: text for rel, text, _ in files}
    parts, used = [], 0

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

    add("配置信号", "\n".join(
        ["- 子模块: %s" % ", ".join("%s -> %s" % (g["path"], g["url"])
                                    for g in signals["gitmodules"][:10]),
         "- vendor 目录: %s" % ", ".join("%s (%s)" % (v["path"], v["upstream"] or "未知上游")
                                         for v in signals["vendored"][:10]),
         "- skills 目录: %s" % ", ".join(s["name"] for s in signals["skills"][:20]),
         "- MCP 服务: %s" % ", ".join(m["name"] for m in signals["mcp_servers"][:15]),
         "- AI 依赖: %s" % ", ".join(sorted({d["name"] for d in signals["ai_dependencies"]})[:25]),
         ]), 4000)

    # 优先放有候选调用点的文件
    hot = {c["file"] for c in candidates}
    ordered = sorted(files, key=lambda row: (row[0] not in hot, row[0]))
    for rel, text, _lang in ordered[:40]:
        add("文件 %s" % rel, text, 2600 if rel in hot else 1200)

    header = ("仓库: %s\n扫描文件数: %d\n候选引用点: %d\n"
              % (repo_name or "(未知)", len(files), len(candidates)))
    return header + "".join(parts)
