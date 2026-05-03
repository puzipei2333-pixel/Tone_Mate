"""
讯飞开放评测（ISE）流式 WebSocket 封装。

接口：wss://ise-api.xfyun.cn/v2/open-ise
鉴权：HMAC-SHA256，authorization / date / host 拼接到 URL query（见 build_auth_url）
文档：https://www.xfyun.cn/doc/Ise/IseAPI.html
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import io
import json
import logging
import os
import subprocess
import wave
import tempfile
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import formatdate
from pathlib import Path
from typing import Any

import websockets
from dotenv import load_dotenv
from websockets.exceptions import InvalidStatus

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_ROOT / ".env")

LOGGER = logging.getLogger(__name__)

XFYUN_HOST = "ise-api.xfyun.cn"
XFYUN_PATH = "/v2/open-ise"
XFYUN_WSS_BASE = f"wss://{XFYUN_HOST}{XFYUN_PATH}"

# 评测业务参数（与文档 / 控制台一致）
ISE_LANGUAGE = "zh_cn"
ISE_CATEGORY = "read_sentence"
ISE_ENT = "cn_vip"
ISE_SUB = "ise"
ISE_AUE = "raw"
ISE_AUF = "audio/L16;rate=16000"
ISE_RESULT_LEVEL = "entirety"


def _strip_env_value(value: str | None) -> str:
    if not value:
        return ""
    s = value.strip().strip("\ufeff\ufffe")
    for ch in ("\u200b", "\u200c", "\u200d", "\u2060"):
        s = s.replace(ch, "")
    return s.strip()


def normalize_xunfei_credentials(api_key: str, api_secret: str) -> tuple[str, str]:
    return _strip_env_value(api_key), _strip_env_value(api_secret)


def build_auth_url(api_key: str, api_secret: str) -> str:
    """
    生成带鉴权 query 的 WSS URL（HMAC-SHA256 + Base64）。
    query 含：authorization（Base64 后的鉴权串）、date（GMT）、host。
    """
    if not api_key or not api_secret:
        raise ValueError("api_key 与 api_secret 不能为空")

    api_key, api_secret = normalize_xunfei_credentials(api_key, api_secret)
    date = formatdate(timeval=None, localtime=False, usegmt=True)
    signature_origin = (
        f"host: {XFYUN_HOST}\n"
        f"date: {date}\n"
        f"GET {XFYUN_PATH} HTTP/1.1"
    )
    signature = base64.b64encode(
        hmac.new(
            api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
    ).decode("utf-8")
    authorization_origin = (
        f'api_key="{api_key}", '
        f'algorithm="hmac-sha256", '
        f'headers="host date request-line", '
        f'signature="{signature}"'
    )
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")
    query = urllib.parse.urlencode(
        {"authorization": authorization, "date": date, "host": XFYUN_HOST},
        quote_via=urllib.parse.quote,
    )
    url = f"{XFYUN_WSS_BASE}?{query}"
    LOGGER.debug("built ISE auth url host=%s path=%s", XFYUN_HOST, XFYUN_PATH)
    return url


def _try_read_pcm_from_wav_s16le_16k_mono(audio_bytes: bytes) -> bytes | None:
    """若已是 RIFF WAV、16kHz、单声道、16-bit LE，则直接读出 PCM 帧（无需 ffmpeg）。"""
    if len(audio_bytes) < 12 or audio_bytes[:4] != b"RIFF":
        return None
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != 16000:
                return None
            return w.readframes(w.getnframes())
    except (wave.Error, EOFError, OSError):
        return None


def convert_audio_to_pcm(audio_bytes: bytes) -> bytes:
    """
    转为 PCM：16-bit LE，16000 Hz，单声道。
    若输入已是该格式的 WAV，则用标准库直接读取；否则调用 ffmpeg（webm/mp3 等）。
    """
    if not audio_bytes:
        raise ValueError("audio_bytes 为空")

    fast = _try_read_pcm_from_wav_s16le_16k_mono(audio_bytes)
    if fast is not None:
        if not fast:
            raise RuntimeError("WAV 中无有效 PCM 帧")
        LOGGER.info(
            "输入为 16k/mono/s16le WAV，跳过 ffmpeg, pcm_size=%s bytes",
            len(fast),
        )
        return fast

    LOGGER.info("converting audio to PCM via ffmpeg, input_size=%s bytes", len(audio_bytes))
    ffmpeg_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "ffmpeg"))
    if not os.path.exists(ffmpeg_path):
        ffmpeg_path = "ffmpeg"  # 本地开发时用系统的

    with tempfile.NamedTemporaryFile(delete=False, suffix=".input") as in_file:
        in_file.write(audio_bytes)
        input_path = Path(in_file.name)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pcm") as out_file:
        output_path = Path(out_file.name)

    cmd = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "s16le",
        str(output_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            LOGGER.error("ffmpeg 失败 returncode=%s stderr=%s", proc.returncode, err)
            raise RuntimeError(f"ffmpeg 转码失败: {err or proc.returncode}")
        pcm = output_path.read_bytes()
        if not pcm:
            LOGGER.error("ffmpeg 输出 PCM 为空")
            raise RuntimeError("ffmpeg 输出 PCM 为空")
        LOGGER.info("PCM 转换完成, pcm_size=%s bytes", len(pcm))
        return pcm
    except FileNotFoundError as exc:
        LOGGER.error("未找到 ffmpeg 可执行文件，请安装 ffmpeg 并加入 PATH")
        raise RuntimeError("未找到 ffmpeg，请先安装 ffmpeg") from exc
    finally:
        for path in (input_path, output_path):
            try:
                path.unlink(missing_ok=True)
            except OSError as unlink_err:
                LOGGER.warning("删除临时文件失败 path=%s err=%s", path, unlink_err)


def _websocket_connect_kwargs() -> dict[str, Any]:
    """可选：XUNFEI_WS_PROXY=direct 时强制不走系统代理。"""
    p = _strip_env_value(os.getenv("XUNFEI_WS_PROXY", ""))
    if not p:
        return {}
    if p.lower() in ("direct", "none", "off", "0", "false", "no"):
        return {"proxy": None}
    if p.lower() in ("auto", "system", "default", "1", "true", "on"):
        return {}
    return {"proxy": p}


def _strip_xml_namespace(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_xml_from_message(data: dict[str, Any]) -> str | None:
    inner = data.get("data")
    if not isinstance(inner, dict):
        return None
    b64 = inner.get("data")
    if not b64 or not isinstance(b64, str):
        return None
    try:
        decoded = base64.b64decode(b64).decode("utf-8", errors="replace").strip()
    except Exception:
        LOGGER.warning("base64 解码 data.data 失败 sid=%s", data.get("sid"))
        return None
    if decoded.startswith("<"):
        return decoded
    return None


def _find_scored_read_sentence(root: ET.Element) -> ET.Element | None:
    scored: list[ET.Element] = []
    for elem in root.iter():
        if _strip_xml_namespace(elem.tag) != "read_sentence":
            continue
        att = elem.attrib
        if "tone_score" in att or "total_score" in att:
            scored.append(elem)
    if scored:
        return scored[-1]
    for elem in root.iter():
        if _strip_xml_namespace(elem.tag) == "read_sentence":
            return elem
    return None


def _parse_ise_xml(xml_text: str) -> dict[str, Any]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        LOGGER.error("ISE 结果 XML 解析失败: %s", exc)
        raise ValueError(f"ISE 结果 XML 无效: {exc}") from exc

    read_sentence = _find_scored_read_sentence(root)
    if read_sentence is None:
        LOGGER.error("XML 中未找到 read_sentence 节点")
        raise ValueError("ISE 结果 XML 中缺少 read_sentence 节点")

    score_candidates = [
        read_sentence.attrib.get("tone_score"),
        read_sentence.attrib.get("total_score"),
        read_sentence.attrib.get("integrity_score"),
        read_sentence.attrib.get("standard_score"),
    ]
    overall_tone_score = 0.0
    for candidate in score_candidates:
        value = _safe_float(candidate)
        if value is not None:
            overall_tone_score = value
            break

    syllables: list[dict[str, Any]] = []
    for elem in read_sentence.iter():
        if _strip_xml_namespace(elem.tag) != "syll":
            continue
        attrs = elem.attrib
        symbol = attrs.get("symbol")
        dp_message = attrs.get("dp_message")
        if not symbol or dp_message is None:
            continue
        syllable_char = (
            attrs.get("char")
            or attrs.get("content")
            or attrs.get("word")
            or attrs.get("text")
            or ""
        )
        syllables.append(
            {
                "char": syllable_char,
                "pinyin": symbol,
                "tone_correct": str(dp_message) == "0",
                "dp_message": str(dp_message),
            }
        )

    return {"overall_tone_score": overall_tone_score, "syllables": syllables}


def _build_ssb_payload(app_id: str, ref_text: str) -> dict[str, Any]:
    """流式首帧：参数上传 cmd=ssb。"""
    return {
        "common": {"app_id": app_id},
        "business": {
            "language": ISE_LANGUAGE,
            "category": ISE_CATEGORY,
            "ent": ISE_ENT,
            "sub": ISE_SUB,
            "aue": ISE_AUE,
            "auf": ISE_AUF,
            # 文档中「完整结果」：部分示例为 result_level，部分为 rst，一并带上以兼容
            "result_level": ISE_RESULT_LEVEL,
            "rst": ISE_RESULT_LEVEL,
            "rstcd": "utf8",
            "tte": "utf-8",
            "ttp_skip": True,
            "cmd": "ssb",
            "text": "\ufeff" + ref_text,
        },
        "data": {"status": 0, "data": ""},
    }


def _build_auw_payload(aus: int, data_status: int, audio_b64: str) -> dict[str, Any]:
    """音频帧 cmd=auw：aus 1 首块 / 2 中间 / 4 尾帧。"""
    return {
        "business": {"cmd": "auw", "aus": aus, "aue": ISE_AUE},
        "data": {
            "status": data_status,
            "data": audio_b64,
            "data_type": 1,
            "encoding": "raw",
        },
    }


async def _evaluate_pcm_streaming(
    pcm_bytes: bytes,
    ref_text: str,
    app_id: str,
    api_key: str,
    api_secret: str,
    *,
    chunk_size: int = 1280,
    interval_sec: float = 0.04,
    recv_timeout_sec: float = 120.0,
) -> dict[str, Any]:
    if not pcm_bytes:
        raise ValueError("PCM 数据为空")

    api_key, api_secret = normalize_xunfei_credentials(api_key, api_secret)
    auth_url = build_auth_url(api_key, api_secret)
    raw_messages: list[dict[str, Any]] = []
    final_xml_text: str | None = None

    LOGGER.info(
        "连接讯飞 ISE WebSocket 流式评测 ref_len=%s pcm_bytes=%s",
        len(ref_text),
        len(pcm_bytes),
    )

    try:
        async with websockets.connect(
            auth_url,
            ping_interval=None,
            **_websocket_connect_kwargs(),
        ) as ws:
            ssb = _build_ssb_payload(app_id, ref_text)
            await ws.send(json.dumps(ssb, ensure_ascii=False))
            LOGGER.debug("已发送 ssb 参数帧")
            await asyncio.sleep(interval_sec)

            total = len(pcm_bytes)
            offset = 0
            first_audio = True
            chunk_index = 0

            while offset < total:
                chunk = pcm_bytes[offset : offset + chunk_size]
                offset += len(chunk)
                b64 = base64.b64encode(chunk).decode("utf-8")
                payload = _build_auw_payload(1 if first_audio else 2, 1, b64)
                await ws.send(json.dumps(payload))
                first_audio = False
                chunk_index += 1
                if chunk_index == 1 or chunk_index % 50 == 0:
                    LOGGER.debug(
                        "已发送音频帧 chunk=%s offset=%s/%s",
                        chunk_index,
                        offset,
                        total,
                    )
                await asyncio.sleep(interval_sec)

            await ws.send(json.dumps(_build_auw_payload(4, 2, "")))
            LOGGER.debug("已发送尾帧 auw aus=4")
            await asyncio.sleep(interval_sec)

            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=recv_timeout_sec)
                except asyncio.TimeoutError as exc:
                    LOGGER.error("接收超时 %.1fs，已收消息数=%s", recv_timeout_sec, len(raw_messages))
                    raise TimeoutError(
                        f"{recv_timeout_sec}s 内未收到讯飞下一条 WebSocket 消息"
                    ) from exc

                try:
                    data = json.loads(msg)
                except json.JSONDecodeError as exc:
                    LOGGER.error("非 JSON 下行消息前 500 字符: %s", str(msg)[:500])
                    raise RuntimeError("讯飞返回非 JSON 消息") from exc

                raw_messages.append(data)
                code = data.get("code", -1)
                sid = data.get("sid", "")
                if code != 0:
                    LOGGER.error(
                        "讯飞业务错误 code=%s sid=%s message=%s",
                        code,
                        sid,
                        data.get("message"),
                    )
                    raise RuntimeError(
                        f"讯飞 ISE 错误 code={code}, sid={sid}, message={data.get('message')}"
                    )

                xml_piece = _extract_xml_from_message(data)
                if xml_piece:
                    final_xml_text = xml_piece
                    LOGGER.debug("收到含 XML 片段 sid=%s xml_len=%s", sid, len(xml_piece))

                inner = data.get("data")
                status = inner.get("status") if isinstance(inner, dict) else None
                LOGGER.debug("下行 sid=%s data.status=%s", sid, status)

                if status == 2:
                    LOGGER.info("收到结束帧 data.status=2 sid=%s", sid)
                    break

    except asyncio.CancelledError:
        LOGGER.warning("ISE 评测任务被取消")
        raise
    except InvalidStatus as exc:
        body = exc.response.body or b""
        detail = body.decode("utf-8", errors="replace")
        LOGGER.error(
            "WebSocket 握手失败 HTTP %s: %s",
            exc.response.status_code,
            detail[:2000],
        )
        hint = ""
        if "apikey not found" in detail.lower():
            hint = (
                " 提示：请核对开放平台该应用的 APIKey，并确认已开通「语音评测/开放评测 ISE」。"
            )
        raise RuntimeError(
            f"讯飞握手 HTTP {exc.response.status_code}: {detail}{hint}"
        ) from exc
    except websockets.exceptions.WebSocketException:
        LOGGER.exception("WebSocket 通信异常")
        raise
    except OSError:
        LOGGER.exception("网络或系统错误")
        raise

    if not final_xml_text:
        LOGGER.error("未解析到 XML，共收到 %s 条 JSON 消息", len(raw_messages))
        raise RuntimeError("讯飞返回中未找到 base64 XML 评测结果")

    parsed = _parse_ise_xml(final_xml_text)
    LOGGER.info(
        "ISE 解析完成 overall_tone_score=%s syllables=%s",
        parsed["overall_tone_score"],
        len(parsed["syllables"]),
    )

    return {
        "overall_tone_score": parsed["overall_tone_score"],
        "syllables": parsed["syllables"],
        "raw_result": {
            "messages": raw_messages,
            "xml": final_xml_text,
        },
    }


async def evaluate_pronunciation(
    audio_bytes: bytes,
    ref_text: str,
    app_id: str | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
) -> dict[str, Any]:
    """
    对录音做讯飞 ISE 流式评测（先 ffmpeg 转 PCM，再 WebSocket 流式上传）。

    app_id / api_key / api_secret 若为空则从环境变量读取：
    XUNFEI_APP_ID, XUNFEI_API_KEY, XUNFEI_API_SECRET（已由模块加载 .env）。

    返回：
        overall_tone_score, syllables, raw_result（含全量下行 JSON 与最终 XML）
    """
    app_id = _strip_env_value(app_id or os.getenv("XUNFEI_APP_ID", ""))
    api_key = _strip_env_value(api_key or os.getenv("XUNFEI_API_KEY", ""))
    api_secret = _strip_env_value(api_secret or os.getenv("XUNFEI_API_SECRET", ""))
    api_key, api_secret = normalize_xunfei_credentials(api_key, api_secret)

    if not app_id or not api_key or not api_secret:
        raise ValueError("缺少讯飞凭证：请设置 XUNFEI_APP_ID / XUNFEI_API_KEY / XUNFEI_API_SECRET 或传入参数")
    if not ref_text or not ref_text.strip():
        raise ValueError("ref_text 不能为空")

    ref_text = ref_text.strip()
    try:
        pcm_bytes = convert_audio_to_pcm(audio_bytes)
        return await _evaluate_pcm_streaming(
            pcm_bytes,
            ref_text,
            app_id,
            api_key,
            api_secret,
        )
    except (ValueError, RuntimeError, TimeoutError):
        raise
    except Exception:
        LOGGER.exception("evaluate_pronunciation 未预期异常")
        raise


async def test_xunfei_connection(
    ref_text: str = "今天天气怎么样",
    app_id: str | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
) -> dict[str, Any]:
    """短静音 PCM 连通性测试（不调用 ffmpeg）。"""
    app_id = _strip_env_value(app_id or os.getenv("XUNFEI_APP_ID", ""))
    api_key = _strip_env_value(api_key or os.getenv("XUNFEI_API_KEY", ""))
    api_secret = _strip_env_value(api_secret or os.getenv("XUNFEI_API_SECRET", ""))
    api_key, api_secret = normalize_xunfei_credentials(api_key, api_secret)
    if not app_id or not api_key or not api_secret:
        raise ValueError("缺少讯飞凭证：请设置 XUNFEI_APP_ID / XUNFEI_API_KEY / XUNFEI_API_SECRET")

    sample_rate = 16000
    duration_sec = 1.2
    pcm_bytes = b"\x00\x00" * int(sample_rate * duration_sec)
    return await _evaluate_pcm_streaming(pcm_bytes, ref_text.strip(), app_id, api_key, api_secret)


async def analyze_tone(text: str, pinyin: str | None = None) -> dict[str, Any]:
    """兼容旧路由：无音频时仅返回配置状态说明。"""
    return {
        "configured": all(
            [
                os.getenv("XUNFEI_APP_ID"),
                os.getenv("XUNFEI_API_KEY"),
                os.getenv("XUNFEI_API_SECRET"),
            ]
        ),
        "text": text,
        "pinyin": pinyin,
        "details": "完整评测请调用 evaluate_pronunciation(audio_bytes, ref_text, ...)。",
    }
