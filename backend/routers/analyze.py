"""
声调分析：multipart 上传音频 + 参考文本，讯飞 ISE + DeepSeek 反馈。
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pypinyin import Style, lazy_pinyin, pinyin

from services.deepseek_service import generate_feedback, generate_practice_recommendation
from services.xunfei_ise import evaluate_pronunciation

router = APIRouter(tags=["analyze"])
LOGGER = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 10 * 1024 * 1024
REQUEST_TIMEOUT_SEC = 30.0


def _grade_from_score(score: float) -> str:
    if score >= 90:
        return "优秀"
    if score >= 75:
        return "良好"
    if score >= 60:
        return "需改进"
    return "继续加油"


def _tone_num_from_pinyin_num(pinyin_num: str) -> int | None:
    m = re.search(r"([1-5])$", (pinyin_num or "").strip())
    return int(m.group(1)) if m else None


def _char_to_toned_pinyin(char: str) -> str:
    if not char or not char.strip():
        return ""
    try:
        arr = pinyin(char.strip(), style=Style.TONE, heteronym=False)
        if arr and arr[0]:
            return arr[0][0] or ""
    except Exception:
        LOGGER.warning("pypinyin 转换失败 char=%r", char)
    return ""


def _build_syllables_response(raw_syllables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in raw_syllables:
        if not isinstance(s, dict):
            continue
        ch = str(s.get("char", "") or "")
        pinyin_num = str(s.get("pinyin", "") or "")
        item: dict[str, Any] = {
            "char": ch,
            "pinyin": _char_to_toned_pinyin(ch),
            "pinyin_num": pinyin_num,
            "tone_correct": bool(s.get("tone_correct")),
        }
        tn = _tone_num_from_pinyin_num(pinyin_num)
        if tn is None and ch:
            try:
                t3 = lazy_pinyin(ch, style=Style.TONE3, heteronym=False)
                if t3:
                    tn = _tone_num_from_pinyin_num(t3[0])
            except Exception:
                pass
        if tn is not None:
            item["tone_num"] = tn
        out.append(item)
    return out


def _feedback_public(fb: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": fb.get("summary") or "",
        "char_feedback": fb.get("char_feedback") if isinstance(fb.get("char_feedback"), list) else [],
        "practice_suggestions": fb.get("practice_suggestions")
        if isinstance(fb.get("practice_suggestions"), list)
        else [],
    }


async def _analyze_pipeline(audio_bytes: bytes, ref_text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    evaluation = await evaluate_pronunciation(audio_bytes, ref_text)
    feedback = await generate_feedback(evaluation, ref_text)
    return evaluation, feedback


@router.get("/health")
async def api_health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/analyze")
async def analyze_audio(
    audio: UploadFile = File(..., description="浏览器 MediaRecorder 录制的 webm 等音频"),
    ref_text: str = Form(..., description="用户朗读参考文本"),
) -> dict[str, Any]:
    ref_text = (ref_text or "").strip()
    if not ref_text:
        raise HTTPException(status_code=400, detail="ref_text 不能为空")

    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="音频文件为空")
    if len(raw) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"音频超过大小限制（最大 {MAX_AUDIO_BYTES // (1024 * 1024)}MB）",
        )

    LOGGER.info(
        "analyze_audio filename=%s bytes=%s ref_len=%s",
        audio.filename,
        len(raw),
        len(ref_text),
    )

    try:
        evaluation, feedback = await asyncio.wait_for(
            _analyze_pipeline(raw, ref_text),
            timeout=REQUEST_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError as exc:
        LOGGER.error("analyze_audio 超时 %.1fs", REQUEST_TIMEOUT_SEC)
        raise HTTPException(
            status_code=504,
            detail=f"处理超时（{int(REQUEST_TIMEOUT_SEC)} 秒），请缩短音频或稍后重试",
        ) from exc
    except ValueError as exc:
        LOGGER.warning("参数或凭证错误: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        LOGGER.error("讯飞或转码失败: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        LOGGER.exception("analyze_audio 未预期错误: %s", exc)
        raise HTTPException(status_code=500, detail="服务器内部错误") from exc

    try:
        overall = float(evaluation.get("overall_tone_score", 0) or 0)
    except (TypeError, ValueError):
        overall = 0.0

    syllables_raw = evaluation.get("syllables") or []
    if not isinstance(syllables_raw, list):
        syllables_raw = []

    practice_recommendation = generate_practice_recommendation(syllables_raw)

    return {
        "success": True,
        "ref_text": ref_text,
        "overall_score": overall,
        "grade": _grade_from_score(overall),
        "syllables": _build_syllables_response(syllables_raw),
        "feedback": _feedback_public(feedback),
        "practice_recommendation": practice_recommendation,
    }
