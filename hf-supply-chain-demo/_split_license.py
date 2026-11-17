# -*- coding: utf-8 -*-
"""把许可证审计结果按批次拆分写回各自目录，并生成一份覆盖全部仓库的合并报告。"""

import glob
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import openpyxl

SRC_XLSX = None
_desk = os.path.expanduser(r"~\Desktop")
for _f in sorted(glob.glob(os.path.join(_desk, "*github_url+license.xlsx")), reverse=True):
    if os.path.basename(_f).startswith("~$"):
        continue
    SRC_XLSX = _f
    break
print("使用表格:", SRC_XLSX)


def slug(url):
    m = re.search(r"github\.com[/:]([^/\s]+)/([^/\s#?]+)", url or "")
    return ("%s/%s" % (m.group(1), m.group(2))).lower() if m else ""


# ---------- 收集所有审计记录 ----------
def score(rec):
    """给许可证记录打分，用于在多次审计结果中挑最可信的一份。

    同一个仓库会被审计多次（分析阶段带大模型、离线补审计用 --no-llm），
    两次结论可能不同：离线那次如果克隆残缺就找不到 LICENSE，会得出
    「无法确认 / 证据为空」。旧规则只比子许可证条数，两者都是 0 时
    就随机取了较差的那份，导致 272 个仓库的结论从「一致」退化成「无法确认」。
    """
    ev = rec.get("evidence") or {}
    s = 0
    if ev.get("file"):
        s += 8                      # 有证据文件最可信
    if ev.get("via"):
        s += 2
    if rec.get("sub_licenses"):
        s += 4
    if (rec.get("verdict") or "") in ("一致", "不一致"):
        s += 2                      # 明确结论优于「无法确认」
    if rec.get("license"):
        s += 1
    return s


entries = {}
for f in glob.glob("audit_refill/*/license_report.json") + \
         glob.glob("output_4001_4500/*/license_report.json") + \
         glob.glob("output_3501_4000/*/license_report.json") + \
         glob.glob("audit_out/*/license_report.json") + \
         glob.glob("backfill_out/*/license_report.json") + \
         glob.glob("output_2501_3000/*/license_report.json") + \
         glob.glob("output_3001_3500/*/license_report.json") + \
         glob.glob("output_2001_2500/*/license_report.json") + \
         glob.glob("output_2001_2500_final/license_report.json") + \
         glob.glob("output_1501_2000/*/license_report.json") + \
         glob.glob("output_1001_1500/*/license_report.json") + \
         glob.glob("output_*_final/license_report.json") + \
         glob.glob("aggregate_*/license_report.json") + \
         glob.glob("output_retry_local/*/license_report.json") + \
         ["final_1000/final/license_report.json"]:
    if not os.path.isfile(f):
        continue
    try:
        d = json.load(io.open(f, encoding="utf-8"))
    except Exception:
        continue
    for r in d.get("repos", []):
        key = slug(r.get("url") or r.get("repo"))
        if not key:
            continue
        old = entries.get(key)
        if old is None or score(r) > score(old):
            entries[key] = r

print("汇总到许可证记录:", len(entries), "个仓库")
with_sub = sum(1 for r in entries.values() if r.get("sub_licenses"))
total_sub = sum(len(r.get("sub_licenses") or []) for r in entries.values())
print("其中检出子目录许可证: %d 个仓库，共 %d 条" % (with_sub, total_sub))

# ---------- 各批次的仓库清单 ----------
wb = openpyxl.load_workbook(SRC_XLSX, read_only=True, data_only=True)
ws = wb[wb.sheetnames[0]]
rows = [[c if c is not None else "" for c in r] for r in ws.iter_rows(values_only=True)]
data = rows[1:]

batch1 = {slug(str(r[1] or "")) for r in data[:1000]}
batches = {
    "final_1000_merged": batch1,
    "output_1001_1500_final": set(),
    "output_1501_2000_final": set(),
    "output_2001_2500_final": set(),
    "output_2501_3000_final": set(),
    "output_3001_3500_final": set(),
    "output_3501_4000_final": set(),
    "output_4001_4500_final": set(),
}
for name, target in (("output_1001_1500_final", "_targets_1001_1500.txt"),
                     ("output_1501_2000_final", "_targets_1501_2000.txt"),
                     ("output_2001_2500_final", "_targets_2001_2500.txt"),
                     ("output_2501_3000_final", "_targets_2501_3000.txt"),
                     ("output_3001_3500_final", "_targets_3001_3500.txt"),
                     ("output_3501_4000_final", "_targets_3501_4000.txt"),
                     ("output_4001_4500_final", "_targets_4001_4500.txt")):
    if os.path.isfile(target):
        with io.open(target, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    batches[name].add(slug(line.split()[0]))

import datetime

for out_dir, keys in batches.items():
    subset = [entries[k] for k in keys if k in entries]
    if not subset:
        print("%s: 无可用记录" % out_dir)
        continue
    os.makedirs(out_dir, exist_ok=True)
    payload = {
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "repo_count": len(subset),
        "repos": sorted(subset, key=lambda x: slug(x.get("url") or x.get("repo"))),
    }
    with io.open(os.path.join(out_dir, "license_report.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    s = sum(1 for r in subset if r.get("sub_licenses"))
    t = sum(len(r.get("sub_licenses") or []) for r in subset)
    print("%-26s 仓库 %4d ｜ 含子许可证 %3d ｜ 子许可证 %4d 条"
          % (out_dir, len(subset), s, t))

# ---------- 全量合并报告 ----------
out = "license_all_4500"
os.makedirs(out, exist_ok=True)
payload = {
    "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    "repo_count": len(entries),
    "repos": sorted(entries.values(), key=lambda x: slug(x.get("url") or x.get("repo"))),
}
with io.open(os.path.join(out, "license_report.json"), "w", encoding="utf-8") as fh:
    json.dump(payload, fh, ensure_ascii=False, indent=2)
print("\n全量合并报告 → %s（%d 个仓库）" % (out, len(entries)))
