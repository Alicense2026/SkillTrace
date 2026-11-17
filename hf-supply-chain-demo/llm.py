# -*- coding: utf-8 -*-
"""大模型调用封装（OpenAI 兼容接口），支持在多个后端之间切换。

为什么要可切换：
  需求里要求从 DeepSeek 换成 GPT-6 Luna，但两者都走 OpenAI 兼容协议，
  所以把 base_url / model / key 全部配置化，切后端只需要改 .env 一行。

配置方式（.env）：
  LLM_PROVIDER=deepseek          # 或者 luna
  LLM_MODEL=                     # 可选，覆盖 provider 默认模型
  LLM_BASE_URL=                  # 可选，覆盖 provider 默认地址
  LLM_API_KEY=                   # 可选，覆盖 provider 默认 key
  DEEPSEEK_API_KEY=sk-...        # provider=deepseek 时读这个
  LUNA_API_KEY=sk-...            # provider=luna 时读这个

工程上的两个硬约束（都是实测踩出来的，别改回去）：
  1. 不要用 response_format={"type":"json_object"}。实测这个参数下接口会长时间不返回
     （一次等了 2013 秒），普通模式只要 2~3 秒。改用"提示词要求 JSON + 本地宽松解析"。
  2. 必须有墙钟硬超时。requests 的 read timeout 对"连接没断、服务端迟迟不结束响应"
     这种情况不生效，所以要把请求丢进 daemon 线程再 join(timeout)。
"""

from __future__ import annotations

import json
import os
import re
import threading
import time

import requests
from dotenv import load_dotenv

load_dotenv()
# 支持 .env.local 做本机覆盖（比如切换模型后端、填私有 base_url），不污染 .env
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.local"))

PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "key_env": "DEEPSEEK_API_KEY",
    },
    # 备用后端：截图里给出的 gpt-5.6-sol（https://api.example.invalid）。
    # 实测（2026-10-21）不适合本 demo：
    #   * 单次调用 15~320 秒；9k token 的提示词要 320 秒
    #   * 每次请求自带 4.4k~5.7k 输入的隐形开销（代理注入的系统提示）
    #   * openpencil 的大判定请求会超时，导致降级成"未经复核"
    # 保留这个预设是为了以后能一行切换，默认仍用 deepseek。
    "luna": {
        "base_url": os.getenv("LUNA_BASE_URL", "https://api.example.invalid"),
        "model": os.getenv("LUNA_MODEL", "gpt-5.6-sol"),
        "key_env": "LUNA_API_KEY",
    },
}

# 兜底 system：既能让输出更稳，也能避免某些代理静默注入超长系统提示
DEFAULT_SYSTEM = "You are a helpful assistant. Follow the user's requested output format exactly."

CONNECT_TIMEOUT = float(os.getenv("LLM_CONNECT_TIMEOUT", "15"))
READ_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120"))
HARD_TIMEOUT = float(os.getenv("LLM_HARD_TIMEOUT", "120"))

# 用量统计：汇报里要说明"跑一个仓库花多少 token / 多少时间"
USAGE = {
    "provider": "",
    "model": "",
    "calls": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "failures": 0,
    "seconds": 0.0,
}


class LLMError(RuntimeError):
    """大模型不可用时抛出；调用方应降级而不是让整条流水线崩掉。"""


def reset_usage():
    USAGE.update(calls=0, prompt_tokens=0, completion_tokens=0,
                 total_tokens=0, failures=0, seconds=0.0)


def settings():
    """解析当前生效的 provider / base_url / model / api_key。"""
    name = (os.getenv("LLM_PROVIDER") or "deepseek").strip().lower()
    preset = PROVIDERS.get(name, PROVIDERS["deepseek"])
    base_url = (os.getenv("LLM_BASE_URL") or preset["base_url"]).rstrip("/")
    model = os.getenv("LLM_MODEL") or preset["model"]
    api_key = os.getenv("LLM_API_KEY") or os.getenv(preset["key_env"])
    USAGE["provider"] = name
    USAGE["model"] = model
    if not api_key:
        raise LLMError("没有配置大模型 key：请在 .env 里设置 %s 或 LLM_API_KEY"
                       % preset["key_env"])
    return {"provider": name, "base_url": base_url, "model": model, "api_key": api_key}


def _post_with_deadline(url, payload, headers, timeout):
    """在 daemon 线程里发请求，用墙钟卡一个硬上限（见模块注释第 2 条）。"""
    box = {}

    def runner():
        try:
            box["response"] = requests.post(
                url, json=payload, headers=headers,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        except BaseException as exc:      # noqa: BLE001 - 原样带回主线程
            box["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError("请求超过 %.0f 秒仍未返回" % timeout)
    if "error" in box:
        raise box["error"]
    return box["response"]


def chat(prompt, system=None, temperature=0.0, json_mode=False, retries=3):
    """调用大模型，返回文本内容。"""
    conf = settings()
    if not system:
        system = DEFAULT_SYSTEM
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": prompt}]

    payload = {"model": conf["model"], "messages": messages, "temperature": temperature}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    headers = {"Authorization": "Bearer " + conf["api_key"],
               "Content-Type": "application/json"}
    url = conf["base_url"] + "/chat/completions"

    last_error = None
    for attempt in range(retries):
        started = time.time()
        try:
            resp = _post_with_deadline(url, payload, headers, HARD_TIMEOUT)
            if resp.status_code != 200:
                raise LLMError("HTTP %s: %s" % (resp.status_code, resp.text[:200]))
            data = resp.json()
            content = (data["choices"][0]["message"]["content"] or "").strip()

            usage = data.get("usage") or {}
            USAGE["calls"] += 1
            USAGE["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
            USAGE["completion_tokens"] += int(usage.get("completion_tokens") or 0)
            USAGE["total_tokens"] += int(usage.get("total_tokens") or 0)
            USAGE["seconds"] += time.time() - started
            return content
        except Exception as exc:          # 网络抖动 / 限流 / 超时都重试
            last_error = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    USAGE["failures"] += 1
    raise LLMError("大模型调用失败: %s" % last_error)


def _loads_loose(text):
    """尽量把返回内容解析成 JSON（去 ``` 包裹、截取最外层括号）。"""
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if starts:
        start = min(starts)
        end = max(text.rfind("}"), text.rfind("]"))
        if end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                return None
    return None


def chat_json(prompt, system=None, temperature=0.0, retries=2):
    """调用大模型并解析 JSON；失败返回 None，由调用方走确定性兜底。"""
    enabled = os.getenv("LLM_JSON_MODE", "").strip() in ("1", "true", "yes")
    for _ in range(retries):
        try:
            raw = chat(prompt, system=system, temperature=temperature,
                       json_mode=enabled, retries=2)
        except LLMError:
            return None
        data = _loads_loose(raw)
        if data is not None:
            return data
    return None


def available():
    """大模型是否可用（用于决定要不要降级）。"""
    try:
        settings()
        return True
    except LLMError:
        return False
