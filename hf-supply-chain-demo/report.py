# -*- coding: utf-8 -*-
"""结果输出：控制台表格 + CSV / Markdown / Excel。

9 列（对应需求）：
  1 GitHub仓库名
  2 GitHub URL
  3 GitHub许可证
  4 AI 资产名（model / dataset / tool）
  5 资产 URL
  6 资产许可证
  7 调用方式（代码层面集成 / 远程服务调用）
  8 代码层面集成是否修改（远程调用输出 \）
  9 调用证据

Excel 优先用 pandas + openpyxl；环境里没装时退回到内置的纯标准库 xlsx 写出器。
"""

from __future__ import annotations

import csv
import json
import os
import re
import time
import zipfile
from xml.sax.saxutils import escape

COLUMNS = [
    "GitHub仓库名",
    "GitHub URL",
    "GitHub许可证",
    "AI模型/数据集/工具名",
    "资产URL",
    "资产许可证",
    "调用方式",
    "代码集成是否修改",
    "调用证据",
]
KEYS = [
    "github_repo",
    "github_url",
    "github_license",
    "artifact_name",
    "artifact_url",
    "artifact_license",
    "integration",
    "modified",
    "evidence",
]
COLUMN_WIDTHS = [18, 40, 14, 32, 44, 15, 17, 17, 96]


def _cell(value):
    if value is None:
        return ""
    return str(value)


def _escape_md(text):
    return _cell(text).replace("|", "\\|").replace("\n", " ").strip()


def _kind_tag(row):
    kind = row.get("artifact_kind")
    return "〔%s〕" % kind if kind else ""


def render_markdown(rows, max_evidence=110):
    lines = ["| " + " | ".join(COLUMNS) + " |",
             "|" + "|".join(["---"] * len(COLUMNS)) + "|"]
    for row in rows:
        cells = []
        for key in KEYS:
            text = _escape_md(row.get(key))
            if key == "artifact_name" and row.get("artifact_kind"):
                text = "%s %s" % (_kind_tag(row), text)
            if key == "evidence" and max_evidence and len(text) > max_evidence:
                text = text[:max_evidence] + " …"
            cells.append(text)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render_markdown_full(rows):
    return render_markdown(rows, max_evidence=0)


def render_evidence_details(rows):
    lines = []
    for index, row in enumerate(rows, 1):
        lines.append("%d) %s  →  %s %s"
                     % (index, row.get("github_repo") or "?",
                        _kind_tag(row), row.get("artifact_name") or "?"))
        lines.append("   方式: %s ｜ 是否修改: %s ｜ 许可证: %s"
                     % (row.get("integration") or "?", row.get("modified") or "?",
                        row.get("artifact_license") or "?"))
        lines.append("   %s" % _cell(row.get("evidence")))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 输入仓库的许可证审计（只针对 GitHub 仓库自身，不涉及 AI 资产）
# --------------------------------------------------------------------------

AUDIT_COLUMNS = ["仓库", "输入许可证", "仓库主许可证", "仓库全部许可证", "结论",
                 "依据文件", "依据方式", "行号", "证据片段",
                 "专属许可证子目录数", "专属许可证清单", "说明"]


def render_license_audit_md(audit_rows):
    if not audit_rows:
        return ""
    lines = ["", "## 输入仓库许可证审计", "",
             "| " + " | ".join(AUDIT_COLUMNS) + " |",
             "|" + "|".join(["---"] * len(AUDIT_COLUMNS)) + "|"]
    for row in audit_rows:
        cells = []
        for name in AUDIT_COLUMNS:
            text = _escape_md(row.get(name))
            if name == "证据片段" and len(text) > 90:
                text = text[:90] + " …"
            if name == "专属许可证清单" and len(text) > 120:
                text = text[:120] + " …"
            cells.append(text)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_license_audit_csv(audit_rows, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(AUDIT_COLUMNS)
        for row in audit_rows:
            writer.writerow([_cell(row.get(name)) for name in AUDIT_COLUMNS])
    return path


def _license_evidence(item, fallback_file=""):
    """把一条许可证证据整理成统一结构。"""
    return {
        "file": item.get("file") or fallback_file,
        "line": item.get("line") if item.get("line") not in (None, "") else "",
        "via": item.get("via") or "",
        "text": item.get("snippet") or "",
    }


def build_license_entries(records):
    """records: [{"name", "url", "audit"}] → 仓库许可证报告条目。

    每个仓库一条，用「仓库名 + URL」作为标识；
    `sub_licenses` 只放与主许可证不同的「专属许可证」，并带上所在的文件夹。
    """
    entries = []
    for record in records:
        audit = record.get("audit") or {}
        root = audit.get("root") or {}
        all_licenses = audit.get("root_licenses") or []
        main_license = (audit.get("root_spdx")
                        or audit.get("confirmed_spdx")
                        or "unknown")

        sub_licenses = []
        for sub in (audit.get("conflicts") or []):
            sub_licenses.append({
                "folder": sub.get("dir") or ".",
                "license": sub.get("spdx") or "unknown",
                "category": sub.get("category") or "",
                "evidence": _license_evidence(sub),
            })

        entries.append({
            "repo": record.get("name") or "",
            "url": record.get("url") or "",
            "license": main_license,
            "licenses_all": all_licenses or ([main_license] if main_license else []),
            "evidence": _license_evidence(root),
            "sub_license_count": len(sub_licenses),
            "sub_licenses": sub_licenses,
            "provided_license": audit.get("provided") or "",
            "verdict": audit.get("verdict") or "",
            "note": audit.get("verdict_reason") or "",
        })
    return entries


def write_license_json(entries, path):
    """写出独立的仓库许可证 JSON 报告（不影响其它输出）。"""
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repo_count": len(entries),
        "repos": entries,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return path


# --------------------------------------------------------------------------
# 内置 xlsx 写出器（不依赖 openpyxl / pandas）
# --------------------------------------------------------------------------

def _column_name(index):
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def _sheet_xml(table):
    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
             "<cols>"]
    for index, width in enumerate(COLUMN_WIDTHS):
        parts.append('<col min="%d" max="%d" width="%d" customWidth="1"/>'
                     % (index + 1, index + 1, width))
    parts.append("</cols><sheetData>")
    for row_index, values in enumerate(table, 1):
        parts.append('<row r="%d">' % row_index)
        for col_index, value in enumerate(values):
            text = _cell(value).replace("\r", " ").replace("\n", " ")
            text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
            parts.append('<c r="%s%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                         % (_column_name(col_index), row_index, escape(text)))
        parts.append("</row>")
    parts.append("</sheetData></worksheet>")
    return "".join(parts)


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

WORKBOOK = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="supply" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""

WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""


def write_xlsx_fallback(rows, path):
    table = [COLUMNS] + [[_cell(row.get(key)) for key in KEYS] for row in rows]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("[Content_Types].xml", CONTENT_TYPES)
        handle.writestr("_rels/.rels", ROOT_RELS)
        handle.writestr("xl/workbook.xml", WORKBOOK)
        handle.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        handle.writestr("xl/worksheets/sheet1.xml", _sheet_xml(table))
    return path


def _openpyxl_available():
    try:
        import openpyxl  # noqa: F401
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# 写文件
# --------------------------------------------------------------------------

def _alternate_paths(path):
    base, ext = os.path.splitext(path)
    # 先试一个稳定名字（每次覆盖），再试带时间戳的
    return ["%s_latest%s" % (base, ext),
            "%s_%s%s" % (base, time.strftime("%H%M%S"), ext)]


def _write_with_fallback(path, action):
    """目标被占用（比如结果表正在 Excel 里开着、或文件被其他进程锁住）时换个名字写。"""
    try:
        action(path)
        return path, None
    except OSError as exc:
        for alternate in _alternate_paths(path):
            try:
                action(alternate)
            except OSError:
                continue
            return alternate, ("%s 正被其他程序占用，已改写到 %s"
                               % (os.path.basename(path), os.path.basename(alternate)))
        return None, "无法写出 %s：%s" % (path, exc)


def write_outputs(rows, out_dir="output", detail=None, extra=None, audit_rows=None):
    os.makedirs(out_dir, exist_ok=True)
    written, notes = {}, []

    def write_csv(target):
        with open(target, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(COLUMNS)
            for row in rows:
                writer.writerow([_cell(row.get(key)) for key in KEYS])

    def write_md(target):
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("# GitHub → AI 资产 供应链分析结果\n\n")
            handle.write(render_markdown_full(rows))
            handle.write("\n")
            section = render_license_audit_md(audit_rows)
            if section:
                handle.write(section)
                handle.write("\n")

    def write_xlsx(target):
        if _openpyxl_available():
            try:
                import pandas as pd
                frame = pd.DataFrame(
                    [{COLUMNS[i]: _cell(row.get(KEYS[i])) for i in range(len(KEYS))}
                     for row in rows], columns=COLUMNS)
                frame.to_excel(target, index=False)
                return
            except Exception:
                pass
        write_xlsx_fallback(rows, target)

    def write_detail(target):
        payload = {"rows": rows, "detail": detail, "summary": extra or {}}
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)

    jobs = [("csv", "result.csv", write_csv),
            ("md", "result.md", write_md),
            ("xlsx", "result.xlsx", write_xlsx)]
    if detail is not None:
        jobs.append(("json", "result.json", write_detail))
    if audit_rows:
        jobs.append(("license_audit", "license_audit.csv",
                     lambda target: write_license_audit_csv(audit_rows, target)))

    for kind, name, action in jobs:
        path, note = _write_with_fallback(os.path.join(out_dir, name), action)
        if path:
            written[kind] = path
        if note:
            notes.append(note)
    if notes:
        written["notes"] = notes
    return written
