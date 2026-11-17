# -*- coding: utf-8 -*-
"""识别 GitHub 仓库使用的许可证【名字】（只要名字，不要正文）。

优先级：
  1. 用户通过命令行直接给出的许可证名（demo 的输入要求里包含它）
  2. 仓库里的 LICENSE / COPYING 文件正文 -> 用签名规则匹配出 SPDX 名字
  3. GitHub REST API /license（未登录容易限流，所以放在本地之后）
  4. 交给 DeepSeek 读许可证正文判断（非标准许可证兜底）
  5. 都失败 -> "unknown"
"""

from __future__ import annotations

import os
import re

from github.api import repo_license

# 扫描许可证文件时跳过的目录
SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
    ".mypy_cache", ".pytest_cache", "site-packages", ".idea", ".vscode",
    "third_party", "vendor", "docs/_build",
}

LICENSE_FILE_RE = re.compile(r"^(licen[cs]e|copying|copyright|unlicense)(\.|$)", re.I)

# 顺序很重要：包含关系强的放前面（AGPL 正文里也含 "GNU GENERAL PUBLIC LICENSE"）
SIGNATURES = [
    ("AGPL-3.0", [r"gnu affero general public license"]),
    ("LGPL-3.0", [r"gnu lesser general public license", r"version 3"]),
    ("LGPL-2.1", [r"gnu lesser general public license", r"version 2\.1"]),
    ("GPL-3.0", [r"gnu general public license", r"version 3"]),
    ("GPL-2.0", [r"gnu general public license", r"version 2"]),
    ("Apache-2.0", [r"apache license", r"version 2\.0"]),
    ("MPL-2.0", [r"mozilla public license version 2\.0"]),
    ("CC0-1.0", [r"cc0 1\.0 universal"]),
    ("CC-BY-SA-4.0", [r"creative commons attribution-sharealike 4\.0"]),
    ("CC-BY-4.0", [r"creative commons attribution 4\.0"]),
    ("EPL-2.0", [r"eclipse public license"]),
    ("Unlicense", [r"free and unencumbered software released into the public domain"]),
    ("BSL-1.0", [r"boost software license"]),
    ("Zlib", [r"this software is provided 'as-is'", r"permission is granted to anyone to use this software"]),
    ("ISC", [r"permission to use, copy, modify, and(/or| or) distribute this software"]),
    ("BSD-3-Clause", [r"redistribution and use in source and binary forms", r"neither the name of"]),
    ("BSD-2-Clause", [r"redistribution and use in source and binary forms"]),
    ("MIT", [r"permission is hereby granted, free of charge"]),
]


# --------------------------------------------------------------------------
# 本地文件
# --------------------------------------------------------------------------

def find_license_file(repo_path, max_depth=1):
    """在仓库里找最像许可证的文件，返回 (路径, 内容) 或 (None, None)。"""
    candidates = []
    base = repo_path.rstrip("\\/")
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if root.rstrip("\\/").count(os.sep) - base.count(os.sep) > max_depth:
            dirs[:] = []
            continue
        for name in files:
            if LICENSE_FILE_RE.match(name):
                path = os.path.join(root, name)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                # 优先根目录、体积最大的那个
                candidates.append((0 if os.path.dirname(os.path.abspath(path)) == os.path.abspath(base) else 1,
                                   -size, path))
    if not candidates:
        return None, None
    candidates.sort()
    path = candidates[0][2]
    try:
        with open(path, encoding="utf-8", errors="ignore") as handle:
            return path, handle.read()
    except OSError:
        return path, ""


def detect_from_text(text):
    """用签名规则从许可证正文里认出 SPDX 名字，认不出返回 None。"""
    if not text:
        return None
    low = text.lower()
    for name, patterns in SIGNATURES:
        if all(re.search(pattern, low) for pattern in patterns):
            return name
    return None


# --------------------------------------------------------------------------
# 大模型兜底
# --------------------------------------------------------------------------

def detect_with_llm(file_name, text):
    from llm import chat_json

    snippet = (text or "")[:4000]
    data = chat_json(
        "下面是一个开源项目的许可证文件（文件名：%s）。\n"
        "请判断它属于哪个 SPDX 许可证标识符（例如 MIT、Apache-2.0、BSD-3-Clause、GPL-3.0）。\n"
        '只输出 JSON：{"license": "MIT", "confidence": "high|low", "reason": "一句话理由"}\n'
        '判断不出来时 license 填 "unknown"。\n\n'
        "许可证正文：\n%s" % (file_name or "LICENSE", snippet)
    )
    if not data:
        return None
    value = str(data.get("license") or "").strip()
    if not value or value.lower() in ("unknown", "none", "null"):
        return None
    return value


# --------------------------------------------------------------------------
# 对外接口
# --------------------------------------------------------------------------

def get_license(repo_path, full_name=None, provided=None, use_llm=True):
    """返回 dict: {"name": 许可证名字, "source": 来源, "file": 许可证文件相对路径}"""
    result = {"name": "unknown", "source": "unknown", "file": ""}

    # 1) 本地许可证文件
    path, text = find_license_file(repo_path)
    if path:
        try:
            result["file"] = os.path.relpath(path, repo_path)
        except ValueError:
            result["file"] = path
        name = detect_from_text(text)
        if name:
            result.update(name=name, source="local-file")
        elif use_llm:
            name = detect_with_llm(os.path.basename(path), text)
            if name:
                result.update(name=name, source="local-file+llm")

    # 2) 用户显式给出（demo 输入要求里有这一项，优先级最高）
    if provided:
        result.update(name=str(provided).strip(), source="user-input")

    # 3) GitHub API
    if result["name"] == "unknown" and full_name:
        data = repo_license(full_name)
        if data:
            lic = data.get("license") or {}
            spdx = lic.get("spdx_id")
            if spdx and spdx != "NOASSERTION":
                result.update(name=spdx, source="github-api")
            elif lic.get("name"):
                result.update(name=lic["name"], source="github-api")

    return result
