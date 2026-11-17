# -*- coding: utf-8 -*-
"""通用合并：把某个输出目录下的所有分片合并成一份总表。

用法：SRC=output_1501_2000 OUT=output_1501_2000_final python merge_batch.py
"""

import csv
import glob
import io
import os
import re
import statistics
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import report

SRC = os.environ.get("SRC", "output_1501_2000")
OUT = os.environ.get("OUT", SRC + "_final")
TAG = re.compile(r"^〔([^〕]+)〕\s*(.*)$")


def norm(url):
    u = (url or "").strip().lower().rstrip("/")
    if "github.com" in u:
        u = u.split("github.com/")[-1]
    return u


def main():
    rows, seen = [], set()
    for f in sorted(glob.glob(os.path.join(SRC, "*", "result.csv"))):
        try:
            with io.open(f, encoding="utf-8-sig") as fh:
                for rec in csv.DictReader(fh):
                    row = dict(zip(report.KEYS, [rec.get(c, "") for c in report.COLUMNS]))
                    name = row.get("artifact_name") or ""
                    m = TAG.match(name)
                    if m:
                        row["artifact_kind"] = m.group(1).strip()
                        row["artifact_name"] = m.group(2).strip()
                    key = (norm(row.get("github_url")), (row.get("artifact_name") or "").lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(row)
        except Exception:
            continue

    summary = {}
    for f in sorted(glob.glob(os.path.join(SRC, "*", "run_summary.csv"))):
        try:
            with io.open(f, encoding="utf-8-sig") as fh:
                for rec in csv.DictReader(fh):
                    k = norm(rec.get("仓库"))
                    if not k:
                        continue
                    old = summary.get(k)
                    if old is None or (rec.get("状态") or "").startswith("成功"):
                        summary[k] = rec
        except Exception:
            continue

    os.makedirs(OUT, exist_ok=True)
    report.write_outputs(rows, out_dir=OUT, detail=None, extra={}, audit_rows=None)

    COLS = ["仓库", "GitHub许可证", "仓库实际许可证", "许可证审计结论",
            "专属许可证子目录数", "状态", "输出资产数", "扫描文件数", "候选数",
            "LLM调用次数", "输入tokens", "输出tokens", "合计tokens",
            "大模型耗时秒", "端到端秒数"]
    with io.open(os.path.join(OUT, "run_summary.csv"), "w",
                 encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        for rec in summary.values():
            w.writerow({c: rec.get(c, "") for c in COLS})

    ok = sum(1 for v in summary.values() if (v.get("状态") or "").startswith("成功"))
    scans = [int(v.get("扫描文件数") or 0) for v in summary.values()
             if (v.get("状态") or "").startswith("成功")]
    tokens = sum(int(v.get("合计tokens") or 0) for v in summary.values())
    secs = sum(float(v.get("端到端秒数") or 0) for v in summary.values())

    print("=== 合并完成 ===")
    print("目录     : %s → %s" % (SRC, OUT))
    print("仓库     : %d（成功 %d，失败 %d）" % (len(summary), ok, len(summary) - ok))
    print("资产     : %d 条" % len(rows))
    if scans:
        print("扫描文件中位: %d" % statistics.median(scans))
    print("tokens   : %d" % tokens)
    print("累计耗时 : %.1f 小时" % (secs / 3600))

    # ---------- 许可证产物：子目录专属许可证必须一起导出 ----------
    # 曾经只合并了 result.* 和 run_summary.csv，导致交付目录里看不到
    # 「专属许可证所在的具体文件夹 + 专属许可证 + 证据」。
    import json

    lic = {}
    for f in sorted(glob.glob(os.path.join(SRC, "*", "license_report.json"))):
        try:
            d = json.load(io.open(f, encoding="utf-8"))
        except Exception:
            continue
        for r in d.get("repos", []):
            k = norm(r.get("url") or r.get("repo"))
            if not k:
                continue
            old = lic.get(k)
            if old is None or len(r.get("sub_licenses") or []) >= len(old.get("sub_licenses") or []):
                lic[k] = r

    if lic:
        payload = {
            "generated_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
            "repo_count": len(lic),
            "repos": sorted(lic.values(), key=lambda x: norm(x.get("url") or x.get("repo"))),
        }
        with io.open(os.path.join(OUT, "license_report.json"), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        with_sub = sum(1 for r in lic.values() if r.get("sub_licenses"))
        total_sub = sum(len(r.get("sub_licenses") or []) for r in lic.values())
        print("许可证   : %s（%d 个仓库，其中 %d 个含子目录许可证，共 %d 条）"
              % ("license_report.json", len(lic), with_sub, total_sub))

    audit = {}
    for f in sorted(glob.glob(os.path.join(SRC, "*", "license_audit.csv"))):
        try:
            with io.open(f, encoding="utf-8-sig") as fh:
                for rec in csv.DictReader(fh):
                    k = norm(rec.get("仓库"))
                    if k:
                        audit[k] = rec
        except Exception:
            continue
    if audit:
        with io.open(os.path.join(OUT, "license_audit.csv"), "w",
                     encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=report.AUDIT_COLUMNS)
            w.writeheader()
            for rec in audit.values():
                w.writerow({c: rec.get(c, "") for c in report.AUDIT_COLUMNS})
        print("许可证   : %s（%d 行）" % ("license_audit.csv", len(audit)))



if __name__ == "__main__":
    main()
