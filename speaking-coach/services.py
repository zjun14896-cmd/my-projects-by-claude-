# -*- coding: utf-8 -*-
"""
外部 AI 服务（只用 Python 标准库）。

这里集中放所有需要密钥的调用，换服务商只需要改这个文件：
  - 语音转写：豆包「大模型录音文件识别 · 极速版」
  - 理解 / 改写：DeepSeek（OpenAI 兼容的 chat/completions 接口）
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import socket
import struct
import urllib.error
import urllib.request
import uuid
import wave


class ServiceError(Exception):
    """给用户看的错误信息（中文）。"""


def _post_json(url: str, payload: dict, headers: dict, timeout: int):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()
    except urllib.error.URLError as e:
        raise ServiceError("网络连接失败：%s" % e.reason)
    except (socket.timeout, TimeoutError):
        raise ServiceError("请求超时（%d 秒），请稍后重试" % timeout)


# ---------------------------------------------------------------------------
# 豆包语音：大模型录音文件识别 · 极速版
# 参考字节官方示例 bytedance/agentkit-samples skills/byted-voice-to-text/scripts/asr_flash.py
# 注意：尚未用真实密钥实测，拿到密钥后用「设置 → 测试连接」验证。
# ---------------------------------------------------------------------------

DOUBAO_FLASH_URL = os.environ.get(
    "DOUBAO_ASR_URL", "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
)


def doubao_ready(s: dict) -> bool:
    return bool(s.get("doubao_api_key") or (s.get("doubao_app_id") and s.get("doubao_access_token")))


def _doubao_headers(s: dict) -> dict:
    headers = {
        "X-Api-Resource-Id": s.get("doubao_resource_id") or "volc.bigasr.auc_turbo",
        "X-Api-Request-Id": str(uuid.uuid4()),
        "X-Api-Sequence": "-1",
    }
    if s.get("doubao_app_id") and s.get("doubao_access_token"):
        # 旧版控制台：App ID + Access Token
        headers["X-Api-App-Key"] = s["doubao_app_id"]
        headers["X-Api-Access-Key"] = s["doubao_access_token"]
    else:
        # 新版控制台：API Key
        headers["X-Api-Key"] = s.get("doubao_api_key", "")
    return headers


def doubao_transcribe(wav_bytes: bytes, s: dict) -> list:
    """把 16kHz 单声道 WAV 交给豆包识别，返回 [{start, end, text}]（秒）。"""
    if not doubao_ready(s):
        raise ServiceError("还没有配置豆包语音的密钥")
    audio = {"data": base64.b64encode(wav_bytes).decode("ascii")}
    if s.get("doubao_language"):
        audio["language"] = s["doubao_language"]
    payload = {
        "user": {"uid": "speaking-coach"},
        "audio": audio,
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
            "enable_ddc": False,  # 关闭「语义顺滑」，尽量保留原话（含重复、口误）
            "show_utterances": True,
        },
    }
    status, headers, body = _post_json(DOUBAO_FLASH_URL, payload, _doubao_headers(s), timeout=600)
    code = headers.get("X-Api-Status-Code", "")
    if code == "20000003":  # 静音音频
        return []
    if code != "20000000":
        msg = headers.get("X-Api-Message", "") or body[:300].decode("utf-8", "replace")
        raise ServiceError("豆包识别失败（HTTP %s，code=%s）：%s" % (status, code or "无", msg))

    result = json.loads(body.decode("utf-8")).get("result") or {}
    if isinstance(result, list):
        result = result[0] if result else {}
    segs = []
    for u in result.get("utterances") or []:
        text = (u.get("text") or "").strip()
        if text:
            segs.append({"start": u.get("start_time", 0) / 1000.0, "end": u.get("end_time", 0) / 1000.0, "text": text})
    if not segs and (result.get("text") or "").strip():
        segs.append({"start": None, "end": None, "text": result["text"].strip()})
    return segs


def _silent_wav(seconds: float = 1.0, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<h", 0) * int(rate * seconds))
    return buf.getvalue()


def doubao_test(s: dict) -> str:
    """发 1 秒静音，能通过鉴权就算成功。"""
    doubao_transcribe(_silent_wav(), s)
    return "豆包连接正常"


# ---------------------------------------------------------------------------
# DeepSeek
# ---------------------------------------------------------------------------

def deepseek_ready(s: dict) -> bool:
    return bool(s.get("deepseek_api_key"))


def _deepseek_json(s: dict, system: str, user: str, timeout: int = 240) -> dict:
    if not deepseek_ready(s):
        raise ServiceError("还没有配置 DeepSeek 密钥")
    url = (s.get("deepseek_base_url") or "https://api.deepseek.com").rstrip("/") + "/chat/completions"
    payload = {
        "model": s.get("deepseek_model") or "deepseek-chat",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
        "stream": False,
    }
    status, _, body = _post_json(url, payload, {"Authorization": "Bearer " + s["deepseek_api_key"]}, timeout)
    if status != 200:
        detail = body[:300].decode("utf-8", "replace")
        try:
            detail = json.loads(body.decode("utf-8"))["error"]["message"]
        except Exception:
            pass
        hint = {401: "密钥无效", 402: "账户余额不足", 429: "请求太频繁"}.get(status, "")
        raise ServiceError("DeepSeek 请求失败（HTTP %s %s）：%s" % (status, hint, detail))
    try:
        content = json.loads(body.decode("utf-8"))["choices"][0]["message"]["content"]
    except Exception:
        raise ServiceError("DeepSeek 返回格式异常")
    return _parse_json_loose(content)


def _parse_json_loose(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text or "", re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    raise ServiceError("AI 返回的内容无法解析，请重试")


def deepseek_test(s: dict) -> str:
    _deepseek_json(s, 'Reply in json: {"ok": true}', "ping")
    return "DeepSeek 连接正常"


UNDERSTAND_SYSTEM = """You help a native Chinese speaker practise spoken English.
They recorded themselves talking freely, with no script. You get the verbatim transcript split into sentences, each with an id like [r12]. The English may contain grammar mistakes, wrong words, Chinglish, repetitions and filler words. That is expected.

Act as an ordinary native English listener. For each requested id, write in Simplified Chinese what you understand that sentence to mean.
Rules:
- Translate the meaning a listener would actually get from the words said. Do NOT correct or polish the English, and do not read in meaning the words don't support.
- Use the neighbouring sentences as context.
- If part of a sentence is unclear or ambiguous, give your best reading and put the doubtful part in 【】 with a short note, e.g. 【听不太懂，可能是指…】.
- If a sentence is only filler (e.g. "um, so, yeah"), write （语气词，无实际内容）.
- Natural Chinese, usually one or two sentences.

Return json only, exactly one item per requested id:
{"items": [{"id": "r12", "zh": "..."}]}"""


def understand(s: dict, context: list, ids: list) -> list:
    """context: [{id, en}]，ids: 需要翻译的句子 id。返回 [{id, zh}]。"""
    lines = "\n".join("[%s] %s" % (r["id"], r.get("en", "")) for r in context)
    user = "Transcript (context):\n%s\n\nGive your understanding ONLY for these ids: %s" % (lines, ", ".join(ids))
    data = _deepseek_json(s, UNDERSTAND_SYSTEM, user)
    wanted = set(ids)
    return [
        {"id": str(it.get("id", "")), "zh": str(it.get("zh", "")).strip()}
        for it in data.get("items") or []
        if str(it.get("id", "")) in wanted
    ]


IMPROVE_SYSTEM = """You are a friendly English speaking coach for a native Chinese speaker. They spoke freely without a script, and have already proofread the transcript so it shows exactly what they said.

For each sentence you get:
- en: what they actually said (verbatim, may contain mistakes)
- ai_zh: how an AI listener understood it (Chinese)
- ai_understood: true = they confirmed ai_zh is what they meant; false = ai_zh is NOT what they meant; null = not checked (assume true)
- intended: when ai_understood is false, what they really meant, in Chinese (may be empty; then infer from context)

For each sentence produce:
1. "natural": how a native speaker would naturally SAY the intended meaning in everyday conversation. Keep it spoken (contractions are fine), keep the speaker's own ideas and roughly the same length, don't make it fancy or formal, drop pure filler.
2. "issues": the 1-3 most important problems, each {"said": the exact words they used (copied from en), "better": what replaces it in natural, "why": a short explanation in Simplified Chinese}. Focus on what matters for being understood and sounding natural: grammar, word choice, collocation, Chinglish word order, unclear meaning. Ignore tiny fillers. If ai_understood is false, the FIRST issue must explain what in their English made the listener misunderstand. If the sentence is already natural and correct, return [].

Return json only, exactly one item per id:
{"items": [{"id": "r12", "natural": "...", "issues": [{"said": "...", "better": "...", "why": "..."}]}]}"""


def improve(s: dict, items: list) -> list:
    """items: [{id, en, ai_zh, ai_understood, intended}]。返回 [{id, natural, issues}]。"""
    user = "Sentences:\n" + json.dumps({"items": items}, ensure_ascii=False, indent=1)
    data = _deepseek_json(s, IMPROVE_SYSTEM, user)
    wanted = {it["id"] for it in items}
    out = []
    for it in data.get("items") or []:
        rid = str(it.get("id", ""))
        if rid not in wanted:
            continue
        issues = []
        for x in it.get("issues") or []:
            if isinstance(x, dict):
                issues.append({k: str(x.get(k, "")).strip() for k in ("said", "better", "why")})
        out.append({"id": rid, "natural": str(it.get("natural", "")).strip(), "issues": issues})
    return out
