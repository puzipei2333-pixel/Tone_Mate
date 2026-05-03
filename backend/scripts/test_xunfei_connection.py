#!/usr/bin/env python3
"""
连通性测试：鉴权 + WebSocket + 短静音 PCM 流式评测（无需 ffmpeg）。
依赖：websockets、python-dotenv；密钥来自 backend/.env。
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s %(message)s",
)

from services.xunfei_ise import test_xunfei_connection  # noqa: E402


async def main() -> None:
    result = await test_xunfei_connection(ref_text="今天天气怎么样")
    print("connection_ok", True)
    print("overall_tone_score", result.get("overall_tone_score"))
    print("syllable_count", len(result.get("syllables") or []))
    msgs = result.get("raw_result", {}).get("messages") or []
    if msgs:
        print("last_sid", msgs[-1].get("sid"))


if __name__ == "__main__":
    asyncio.run(main())
