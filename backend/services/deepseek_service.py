"""
DeepSeek（OpenAI 兼容）声调练习反馈生成。
依赖：pip install openai；环境变量 DEEPSEEK_API_KEY。
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_ROOT / ".env")

LOGGER = logging.getLogger(__name__)

DEEPSEEK_BASE_URL_DEFAULT = "https://api.deepseek.com"
DEEPSEEK_MODEL_DEFAULT = "deepseek-chat"

SYSTEM_PROMPT = (
    "你是一位专业的普通话声调教练。你的任务是根据语音评测结果，给出简洁、友好、具体的练习建议。"
    "回答用中文，语气鼓励但实用。严格按照 JSON 格式返回结果，不要包含任何其他文字。"
)


def _strip(s: str | None) -> str:
    return (s or "").strip()


def _last_tone_digit(pinyin: str) -> str | None:
    """从讯飞 style 拼音末尾取声调数字，如 ma1 -> 1。"""
    if not pinyin:
        return None
    m = re.search(r"([1-5])$", pinyin.strip())
    return m.group(1) if m else None


def _tone_label(digit: str | None) -> str:
    mapping = {
        "1": "第一声（阴平）",
        "2": "第二声（阳平）",
        "3": "第三声（上声）",
        "4": "第四声（去声）",
        "5": "轻声",
    }
    return mapping.get(digit or "", "标准声调")


def _build_error_lines(syllables: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """声调错误的音节列表 + 供 prompt 使用的多行文本。"""
    errors: list[dict[str, Any]] = []
    lines: list[str] = []
    for s in syllables:
        if s.get("tone_correct") is True:
            continue
        ch = _strip(str(s.get("char", "")))
        py = _strip(str(s.get("pinyin", "")))
        digit = _last_tone_digit(py) or "?"
        errors.append(s)
        lines.append(f"「{ch}」标准读音「{py}」（第{digit}声）")
    return errors, "\n".join(lines) if lines else "（无：全部音节声调判定为正确）"


def _build_user_prompt(ref_text: str, score: float, error_block: str) -> str:
    return f"""用户朗读了：「{ref_text}」
整体声调得分：{score}/100

声调错误的字：
{error_block}

每个错误字格式：「字」标准读音「拼音」（第X声）

请以 JSON 格式返回，包含以下字段：
{{
  "summary": "一句话总结整体表现（鼓励为主）",
  "char_feedback": [
    {{
      "char": "麻",
      "correct_tone": "第二声（阳平）",
      "description": "音调从中音升到高音，像在反问'是吗？'",
      "tip": "想象电梯从2楼上升到5楼"
    }}
  ],
  "practice_suggestions": ["建议1", "建议2"]
}}

要求：
1. summary 控制在 30 字以内
2. 每个错误字都要有 description 和 tip
3. practice_suggestions 给出 2 条本周练习建议
4. 只返回 JSON，不要其他文字"""


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """从模型输出中截取第一个完整 JSON 对象（忽略前后说明、Markdown ```json 围栏等）。"""
    text = text.strip()
    # 去掉 ```json ... ``` 或 ``` ... ``` 包裹
    if "```" in text:
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if fence:
            text = fence.group(1).strip()
        else:
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE | re.MULTILINE)
            text = re.sub(r"\s*```\s*$", "", text)
            text = text.strip()
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    # 再试整段解析
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def _normalize_parsed(data: dict[str, Any]) -> dict[str, Any]:
    summary = _strip(str(data.get("summary", "")))
    char_feedback = data.get("char_feedback")
    if not isinstance(char_feedback, list):
        char_feedback = []
    normalized_cf: list[dict[str, Any]] = []
    for item in char_feedback:
        if not isinstance(item, dict):
            continue
        normalized_cf.append(
            {
                "char": _strip(str(item.get("char", ""))),
                "correct_tone": _strip(str(item.get("correct_tone", ""))),
                "description": _strip(str(item.get("description", ""))),
                "tip": _strip(str(item.get("tip", ""))),
            }
        )
    ps = data.get("practice_suggestions")
    if not isinstance(ps, list):
        ps = []
    practice_suggestions = [_strip(str(x)) for x in ps if _strip(str(x))]
    return {
        "summary": summary[:30],
        "char_feedback": normalized_cf,
        "practice_suggestions": practice_suggestions[:10],
    }


def _rule_based_feedback(
    evaluation_result: dict[str, Any],
    ref_text: str,
    *,
    raw_response: str = "",
) -> dict[str, Any]:
    """API 失败或 JSON 无效时的降级结果。"""
    try:
        score = float(evaluation_result.get("overall_tone_score", 0) or 0)
    except (TypeError, ValueError):
        score = 0.0
    syllables = evaluation_result.get("syllables") or []
    if not isinstance(syllables, list):
        syllables = []

    errors, _ = _build_error_lines(syllables)
    char_feedback: list[dict[str, Any]] = []
    for s in errors:
        ch = _strip(str(s.get("char", "")))
        py = _strip(str(s.get("pinyin", "")))
        digit = _last_tone_digit(py)
        tone_label = _tone_label(digit)
        char_feedback.append(
            {
                "char": ch,
                "correct_tone": tone_label,
                "description": f"该字目标为{tone_label}，注意起点与拐点的音高变化。",
                "tip": f"对照「{py}」慢读，用手势画出声调走向，再代入整句练习。",
            }
        )

    n_err = len(char_feedback)
    if score >= 85 and n_err == 0:
        summary = "声调整体很稳，继续保持语感与节奏。"
    elif score >= 70:
        summary = "基础不错，集中攻克标出的几个声调即可。"
    else:
        summary = "还有提升空间，按字跟读、对比练习会很快见效。"

    practice_suggestions = [
        "本周每天选 5 个易混字做「对照朗读」，录音回听二声与三声。",
        "把练习句拆成词组，先慢后快，保证每个字调型完整再连读。",
    ]

    out = {
        "summary": summary[:30],
        "char_feedback": char_feedback,
        "practice_suggestions": practice_suggestions[:2],
        "raw_response": raw_response,
        "fallback": True,
    }
    LOGGER.warning(
        "使用规则降级反馈 score=%s error_chars=%s",
        score,
        n_err,
    )
    return out


async def generate_feedback(evaluation_result: dict, ref_text: str) -> dict:
    """
    根据讯飞式 evaluation_result 与 ref_text，调用 DeepSeek 生成结构化练习反馈。

    返回字段：summary, char_feedback, practice_suggestions, raw_response；
    失败或非 JSON 时使用规则降级，并设置 fallback=True。
    """
    ref_text = _strip(ref_text)
    if not isinstance(evaluation_result, dict):
        LOGGER.error("evaluation_result 不是 dict")
        return _rule_based_feedback({}, ref_text, raw_response="")

    try:
        score = float(evaluation_result.get("overall_tone_score", 0) or 0)
    except (TypeError, ValueError):
        score = 0.0
        LOGGER.warning("overall_tone_score 无法解析为浮点数，按 0 处理")

    syllables = evaluation_result.get("syllables") or []
    if not isinstance(syllables, list):
        syllables = []
        LOGGER.warning("syllables 缺失或非列表，按空列表处理")

    _, error_block = _build_error_lines(syllables)
    user_content = _build_user_prompt(ref_text, score, error_block)

    api_key = _strip(os.getenv("DEEPSEEK_API_KEY", ""))
    base_url = _strip(os.getenv("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL_DEFAULT)).rstrip("/")
    model = _strip(os.getenv("DEEPSEEK_MODEL", DEEPSEEK_MODEL_DEFAULT))

    if not api_key:
        LOGGER.error("未配置 DEEPSEEK_API_KEY，返回规则降级反馈")
        return _rule_based_feedback(evaluation_result, ref_text, raw_response="")

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    raw_text = ""

    try:
        LOGGER.info(
            "调用 DeepSeek generate_feedback model=%s ref_len=%s syllables=%s",
            model,
            len(ref_text),
            len(syllables),
        )
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=800,
            temperature=0.7,
        )
        raw_text = (response.choices[0].message.content or "").strip()
        LOGGER.debug("DeepSeek 原始输出长度=%s", len(raw_text))

        parsed = _extract_json_object(raw_text)
        if parsed is None:
            LOGGER.error("无法从模型输出解析 JSON，前 400 字：%s", raw_text[:400])
            fb = _rule_based_feedback(evaluation_result, ref_text, raw_response=raw_text)
            fb["parse_error"] = True
            return fb

        normalized = _normalize_parsed(parsed)
        summ = normalized["summary"]
        if len(summ) > 30:
            normalized["summary"] = summ[:30]

        ps = list(normalized["practice_suggestions"])
        if len(ps) < 2:
            extra = _rule_based_feedback(evaluation_result, ref_text)["practice_suggestions"]
            for e in extra:
                if e and e not in ps:
                    ps.append(e)
                if len(ps) >= 2:
                    break

        out = {
            "summary": normalized["summary"],
            "char_feedback": normalized["char_feedback"],
            "practice_suggestions": ps[:2],
            "raw_response": raw_text,
            "fallback": False,
        }

        LOGGER.info(
            "DeepSeek 反馈生成成功 summary_len=%s char_feedback=%s",
            len(out["summary"]),
            len(out["char_feedback"]),
        )
        return out

    except Exception as exc:
        LOGGER.error("DeepSeek API 调用失败: %s", exc)
        fb = _rule_based_feedback(evaluation_result, ref_text, raw_response=raw_text)
        fb["error"] = str(exc)
        return fb


async def generate_suggestion(text: str, analysis: dict) -> dict:
    """
    兼容旧路由：若 analysis 含 syllables 则走 generate_feedback，否则简短说明。
    """
    if isinstance(analysis, dict) and "syllables" in analysis and analysis.get("syllables"):
        fb = await generate_feedback(analysis, text)
        return {
            "configured": True,
            "mode": "structured_feedback",
            "summary": fb.get("summary"),
            "char_feedback": fb.get("char_feedback"),
            "practice_suggestions": fb.get("practice_suggestions"),
            "raw_response": fb.get("raw_response"),
            "fallback": fb.get("fallback"),
            "error": fb.get("error"),
        }

    api_key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    base_url = (os.getenv("DEEPSEEK_BASE_URL") or DEEPSEEK_BASE_URL_DEFAULT).strip().rstrip("/")
    model = (os.getenv("DEEPSEEK_MODEL") or DEEPSEEK_MODEL_DEFAULT).strip()

    if not api_key:
        return {
            "configured": False,
            "advice": "",
            "note": "未配置 DEEPSEEK_API_KEY，跳过大模型建议。",
        }

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    payload = json.dumps(analysis, ensure_ascii=False, indent=2)
    messages = [
        {
            "role": "system",
            "content": (
                "你是中文声调与发音辅导老师。根据用户练习文本与讯飞语音评测 JSON，"
                "给出简短、可执行的改进建议（分点列出，控制在 120 字以内）。"
            ),
        },
        {
            "role": "user",
            "content": f"练习文本：{text}\n\n评测数据（JSON）：\n{payload}",
        },
    ]

    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.4,
        )
        advice = (resp.choices[0].message.content or "").strip()
        return {
            "configured": True,
            "model": model,
            "advice": advice,
        }
    except Exception as exc:
        return {
            "configured": True,
            "model": model,
            "advice": "",
            "error": str(exc),
        }
