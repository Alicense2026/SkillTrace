# -*- coding: utf-8 -*-
"""把 GitHub 仓库拉到本地。

策略（按顺序）：
  1. 目录已存在且非空  -> 直接复用
  2. git clone --depth 1（浅克隆，快）
  3. 回退：下载 GitHub 的 zip 源码包再解压
     （有些机器 / 网络环境下 git 的 TLS 后端会失败，但 Python 的 HTTPS 是好的，
       所以这一步是必要的备份方案，而不是可选优化）
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import uuid
import zipfile

import requests

CODELOAD = "https://codeload.github.com"
USER_AGENT = "hf-supply-chain-demo"


def parse_github_url(url):
    """从各种写法的地址里取出 (owner, repo)。支持 https / ssh / 带 .git。"""
    if not url:
        return None
    text = url.strip().rstrip("/")
    text = re.sub(r"\.git$", "", text)
    match = re.search(r"github\.com[/:]([^/\s]+)/([^/\s]+)", text)
    if not match:
        return None
    owner = match.group(1)
    repo = match.group(2).split("?")[0].split("#")[0]
    if not owner or not repo:
        return None
    return owner, repo


def repo_dir_name(url):
    """本地目录名，带 owner 前缀避免同名仓库互相覆盖。"""
    parsed = parse_github_url(url)
    if parsed:
        owner, repo = parsed
        return "%s__%s" % (owner, repo)
    return re.sub(r"[^\w.\-]+", "_", url.rstrip("/").split("/")[-1]) or "repo"


CLONE_MARKER = ".clone_complete"
MIN_FILES_FOR_LEGACY = 10


def _is_usable(dest):
    """判断已有的克隆目录能不能直接复用。

    坑一：进程被 timeout 杀掉时，目录可能只是个空壳（0 个文件），
    但 `os.listdir()` 非空就会被当成「已存在」复用，结果扫描 0 个文件、
    输出 0 条资产，还不报错。

    坑二：被中断的 `git clone` 只留下一个 `.git` 目录（里面有 14 个
    hooks/*.sample 之类的模板文件）。如果按「有 .git 就算完整」判断，
    这些空壳会被当成完整仓库复用 —— 实测 1000 个仓库里有 415 个踩了这个坑，
    全部扫出 0 个代码文件、0 条资产，却记成"成功"。

    所以这里只认两种：有完成标记，或 .git 之外确实有足够多的真实文件。
    """
    if os.path.isfile(os.path.join(dest, CLONE_MARKER)):
        return True
    count = 0
    for _root, dirs, files in os.walk(dest):
        dirs[:] = [d for d in dirs if d != ".git"]
        count += len(files)
        if count >= MIN_FILES_FOR_LEGACY:
            return True
    return False


def _mark_complete(dest):
    try:
        with open(os.path.join(dest, CLONE_MARKER), "w", encoding="utf-8") as fh:
            fh.write("ok\n")
    except OSError:
        pass


def clone_repo(url, dest_root="repos", force=False, quiet=False):
    """把仓库拉到 dest_root/<owner>__<repo>，返回本地路径。"""
    name = repo_dir_name(url)
    dest = os.path.join(dest_root, name)
    os.makedirs(dest_root, exist_ok=True)

    if os.path.isdir(dest) and os.listdir(dest) and not force:
        if _is_usable(dest):
            _log(quiet, "本地已存在，直接复用: %s" % dest)
            return dest
        _log(quiet, "本地目录不完整（空壳/残缺），重新拉取: %s" % dest)
        shutil.rmtree("\\\\?\\" + os.path.abspath(dest), ignore_errors=True)

    if force and os.path.isdir(dest):
        shutil.rmtree(dest, ignore_errors=True)

    _log(quiet, "拉取仓库: %s" % url)
    # CLONE_METHOD=zip 时优先走 codeload 压缩包：跨国际链路时 git 协议
    # 经常超时/断流（实测 git clone 600 秒超时、invalid index-pack output），
    # 而 HTTP 下载更稳、还能重试。
    method = os.getenv("CLONE_METHOD", "auto").strip().lower()
    if method == "zip":
        if _zip_download(url, dest, quiet=quiet):
            _mark_complete(dest)
            return dest
        _log(quiet, "zip 失败，改用 git clone ...")
        if _git_clone(url, dest, quiet=quiet):
            _mark_complete(dest)
            return dest
    else:
        if _git_clone(url, dest, quiet=quiet):
            _mark_complete(dest)
            return dest
        _log(quiet, "git clone 失败，改用下载 zip 源码包 ...")
        if _zip_download(url, dest, quiet=quiet):
            _mark_complete(dest)
            return dest

    # 两种方式都失败：必须清掉可能留下的半成品目录，
    # 否则下次运行会把它当成"本地已存在"直接复用，分析一个残缺仓库。
    if os.path.isdir(dest):
        shutil.rmtree("\\\\?\\" + os.path.abspath(dest), ignore_errors=True)

    raise RuntimeError("无法获取仓库 %s（git clone 与 zip 下载都失败）" % url)


# --------------------------------------------------------------------------
# 方式一：git clone
# --------------------------------------------------------------------------

GIT_CLONE_TIMEOUT = int(os.getenv("GIT_CLONE_TIMEOUT", "600"))


def _git_clone(url, dest, quiet=False):
    if shutil.which("git") is None:
        return False
    if os.path.isdir(dest):
        shutil.rmtree(dest, ignore_errors=True)
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"      # 绝不弹窗等输入
    env["GIT_ASKPASS"] = "echo"
    cmd = ["git", "clone", "--depth", "1", "--single-branch", url, dest]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env,
                              timeout=GIT_CLONE_TIMEOUT)
    except Exception as exc:
        _log(quiet, "  git 执行异常: %s" % exc)
        return False
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        _log(quiet, "  git 报错: %s" % (detail[-1] if detail else proc.returncode))
        shutil.rmtree(dest, ignore_errors=True)
        return False
    if not os.path.isdir(dest) or not os.listdir(dest):
        return False
    _log(quiet, "  git clone 完成: %s" % dest)
    return True


# --------------------------------------------------------------------------
# 方式二：下载 zip 源码包（不依赖 git）
# --------------------------------------------------------------------------

def _candidate_branches(url):
    branches = []
    parsed = parse_github_url(url)
    if parsed:
        info = None
        try:
            from github.api import repo_info
            info = repo_info("%s/%s" % parsed)
        except Exception:
            info = None
        if info and info.get("default_branch"):
            branches.append(info["default_branch"])
    # codeload 支持 HEAD，会自动解析默认分支，不依赖 GitHub API。
    # 批量跑几十个仓库后 API 很容易撞上 60 次/小时的限流，一旦取不到分支
    # 就只会去试 main/master，像 carbon-lang（默认 trunk）这种就会全 404。
    branches.append("HEAD")
    branches.extend(["main", "master", "trunk", "develop", "dev"])
    seen, result = set(), []
    for branch in branches:
        if branch and branch not in seen:
            seen.add(branch)
            result.append(branch)
    return result


MAX_DOWNLOAD_BYTES = int(os.getenv("MAX_REPO_ZIP_BYTES", str(400 * 1024 * 1024)))
ZIP_RETRY_ON_429 = int(os.getenv("ZIP_RETRY_ON_429", "4"))
ZIP_RETRIES = int(os.getenv("ZIP_RETRIES", "3"))

# 可选：GitHub 加速代理，形如 https://gh-proxy.com
# 国内网络直连 codeload 只有 ~30KB/s，走代理实测 5MB/s（快 200 倍）。
# 代价：下载流量会经过第三方，仅适合公开仓库；不需要时留空即可。
GITHUB_PROXY = os.getenv("GITHUB_PROXY", "").strip()


def _proxy(url):
    if not GITHUB_PROXY:
        return url
    if url.startswith(GITHUB_PROXY):
        return url
    return GITHUB_PROXY.rstrip("/") + "/" + url


def _download_to_file(zip_url, target, quiet=False):
    """流式下载 zip 到临时文件，避免把几百 MB 的包整个读进内存。

    超过 MAX_DOWNLOAD_BYTES 就放弃，并由上层报"仓库过大"，而不是 OOM。

    两类失败都要重试，否则批量跑会大面积误判为"仓库拉不下来"：
      * 429：GitHub 限流（同一出口 IP 很容易被限）
      * 传输中断：IncompleteRead / ConnectionError，链路差时常见
    """
    import time as _time

    last_error = None
    for attempt in range(ZIP_RETRIES + 1):
        try:
            resp = requests.get(zip_url, timeout=300, stream=True,
                                headers={"User-Agent": USER_AGENT})
        except requests.RequestException as exc:
            last_error = exc
            _log(quiet, "  下载异常(%s)，重试 %d/%d"
                        % (type(exc).__name__, attempt + 1, ZIP_RETRIES))
            _time.sleep(3 * (attempt + 1))
            continue

        if resp.status_code == 429 and attempt < ZIP_RETRY_ON_429:
            wait = 15 * (attempt + 1)
            try:
                wait = int(resp.headers.get("Retry-After") or wait)
            except (TypeError, ValueError):
                pass
            _log(quiet, "  被限流(429)，%d 秒后重试（第 %d 次）" % (wait, attempt + 1))
            resp.close()
            _time.sleep(min(wait, 120))
            continue

        if resp.status_code != 200:
            return None, resp.status_code

        # 代理在并发压力下会「静默截断」：HTTP 200、没有异常，但内容少了一截，
        # 直到解压时才报 "File is not a zip file"。所以下载完必须自己校验：
        #   1) 收到的字节数要等于 Content-Length
        #   2) 文件要能被识别成合法 zip
        expected = resp.headers.get("Content-Length")
        try:
            expected = int(expected) if expected else None
        except (TypeError, ValueError):
            expected = None

        total = 0
        try:
            with open(target, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        return None, "too-large"
                    fh.write(chunk)
        except Exception as exc:          # IncompleteRead / ConnectionError 等
            last_error = exc
            _log(quiet, "  传输中断(%s)，重试 %d/%d"
                        % (type(exc).__name__, attempt + 1, ZIP_RETRIES))
            try:
                os.remove(target)
            except OSError:
                pass
            _time.sleep(3 * (attempt + 1))
            continue
        finally:
            resp.close()

        if expected is not None and total != expected:
            _log(quiet, "  下载不完整(%d/%d 字节)，重试 %d/%d"
                        % (total, expected, attempt + 1, ZIP_RETRIES))
            try:
                os.remove(target)
            except OSError:
                pass
            _time.sleep(3 * (attempt + 1))
            continue

        if not zipfile.is_zipfile(target):
            _log(quiet, "  下载内容不是合法 zip，重试 %d/%d" % (attempt + 1, ZIP_RETRIES))
            try:
                os.remove(target)
            except OSError:
                pass
            _time.sleep(3 * (attempt + 1))
            continue

        return total, 200

    _log(quiet, "  下载最终失败: %s" % (type(last_error).__name__ if last_error else "未知"))
    return None, "error"


def _zip_download(url, dest, quiet=False):
    parsed = parse_github_url(url)
    if not parsed:
        return False
    owner, repo = parsed

    parent = os.path.dirname(os.path.abspath(dest)) or "."
    os.makedirs(parent, exist_ok=True)

    for branch in _candidate_branches(url):
        # codeload 的默认分支地址是 zip/HEAD，没有 refs/heads/HEAD 这种写法。
        if branch == "HEAD":
            zip_url = "%s/%s/%s/zip/HEAD" % (CODELOAD, owner, repo)
        else:
            zip_url = "%s/%s/%s/zip/refs/heads/%s" % (CODELOAD, owner, repo, branch)

        # 代理优先、直连兜底：加速代理在并发高时会返回 404/403（假失败），
        # 这时必须换直连再试一次，否则整仓库被误判为"拉取失败"。
        urls = []
        if GITHUB_PROXY:
            urls.append(("proxy", _proxy(zip_url)))
        urls.append(("direct", zip_url))

        for via, target_url in urls:
            tmp_dir = _make_work_dir(parent)
            archive = os.path.join(tmp_dir, "_repo.zip")
            try:
                size, status = _download_to_file(target_url, archive, quiet=quiet)
                if status == "too-large":
                    _log(quiet, "  跳过：%s 的压缩包超过 %d MB 上限（可用 MAX_REPO_ZIP_BYTES 调整）"
                                % (repo, MAX_DOWNLOAD_BYTES >> 20))
                    return False
                if status != 200 or not size:
                    _log(quiet, "  zip 下载失败(%s/%s): HTTP %s" % (branch, via, status))
                    continue
                _log(quiet, "  zip 已下载(%s 分支 via %s, %.1f MB)"
                            % (branch, via, size / 1048576.0))

                with zipfile.ZipFile(archive) as zf:
                    # Windows 默认 260 字符路径上限，而仓库里常有一百多字符的文件名
                    # （例如 gemini-cli 的 __snapshots__ 长文件名），直接 extractall 会
                    # 报 "No such file or directory"。加上 \\?\ 前缀可绕过该限制。
                    long_root = "\\\\?\\" + os.path.abspath(tmp_dir)
                    zf.extractall(long_root)
                os.remove(archive)
                entries = [e for e in os.listdir(tmp_dir)
                           if os.path.isdir(os.path.join(tmp_dir, e))]
                if not entries:
                    continue
                inner = os.path.join(tmp_dir, entries[0])
                # 目标目录若残留（上次失败留下的半成品），必须彻底删掉；
                # 否则 os.rename 会失败并退化成 shutil.copytree，
                # 而 copytree 不带 \\?\ 前缀，长路径仓库（n8n 等）会集体报 WinError 3。
                if os.path.isdir(dest):
                    shutil.rmtree("\\\\?\\" + os.path.abspath(dest), ignore_errors=True)
                try:
                    os.rename(inner, dest)
                except OSError:
                    shutil.move(inner, dest)
                _log(quiet, "  zip 解压完成(%s 分支): %s" % (branch, dest))
                return True
            except Exception as exc:
                _log(quiet, "  zip 解压失败(%s/%s): %s" % (branch, via, exc))
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    return False


def _make_work_dir(parent):
    """在 parent 下建一个临时工作目录。

    注意：这里刻意不用 tempfile.mkdtemp —— 它用 mode=0o700 建目录，
    在 Windows 上会生成一个受限的 DACL，导致后续在里面的解压/写入被拒绝。
    用 os.makedirs 的默认权限创建，才能正常继承父目录的权限。
    """
    for _ in range(50):
        path = os.path.join(parent, "ghzip_%s" % uuid.uuid4().hex[:8])
        if not os.path.exists(path):
            os.makedirs(path)
            return path
    raise RuntimeError("无法在 %s 下创建临时目录" % parent)


def _log(quiet, message):
    if not quiet:
        print(message)
