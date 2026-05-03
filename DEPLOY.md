# 声调校准项目部署说明

前后端分离：**前端 Vercel（Vite）** + **后端 Render（FastAPI）**。本地开发通过 Vite 代理访问后端。

---

## 一、后端（Render）

### 1. 准备代码仓库

将包含 `backend/` 的仓库推送到 GitHub / GitLab（Render 从 Git 拉取）。

### 2. 在 Render 创建 Web Service

1. 打开 [Render Dashboard](https://dashboard.render.com/) → **New** → **Web Service**。
2. 连接仓库，**Root Directory** 填 **`backend`**（与仓库内 `render.yaml`、`Procfile` 位置一致）。
3. Render 会识别 `render.yaml` 或你手动填写：
   - **Runtime**：Python 3
   - **Build Command**：`pip install -r requirements.txt`
   - **Start Command**：`uvicorn main:app --host 0.0.0.0 --port $PORT`（与 `Procfile` 一致；`$PORT` 由 Render 注入）

### 3. 配置环境变量（Dashboard → Environment）

在 Render 中为该服务添加（**值在控制台填写，勿写入 Git**）：

| 变量名 | 说明 |
|--------|------|
| `XUNFEI_APP_ID` | 讯飞开放平台 AppID |
| `XUNFEI_API_KEY` | 讯飞 API Key |
| `XUNFEI_API_SECRET` | 讯飞 API Secret |
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `DEEPSEEK_BASE_URL` | 可选，默认 `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 可选，默认 `deepseek-chat` |
| `FRONTEND_URL` | 正式前端地址，如 `https://your-app.vercel.app`（用于 CORS 白名单） |
| `XUNFEI_WS_PROXY` | 可选；若本机代理干扰讯飞 WebSocket，可设为 `direct` |

`PORT` 由 Render 自动提供，无需手动添加。

### 4. 部署与健康检查

部署完成后，记下服务的 **HTTPS 根地址**，例如：`https://tone-calibration-api.onrender.com`。

验证：

```bash
curl -sS "https://你的服务.onrender.com/api/health"
```

应返回：`{"status":"ok"}`。

---

## 二、前端（Vercel）

### 1. 准备仓库与根目录

在 Vercel 新建项目并导入同一仓库，**Root Directory** 设为 **`frontend`**（以便读取 `frontend/vercel.json` 与 `package.json`）。

### 2. 构建与环境变量

- **Framework Preset**：Vite（或自动检测）。
- **Build Command**：`npm run build`（与 `vercel.json` 一致）。
- **Output Directory**：`dist`。

在 Vercel 项目 → **Settings → Environment Variables** 中添加：

| 名称 | 值示例 | 环境 |
|------|--------|------|
| `VITE_API_BASE_URL` | `https://你的服务.onrender.com`（**无尾部斜杠**） | Production / Preview |

说明：`VITE_*` 在 **构建时** 注入；修改后需 **Redeploy** 才生效。

### 3. 部署与验证

部署完成后访问 Vercel 提供的 URL，在浏览器中：

1. 打开参考文本、完成录音、提交分析。
2. 打开开发者工具 → **Network**，确认请求发往 **`VITE_API_BASE_URL/api/analyze`**，且状态为 200。

---

## 三、本地开发

1. 复制根目录 `.env.example` 为 `backend/.env`，并填写真实密钥。
2. 后端：`cd backend && source .venv/bin/activate && uvicorn main:app --reload --port 8000`
3. 前端：`cd frontend && npm install && npm run dev`
4. 本地 **不写** `VITE_API_BASE_URL` 时，前端使用相对路径 **`/api/analyze`**，由 **`vite.config.js` 仅在 `development` 模式** 下代理到 `http://127.0.0.1:8000`。

---

## 四、CORS 与联调注意

- 后端通过 **`allow_origin_regex`** 匹配 **`https://*.vercel.app`**，并通过 **`FRONTEND_URL`** 支持自定义生产域名。
- 本地 **`http://localhost:5173`**、**`http://127.0.0.1:5173`** 已加入白名单。
- 若使用 **Vercel 自定义域名**，请把该 **`https://...` 完整地址** 写入 Render 上的 **`FRONTEND_URL`** 并重新部署后端。

---

## 五、常见问题

| 现象 | 处理 |
|------|------|
| 前端 404 / 跨域 | 检查 `FRONTEND_URL`、Vercel 域名是否被 CORS 覆盖；浏览器看具体 `Origin`。 |
| 分析接口 502 | Render 上是否安装/可用 `ffmpeg`（若用 webm）；或改用 16k/mono WAV 测试。 |
| 构建后仍请求 localhost | 未设置或未重新构建 **`VITE_API_BASE_URL`**。 |

---

## 六、文件清单

| 路径 | 用途 |
|------|------|
| `frontend/vercel.json` | Vercel 构建命令与 `dist` 输出 |
| `frontend/vite.config.js` | 仅开发环境 `/api` 代理 |
| `backend/render.yaml` | Render Blueprint 示例（含环境变量键名） |
| `backend/Procfile` | 兼容 Heroku/Render 的进程启动命令 |
| `.env.example` | 本地/文档用环境变量模板（无敏感值） |
