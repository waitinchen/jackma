# GCP 部署指南 - 江彬語氣靈

本指南說明如何將江彬語氣靈部署到 Google Cloud Platform。

## 架構概覽

```
┌─────────────────────────────────────────────────────────────┐
│                      Google Cloud Platform                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌──────────────┐      ┌──────────────┐                    │
│   │  Cloud Run   │◄────►│  Cloud SQL   │                    │
│   │  (應用程式)   │      │ (PostgreSQL) │                    │
│   └──────────────┘      └──────────────┘                    │
│          │                                                   │
│          ▼                                                   │
│   ┌──────────────┐      ┌──────────────┐                    │
│   │Secret Manager│      │Cloud Storage │ (選用)             │
│   │  (API Keys)  │      │  (音檔儲存)  │                    │
│   └──────────────┘      └──────────────┘                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 步驟一：建立 GCP 專案

```bash
# 1. 安裝 gcloud CLI (如果還沒安裝)
# https://cloud.google.com/sdk/docs/install

# 2. 登入 GCP
gcloud auth login

# 3. 建立新專案 (或使用現有專案)
gcloud projects create jiangbin-voice --name="江彬語氣靈"

# 4. 設定預設專案
gcloud config set project jiangbin-voice

# 5. 啟用必要的 API
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  containerregistry.googleapis.com
```

---

## 步驟二：建立 Cloud SQL (PostgreSQL)

```bash
# 1. 建立 PostgreSQL 實例 (選擇離你最近的區域)
gcloud sql instances create jiangbin-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=asia-east1 \
  --storage-size=10GB \
  --storage-auto-increase

# 2. 設定 root 密碼
gcloud sql users set-password postgres \
  --instance=jiangbin-db \
  --password=YOUR_SECURE_PASSWORD

# 3. 建立資料庫
gcloud sql databases create jiangbin \
  --instance=jiangbin-db

# 4. 啟用 pgvector 擴展 (需要連線到資料庫執行)
# 先取得連線名稱
gcloud sql instances describe jiangbin-db --format="value(connectionName)"
# 輸出類似: jiangbin-voice:asia-east1:jiangbin-db

# 5. 使用 Cloud SQL Proxy 連線 (本地測試用)
# 下載: https://cloud.google.com/sql/docs/postgres/sql-proxy
./cloud-sql-proxy jiangbin-voice:asia-east1:jiangbin-db &

# 6. 連線並啟用 pgvector
psql "host=127.0.0.1 port=5432 user=postgres dbname=jiangbin"
# 在 psql 中執行:
CREATE EXTENSION IF NOT EXISTS vector;
\q
```

---

## 步驟三：設定 Secret Manager (存放 API Keys)

```bash
# 1. 建立 secrets (每個 API Key 一個)
echo -n "your-gemini-api-key" | gcloud secrets create gemini-api-key --data-file=-
echo -n "your-openai-api-key" | gcloud secrets create openai-api-key --data-file=-
echo -n "your-elevenlabs-api-key" | gcloud secrets create elevenlabs-api-key --data-file=-
echo -n "your-elevenlabs-voice-id" | gcloud secrets create elevenlabs-voice-id --data-file=-
echo -n "your-elevenlabs-model-id" | gcloud secrets create elevenlabs-model-id --data-file=-
echo -n "your-elevenlabs-agent-id" | gcloud secrets create elevenlabs-agent-id --data-file=-

# 2. 產生並儲存 JWT Secret
openssl rand -hex 32 | gcloud secrets create jwt-secret-key --data-file=-

# 3. 授權 Cloud Run 存取 secrets
PROJECT_NUMBER=$(gcloud projects describe jiangbin-voice --format="value(projectNumber)")
gcloud secrets add-iam-policy-binding gemini-api-key \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# 對其他 secrets 重複上述指令...
for SECRET in openai-api-key elevenlabs-api-key elevenlabs-voice-id elevenlabs-model-id elevenlabs-agent-id jwt-secret-key; do
  gcloud secrets add-iam-policy-binding $SECRET \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
done
```

---

## 步驟四：部署到 Cloud Run

### 方法 A：使用 Cloud Build (推薦，自動化)

```bash
# 1. 設定 Cloud Build 觸發器
gcloud builds triggers create github \
  --repo-name=jiangbin \
  --repo-owner=YOUR_GITHUB_USERNAME \
  --branch-pattern="^main$" \
  --build-config=cloudbuild.yaml \
  --substitutions=_REGION=asia-east1,_CLOUD_SQL_CONNECTION=jiangbin-voice:asia-east1:jiangbin-db,_DATABASE_URL="postgresql://postgres:YOUR_PASSWORD@/jiangbin?host=/cloudsql/jiangbin-voice:asia-east1:jiangbin-db"

# 2. 推送程式碼到 GitHub，自動觸發部署
git push origin main
```

### 方法 B：手動部署

```bash
# 1. 建置 Docker 映像
docker build -t gcr.io/jiangbin-voice/jiangbin-api .

# 2. 推送到 Container Registry
docker push gcr.io/jiangbin-voice/jiangbin-api

# 3. 部署到 Cloud Run
gcloud run deploy jiangbin-api \
  --image gcr.io/jiangbin-voice/jiangbin-api \
  --region asia-east1 \
  --platform managed \
  --allow-unauthenticated \
  --add-cloudsql-instances jiangbin-voice:asia-east1:jiangbin-db \
  --set-env-vars "DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@/jiangbin?host=/cloudsql/jiangbin-voice:asia-east1:jiangbin-db" \
  --set-secrets "GEMINI_API_KEY=gemini-api-key:latest,OPENAI_API_KEY=openai-api-key:latest,ELEVENLABS_API_KEY=elevenlabs-api-key:latest,ELEVENLABS_VOICE_ID=elevenlabs-voice-id:latest,JWT_SECRET_KEY=jwt-secret-key:latest" \
  --memory 1Gi \
  --cpu 1 \
  --timeout 300
```

---

## 步驟五：設定自訂網域 (選用)

```bash
# 1. 驗證網域擁有權
gcloud domains verify YOUR_DOMAIN.com

# 2. 對應網域到 Cloud Run
gcloud run domain-mappings create \
  --service jiangbin-api \
  --domain api.YOUR_DOMAIN.com \
  --region asia-east1

# 3. 依照指示設定 DNS 記錄
```

---

## 環境變數對照表

| 變數名稱 | 來源 | 說明 |
|---------|------|------|
| `DATABASE_URL` | Cloud Run 環境變數 | Cloud SQL 連線字串 |
| `GEMINI_API_KEY` | Secret Manager | Google Gemini API |
| `OPENAI_API_KEY` | Secret Manager | OpenAI Whisper API |
| `ELEVENLABS_API_KEY` | Secret Manager | ElevenLabs TTS API |
| `ELEVENLABS_VOICE_ID` | Secret Manager | 江彬聲音 ID |
| `ELEVENLABS_MODEL_ID` | Secret Manager | TTS 模型 ID |
| `ELEVENLABS_AGENT_ID` | Secret Manager | 即時對話 Agent ID |
| `JWT_SECRET_KEY` | Secret Manager | JWT 簽名密鑰 |

---

## 費用估算 (月)

| 服務 | 規格 | 預估費用 |
|------|------|---------|
| Cloud SQL | db-f1-micro, 10GB | ~$10-15 USD |
| Cloud Run | 1 vCPU, 1GB RAM | ~$5-20 USD (依流量) |
| Secret Manager | 6 secrets | < $1 USD |
| Container Registry | 映像儲存 | < $1 USD |
| **總計** | | **~$20-40 USD/月** |

> 💡 提示：新用戶有 $300 USD 免費額度，可用 90 天

---

## 常見問題

### Q: Cloud SQL 連線失敗？
確認 Cloud Run 服務帳號有 `Cloud SQL Client` 角色：
```bash
gcloud projects add-iam-policy-binding jiangbin-voice \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/cloudsql.client"
```

### Q: pgvector 擴展無法安裝？
Cloud SQL PostgreSQL 15+ 已內建支援 pgvector，只需執行 `CREATE EXTENSION vector;`

### Q: 部署後 API 回應很慢？
Cloud Run 有冷啟動問題，可設定最小實例數：
```bash
gcloud run services update jiangbin-api --min-instances 1
```
（會增加費用）

---

## 本地開發連線 Cloud SQL

```bash
# 1. 啟動 Cloud SQL Proxy
./cloud-sql-proxy jiangbin-voice:asia-east1:jiangbin-db &

# 2. 設定本地 .env
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@127.0.0.1:5432/jiangbin

# 3. 啟動開發伺服器
uvicorn app.main:app --reload
```
