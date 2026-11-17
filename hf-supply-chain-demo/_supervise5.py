# -*- coding: utf-8 -*-
"""通用守护进程（动态分片 + 失败重试最多 3 次）。

相比 _supervise4 的两点改进：

1. 动态分片：任何 worker 退出时，把全局剩余仓库按空闲 worker 数重新均分，
   收尾阶段也能保持满并发。

2. 失败重试：仓库失败一次不再永久放弃。状态记在 .retry_state.json，
   同一仓库失败满 MAX_FAILS（默认 3）次才真正出局。
   确定性失败（体积超限、私有仓库、404）直接算出局，不做无意义重试。

分片目录自动递增（p00、p01… 之后是 p12、p13…），重跑不会覆盖历史数据。
"""

import csv
import glob
import io
import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LIST = os.environ.get("REPO_LIST", "_targets_6001_6500.txt")
OUT = os.environ.get("OUT_DIR", "output_6001_6500")
WORKERS = int(os.environ.get("WORKERS", "12"))
TAG = os.environ.get("SHARD_TAG", "w")
IDLE_LIMIT = int(os.environ.get("IDLE_LIMIT", "3600"))
MAX_FAILS = int(os.environ.get("MAX_FAILS", "3"))
WORKDIR = os.environ.get("CLONE_DIR",
                         os.path.join(os.path.dirname(os.path.abspath(__file__)), "repos"))
LOGS = os.environ.get("LOG_DIR", "logs_local")
STATE_PATH = os.environ.get("RETRY_STATE", ".retry_state.json")

# 这些失败是确定性的，重试也没用
PERMANENT = ("超过", "私有", "404", "not found", "Not Found", "空仓库",
             "无文件", "空目录")

with open(LIST, encoding="utf-8") as fh:
    all_lines = [l.strip() for l in fh if l.strip()]

os.makedirs("shards_local", exist_ok=True)
os.makedirs(OUT, exist_ok=True)
os.makedirs(LOGS, exist_ok=True)
os.makedirs(WORKDIR, exist_ok=True)

env = dict(os.environ)
env.update({
    "CLONE_METHOD": "zip",
    "GIT_CLONE_TIMEOUT": "180",
    "ZIP_RETRIES": "3",
    "MAX_REPO_ZIP_BYTES": str(50 * 1024 * 1024),
    "GITHUB_PROXY": "https://gh-proxy.com",
    "REGISTRY_RETRIES": os.environ.get("REGISTRY_RETRIES", "1"),
    "REGISTRY_TIMEOUT": os.environ.get("REGISTRY_TIMEOUT", "8"),
    "REPO_HARD_TIMEOUT": os.environ.get("REPO_HARD_TIMEOUT", "3600"),
})


def slug(url):
    name = (url or "").split()[0] if (url or "").strip() else ""
    if "github.com" in name:
        name = name.split("github.com/")[-1].strip("/")
    parts = name.split("/")
    return ("%s/%s" % (parts[0], parts[1])).lower() if len(parts) >= 2 else name.lower()


def load_state():
    if os.path.isfile(STATE_PATH):
        try:
            with io.open(STATE_PATH, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    return {}


def save_state(state):
    tmp = STATE_PATH + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_PATH)


def scan_results():
    """返回 (成功集合, 失败信息 dict)。失败信息里记最大失败次数和是否确定性失败。"""
    ok, fails = set(), {}
    for path in glob.glob(os.path.join(OUT, "p*", "run_summary.csv")):
        try:
            with io.open(path, encoding="utf-8-sig") as fh:
                for r in csv.DictReader(fh):
                    key = slug(r.get("仓库") or "")
                    if not key:
                        continue
                    st = r.get("状态") or ""
                    if st.startswith("成功"):
                        ok.add(key)
                        continue
                    info = fails.setdefault(key, {"count": 0, "permanent": False})
                    info["count"] += 1
                    if any(m in st for m in PERMANENT):
                        info["permanent"] = True
        except Exception:
            pass
    return ok, fails


def sync_state():
    """把扫描结果并入状态文件：失败次数取「历史最大」与「本次观察」的较大值。"""
    state = load_state()
    ok, fails = scan_results()
    for key in ok:
        state[key] = {"attempts": MAX_FAILS, "status": "成功"}
    for key, info in fails.items():
        prev = state.get(key, {})
        attempts = max(int(prev.get("attempts", 0)), info["count"])
        if info["permanent"]:
            attempts = MAX_FAILS          # 确定性失败直接出局
        state[key] = {"attempts": attempts,
                      "status": "确定性失败" if info["permanent"] else "可重试失败"}
    save_state(state)
    return state


def remaining_all(state):
    out = []
    for line in all_lines:
        key = slug(line)
        rec = state.get(key) or {}
        if int(rec.get("attempts", 0)) >= MAX_FAILS:
            continue
        out.append(line)
    return out


def next_offset():
    idx = []
    for p in glob.glob(os.path.join(OUT, "p*")):
        try:
            idx.append(int(os.path.basename(p)[1:]))
        except ValueError:
            pass
    return (max(idx) + 1) if idx else 0


def start(i, chunk, offset):
    path = os.path.join("shards_local", "%s_%02d.txt" % (TAG, i))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(chunk) + ("\n" if chunk else ""))
    log = open(os.path.join(LOGS, "%s%02d.log" % (TAG, i)), "a",
               encoding="utf-8", buffering=1)
    p = subprocess.Popen(
        [sys.executable, "-u", "main.py", "--repos-file", path,
         "--out", os.path.join(OUT, "p%02d" % (i + offset)), "--workdir", WORKDIR,
         "--no-cache"],
        stdout=log, stderr=subprocess.STDOUT, env=env)
    return p, log



def count_no_progress(chunk, state):
    """worker 毫无产出就退出时，把它名下仓库各记一次失败，避免无限空转。"""
    for line in chunk:
        key = slug(line)
        rec = state.setdefault(key, {"attempts": 0, "status": "空跑未产出"})
        rec["attempts"] = int(rec.get("attempts", 0)) + 1
        if rec["attempts"] >= MAX_FAILS:
            rec["status"] = "多次空跑放弃"
    save_state(state)


def rows_before():
    return sum(len(glob.glob(os.path.join(OUT, p, "run_summary.csv")))
               and sum(1 for _ in io.open(glob.glob(os.path.join(OUT, p, "run_summary.csv"))[0],
                                          encoding="utf-8-sig"))
               for p in [os.path.basename(d) for d in glob.glob(os.path.join(OUT, "p*"))])


def spread(items, n):
    return [items[i::n] for i in range(max(n, 1))]


state = sync_state()
offset = next_offset()
left = remaining_all(state)
print("目标 %d ｜ 待处理 %d ｜ 并发 %d ｜ 新分片起点 p%02d ｜ 最大失败 %d 次"
      % (len(all_lines), len(left), WORKERS, offset, MAX_FAILS), flush=True)

procs = {}
chunk_map = {}
for i, chunk in enumerate(spread(left, min(WORKERS, max(len(left), 1)))):
    if not chunk:
        continue
    p, log = start(i, chunk, offset)
    procs[i] = (p, log)
    chunk_map[i] = chunk
    print("worker %d pid=%d 分配 %d" % (i, p.pid, len(chunk)), flush=True)

last_rows = rows_before()
print("守护开始：%d 个 worker，输出 %s" % (len(procs), OUT), flush=True)

while procs:
    time.sleep(180)
    relaunch = False
    for i in list(procs):
        p, log = procs[i]
        lp = os.path.join(LOGS, "%s%02d.log" % (TAG, i))
        idle = time.time() - os.path.getmtime(lp) if os.path.isfile(lp) else 0
        dead = p.poll() is not None
        if not dead and idle <= IDLE_LIMIT:
            continue
        try:
            if not dead:
                p.kill()
        except Exception:
            pass
        log.close()
        del procs[i]
        print("[%s] worker %d %s"
              % (time.strftime("%H:%M"), i, "退出" if dead else "卡死%.0fs" % idle),
              flush=True)
        relaunch = True
        # 本轮无任何产出 → 计一次失败，且放慢重启节奏
        now_rows = rows_before()
        if now_rows <= last_rows:
            st = load_state()
            count_no_progress(chunk_map.get(i, []), st)
            print("  无产出退出，已计入失败并休眠 60 秒", flush=True)
            time.sleep(60)
        last_rows = max(last_rows, now_rows)

    state = sync_state()
    left = remaining_all(state)
    if not left:
        print("剩余为 0，收尾", flush=True)
        break

    if relaunch:
        offset = next_offset()
        free = [i for i in range(WORKERS) if i not in procs]
        chunks = spread(left, min(len(free), len(left)))
        for i, chunk in zip(free, chunks):
            if not chunk:
                continue
            p, log = start(i, chunk, offset)
            procs[i] = (p, log)
            chunk_map[i] = chunk
            print("  重新分配 worker %d pid=%d 分到 %d ｜ 全局剩余 %d ｜ 分片起点 p%02d"
                  % (i, p.pid, len(chunk), len(left), offset), flush=True)

for i in list(procs):
    try:
        procs[i][0].kill()
    except Exception:
        pass

st = load_state()
give_up = [k for k, v in st.items() if int(v.get("attempts", 0)) >= MAX_FAILS
           and v.get("status") != "成功"]
print("全部结束 ｜ 状态文件记录 %d 个仓库 ｜ 其中放弃 %d 个" % (len(st), len(give_up)),
      flush=True)
