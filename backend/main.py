import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.analyze import router as analyze_router

_BACKEND_ROOT = Path(__file__).resolve().parent
load_dotenv(_BACKEND_ROOT / ".env")

app = FastAPI(title="Tone Calibration API", version="0.1.0")


def _cors_origins() -> list[str]:
    origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    front = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
    if front:
        origins.append(front)
    return list(dict.fromkeys(origins))


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=r"https://.*\.vercel\.app$",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router, prefix="/api")


@app.get("/health")
async def health_check() -> dict:
    """根路径健康检查（兼容旧文档）。"""
    return {"status": "ok"}
