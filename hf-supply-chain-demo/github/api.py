# -*- coding: utf-8 -*-
"""GitHub REST API 的小封装。

注意：未登录时 GitHub 只给 60 次/小时，很容易被限流，
所以这里任何失败都只返回 None，让上层用本地文件内容兜底。
在 .env 里配置 GITHUB_TOKEN 可以显著提高限额。
"""

from __future__ import annotations

import os
import time

import requests

API_ROOT = "https://api.github.com"
_TIMEOUT = 30
_RETRIES = 3


def headers():
    head = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "hf-supply-chain-demo",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        head["Authorization"] = "Bearer %s" % token
    return head


def get_json(path_or_url):
    """GET 一个 GitHub API 地址，返回 dict/list；失败返回 None。

    GitHub 未登录时是 60 次/小时，被限流会返回 403；
    这种情况下重试没有意义，直接返回 None，让上层用本地文件内容兜底。
    """
    url = path_or_url if path_or_url.startswith("http") else API_ROOT + path_or_url
    for attempt in range(_RETRIES):
        try:
            resp = requests.get(url, headers=headers(), timeout=_TIMEOUT)
        except Exception:
            if attempt < _RETRIES - 1:
                time.sleep(1.0 * (attempt + 1))
            continue
        if resp.status_code == 200:
            try:
                return resp.json()
            except Exception:
                return None
        if resp.status_code in (401, 403, 404):
            return None
        if attempt < _RETRIES - 1:
            time.sleep(1.0 * (attempt + 1))
    return None


def repo_info(full_name):
    """仓库元信息：默认分支、许可证、star 等。"""
    return get_json("/repos/%s" % full_name)


def repo_license(full_name):
    """仓库许可证信息（spdx_id / name）。"""
    return get_json("/repos/%s/license" % full_name)
