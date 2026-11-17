# -*- coding: utf-8 -*-
"""GitHub → AI model/dataset/tool 供应链分析 —— 主入口。

流程：
  1. 输入 GitHub 仓库 URL（+ 该仓库的许可证名字，可留空自动识别）
  2. 拉取仓库（git clone，失败回退下载 zip）
  3. astscan 召回：AST（Python）/ 常量传播（Rust/TS/Go 等）+ 配置信号
  4. 大模型判定：哪些是真正在用的 model / dataset / tool
  5. registries 解析：Hugging Face / MCP 注册中心 / 社区站 / GitHub 兜底，拿到 URL 和许可证
  6. integration 判定：代码层面集成 or 远程服务调用；集成的话有没有改过
  7. 输出 9 列表格（控制台 + output/result.csv|md|xlsx|json）
  8. 打印本次 token 用量与耗时

用法：
    python main.py --repo https://github.com/zseven-w/openpencil --license MIT
    python main.py https://github.com/zseven-w/openpencil MIT
    python main.py                      # 交互式输入
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time

from dotenv import load_dotenv

load_dotenv()
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.local"))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

_PYLIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pylibs")
if os.path.isdir(_PYLIB) and _PYLIB not in sys.path:
    sys.path.insert(0, _PYLIB)

import csv
import threading

import license_audit
import llm
import registries
import report
import supply
from github.clone import clone_repo, parse_github_url
from github.license import get_license

REPO_HARD_TIMEOUT = float(os.getenv("REPO_HARD_TIMEOUT", "900"))


def analyze_with_watchdog(timeout, func, *args, **kwargs):
    """给单个仓库加硬超时。

    实测有仓库会在网络读取上无限期挂起（46 分钟只涨 10 秒 CPU），
    而 requests 的读超时对「连接不断但不返回」不生效。
    这里把处理放到守护线程里，超时就放弃它、跳到下一个仓库，
    保证整批任务永远能往前走。被放弃的线程会随进程结束一起消失。
    """
    box = {}

    def runner():
        try:
            box["ok"] = func(*args, **kwargs)
        except BaseException as exc:      # noqa: BLE001 - 透传给主线程处理
            box["err"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError("单仓库处理超过 %.0f 秒，已跳过" % timeout)
    if "err" in box:
        raise box["err"]
    return box.get("ok")
from github.license import get_license
from report import render_evidence_details, render_markdown, write_outputs


def analyze_one(url, license_name=None, workdir="repos", use_llm=True,
                force_clone=False, max_artifacts=supply.DEFAULT_MAX_ARTIFACTS,
                quiet=False):
    parsed = parse_github_url(url)
    if not parsed:
        raise ValueError("无法解析 GitHub 地址: %s" % url)
    owner, repo_name = parsed
    full_name = "%s/%s" % (owner, repo_name)

    if not quiet:
        print("\n" + "=" * 74)
        print("目标仓库: %s" % full_name)

    repo_path = clone_repo(url, dest_root=workdir, force=force_clone, quiet=quiet)

    # 对「输入的仓库本身」做许可证审计：扫 LICENSE / README / 清单文件 / 源文件头，
    # 核实输入是否正确，并找出子目录里属于自己的许可证。
    # 注意：仓库里用到的 AI 资产许可证不走这里，仍由 registries 负责。
    audit_res = license_audit.audit(repo_path, provided=license_name, use_llm=use_llm)

    # 本地一点线索都没有时，才回退到 GitHub /license 接口
    if not audit_res.get("root_spdx"):
        fallback = get_license(repo_path, full_name=full_name, provided=None,
                               use_llm=use_llm)
        if fallback.get("name") and fallback["name"] != "unknown":
            audit_res["root_spdx"] = fallback["name"]
            audit_res["root_licenses"] = [fallback["name"]]
            audit_res["confirmed_spdx"] = fallback["name"]
            audit_res["root"] = {
                "spdx": fallback["name"], "file": "(GitHub /license 接口)",
                "line": "", "via": "github-api",
                "snippet": "GitHub API 返回的许可证：%s" % fallback["name"]}

    lic = {"name": audit_res["confirmed_spdx"], "source": "license-audit",
           "file": (audit_res.get("root") or {}).get("file") or ""}
    if not quiet:
        print("  " + license_audit.summary_line(audit_res))
        if audit_res["verdict"] in ("不一致", "输入非 SPDX"):
            print("  ⚠ 第 3 列按仓库实际填写：%s（你输入的是 %r）"
                  % (audit_res["confirmed_spdx"], license_name))
        for item in (audit_res.get("conflicts") or [])[:5]:
            print("     · 子目录专属许可证: %-44s %s%s"
                  % ((item.get("dir") or ".")[:44], item.get("spdx"),
                     ("[%s]" % item["category"]) if item.get("category") else ""))

    rows, details, scan = supply.analyze(
        repo_path, repo_name, url, lic["name"], use_llm=use_llm,
        max_artifacts=max_artifacts, quiet=quiet)

    return rows, details, {
        "repo": full_name,
        "repo_path": repo_path,
        "github_license": lic,
        "license_audit": audit_res,
        "license_actual": audit_res["confirmed_spdx"],
        "files_scanned": scan["files_scanned"],
        "candidates": len(scan["candidates"]),
        "config_signals": {k: len(v) for k, v in scan["signals"].items()},
    }


def build_parser():
    parser = argparse.ArgumentParser(
        description="识别 GitHub 仓库使用的 AI model / dataset / tool，并给出供应链表格",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python main.py --repo https://github.com/zseven-w/openpencil --license MIT
  python main.py https://github.com/zseven-w/openpencil MIT
  python main.py --repo URL1 --license MIT --repo URL2 --license Apache-2.0
  python main.py            # 交互式输入
""")
    parser.add_argument("url", nargs="?", help="GitHub 仓库地址")
    parser.add_argument("license_name", nargs="?", help="该仓库的许可证名字（可省略，自动识别）")
    parser.add_argument("--repo", action="append", default=[], metavar="URL",
                        help="GitHub 仓库地址（可重复）")
    parser.add_argument("--license", dest="licenses", action="append", default=[],
                        metavar="NAME", help="与 --repo 一一对应的许可证名字")
    parser.add_argument("--repos-file", metavar="FILE",
                        help="从文件批量读取（每行 'URL 许可证'）")
    parser.add_argument("--workdir", default="repos", help="仓库克隆目录（默认 repos）")
    parser.add_argument("--out", default="output", help="结果输出目录（默认 output）")
    parser.add_argument("--max-artifacts", type=int, default=supply.DEFAULT_MAX_ARTIFACTS,
                        help="每个仓库最多输出几条资产（默认 %d，0 表示不限）"
                             % supply.DEFAULT_MAX_ARTIFACTS)
    parser.add_argument("--audit-only", action="store_true",
                        help="只审计输入仓库自身的许可证（不做 AI 资产分析）")
    parser.add_argument("--no-llm", action="store_true", help="不用大模型（只用确定性规则）")
    parser.add_argument("--force-clone", action="store_true", help="强制重新拉取仓库")
    parser.add_argument("--no-cache", action="store_true", help="不使用本地缓存")
    parser.add_argument("--quiet", action="store_true", help="少打印过程日志")
    return parser


def collect_targets(args):
    targets = []
    for index, url in enumerate(args.repo):
        targets.append((url, args.licenses[index] if index < len(args.licenses) else None))
    if args.url:
        targets.insert(0, (args.url, args.license_name))
    if args.repos_file:
        with open(args.repos_file, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                targets.append((parts[0], parts[1] if len(parts) > 1 else None))
    if not targets:
        url = input("GitHub URL: ").strip()
        if not url:
            raise SystemExit("没有输入仓库地址，退出。")
        lic = input("该仓库的许可证名字（可留空自动识别）: ").strip() or None
        targets.append((url, lic))
    return targets


def repo_url_of(name, url=""):
    """仓库地址：优先用输入里的原始 URL，否则由 owner/name 拼一个规范地址。"""
    if url:
        return url
    name = (name or "").strip().strip("/")
    if name.count("/") == 1:
        return "https://github.com/" + name
    return ""


def write_license_report(records, out_dir, filename="license_report.json"):
    """单独输出一份「仓库许可证」JSON 报告，不影响其它输出文件。

    records: [{"name": 仓库名, "url": 仓库地址, "audit": license_audit.audit(...)}]
    """
    records = [r for r in records if r.get("audit")]
    if not records:
        return None
    try:
        os.makedirs(out_dir, exist_ok=True)
        entries = report.build_license_entries(records)
        return report.write_license_json(entries, os.path.join(out_dir, filename))
    except OSError:
        return None


_TAG_PATTERN = re.compile(r"^〔([^〕]+)〕\s*(.*)$")


def _read_existing_rows(path):
    """读回已经落盘的 result.csv（用于重启后累加，而不是覆盖）。

    资产类型（〔model〕/〔dataset〕/〔tool〕）在 CSV 里以名字前缀的形式保存，
    读回时必须拆出来还原成 artifact_kind，否则后续重新渲染 markdown 时
    类型标注会全部丢失。
    """
    out = []
    if not os.path.isfile(path):
        return out
    try:
        with open(path, encoding="utf-8-sig") as fh:
            for rec in csv.DictReader(fh):
                row = dict(zip(report.KEYS, [rec.get(c, "") for c in rec.keys()]))
                name = row.get("artifact_name") or ""
                m = _TAG_PATTERN.match(name)
                if m:
                    row["artifact_kind"] = m.group(1).strip()
                    row["artifact_name"] = m.group(2).strip()
                out.append(row)
    except Exception:
        pass
    return out


def _read_existing_summary(path):
    """读回已有的 run_summary.csv，返回 {仓库: 行字典}。"""
    out = {}
    if not os.path.isfile(path):
        return out
    try:
        with open(path, encoding="utf-8-sig") as fh:
            for rec in csv.DictReader(fh):
                key = (rec.get("仓库") or "").strip()
                if key:
                    out[key] = rec
    except Exception:
        pass
    return out


SUMMARY_COLUMNS = ["仓库", "GitHub许可证", "仓库实际许可证", "许可证审计结论",
                   "专属许可证子目录数", "状态", "输出资产数", "扫描文件数", "候选数",
                   "LLM调用次数", "输入tokens", "输出tokens", "合计tokens",
                   "大模型耗时秒", "端到端秒数"]


def flush_partial(rows, summaries, out_dir):
    """每跑完一个仓库就把当前成果落盘。

    两个硬要求：
      1. 原子写，进程被 kill 时不留下截断的 CSV；
      2. **累加而非覆盖** —— 卡死重启后新进程的 summaries 是空的，
         如果直接覆盖就会把上一个进程的成果冲掉（实测丢过 140 个仓库）。
    """
    try:
        os.makedirs(out_dir, exist_ok=True)

        # --- result.csv：合并旧行 + 新行，按 (仓库URL, 资产名) 去重 ---
        target = os.path.join(out_dir, "result.csv")
        merged, seen = [], set()
        for row in _read_existing_rows(target) + list(rows):
            key = ((row.get("github_url") or "").lower().rstrip("/"),
                   (row.get("artifact_name") or "").lower())
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)
        tmp = target + ".tmp"
        with open(tmp, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(report.COLUMNS)
            for row in merged:
                cells = []
                for key in report.KEYS:
                    text = row.get(key, "")
                    # 把资产类型作为前缀写进名字列，这样 CSV 自己就能保存类型信息
                    if key == "artifact_name" and row.get("artifact_kind"):
                        text = "〔%s〕%s" % (row["artifact_kind"], text or "")
                    cells.append(text)
                writer.writerow(cells)
        os.replace(tmp, target)

        # --- run_summary.csv：合并旧行 + 新行（新的覆盖旧的）---
        summary_path = os.path.join(out_dir, "run_summary.csv")
        merged_summary = _read_existing_summary(summary_path)
        for item in summaries:
            repo = item.get("repo", "")
            given = item.get("github_license")
            if isinstance(given, dict):
                given = given.get("name", "")
            audit = item.get("license_audit") or {}
            merged_summary[repo] = {
                "仓库": repo, "GitHub许可证": given or "",
                "仓库实际许可证": audit.get("confirmed_spdx") or item.get("license_actual") or "",
                "许可证审计结论": audit.get("verdict", ""),
                "专属许可证子目录数": len(audit.get("conflicts") or []),
                "状态": item.get("status", ""), "输出资产数": item.get("rows", 0),
                "扫描文件数": item.get("files_scanned", 0),
                "候选数": item.get("candidates", 0),
                "LLM调用次数": item.get("llm_calls", 0),
                "输入tokens": item.get("tokens_in", 0),
                "输出tokens": item.get("tokens_out", 0),
                "合计tokens": item.get("tokens_total", 0),
                "大模型耗时秒": item.get("llm_seconds", 0),
                "端到端秒数": item.get("seconds", 0),
            }
        with open(summary_path + ".tmp", "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=SUMMARY_COLUMNS)
            writer.writeheader()
            for rec in merged_summary.values():
                writer.writerow({k: rec.get(k, "") for k in SUMMARY_COLUMNS})
        os.replace(summary_path + ".tmp", summary_path)

        audit_rows = [license_audit.to_row(item.get("repo", ""), item["license_audit"])
                      for item in summaries if item.get("license_audit")]
        if audit_rows:
            report.write_license_audit_csv(
                audit_rows, os.path.join(out_dir, "license_audit.csv"))
        write_license_report(
            [{"name": item.get("repo", ""),
              "url": repo_url_of(item.get("repo", "")),
              "audit": item.get("license_audit")} for item in summaries],
            out_dir)
    except Exception:
        pass


def write_run_summary(summaries, out_dir="output"):
    """把每个仓库的 token / 耗时写成一张汇总表，便于对账。"""
    import csv

    path = os.path.join(out_dir, "run_summary.csv")
    columns = ["仓库", "GitHub许可证", "仓库实际许可证", "许可证审计结论",
               "专属许可证子目录数", "状态", "输出资产数", "扫描文件数", "候选数",
               "LLM调用次数", "输入tokens", "输出tokens", "合计tokens",
               "大模型耗时秒", "端到端秒数"]
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(columns)
            for item in summaries:
                audit = item.get("license_audit") or {}
                given = item.get("github_license")
                if isinstance(given, dict):
                    given = given.get("name", "")
                writer.writerow([
                    item.get("repo", ""), given or "",
                    audit.get("confirmed_spdx") or item.get("license_actual") or "",
                    audit.get("verdict", ""),
                    len(audit.get("conflicts") or []),
                    item.get("status", ""), item.get("rows", 0),
                    item.get("files_scanned", 0), item.get("candidates", 0),
                    item.get("llm_calls", 0), item.get("tokens_in", 0),
                    item.get("tokens_out", 0), item.get("tokens_total", 0),
                    item.get("llm_seconds", 0), item.get("seconds", 0),
                ])
        return path
    except OSError as exc:
        print("[注意] 汇总表写出失败: %s" % exc)
        return None


def run_audit_only(targets, args):
    """只审计输入仓库自身的许可证，不做 AI 资产分析。

    用于回答「我表格里给的许可证对不对」「大仓库里有没有自带许可证的子目录」。
    """
    rows = []
    records = []
    for index, (url, license_name) in enumerate(targets, 1):
        parsed = parse_github_url(url)
        if not parsed:
            print("[跳过] 无法解析: %s" % url)
            continue
        full_name = "%s/%s" % parsed
        print("\n[%d/%d] %s" % (index, len(targets), full_name))
        try:
            repo_path = clone_repo(url, dest_root=args.workdir, force=False,
                                   quiet=args.quiet)
            res = license_audit.audit(repo_path, provided=license_name,
                                      use_llm=not args.no_llm)
        except Exception as exc:
            print("  [失败] %s: %s" % (type(exc).__name__, str(exc)[:140]))
            continue
        print("  " + license_audit.summary_line(res))
        for item in (res.get("conflicts") or [])[:6]:
            print("     · 子目录专属: %-46s %s%s"
                  % ((item.get("dir") or ".")[:46], item.get("spdx"),
                     ("[%s]" % item["category"]) if item.get("category") else ""))
        rows.append(license_audit.to_row(full_name, res))
        records.append({"name": full_name, "url": url, "audit": res})

    os.makedirs(args.out, exist_ok=True)
    csv_path = report.write_license_audit_csv(
        rows, os.path.join(args.out, "license_audit.csv"))
    md_path = os.path.join(args.out, "license_audit.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("# 输入仓库许可证审计\n")
        fh.write(report.render_license_audit_md(rows))
        fh.write("\n")
    json_path = write_license_report(records, args.out)

    from collections import Counter
    verdicts = Counter(r.get("结论") or "-" for r in rows)
    with_subs = sum(1 for r in rows if (r.get("专属许可证子目录数") or 0) > 0)
    print("\n" + "=" * 74)
    print("许可证审计汇总（%d 个仓库）" % len(rows))
    print("=" * 74)
    print("  结论: " + " ｜ ".join("%s %d" % (k, v) for k, v in verdicts.most_common()))
    print("  含子目录专属许可证: %d 个仓库" % with_subs)
    print("  csv: %s" % csv_path)
    print("  md : %s" % md_path)
    if json_path:
        print("  json: %s" % json_path)
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)

    llm.reset_usage()
    registries.set_cache_enabled(not args.no_cache)
    registries.reset_health()
    started_at = time.time()

    use_llm = not args.no_llm
    if use_llm:
        try:
            conf = llm.settings()
            print("大模型: %s / %s" % (conf["provider"], conf["model"]))
        except llm.LLMError as exc:
            print("[警告] %s → 自动切换到确定性模式" % exc)
            use_llm = False

    targets = collect_targets(args)
    if args.audit_only:
        return run_audit_only(targets, args)
    all_rows, all_details, summaries = [], [], []

    for index, (url, license_name) in enumerate(targets, 1):
        repo_started = time.time()
        before = dict(llm.USAGE)
        print("\n[%d/%d] %s" % (index, len(targets), url))
        try:
            rows, details, summary = analyze_with_watchdog(
                REPO_HARD_TIMEOUT, analyze_one,
                url, license_name=license_name, workdir=args.workdir,
                use_llm=use_llm, force_clone=args.force_clone,
                max_artifacts=args.max_artifacts, quiet=args.quiet)
        except Exception as exc:
            elapsed = time.time() - repo_started
            after = llm.USAGE
            summaries.append({
                "repo": url, "github_license": license_name or "",
                "status": "失败: %s: %s" % (type(exc).__name__, str(exc)[:120]),
                "rows": 0, "files_scanned": 0, "candidates": 0,
                "seconds": round(elapsed, 1),
                "tokens_in": after["prompt_tokens"] - before["prompt_tokens"],
                "tokens_out": after["completion_tokens"] - before["completion_tokens"],
                "tokens_total": after["total_tokens"] - before["total_tokens"],
                "llm_calls": after["calls"] - before["calls"],
                "llm_seconds": round(after["seconds"] - before["seconds"], 1),
            })
            print("[失败] %s -> %s: %s" % (url, type(exc).__name__, exc))
            continue

        elapsed = time.time() - repo_started
        after = llm.USAGE
        summary.update({
            "status": "成功",
            "seconds": round(elapsed, 1),
            "rows": len(rows),
            "tokens_in": after["prompt_tokens"] - before["prompt_tokens"],
            "tokens_out": after["completion_tokens"] - before["completion_tokens"],
            "tokens_total": after["total_tokens"] - before["total_tokens"],
            "llm_calls": after["calls"] - before["calls"],
            "llm_seconds": round(after["seconds"] - before["seconds"], 1),
        })
        summaries.append(summary)
        print("  -> %d 条资产 ｜ %.1f 秒 ｜ %d tokens ｜ %d 次 LLM 调用"
              % (len(rows), elapsed, summary["tokens_total"], summary["llm_calls"]))
        all_rows.extend(rows)
        all_details.extend(details)
        flush_partial(all_rows, summaries, args.out)

    if not all_rows:
        print("没有产生任何结果。")
        return 1

    print("\n" + "=" * 74)
    print("供应链分析结果（9 列）")
    print("=" * 74)
    print(render_markdown(all_rows))

    print("\n" + "=" * 74)
    print("证据明细")
    print("=" * 74)
    print(render_evidence_details(all_rows))

    usage = llm.USAGE
    total_seconds = time.time() - started_at
    extra = {
        "llm": dict(usage),
        "repos": summaries,
        "total_seconds": round(total_seconds, 1),
        "registry": dict(registries.HEALTH),
    }
    audit_rows = [license_audit.to_row(item.get("repo", ""), item["license_audit"])
                  for item in summaries if item.get("license_audit")]

    # 收尾写盘也必须是「合并」而不是覆盖：一个分片会被守护进程多次重启，
    # 每次重启的进程只持有自己那轮的结果，直接覆盖会把前面的成果冲掉
    # （实测丢过 50 个仓库、322 条资产）。
    flush_partial(all_rows, summaries, args.out)
    merged_rows = _read_existing_rows(os.path.join(args.out, "result.csv"))
    written = write_outputs(merged_rows, out_dir=args.out, detail=all_details,
                            extra=extra, audit_rows=audit_rows)
    written["run_summary"] = os.path.join(args.out, "run_summary.csv")

    # 单独的「仓库许可证」JSON 报告（其它输出保持原样）
    json_path = write_license_report(
        [{"name": item.get("repo", ""),
          "url": repo_url_of(item.get("repo", "")),
          "audit": item.get("license_audit")} for item in summaries],
        args.out)
    if json_path:
        written["license_report"] = json_path

    if audit_rows:
        from collections import Counter
        verdicts = Counter(r.get("结论") or "-" for r in audit_rows)
        with_subs = sum(1 for r in audit_rows if (r.get("专属许可证子目录数") or 0) > 0)
        print("\n" + "=" * 74)
        print("输入仓库许可证审计")
        print("=" * 74)
        print("  结论分布: " + " ｜ ".join("%s %d" % (k, v) for k, v in verdicts.most_common()))
        print("  含子目录专属许可证的仓库: %d 个" % with_subs)
        for row in audit_rows:
            if row.get("结论") in ("不一致", "输入非 SPDX") or (row.get("专属许可证子目录数") or 0) > 0:
                print("  - %-42s 输入 %-12s → 实际 %-18s %s"
                      % (str(row.get("仓库"))[:42], row.get("输入许可证") or "-",
                         row.get("仓库主许可证") or "-", row.get("结论")))
                if row.get("专属许可证清单"):
                    print("      子目录: %s" % str(row["专属许可证清单"])[:120])

    print("\n" + "=" * 74)
    print("已写出文件")
    print("=" * 74)
    for kind, path in written.items():
        if kind == "notes":
            for note in path:
                print("  [注意] %s" % note)
        else:
            print("  %-5s %s" % (kind, path))

    print("\n" + "=" * 74)
    print("本次开销")
    print("=" * 74)
    print("  仓库数: %d ｜ 输出资产: %d 条" % (len(summaries), len(all_rows)))
    print("  大模型: %s / %s，成功调用 %d 次（失败 %d 次）"
          % (usage["provider"], usage["model"], usage["calls"], usage["failures"]))
    print("  tokens: 输入 %d + 输出 %d = 合计 %d"
          % (usage["prompt_tokens"], usage["completion_tokens"], usage["total_tokens"]))
    print("  大模型耗时: %.1f 秒 ｜ 端到端总耗时: %.1f 秒"
          % (usage["seconds"], total_seconds))
    print("  注册中心请求: 实时 %d 次, 缓存命中 %d 次, 失败 %d 次"
          % (registries.HEALTH["live"], registries.HEALTH["cache_hits"],
             registries.HEALTH["failures"]))
    for summary in summaries:
        print("  - %-52s %-4s %2d 条 %8d tokens %6.1f 秒"
              % ((summary.get("repo") or "")[:52], summary.get("status", "")[:4],
                 summary.get("rows", 0), summary.get("tokens_total", 0),
                 summary.get("seconds", 0)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
