# 馬雲語氣靈 — 基礎設施與環境說明書

**版本：v1.0 ｜ 日期：2026-04-02**
**用途：換網址、換人格、換基礎設施、換服務器時的參考指南**

---

## 一、專案架構總覽

```
┌─────────────────────────────────────────────────────────┐
│                    用戶端（瀏覽器/手機）                    │
│                  jackma.tonetown.ai                      │
└────────────┬──────────────────────┬──────────────────────┘
             │ HTTPS                │ WebSocket (WSS)
             ▼                      ▼
┌────────────────────┐   ┌────────────────────────────────┐
│   jackma-api       │   │   LiveKit Cloud (JackMa_V1)    │
│   Cloud Run        │   │   wss://jackmav1-r51dx60y      │
│   port 8080        │   │   .livekit.cloud                │
│                    │   │                                │
│  - FastAPI 後端    │   │   ┌─────────────────────┐      │
│  - 前端靜態檔     │   │   │  jackma-agent       │      │
│  - 文字聊天 API   │   │   │  Cloud Run          │      │
│  - 錄音→文字 API  │   │   │  port 8080          │      │
│  - TTS: MiniMax    │   │   │                     │      │
│  - LLM: Gemini     │   │   │  - LiveKit Worker   │      │
│                    │   │   │  - STT: Deepgram    │      │
│                    │   │   │  - LLM: Claude      │      │
│                    │   │   │  - TTS: MiniMax     │      │
│                    │   │   │  - VAD: Silero      │      │
│                    │   │   └─────────────────────┘      │
└────────┬───────────┘   └────────────────────────────────┘
         │
         ▼
┌────────────────────┐
│   jackma-db        │
│   Cloud SQL        │
│   PostgreSQL 15    │
│   + pgvector       │
└────────────────────┘
```

### 三種通話模式

| 模式 | 路徑 | 元件鏈 |
|------|------|--------|
| 1. 文字→文字 | 首頁打字 | 前端 → jackma-api → Gemini LLM → MiniMax TTS → 回傳音檔 |
| 2. 錄音→文字 | 首頁按住錄音 | 前端 → jackma-api → Deepgram STT → Gemini LLM → MiniMax TTS → 回傳音檔 |
| 3. 即時對話 | 點通話按鈕 | 前端 → LiveKit Cloud → jackma-agent → Deepgram STT → Claude LLM → MiniMax TTS → LiveKit WebRTC |

---

## 二、GCP 資源清單

| 資源 | 名稱 | 專案 | 區域 | 備註 |
|------|------|------|------|------|
| GCP Project | jianbinv3 | - | - | 與江彬共用專案（不可改名） |
| Cloud Run API | jackma-api | jianbinv3 | asia-east1 | 前端+後端 |
| Cloud Run Agent | jackma-agent | jianbinv3 | asia-east1 | LiveKit 語音 Agent |
| Cloud SQL | jackma-db | jianbinv3 | asia-east1-c | PostgreSQL 15 + pgvector |
| Artifact Registry | jackma-repo | jianbinv3 | asia-east1 | Docker image 倉庫 |
| Cloud Storage | jackma-images | jianbinv3 | asia-east1 | 圖片上傳存放 |
| Domain Mapping | jackma.tonetown.ai | jianbinv3 | asia-east1 | CNAME → ghs.googlehosted.com |

---

## 三、Secret Manager 密鑰清單

### 馬雲專用密鑰（`jackma-` 前綴，不與江彬共用）

| Secret 名稱 | 環境變數 | 用途 | 服務 |
|-------------|----------|------|------|
| jackma-livekit-url | LIVEKIT_URL | LiveKit Cloud WebSocket URL | API + Agent |
| jackma-livekit-api-key | LIVEKIT_API_KEY | LiveKit API 認證 | API + Agent |
| jackma-livekit-api-secret | LIVEKIT_API_SECRET | LiveKit API 密鑰 | API + Agent |

### 共用密鑰（江彬和馬雲共用，修改會影響兩邊）

| Secret 名稱 | 環境變數 | 用途 | 服務 |
|-------------|----------|------|------|
| gemini-api-key | GEMINI_API_KEY | Gemini LLM | API + Agent |
| elevenlabs-api-key | ELEVENLABS_API_KEY | ElevenLabs TTS（馬雲已不用） | API |
| elevenlabs-voice-id | ELEVENLABS_VOICE_ID | ElevenLabs 聲音（馬雲已不用） | API |
| jwt-secret-key | JWT_SECRET_KEY | JWT 認證簽名 | API |
| minimax-api-key | MINIMAX_API_KEY | MiniMax TTS API | API + Agent |
| minimax-group-id | MINIMAX_GROUP_ID | MiniMax 帳號群組 | API + Agent |
| minimax-voice-id | MINIMAX_VOICE_ID | MiniMax 聲紋 ID | API + Agent |
| anthropic-api-key | ANTHROPIC_API_KEY | Claude LLM | Agent |
| deepgram-api-key | DEEPGRAM_API_KEY | Deepgram STT | Agent |

> **重要教訓**：LiveKit secrets 必須用 `jackma-` 前綴隔離。之前共用 `livekit-url` 等 secrets，導致江彬 Agent 被切到馬雲的 LiveKit Cloud，搶了馬雲的 dispatch。

---

## 四、硬編碼值（代碼中固定，不從環境變數讀）

| 值 | 位置 | 用途 | 換人格時要改 |
|----|------|------|-------------|
| `moss_audio_062371e7-2c0c-11f1-a44a-c658cff0ef65` | agent/jackma_agent.py, app/services/tts.py | 馬雲克隆聲紋 | ✅ 必改 |
| `("马云", 10.0)` | agent/jackma_agent.py | STT 關鍵字加權 | ✅ 必改 |
| `https://api.minimax.io/v1/t2a_v2` | agent/minimax_tts.py, app/services/tts.py | MiniMax API 端點 | ❌ 不用改 |
| `claude-haiku-4-5-20251001` | agent/jackma_agent.py | Agent LLM 模型 | ❌ 通常不改 |
| `gemini-2.5-flash` | app/services/llm.py | 文字聊天 LLM | ❌ 通常不改 |
| `nova-2` | agent/jackma_agent.py | STT 模型 | ❌ 通常不改 |
| `speech-02-turbo` | agent/jackma_agent.py, app/services/tts.py | TTS 模型 | ❌ 通常不改 |

---

## 五、環境變數完整清單

### deploy-gcp.yml 注入的環境變數

| 變數 | jackma-api | jackma-agent | 來源 |
|------|:----------:|:------------:|------|
| DATABASE_URL | ✅ | ✅ | --set-env-vars（硬寫連線字串） |
| ELEVENLABS_MODEL_ID | ✅ | ❌ | --set-env-vars |
| TTS_PROVIDER | ❌ | ✅ | --set-env-vars (=minimax) |
| GEMINI_API_KEY | ✅ | ✅ | Secret Manager |
| ELEVENLABS_API_KEY | ✅ | ✅ | Secret Manager |
| ELEVENLABS_VOICE_ID | ✅ | ✅ | Secret Manager |
| JWT_SECRET_KEY | ✅ | ❌ | Secret Manager |
| LIVEKIT_URL | ✅ | ✅ | Secret Manager (jackma-livekit-url) |
| LIVEKIT_API_KEY | ✅ | ✅ | Secret Manager (jackma-livekit-api-key) |
| LIVEKIT_API_SECRET | ✅ | ✅ | Secret Manager (jackma-livekit-api-secret) |
| MINIMAX_API_KEY | ✅ | ✅ | Secret Manager |
| MINIMAX_GROUP_ID | ✅ | ✅ | Secret Manager |
| MINIMAX_VOICE_ID | ✅ | ✅ | Secret Manager |
| ANTHROPIC_API_KEY | ❌ | ✅ | Secret Manager |
| DEEPGRAM_API_KEY | ❌ | ✅ | Secret Manager |

### config.py Feature Flags

| Flag | 預設值 | 用途 |
|------|--------|------|
| ENABLE_USER_PROFILE | True | 用戶資料從對話中學習 |
| ENABLE_USER_EVENTS | True | 追蹤用戶事件 |
| ENABLE_JACKMA_ACTIONS | True | 記錄馬雲說過的話 |
| ENABLE_AUTO_EXTRACT | False | LLM 自動抽取用戶資訊 |
| ENABLE_PROACTIVE_CARE | True | 主動關心機制 |
| ENABLE_VISION | True | 圖片辨識 |

---

## 六、換人格 SOP（例：馬雲 → 李嘉誠）

### Step 1：代碼層面（必改）

| 檔案 | 改什麼 |
|------|--------|
| `app/services/llm.py` | SYSTEM_PROMPT 替換為新靈魂檔 |
| `app/services/llm_backup.py` | 同上 |
| `app/services/vision.py` | VISION_SYSTEM_PROMPT 替換 |
| `agent/jackma_agent.py` | 1. 聲紋 ID 改新的<br>2. STT 關鍵字改新名字<br>3. 開場白/靜默提示改新語氣 |
| `app/services/tts.py` | 聲紋 ID 改新的 |
| `agent/context_builder.py` | 函數名/註解改新名 |
| 前端所有 UI 文字 | 名字、描述、頭像 |

### Step 2：基礎設施（建議獨立）

1. **LiveKit Cloud**：建新 project，取得獨立的 URL/Key/Secret
2. **Secret Manager**：建 `{新名}-livekit-url` 等獨立 secrets
3. **Cloud SQL**：可共用 jackma-db 或建新的
4. **deploy-gcp.yml**：`--set-secrets` 改指向新 secret names

### Step 3：絕對不能做的事

- ❌ 修改共用 secrets 的值（會影響其他人格）
- ❌ 用同一個 LiveKit Cloud project（Agent 會互搶 dispatch）
- ❌ 不驗證就部署（GATE 機制）

---

## 七、換網址 SOP（例：jackma.tonetown.ai → mayun.example.com）

### Step 1：DNS
在域名管理商加 CNAME：`mayun` → `ghs.googlehosted.com`

### Step 2：Cloud Run Domain Mapping
```bash
gcloud beta run domain-mappings create \
  --service=jackma-api \
  --domain=mayun.example.com \
  --region=asia-east1
```

### Step 3：CORS
更新 `app/main.py` 的 `allow_origins` 加入新網址

### Step 4：等 SSL 憑證自動簽發（5-15 分鐘）

---

## 八、換服務器 SOP（例：GCP → AWS）

### 需要遷移的元件

| 元件 | GCP 服務 | AWS 對應 |
|------|---------|---------|
| API 服務 | Cloud Run | ECS Fargate / App Runner |
| Agent 服務 | Cloud Run | ECS Fargate（需常駐） |
| 資料庫 | Cloud SQL | RDS PostgreSQL |
| 密鑰管理 | Secret Manager | AWS Secrets Manager |
| Docker Registry | Artifact Registry | ECR |
| 檔案存放 | Cloud Storage | S3 |
| CI/CD | GitHub Actions + gcloud | GitHub Actions + aws-cli |
| DNS Mapping | Cloud Run Domain Mapping | Route 53 + ALB |

### 不需要遷移的元件（第三方服務）

- LiveKit Cloud（獨立 SaaS）
- MiniMax TTS API
- Deepgram STT API
- Claude / Gemini LLM API
- ElevenLabs API

---

## 九、LiveKit Cloud 資訊

| 項目 | 值 |
|------|-----|
| Project 名稱 | JackMa_V1 |
| Project ID | p_2eb02c68hfw |
| WebSocket URL | wss://jackmav1-r51dx60y.livekit.cloud |
| API Key | APIvzUa5n9bLegS |
| Dashboard | https://cloud.livekit.io/projects/p_2eb02c68hfw |

> **隔離原則**：每個人格必須有獨立的 LiveKit Cloud project。不可共用。

---

## 十、資料庫連線資訊

| 項目 | 值 |
|------|-----|
| 實例名稱 | jackma-db |
| 連線名稱 | jianbinv3:asia-east1:jackma-db |
| IP | 104.199.234.58 |
| 資料庫名 | jackma |
| 用戶名 | jackma |
| 密碼 | JackMa2026DB |
| pgvector | 已啟用 |

### 本地連線
```bash
gcloud sql connect jackma-db --user=postgres --database=jackma
# 密碼: JackMa2026DB
```

---

## 十一、GitHub 部署設定

| 項目 | 值 |
|------|-----|
| Repo | https://github.com/waitinchen/jackma |
| Branch | main |
| CI/CD | `.github/workflows/deploy-gcp.yml` |
| GitHub Secret | GCP_SA_KEY（Service Account JSON） |
| Service Account | github-deploy@jianbinv3.iam.gserviceaccount.com |

### 部署流程
```
git push main → GitHub Actions → Build Docker images → Push to Artifact Registry → Deploy to Cloud Run
```

部署時間：~5 分鐘

---

## 十二、踩坑教訓（避免再犯）

### 1. LiveKit secrets 必須隔離
**事故**：馬雲和江彬共用 `livekit-url` secret，更新馬雲的值後江彬 Agent 被切到馬雲的 LiveKit，搶走 dispatch。
**規則**：每個人格用 `{人格名}-livekit-*` 獨立 secrets。

### 2. TTS 有兩套，都要改
**事故**：改了 Agent 的 TTS（模式 3 正確），忘了改 API 的 TTS（模式 1、2 還是江彬聲音）。
**規則**：`agent/jackma_agent.py` 和 `app/services/tts.py` 是兩套獨立 TTS，改聲音要改兩處。

### 3. API 服務也需要 MiniMax secrets
**事故**：deploy-gcp.yml 的 jackma-api 沒注入 MINIMAX secrets，API 端報「MiniMax TTS 未設定」。
**規則**：jackma-api 和 jackma-agent 都需要 MiniMax secrets。

### 4. MiniMax API URL 要統一
**事故**：Agent 用 `api.minimax.io`（正確），API 用 `api.minimax.chat`（錯誤），導致模式 1、2 無聲音。
**規則**：統一用 `https://api.minimax.io/v1/t2a_v2`。

### 5. 硬編碼 voice_id 防止污染
**事故**：voice_id 從環境變數讀取，可能被 Secret Manager 裡的舊值污染。
**規則**：聲紋 ID 硬編碼在代碼裡，不從環境變數讀。

### 6. 不要用 module-level 預載
**事故**：把 Silero VAD 等 heavy 模組移到 module-level 預載，超過 LiveKit worker 初始化超時，Agent crash。
**規則**：heavy 模組在 entrypoint 內初始化，或用 lazy initialization。

---

*語氣城出品。施工圖品質。下次換人格照著走，不會再踩坑。*
