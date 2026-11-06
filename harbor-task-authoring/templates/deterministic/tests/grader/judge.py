"""判分模型调用：按环境变量选协议，带重试与总时限；拿不到可用返回时抛 JudgeUnavailable。

环境变量优先级：
1. JUDGE_API_KEY + JUDGE_BASE_URL + JUDGE_MODEL，协议由 JUDGE_API_PROTOCOL 指定
   （responses | openai | anthropic | gemini，默认 responses）；
2. 托管评测环境：GEMINI_API_KEY + GOOGLE_GEMINI_BASE_URL + MODEL_NAME（task.toml
   [metadata] judge_model 声明后由评测环境注入），按模型名选网关路由（见 _cfg）。
思考强度：GRADE_REASONING_EFFORT（如 max），只对 Responses 协议生效。
单次调用超时 GRADE_CALL_TIMEOUT（默认 900 秒），全部 llm 项共享总预算 GRADE_JUDGE_BUDGET。
重试与降级：总预算内等待排队，不因单次超时立即放弃。
只用标准库，不依赖 requests。
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request


class JudgeUnavailable(Exception):
    """判分模型在预算内没有可用返回——上层不写 reward，按判分出错处理。"""


def _effort() -> str:
    return os.environ.get("GRADE_REASONING_EFFORT", "").strip()


def _cfg() -> dict:
    key = os.environ.get("JUDGE_API_KEY", "")
    base = os.environ.get("JUDGE_BASE_URL", "")
    if key and base:
        return {"key": key, "base": base.rstrip("/"),
                "model": os.environ.get("JUDGE_MODEL", "gpt-6.1-sol"),
                "api": os.environ.get("JUDGE_API_PROTOCOL", "responses").lower()}
    # 托管评测环境：judge_model 声明后注入判分令牌与 <网关>/gemini 地址（变量名沿用 Gemini 评分器的约定）。
    # 同一个网关按路径区分协议，令牌只放行绑定的判分模型，所以按模型名选路由：
    #   gpt-*    → <网关>/openai/v1/responses（OpenAI Responses，支持思考强度）
    #   claude-* → <网关>/anthropic/v1/messages
    #   其他     → <网关>/gemini/v1beta/models/<模型>:generateContent
    key = os.environ.get("GEMINI_API_KEY", "")
    base = os.environ.get("GOOGLE_GEMINI_BASE_URL", "").rstrip("/")
    if key and base:
        model = os.environ.get("MODEL_NAME", "gpt-6.1-sol")
        root = base[: -len("/gemini")] if base.endswith("/gemini") else base
        if model.startswith(("gpt-", "o1", "o3", "o4")):
            return {"key": key, "base": f"{root}/openai/v1", "model": model, "api": "responses"}
        if model.startswith("claude-"):
            return {"key": key, "base": f"{root}/anthropic", "model": model, "api": "anthropic"}
        return {"key": key, "base": base, "model": model, "api": "gemini"}
    return {}


def describe() -> str:
    c = _cfg()
    if not c:
        return "unconfigured"
    return f"{c['api']}/{c['model']}" + (f"@{_effort()}" if _effort() else "")


def _responses(c: dict, prompt: str, timeout: float) -> str:
    """OpenAI Responses 流式调用：订阅账号池只稳定支持流式；拼接 output_text 增量，以 completed 事件为准。"""
    # 思考强度 max 时推理也计入输出上限；上限太小会把答案挤没（返回空文本），可用 GRADE_MAX_OUTPUT_TOKENS 放大
    payload = {"model": c["model"], "input": prompt, "stream": True,
               "max_output_tokens": int(os.environ.get("GRADE_MAX_OUTPUT_TOKENS", "32000"))}
    if _effort():
        payload["reasoning"] = {"effort": _effort()}
    req = urllib.request.Request(f"{c['base']}/responses", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "Accept": "text/event-stream",
                                          "Authorization": f"Bearer {c['key']}"}, method="POST")
    deltas, full = [], None
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", "ignore").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                ev = json.loads(data)
            except ValueError:
                continue
            t = ev.get("type", "")
            if t == "response.output_text.delta":
                deltas.append(ev.get("delta", ""))
            elif t in ("response.completed", "response.incomplete"):
                resp = ev.get("response") or {}
                if isinstance(resp.get("output_text"), str) and resp["output_text"].strip():
                    full = resp["output_text"]
                else:
                    parts = [ct.get("text", "") for item in resp.get("output") or []
                             for ct in item.get("content") or [] if ct.get("type") in ("output_text", "text")]
                    full = "".join(parts) or None
            elif t in ("response.failed", "error"):
                raise RuntimeError(json.dumps(ev, ensure_ascii=False)[:300])
    return full or "".join(deltas)


def _post(url: str, payload: dict, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **headers}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _once(c: dict, prompt: str, timeout: float) -> str:
    api = c["api"]
    if api == "responses":
        return _responses(c, prompt, timeout)
    if api == "gemini":
        base = c["base"][:-3] if c["base"].endswith("/v1") else c["base"]
        url = f"{base}/v1beta/models/{c['model']}:generateContent"
        payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                   "generationConfig": {"temperature": 0, "maxOutputTokens": 8192,
                                        "responseMimeType": "application/json"}}
        d = _post(url, payload, {"x-goog-api-key": c["key"]}, timeout)
        return "".join(p.get("text", "") for cand in d.get("candidates") or []
                       for p in ((cand.get("content") or {}).get("parts") or []))
    if api == "anthropic":
        base = c["base"][:-3] if c["base"].endswith("/v1") else c["base"]
        payload = {"model": c["model"], "max_tokens": 4096, "temperature": 0,
                   "messages": [{"role": "user", "content": prompt}]}
        d = _post(f"{base}/v1/messages", payload,
                  {"x-api-key": c["key"], "Authorization": f"Bearer {c['key']}",
                   "anthropic-version": "2023-06-01"}, timeout)
        return "".join(b.get("text", "") for b in d.get("content") or [] if b.get("type") == "text")
    payload = {"model": c["model"], "temperature": 0, "max_tokens": 4096,
               "messages": [{"role": "user", "content": prompt}]}
    d = _post(f"{c['base']}/chat/completions", payload, {"Authorization": f"Bearer {c['key']}"}, timeout)
    msg = ((d.get("choices") or [{}])[0].get("message") or {})
    return msg.get("content") or msg.get("reasoning_content") or ""


_DEADLINE = [0.0]


def call(prompt: str) -> str:
    """调一次判分模型；全部 llm 项共享 GRADE_JUDGE_BUDGET 秒（默认 3600）的总预算，可多线程并发调用。"""
    c = _cfg()
    if not c:
        raise JudgeUnavailable("没有判分模型配置（JUDGE_* 或 GEMINI_* 均未注入）")
    if _DEADLINE[0] <= 0:
        _DEADLINE[0] = time.time() + float(os.environ.get("GRADE_JUDGE_BUDGET", "3600"))
    last = ""
    for attempt in range(12):
        left = _DEADLINE[0] - time.time()
        if left <= 15:
            break
        if attempt:
            # 并发超限等瞬时错误：指数退避（最长 120 秒）加随机抖动，避免多份判分同时重试
            time.sleep(min(120.0, 5.0 * 2 ** (attempt - 1), left / 8) * (0.75 + 0.5 * (time.time_ns() % 1000) / 1000))
        try:
            text = _once(c, prompt, timeout=min(float(os.environ.get("GRADE_CALL_TIMEOUT", "900")), max(30.0, left - 10)))
            if text.strip():
                return text
            last = "空返回"
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read()[:200]!r}"
            if e.code in (400, 401, 403, 404):
                break
        except Exception as e:  # 网络、超时、解析错误都按传输失败重试
            last = f"{type(e).__name__}: {e}"
    raise JudgeUnavailable(f"判分模型无可用返回（{describe()}）：{last[:300]}")


def extract_json(text: str):
    if not text or "{" not in text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    frag = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    try:
        return json.loads(frag)
    except Exception:
        return None
