# Dockerfile for JackMa Voice Spirit API (v2.4 - GCP Cloud Run)
# Multi-stage build: 先構建前端，再構建後端
FROM node:20-slim AS frontend-builder

WORKDIR /app

# 複製前端項目文件
COPY voice-chat-rwd/package*.json ./
RUN npm ci

# 複製前端源碼並構建
COPY voice-chat-rwd/ ./
RUN npm run build

# 驗證構建結果
RUN ls -la ../web_static/assets/ || echo "Build output directory check"

# Python 後端階段
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Cloud Run 會設定 PORT 環境變數
    PORT=8080

WORKDIR /app

# 安裝系統依賴 (Cloud SQL Proxy 需要)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 安裝 Python 依賴
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 複製主程式
COPY app/ ./app/
COPY init_db.py ./

# 從前端構建階段複製構建好的靜態文件
# 注意：vite.config.ts 中設置 outDir: "../web_static"，工作目錄是 /app，所以構建輸出在 /web_static（上一級目錄）
COPY --from=frontend-builder /web_static/ ./web_static/
COPY static/ ./static/

# 複製 Knowledge Base（長期記憶）
COPY Pre-training-memory.md ./

# 創建音頻目錄
RUN mkdir -p static/audio

# 暴露端口 (Cloud Run 使用 PORT 環境變數)
EXPOSE 8080

# 啟動命令 - 使用 $PORT 環境變數 (Cloud Run 要求)
CMD exec uvicorn app.main:app --host 0.0.0.0 --port $PORT
