# 声调校准网站 MVP

前后端分离：`frontend/`（React 18 + Vite + Tailwind CSS）、`backend/`（FastAPI）。

## 启动前端

```bash
cd frontend
npm install
npm run dev
```

默认开发地址：<http://localhost:5173>

## 启动后端

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

在 Windows 上激活虚拟环境使用 `venv\Scripts\activate`。

默认 API 地址：<http://localhost:8000>

- 健康检查：`GET /health`
- 分析：`POST /api/analyze`

请求体示例：

```json
{
  "text": "你好",
  "pinyin": "ni3 hao3"
}
```

## 环境变量（`backend/.env`）

勿将 `.env` 提交到 git（根目录 `.gitignore` 已忽略）。

| 变量 | 说明 |
| --- | --- |
| `XUNFEI_APP_ID` | 讯飞开放平台应用 AppID |
| `XUNFEI_API_KEY` | 讯飞 API Key |
| `XUNFEI_API_SECRET` | 讯飞 API Secret |
| `DEEPSEEK_API_KEY` | DeepSeek API Key（OpenAI 兼容） |
| `DEEPSEEK_BASE_URL` | 可选，默认 `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 可选，默认 `deepseek-chat` |
| `XUNFEI_WS_PROXY` | 可选；设为 `direct` 可强制 WebSocket 直连讯飞（不经系统代理） |

若本机使用 SOCKS 代理且 `websockets` 报错缺少 `python-socks`，可额外执行：`pip install python-socks`。

## 项目结构概览

- `frontend/`：Vite + React（JavaScript）+ Tailwind
- `backend/main.py`：FastAPI 入口
- `backend/routers/analyze.py`：分析路由
- `backend/services/xunfei_ise.py`：讯飞语音评测（ISE WebSocket）封装
- `backend/services/deepseek_service.py`：DeepSeek 建议生成（`openai` 库）
