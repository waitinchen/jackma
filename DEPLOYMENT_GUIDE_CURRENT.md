# 馬雲語氣靈 - 當前部署指南

> 最後更新：2026-02-07

## 部署架構

```
┌─────────────────────────────────────────────────────────────┐
│                    GCP Cloud Run (asia-east1)                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌──────────────────┐       ┌──────────────────┐           │
│   │ jackma-frontend│       │   jackma-api   │           │
│   │ (Nginx + React)  │ ────► │ (FastAPI+Python) │           │
│   │ 靜態檔案服務      │       │ 後端 API 服務    │           │
│   └──────────────────┘       └──────────────────┘           │
│                                      │                       │
│                                      ▼                       │
│                              ┌──────────────────┐           │
│                              │   Cloud SQL      │           │
│                              │ (PostgreSQL 15)  │           │
│                              │ + pgvector       │           │
│                              └──────────────────┘           │
│                                      │                       │
│                                      ▼                       │
│                              ┌──────────────────┐           │
│                              │  Cloud Storage   │           │
│                              │ (jackma-images)│           │
│                              └──────────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

## 服務 URL

| 服務 | URL |
|------|-----|
| 前端 | https://jackma-frontend-652703327350.asia-east1.run.app |
| 後端 API | https://jackma-api-652703327350.asia-east1.run.app |

---

## 一、前置準備

### 1.1 Windows 環境設定

由於 Windows 使用者路徑可能包含中文，需要設定 gcloud 配置目錄：

```powershell
# 建立英文路徑的 gcloud 配置目錄
mkdir C:\gcloud_config

# 每次執行 gcloud 前都要設定這個環境變數
$env:CLOUDSDK_CONFIG = "C:\gcloud_config"
```

### 1.2 部署用資料夾

為避免路徑編碼問題，使用獨立的部署資料夾：

```
C:\jackma-deploy\     # 後端部署用
C:\jackma-frontend\   # 前端部署用
```

---

## 二、後端部署

### 2.1 準備部署檔案

將後端程式碼複製到部署資料夾：

```powershell
# 複製後端程式碼
Copy-Item -Recurse jackma-main\app C:\jackma-deploy\app
Copy-Item -Recurse jackma-main\static C:\jackma-deploy\static
Copy-Item jackma-main\Dockerfile C:\jackma-deploy\
Copy-Item jackma-main\requirements.txt C:\jackma-deploy\
Copy-Item jackma-main\init_db.py C:\jackma-deploy\
```

### 2.2 Dockerfile (後端)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安裝系統依賴
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 安裝 Python 依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式
COPY . .

# 建立音檔目錄
RUN mkdir -p static/audio

# Cloud Run 使用 PORT 環境變數
ENV PORT=8080
EXPOSE 8080

# 啟動應用
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 2.3 建置並部署

```powershell
# 設定 gcloud 路徑
$env:CLOUDSDK_CONFIG = "C:\gcloud_config"

# 切換到部署目錄
Set-Location C:\jackma-deploy

# 建置 Docker 映像並推送到 GCR
gcloud builds submit --tag gcr.io/jackma/jackma-api --timeout=600

# 部署到 Cloud Run
gcloud run deploy jackma-api `
    --image gcr.io/jackma/jackma-api `
    --region asia-east1 `
    --platform managed `
    --allow-unauthenticated `
    --memory 2Gi `
    --cpu 1 `
    --timeout 300 `
    --min-instances 1 `
    --add-cloudsql-instances jackma:asia-east1:jackma-db `
    --set-env-vars "GEMINI_API_KEY=你的KEY" `
    --set-env-vars "OPENAI_API_KEY=你的KEY" `
    --set-env-vars "ELEVENLABS_API_KEY=你的KEY" `
    --set-env-vars "ELEVENLABS_VOICE_ID=256rptWosZS6ffXHUfco" `
    --set-env-vars "ELEVENLABS_MODEL_ID=eleven_flash_v2_5" `
    --set-env-vars "ELEVENLABS_AGENT_ID=agent_0901kernamncf0kr8spv0xw0380t" `
    --set-env-vars "JWT_SECRET_KEY=你的密鑰" `
    --set-secrets "DATABASE_URL=jackma-db-url:latest"
```

---

## 三、前端部署

### 3.1 設定環境變數

**重要**: Vite 環境變數是「建置時」嵌入，必須在 build 前設定！

編輯 `jackma-main/voice-chat-rwd/.env`：

```properties
VITE_API_URL=https://jackma-api-652703327350.asia-east1.run.app
```

### 3.2 建置前端

```powershell
# 進入前端目錄
Set-Location jackma-main\voice-chat-rwd

# 安裝依賴
npm install

# 建置 (輸出到 ../web_static)
npm run build
```

### 3.3 準備部署檔案

```powershell
# 清理並複製建置結果
if (Test-Path "C:\jackma-frontend\dist") { 
    Remove-Item -Recurse -Force "C:\jackma-frontend\dist" 
}
Copy-Item -Recurse jackma-main\web_static C:\jackma-frontend\dist
```

### 3.4 Dockerfile (前端)

在 `C:\jackma-frontend\` 建立 Dockerfile：

```dockerfile
FROM nginx:alpine

# 複製 nginx 設定
COPY nginx.conf /etc/nginx/nginx.conf

# 複製已 build 好的靜態檔案
COPY dist/ /usr/share/nginx/html/

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
```

### 3.5 nginx.conf

在 `C:\jackma-frontend\` 建立 nginx.conf：

```nginx
events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    server {
        listen 8080;
        server_name _;
        root /usr/share/nginx/html;
        index index.html;

        # SPA 路由支援
        location / {
            try_files $uri $uri/ /index.html;
        }

        # 靜態資源快取
        location /assets/ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }

        # PWA Service Worker
        location /sw.js {
            add_header Cache-Control "no-cache";
        }
    }
}
```

### 3.6 建置並部署

```powershell
# 設定 gcloud 路徑
$env:CLOUDSDK_CONFIG = "C:\gcloud_config"

# 切換到部署目錄
Set-Location C:\jackma-frontend

# 建置 Docker 映像並推送到 GCR
gcloud builds submit --tag gcr.io/jackma/jackma-frontend --timeout=600

# 部署到 Cloud Run
gcloud run deploy jackma-frontend `
    --image gcr.io/jackma/jackma-frontend `
    --region asia-east1 `
    --platform managed `
    --allow-unauthenticated `
    --min-instances 1
```

---

## 四、環境變數配置

### 4.1 後端環境變數 (Cloud Run)

| 變數名稱 | 儲存方式 | 值 |
|---------|---------|-----|
| DATABASE_URL | Secret Manager | `postgresql+psycopg2://postgres:密碼@/jackma?host=/cloudsql/jackma:asia-east1:jackma-db` |
| GEMINI_API_KEY | 普通環境變數 | AIzaSy... |
| OPENAI_API_KEY | 普通環境變數 | sk-proj-... |
| ELEVENLABS_API_KEY | 普通環境變數 | sk_... |
| ELEVENLABS_VOICE_ID | 普通環境變數 | 256rptWosZS6ffXHUfco |
| ELEVENLABS_MODEL_ID | 普通環境變數 | eleven_flash_v2_5 |
| ELEVENLABS_AGENT_ID | 普通環境變數 | agent_0901kernamncf0kr8spv0xw0380t |
| JWT_SECRET_KEY | 普通環境變數 | 你的JWT密鑰 |

### 4.2 前端環境變數 (建置時嵌入)

| 變數名稱 | 檔案位置 | 值 |
|---------|---------|-----|
| VITE_API_URL | `voice-chat-rwd/.env` | https://jackma-api-652703327350.asia-east1.run.app |

---

## 五、常見問題

### Q1: 環境變數 "Illegal header value" 錯誤

**原因**: 環境變數值有尾隨空格

**解決**: 在 GCP Console 手動檢查並移除所有環境變數值的尾隨空格

### Q2: 前端 API 呼叫 405 錯誤

**原因**: `VITE_API_URL` 沒有正確嵌入

**解決**: 
1. 確認 `voice-chat-rwd/.env` 有設定 `VITE_API_URL`
2. 重新執行 `npm run build`
3. 重新部署前端

### Q3: 音檔無法播放

**原因**: 前端使用 `window.location.origin` 而非 `API_BASE_URL`

**解決**: 確認 `api.ts` 中的 `playRemoteAudio` 函數使用 `API_BASE_URL`

### Q4: Cloud Run 冷啟動慢

**解決**: 設定 `--min-instances 1` 保持至少一個實例運行

---

## 六、快速部署腳本

### 完整重新部署 (PowerShell)

```powershell
# === 設定 ===
$env:CLOUDSDK_CONFIG = "C:\gcloud_config"

# === 後端部署 ===
Write-Host "=== 部署後端 ===" -ForegroundColor Green
Set-Location C:\jackma-deploy
gcloud builds submit --tag gcr.io/jackma/jackma-api --timeout=600
gcloud run deploy jackma-api --image gcr.io/jackma/jackma-api --region asia-east1 --platform managed --allow-unauthenticated

# === 前端建置 ===
Write-Host "=== 建置前端 ===" -ForegroundColor Green
Set-Location 你的專案路徑\jackma-main\voice-chat-rwd
npm run build

# === 複製建置結果 ===
if (Test-Path "C:\jackma-frontend\dist") { Remove-Item -Recurse -Force "C:\jackma-frontend\dist" }
Copy-Item -Recurse ..\web_static C:\jackma-frontend\dist

# === 前端部署 ===
Write-Host "=== 部署前端 ===" -ForegroundColor Green
Set-Location C:\jackma-frontend
gcloud builds submit --tag gcr.io/jackma/jackma-frontend --timeout=600
gcloud run deploy jackma-frontend --image gcr.io/jackma/jackma-frontend --region asia-east1 --platform managed --allow-unauthenticated

Write-Host "=== 部署完成 ===" -ForegroundColor Green
```

---

## 七、驗證部署

### 檢查後端健康狀態

```bash
curl https://jackma-api-652703327350.asia-east1.run.app/health
```

### 檢查前端

瀏覽器開啟：https://jackma-frontend-652703327350.asia-east1.run.app

### 檢查 API 連線

開啟瀏覽器開發者工具 (F12) → Network 分頁，確認 API 請求發送到正確的後端 URL。
