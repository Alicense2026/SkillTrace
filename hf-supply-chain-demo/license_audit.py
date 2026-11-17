# -*- coding: utf-8 -*-
"""对「输入的 GitHub 仓库」做许可证审计。

解决的问题
----------
1. 用户输入的许可证可能不对（或写成 "Other"/"A_unknown" 这类非 SPDX 值），
   需要回到仓库里核实。
2. 许可证不一定只在 LICENSE 文件里：README 的 License 章节、package.json /
   Cargo.toml / pyproject.toml 等元数据字段、REUSE 的 LICENSES/ 目录、
   源文件头的 SPDX-License-Identifier 都可能是依据。
3. 大仓库里常有用自己许可证的子目录（vendor/、third_party/、独立子项目），
   只看根目录会漏掉。

注意：本模块只服务于「输入仓库自身的许可证」。
仓库里用到的 AI model / dataset / tool 的许可证仍由 registries.py 负责，不走这里。
"""

from __future__ import annotations

import json
import os
import re

# 目录裁剪：这些目录里的许可证与"本仓库怎么授权"无关，且体量巨大
SKIP_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "bower_components", "venv", ".venv",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
    "dist", "build", "target", "coverage", ".nyc_output", ".next", ".nuxt",
    ".idea", ".vscode", ".gradle", ".cargo", "site-packages", ".yarn",
    ".pnp", "Pods", "DerivedData", ".terraform",
}

# 这些子目录名通常意味着"这里是别人写的代码"
VENDOR_DIRS = {
    "vendor", "vendors", "third_party", "third-party", "thirdparty", "3rdparty",
    "external", "extern", "deps", "dependencies", "bundled", "contrib",
    "subprojects", "modules", "externals", "3rd_party",
}

LICENSE_NAME_RE = re.compile(
    r"^(licen[cs]e|copying|notice|unlicense|copyright|patents)([-._].*)?$", re.I)

README_RE = re.compile(r"^readme(\.[a-z]+)?$", re.I)

# 仓库里可能有"许可证字段"的清单文件
MANIFEST_FILES = {
    "package.json", "composer.json", "bower.json", "deno.json",
    "Cargo.toml", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile",
    "pom.xml", "build.gradle", "build.gradle.kts", "project.clj",
    "pubspec.yaml", "Package.swift", "mix.exs", "DESCRIPTION",
}

SPDX_HEADER_RE = re.compile(r"spdx-license-identifier:\s*([A-Za-z0-9.+\- ()]+)", re.I)

# --------------------------------------------------------------------------
# SPDX 识别
# --------------------------------------------------------------------------

# 正文签名：顺序很重要，包含关系强的放前面（AGPL 正文含 "GNU GENERAL PUBLIC LICENSE"）
TEXT_SIGNATURES = [
    ("AGPL-3.0", [r"gnu affero general public license"]),
    ("LGPL-3.0", [r"gnu lesser general public license", r"version 3"]),
    ("LGPL-2.1", [r"gnu lesser general public license", r"version 2\.1"]),
    ("GPL-3.0", [r"gnu general public license", r"version 3"]),
    ("GPL-2.0", [r"gnu general public license", r"version 2"]),
    ("Apache-2.0", [r"apache license", r"version 2\.0"]),
    ("MPL-2.0", [r"mozilla public license", r"version 2\.0"]),
    ("EPL-2.0", [r"eclipse public license", r"2\.0"]),
    ("CC0-1.0", [r"cc0 1\.0 universal"]),
    ("CC-BY-SA-4.0", [r"creative commons attribution-sharealike 4\.0"]),
    ("CC-BY-NC-4.0", [r"creative commons attribution-noncommercial 4\.0"]),
    ("CC-BY-4.0", [r"creative commons attribution 4\.0"]),
    ("Unlicense", [r"free and unencumbered software released into the public domain"]),
    ("BSL-1.0", [r"boost software license"]),
    ("Zlib", [r"this software is provided 'as-is'",
              r"permission is granted to anyone to use this software"]),
    ("ISC", [r"permission to use, copy, modify, and(/or| or) distribute this software"]),
    ("BSD-3-Clause", [r"redistribution and use in source and binary forms",
                      r"neither the name of"]),
    ("BSD-2-Clause", [r"redistribution and use in source and binary forms"]),
    ("MIT", [r"permission is hereby granted, free of charge"]),
    ("WTFPL", [r"do what the fuck you want to public license"]),
    ("Artistic-2.0", [r"the artistic license 2\.0"]),
    ("Python-2.0", [r"python software foundation license"]),
    ("PostgreSQL", [r"postgresql license"]),
    ("Elastic-2.0", [r"elastic license 2\.0"]),
    ("SSPL-1.0", [r"server side public license"]),
    ("BUSL-1.1", [r"business source license"]),
    ("Sustainable-Use", [r"sustainable use license"]),
    ("Llama-Community", [r"llama (community )?license agreement",
                         r"meta platforms"]),
    ("Gemma-Terms", [r"gemma terms of use"]),
]

# 自由文本 / 元数据字段值 -> SPDX
ALIASES = {
    "mit": "MIT", "mit license": "MIT", "the mit license": "MIT",
    "apache": "Apache-2.0", "apache 2": "Apache-2.0", "apache 2.0": "Apache-2.0",
    "apache-2": "Apache-2.0", "apache-2.0": "Apache-2.0",
    "apache license": "Apache-2.0", "apache license 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0", "apache license version 2.0": "Apache-2.0",
    "asl 2.0": "Apache-2.0",
    "bsd": "BSD-3-Clause", "bsd-2": "BSD-2-Clause", "bsd-2-clause": "BSD-2-Clause",
    "bsd 2-clause": "BSD-2-Clause", "bsd-3": "BSD-3-Clause",
    "bsd-3-clause": "BSD-3-Clause", "bsd 3-clause": "BSD-3-Clause",
    "gpl": "GPL-3.0", "gplv2": "GPL-2.0", "gpl-2.0": "GPL-2.0", "gplv3": "GPL-3.0",
    "gpl-3.0": "GPL-3.0", "gpl-2.0-only": "GPL-2.0", "gpl-3.0-only": "GPL-3.0",
    "lgpl": "LGPL-3.0", "lgpl-2.1": "LGPL-2.1", "lgpl-3.0": "LGPL-3.0",
    "agpl": "AGPL-3.0", "agpl-3.0": "AGPL-3.0", "agpl-3.0-only": "AGPL-3.0",
    "mpl": "MPL-2.0", "mpl-2.0": "MPL-2.0", "mozilla public license 2.0": "MPL-2.0",
    "isc": "ISC", "unlicense": "Unlicense", "the unlicense": "Unlicense",
    "cc0": "CC0-1.0", "cc0-1.0": "CC0-1.0",
    "cc-by-4.0": "CC-BY-4.0", "cc-by-sa-4.0": "CC-BY-SA-4.0",
    "cc-by-nc-4.0": "CC-BY-NC-4.0", "cc-by-nc-sa-4.0": "CC-BY-NC-SA-4.0",
    "zlib": "Zlib", "bsl-1.0": "BSL-1.0", "boost": "BSL-1.0",
    "epl-2.0": "EPL-2.0", "eclipse public license 2.0": "EPL-2.0",
    "wtfpl": "WTFPL", "artistic-2.0": "Artistic-2.0",
    "python-2.0": "Python-2.0", "postgresql": "PostgreSQL",
    "elastic-2.0": "Elastic-2.0", "sspl-1.0": "SSPL-1.0", "busl-1.1": "BUSL-1.1",
    "sustainable use license": "Sustainable-Use",
    "llama3": "Llama-Community", "llama 3": "Llama-Community",
    "llama-community": "Llama-Community", "llama community license": "Llama-Community",
    "gemma": "Gemma-Terms",
}

# 不是许可证的占位值（用户表格里会出现）
NON_LICENSE = {"", "-", "—", "other", "a_unknown", "unknown", "none", "null",
               "proprietary", "noassertion", "n/a", "custom"}


def normalize_id(value):
    """把任意写法的许可证名归一成 SPDX 标识；不是标准许可证时返回 None。"""
    if value is None:
        return None
    raw = str(value).strip()
    if raw.lower() in NON_LICENSE:
        return None
    # SPDX 表达式（MIT OR Apache-2.0）原样保留
    if re.search(r"\b(AND|OR|WITH)\b", raw):
        return raw
    key = re.sub(r"\s+", " ", raw.lower()).strip()
    if key in ALIASES:
        return ALIASES[key]
    key2 = key.replace(" license", "").strip()
    if key2 in ALIASES:
        return ALIASES[key2]
    # n8n 这类写在文件头里的自定义引用：LicenseRef-n8n-sustainable-use
    m = re.match(r"licenseref[-_ ]?(.+)$", key)
    if m:
        inner = re.sub(r"[-_]+", " ", m.group(1)).strip()
        direct = normalize_id(inner)
        if direct:
            return direct
        # 逐个子串匹配，把 "n8n sustainable use" 归到 "sustainable use"
        for alias, spdx in sorted(ALIASES.items(), key=lambda kv: -len(kv[0])):
            flat = re.sub(r"[-_]+", " ", alias)
            for candidate in (flat, flat.replace(" license", "").strip()):
                if candidate and len(candidate) >= 6 and candidate in inner:
                    return spdx
        return raw
    # 已经是合法 SPDX 形式（形如 Apache-2.0 / BSD-3-Clause）
    if re.fullmatch(r"[A-Za-z0-9.+\-]{2,40}", raw) and "-" in raw:
        return raw
    return None


def identify_text(text):
    """从许可证正文认 SPDX；返回 (spdx, confidence) 或 (None, None)。

    先只看文件开头的「标题区」：一个 LICENSE 文件常常在正文后面附带别的许可证
    （附录、第三方声明），如果全文匹配，GPL-3.0 的文件里只要出现一次
    "GNU AFFERO GENERAL PUBLIC LICENSE" 就会被误判成 AGPL——实测 netdata、
    chatbox 都踩过这个坑。所以优先采信文件自己报的名字。
    """
    if not text:
        return None, None
    low = text.lower()
    head = low[:900]

    for name, patterns in TEXT_SIGNATURES:
        if all(re.search(p, head) for p in patterns):
            return name, "high"

    for name, patterns in TEXT_SIGNATURES:
        if all(re.search(p, low) for p in patterns):
            return name, "medium"
    return None, None


def identify_loose(text):
    """从 README 等自由文本里抽许可证名（比正文匹配宽松）。"""
    if not text:
        return None
    low = text.lower()
    # 优先找 "licensed under the X" / "under the X license"
    m = re.search(r"licen[cs]ed under (?:the )?([a-z0-9.\- ]{2,40}?)(?: license| licence|\.|,|$)",
                  low)
    if m:
        got = normalize_id(m.group(1)) or normalize_id(m.group(1) + " license")
        if got:
            return got
    for name, patterns in TEXT_SIGNATURES:
        if all(re.search(p, low) for p in patterns):
            return name
    # 兜底：直接找常见 SPDX 名字
    for alias, spdx in sorted(ALIASES.items(), key=lambda kv: -len(kv[0])):
        if re.search(r"\b" + re.escape(alias) + r"\b", low):
            return spdx
    return None


# --------------------------------------------------------------------------
# 扫描
# --------------------------------------------------------------------------

def _line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def _squash(text, limit=160):
    return re.sub(r"\s+", " ", (text or "")).strip()[:limit]


def _read(path, limit=400000):
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def _rel(repo_path, path):
    return os.path.relpath(path, repo_path).replace("\\", "/")


def _category(rel_dir):
    """判断子目录属于哪一类。"""
    parts = [p.lower() for p in rel_dir.split("/") if p]
    if any(p in VENDOR_DIRS for p in parts):
        return "第三方捆绑"
    return "子目录声明"


def _has_manifest(dirpath):
    for name in os.listdir(dirpath):
        if name in MANIFEST_FILES or name.endswith((".gemspec", ".csproj", ".nuspec")):
            return True
    return False


def _manifest_license(path):
    """从清单文件里读许可证声明，返回 (spdx, line, snippet)。"""
    name = os.path.basename(path)
    text = _read(path, 200000)
    if not text:
        return None, 0, ""

    def hit(value, pattern):
        m = re.search(pattern, text, re.M | re.I)
        if not m:
            return None, 0, ""
        spdx = normalize_id(value)
        if not spdx:
            return None, 0, ""
        return spdx, _line_of(text, m.start()), _squash(m.group(0), 120)

    if name == "package.json":
        try:
            data = json.loads(text)
        except Exception:
            data = None
        if isinstance(data, dict):
            value = data.get("license")
            if isinstance(value, dict):
                value = value.get("type")
            if not value and isinstance(data.get("licenses"), list):
                first = data["licenses"][0]
                value = first.get("type") if isinstance(first, dict) else first
            spdx = normalize_id(value)
            if spdx:
                m = re.search(r'"(?:licenses?|type)"\s*:\s*"([^"]+)"', text)
                line = _line_of(text, m.start()) if m else 1
                return spdx, line, _squash(m.group(0) if m else str(value), 120)
        return None, 0, ""

    if name == "composer.json":
        m = re.search(r'"license"\s*:\s*"([^"]+)"', text)
        if m:
            return hit(m.group(1), r'"license"\s*:\s*"[^"]+"')
        return None, 0, ""

    if name == "Cargo.toml":
        return hit(*_first_value(text, r'^\s*license\s*=\s*"([^"]+)"',
                                 r'^\s*license\s*=\s*"[^"]+"'))

    if name == "pyproject.toml":
        for pat_val, pat_full in (
                (r'^\s*license\s*=\s*"([^"]+)"', r'^\s*license\s*=\s*"[^"]+"'),
                (r'^\s*license\s*=\s*\{\s*text\s*=\s*"([^"]+)"',
                 r'^\s*license\s*=\s*\{[^}]*\}'),
                (r'License :: OSI Approved :: ([^\n"]+)"',
                 r'License :: OSI Approved :: [^\n"]+"')):
            spdx, line, snip = hit(*_first_value(text, pat_val, pat_full))
            if spdx:
                return spdx, line, snip
        return None, 0, ""

    if name in ("setup.py", "setup.cfg"):
        return hit(*_first_value(text, r"license\s*=\s*['\"]([^'\"]+)['\"]",
                                 r"license\s*=\s*['\"][^'\"]+['\"]"))

    if name == "pom.xml":
        m = re.search(r"<license>.*?<name>\s*([^<]+?)\s*</name>", text, re.S | re.I)
        if m:
            return hit(m.group(1), r"<name>\s*[^<]+?\s*</name>")
        return None, 0, ""

    if name.endswith(".gemspec"):
        return hit(*_first_value(text, r"\.license\s*=\s*['\"]([^'\"]+)['\"]",
                                 r"\.license\s*=\s*['\"][^'\"]+['\"]"))

    if name.endswith(".csproj") or name.endswith(".nuspec"):
        m = re.search(r"<PackageLicenseExpression>\s*([^<]+?)\s*<", text)
        if not m:
            m = re.search(r'<license[^>]*type="expression"[^>]*>\s*([^<]+?)\s*<', text)
        if m:
            return hit(m.group(1), r"<PackageLicenseExpression>[^<]+<")
        return None, 0, ""

    return None, 0, ""


def _first_value(text, value_pattern, full_pattern):
    """返回 (值, 整行匹配)，供 hit() 用。"""
    m = re.search(value_pattern, text, re.M | re.I)
    if not m:
        return None, full_pattern
    return m.group(1), full_pattern


HEADING_RE = re.compile(r"^(#{1,6})\s*(.+?)\s*$")
LICENSE_HEADING_RE = re.compile(
    r"(^|\b)(licen[cs]e|licensing|许可|授权|协议|版权)", re.I)


def _readme_section(text):
    """从 README 里抽 License 章节，返回 (spdx, line, snippet)。"""
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if not m:
            continue
        if not LICENSE_HEADING_RE.search(m.group(2)):
            continue
        level = len(m.group(1))
        collected = []
        for nxt in range(idx + 1, min(idx + 40, len(lines))):
            h = HEADING_RE.match(lines[nxt])
            if h and len(h.group(1)) <= level:
                break
            collected.append(lines[nxt])
        block = "\n".join(collected).strip()
        if not block:
            continue
        spdx = identify_loose(block)
        if spdx:
            return spdx, idx + 1, _squash(block, 200)
    return None, 0, ""


def _spdx_headers(repo_path, max_files=6000):
    """统计源文件头里的 SPDX-License-Identifier，按顶层目录聚合。"""
    by_dir = {}
    scanned = 0
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if not name.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".go",
                                  ".rs", ".java", ".kt", ".c", ".h", ".cpp",
                                  ".rb", ".sh", ".css", ".scss")):
                continue
            scanned += 1
            if scanned > max_files:
                return by_dir, scanned
            path = os.path.join(root, name)
            try:
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    head = "".join([fh.readline() for _ in range(6)])
            except OSError:
                continue
            m = SPDX_HEADER_RE.search(head)
            if not m:
                continue
            spdx = normalize_id(m.group(1).strip())
            if not spdx:
                continue
            rel = _rel(repo_path, root)
            top = "" if rel == "." else rel.split("/")[0]
            by_dir.setdefault(top, {})
            by_dir[top][spdx] = by_dir[top].get(spdx, 0) + 1
    return by_dir, scanned


def scan(repo_path, max_license_files=200, max_files=8000):
    """扫描仓库里的许可证证据。返回结构化 dict。"""
    repo_path = os.path.abspath(repo_path)
    root_abs = os.path.abspath(repo_path)

    evidence = []          # 主许可证候选（根目录）
    sub_licenses = []      # 子目录专属许可证
    stats = {"files": 0, "license_files": 0, "manifests": 0, "readmes": 0,
             "reuse": 0, "spdx_headers": 0}
    license_files_seen = 0

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel_dir = _rel(repo_path, root)
        if rel_dir == ".":
            rel_dir = ""
        depth = 0 if not rel_dir else len(rel_dir.split("/"))
        if depth > 5:                      # 太深的目录不再往下找
            dirs[:] = []

        # REUSE 规范：LICENSES/<SPDX>.txt
        if os.path.basename(root).lower() == "licenses" and depth <= 1:
            for name in files:
                if not name.lower().endswith(".txt"):
                    continue
                spdx = normalize_id(os.path.splitext(name)[0])
                if spdx:
                    stats["reuse"] += 1
                    evidence.append({
                        "spdx": spdx, "file": _rel(repo_path, os.path.join(root, name)),
                        "line": 1, "via": "reuse-licenses", "weight": 0.95,
                        "snippet": "REUSE 规范：LICENSES/%s" % name})
            continue

        is_root = (root == root_abs)
        has_manifest = False if not files else _has_manifest(root)

        for name in files:
            stats["files"] += 1
            if stats["files"] > max_files:
                break
            path = os.path.join(root, name)
            rel = _rel(repo_path, path)

            # ① 许可证文件
            if LICENSE_NAME_RE.match(name):
                license_files_seen += 1
                if license_files_seen > max_license_files:
                    continue
                stats["license_files"] += 1
                text = _read(path, 200000)
                spdx, conf = identify_text(text)
                entry = {
                    "spdx": spdx, "file": rel, "line": 1,
                    "via": "license-file",
                    "snippet": _squash(text, 180),
                    "weight": 1.0 if is_root else 0.6,
                    "confidence": conf or ("low" if not spdx else conf),
                }
                if is_root:
                    evidence.append(entry)
                else:
                    entry["dir"] = rel_dir
                    entry["category"] = "第三方捆绑" if _category(rel_dir) == "第三方捆绑" \
                        else ("独立子项目" if has_manifest else "子目录声明")
                    sub_licenses.append(entry)
                continue

            # ② README
            if is_root and README_RE.match(name):
                stats["readmes"] += 1
                text = _read(path, 300000)
                spdx, line, snippet = _readme_section(text)
                if spdx:
                    evidence.append({
                        "spdx": spdx, "file": rel, "line": line,
                        "via": "readme", "snippet": snippet, "weight": 0.7,
                        "confidence": "medium"})
                continue

            # ③ 清单文件
            if name in MANIFEST_FILES or name.endswith((".gemspec", ".csproj", ".nuspec")):
                spdx, line, snippet = _manifest_license(path)
                if spdx:
                    stats["manifests"] += 1
                    entry = {
                        "spdx": spdx, "file": rel, "line": line,
                        "via": "manifest", "snippet": snippet,
                        "weight": 0.85 if is_root else 0.55,
                        "confidence": "high" if is_root else "medium"}
                    if is_root:
                        evidence.append(entry)
                    else:
                        entry["dir"] = rel_dir
                        entry["category"] = "第三方捆绑" if _category(rel_dir) == "第三方捆绑" \
                            else "独立子项目"
                        sub_licenses.append(entry)

        if stats["files"] > max_files:
            break

    # ④ 源文件头 SPDX
    headers, scanned = _spdx_headers(repo_path)
    stats["spdx_headers"] = scanned
    header_top = {}
    for top, counter in headers.items():
        best = max(counter.items(), key=lambda kv: kv[1])
        header_top[top] = best
    root_header = header_top.get("")
    if root_header and not any(e["via"] == "license-file" for e in evidence):
        evidence.append({
            "spdx": root_header[0], "file": "(源文件头)", "line": 1,
            "via": "spdx-header",
            "snippet": "根目录 %d 个源文件标注 SPDX-License-Identifier: %s"
                       % (root_header[1], root_header[0]),
            "weight": 0.6, "confidence": "medium"})

    # 子目录许可证去重：同一个目录同一个许可证只留一条（取权重最高的）
    deduped = {}
    for item in sub_licenses:
        key = (item.get("dir") or "", item.get("spdx") or "?")
        if key not in deduped or item.get("weight", 0) > deduped[key].get("weight", 0):
            deduped[key] = item
    sub_licenses = list(deduped.values())

    evidence.sort(key=lambda e: (-e["weight"], e["file"]))
    return {
        "repo_path": repo_path,
        "evidence": evidence,
        "sub_licenses": sorted(sub_licenses, key=lambda e: (e.get("dir", ""), e["file"])),
        "header_by_dir": header_top,
        "stats": stats,
    }


def audit(repo_path, provided=None, use_llm=True, quiet=False):
    """完整审计：扫描 + 与输入比对 + 结论。"""
    result = scan(repo_path)
    evidence = result["evidence"]
    provided_norm = normalize_id(provided)
    provided_raw = (str(provided).strip() if provided else "")

    # 根目录可能有多份许可证文件（如 CC-BY-4.0 文档 + MIT 代码）
    root_licenses = []
    for item in evidence:
        if item.get("spdx") and item["via"].startswith("license-file"):
            if item["spdx"] not in root_licenses:
                root_licenses.append(item["spdx"])

    root = None
    for item in evidence:
        if item.get("spdx"):
            root = dict(item)
            break
    if root is None and evidence:
        root = dict(evidence[0])

    # 正文认不出来时用大模型兜底（仅对根目录的真·许可证文件）
    if root and not root.get("spdx") and root.get("via") == "license-file" and use_llm:
        try:
            from github.license import detect_with_llm
            path = os.path.join(repo_path, root["file"])
            got = detect_with_llm(os.path.basename(root["file"]), _read(path, 200000))
            if got:
                root["spdx"] = got
                root["via"] = "license-file+llm"
                root["confidence"] = "low"
                if got not in root_licenses:
                    root_licenses.insert(0, got)
        except Exception:
            pass

    # 有许可证文件但认不出来 → 标记为自定义许可证，而不是「未识别」
    has_license_file = any(e["via"].startswith("license-file") for e in evidence)
    if root and not root.get("spdx") and has_license_file:
        root["spdx"] = "LicenseRef-Custom"
        root["confidence"] = root.get("confidence") or "low"

    root_spdx = (root or {}).get("spdx")
    # 注意：这里必须用「并集」，不能写成
    #     root_set = {...} or ({root_spdx...})
    # 否则只要 root_licenses 非空，主许可证 root_spdx 就被整个丢掉了。
    # 实际踩过的坑：root_licenses=["MIT"] 而 root_spdx="Apache-2.0" 时，
    # 集合只剩 {"mit"}，输入 Apache-2.0 会被误判成「不一致」，
    # 但「实际许可证」列又显示 Apache-2.0，于是出现「输入和实际相同却判不一致」。
    root_set = {x.lower() for x in root_licenses}
    if root_spdx:
        root_set.add(root_spdx.lower())

    # 子目录：区分「与主许可证相同（重复声明）」和「真正专属」
    for item in result["sub_licenses"]:
        item["same_as_root"] = bool(item.get("spdx")) and item["spdx"].lower() in root_set
    conflicts = [s for s in result["sub_licenses"]
                 if s.get("spdx") and not s.get("same_as_root")]
    same = [s for s in result["sub_licenses"] if s.get("same_as_root")]

    # 结论
    if not provided_raw:
        verdict = "未提供"
        reason = "输入未给许可证，已按仓库实际填写"
    elif not provided_norm:
        verdict = "输入非 SPDX"
        reason = "输入 %r 不是标准 SPDX 标识，已按仓库实际填写（%s）" % (
            provided_raw, root_spdx or "未识别")
    elif not root_spdx:
        verdict = "无法确认"
        reason = "仓库里没找到可识别的许可证声明"
    elif provided_norm.lower() in root_set:
        verdict = "一致"
        reason = "输入与仓库实际一致（%s）" % provided_norm
    else:
        verdict = "不一致"
        extra = "（仓库为多许可证：%s）" % " + ".join(root_licenses) if len(root_licenses) > 1 else ""
        reason = "输入 %s，仓库实际 %s%s" % (provided_norm, root_spdx, extra)

    result.update({
        "provided": provided_raw,
        "provided_norm": provided_norm,
        "root": root,
        "root_spdx": root_spdx,
        "root_licenses": root_licenses,
        "verdict": verdict,
        "verdict_reason": reason,
        "sub_same": same,
        "conflicts": conflicts,
        "confirmed_spdx": root_spdx or provided_norm or provided_raw or "unknown",
    })
    return result


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------

AUDIT_COLUMNS = ["仓库", "输入许可证", "仓库主许可证", "仓库全部许可证", "结论",
                 "依据文件", "依据方式", "行号", "证据片段",
                 "专属许可证子目录数", "专属许可证清单", "说明"]


def to_row(repo_name, audit_result):
    """转成审计 CSV 的一行。"""
    root = audit_result.get("root") or {}
    conflicts = audit_result.get("conflicts") or []
    listing = []
    for item in conflicts[:8]:
        listing.append("%s→%s%s" % (item.get("dir") or ".", item.get("spdx"),
                                    ("[%s]" % item["category"])
                                    if item.get("category") else ""))
    if len(conflicts) > 8:
        listing.append("…共 %d 个" % len(conflicts))
    return {
        "仓库": repo_name,
        "输入许可证": audit_result.get("provided") or "",
        "仓库主许可证": audit_result.get("root_spdx") or "未识别",
        "仓库全部许可证": " + ".join(audit_result.get("root_licenses") or [])
                          or (audit_result.get("root_spdx") or ""),
        "结论": audit_result.get("verdict") or "",
        "依据文件": root.get("file") or "",
        "依据方式": root.get("via") or "",
        "行号": root.get("line") or "",
        "证据片段": root.get("snippet") or "",
        "专属许可证子目录数": len(conflicts),
        "专属许可证清单": "；".join(listing),
        "说明": audit_result.get("verdict_reason") or "",
    }


def summary_line(audit_result):
    """控制台一行摘要。"""
    root = audit_result.get("root") or {}
    conflicts = audit_result.get("conflicts") or []
    same = audit_result.get("sub_same") or []
    parts = ["仓库实际 %s（%s%s）"
             % (audit_result.get("root_spdx") or "未识别",
                root.get("via") or "-",
                (":%s" % root.get("file")) if root.get("file") else "")]
    if len(audit_result.get("root_licenses") or []) > 1:
        parts.append("多许可证 " + " + ".join(audit_result["root_licenses"]))
    if audit_result.get("provided"):
        parts.append("输入 %s → %s" % (audit_result["provided"], audit_result["verdict"]))
    if conflicts or same:
        parts.append("子目录：%d 个专属 / %d 个重复声明" % (len(conflicts), len(same)))
    return " ｜ ".join(parts)
