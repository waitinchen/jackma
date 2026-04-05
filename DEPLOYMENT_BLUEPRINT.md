# 語氣靈即時對話系統 — 萬用部署藍圖 v1.0

**版本：v1.0 ｜ 日期：2026-04-05**
**用途：換人格、換網址、換基礎設施、換服務器的萬用施工圖**
**來源：馬雲語氣靈（JackMa V1）實戰經驗，含 12 條血淚教訓**

---

## 一、系統架構（三模式統一）

```
用戶 ─────────────────────────────────────────────────
  │
  ├─ 模式1: 文字聊天 ──→ {name}-api ──→ LLM ──→ TTS ──→ 音檔回傳
  │                      (FastAPI)     (M2.7)  (MiniMax)
  │
  ├─ 模式2: 錄音對話 ──→ {name}-api ──→ STT ──→ LLM ──→ TTS ──→ 音檔回傳
  │                                  (Deepgram)
  │
  └─ 模式3: 即時對話 ──→ LiveKit Cloud ──→ {name}-agent
                         (WebSocket)      ├─ STT (Deepgram)
                                          ├─ LLM (M2.7-HS)
                                          ├─ TTS (MiniMax)
                                          └─ VAD (Silero)
```

### 關鍵差異：API 端和 Agent 端是兩套獨立系統

| 項目 | 模式 1&2（API 端） | 模式 3（Agent 端） |
|------|-------------------|-------------------|
| 服務 | `{name}-api` | `{name}-agent` |
| LLM | MiniMax M2.7 | MiniMax M2.7-highspeed |
| TTS | `app/services/tts.py` | `agent/minimax_tts.py` |
| STT | Deepgram（API 呼叫） | Deepgram（LiveKit plugin） |
| 記憶體 | 1 GiB | 2 GiB |
| 延遲目標 | < 3s（不含 TTS） | < 5s（端到端） |
| 常駐 | 可縮到 0 | **必須 min-instances=1** |

> **教訓 #1**：改聲音、改 LLM、改 STT 時，**兩邊都要改**。只改一邊會造成模式間體驗不一致。

---

## 二、最佳參數設置（實戰驗證）

### 2.1 LLM 參數

| 參數 | API 端（文字聊天） | Agent 端（即時對話） | 說明 |
|------|-------------------|-------------------|------|
| 模型 | MiniMax-M2.7 | MiniMax-M2.7-highspeed | highspeed 100tps，即時對話需要低延遲 |
| Temperature | 0.7 | 0.7 | 太低太機械，太高太發散 |
| Max Tokens | 2048 | 由 LiveKit 控制 | 語音回覆不需要太長 |
| API Base URL | `https://api.minimax.io/anthropic` | 同左 | Anthropic 兼容 API |
| API Key | MINIMAX_API_KEY | 同左 | TTS/LLM 共用一組 key |

> **教訓 #2**：即時對話用 highspeed（100 tps），標準版（60 tps）延遲太高（9.2s vs 目標 5s）。

### 2.2 TTS 參數

| 參數 | 值 | 說明 |
|------|-----|------|
| API URL | `https://api.minimax.io/v1/t2a_v2` | **不是** api.minimax.chat |
| Model | speech-02-turbo | 低延遲版 |
| Voice ID | 硬編碼在代碼中 | **不從環境變數讀** |
| Speed | 1.0 | 語速正常 |
| Sample Rate | 32000 (API) / 24000 (Agent) | API 輸出 mp3，Agent 輸出 pcm |
| Format | mp3 (API) / pcm (Agent) | Agent 走 LiveKit WebRTC |

> **教訓 #3**：Voice ID 必須硬編碼，防止 Secret Manager 殘留舊值污染。
> **教訓 #4**：API URL 必須統一用 `api.minimax.io`，兩個檔案要一致。

### 2.3 STT 參數

| 參數 | 值 | 說明 |
|------|-----|------|
| Provider | Deepgram | 中文辨識率最高 |
| Model | nova-2 | Nova-3 不支援中文 |
| Language | zh | 不是 zh-CN 也不是 zh-TW |
| Interim Results | true | 即時顯示轉錄中狀態 |
| Keywords | 8 組（見下表） | 提升特定詞彙辨識率 |

**STT Keywords 模板（換人格時要改）：**

```python
stt_keywords = [
    ("{人格名}", 10.0),       # 最高權重
    ("{用戶常用名}", 8.0),     # 用戶名字
    ("{相關品牌1}", 5.0),
    ("{相關品牌2}", 5.0),
    ("{領域詞1}", 3.0),
    ("{領域詞2}", 3.0),
    ("语气灵", 5.0),           # 系統名稱
]
```

### 2.4 VAD 參數（Silero）

| 參數 | 值 | 說明 |
|------|-----|------|
| min_silence_duration | 0.4s | 400ms 靜音才判定講完 |
| prefix_padding_duration | 0.3s | 保留開頭 300ms，避免截斷 |
| min_speech_duration | 0.1s | 最短語音長度 |
| activation_threshold | 0.5 | 語音偵測門檻 |

> 這組參數在中文場景驗證過，不建議隨意調整。

### 2.5 SYSTEM_PROMPT 結構

```
[靈魂檔內容]           ← 人格定義（換人格時替換）
  ├─ 你是誰
  ├─ 核心人格（三層）
  ├─ 語氣模型
  ├─ 邊界觸發
  └─ 絕不說清單

[STT 容錯指令]          ← 固定，不因人格改變
  ├─ 必須做：猜測意圖
  ├─ 禁止做：提及聽不清
  └─ 比喻：當成打錯字的簡訊

[TTS 語言指令]          ← Agent 專用，追加在 prompt 末尾
  ├─ 簡體中文回覆
  ├─ 不用括號/星號
  └─ 數字用中文念
```

---

## 三、基礎設施清單（每個人格需要的）

### 3.1 獨立資源（每個人格必須獨立）

| 資源 | 命名規則 | 為什麼獨立 |
|------|---------|-----------|
| LiveKit Cloud Project | `{Name}_V1` | Agent 會互搶 dispatch |
| LiveKit Secrets | `{name}-livekit-url` 等 | 共用會互相覆蓋 |
| Cloud Run 服務 | `{name}-api`, `{name}-agent` | 獨立部署獨立擴縮 |
| GitHub Repo | `waitinchen/{name}` | 獨立 CI/CD |
| Cloud Storage | `{name}-images` | 圖片隔離 |

### 3.2 可共用資源（同一 GCP 專案內）

| 資源 | 為什麼可共用 |
|------|-------------|
| GCP Project | 帳單統一管理 |
| Artifact Registry | 不同 image name 就行 |
| Secret Manager（非 LiveKit） | 如 gemini-api-key、minimax-api-key |
| Cloud SQL 實例 | 不同 database name |
| Service Account | 同一個 github-deploy SA |

### 3.3 Cloud Run 建議配置

| 設定 | API 服務 | Agent 服務 | 說明 |
|------|---------|-----------|------|
| Memory | 1 GiB | 2 GiB | Agent 載 Silero VAD 模型 |
| CPU | 1 | 2 | Agent 需要更多運算 |
| Timeout | 300s | 3600s | Agent 通話可達 1 小時 |
| Concurrency | 80 | 10 | Agent 同時通話數少 |
| Min Instances | 0 | **1** | Agent 必須常駐等通話 |
| Max Instances | 3 | 3 | 依需求調整 |
| CPU Throttling | 預設 | --no-cpu-throttling | Agent 需要持續運算 |
| CPU Boost | 預設 | --cpu-boost | 加速冷啟動 |

---

## 四、體驗最佳化技巧

### 4.1 連線速度優化（已實施）

| 優化 | 省時 | 原理 |
|------|------|------|
| 前端預連結 | ~5-10s | 進入通話頁就建 LiveKit 連線，按鈕只開麥克風 |
| Gemini 惰性載入 | ~3-5s | Agent 不用 Gemini，不浪費時間初始化 |
| VAD 預載 | ~3-5s | module-level 載入 Silero 模型 |
| DB 連線池預熱 | ~3-5s | 啟動時 SELECT 1 暖 Cloud SQL Proxy |
| DB 查詢並行化 | ~5-8s | 7 個查詢用 asyncio.gather 並行 |

**優化前後對比：**
- 之前：按撥號鈕 → 等 30 秒 → 聽到馬雲
- 之後：進入頁面 → 背景連線 → 按鈕 → ~3 秒聽到馬雲

### 4.2 LLM 遵守指令的技巧

| 技巧 | 說明 |
|------|------|
| STT 容錯用完整段落 | 3 行太短，LLM 不重視。展開成「必須做/禁止做/比喻」結構 |
| 禁止事項用 ❌ 符號 | 視覺突出，LLM 更容易注意到 |
| 給比喻 | 「當成打錯字的簡訊」比抽象規則更有效 |
| 列舉具體例子 | 「不要說'你說的萬一大哥是什麼意思'」比「不要重複」更清楚 |

### 4.3 健康面板最佳實踐

每個燈號顯示**實際串接的系統和模型名稱**，不只是狀態：

```
MIC  Microphone Array (適用於數位...)
STT  Deepgram Nova-2 · 轉錄成功
LLM  MiniMax M2.7-HS · 已回應
TTS  MiniMax · speech-02-turbo
NET  LiveKit JackMa_V1 · 已連線
SPK  正常
```

---

## 五、環境變數完整對照表

### 5.1 Secret Manager

| Secret 名稱 | 環境變數 | API | Agent | 說明 |
|-------------|----------|:---:|:-----:|------|
| `{name}-livekit-url` | LIVEKIT_URL | ✅ | ✅ | **獨立** |
| `{name}-livekit-api-key` | LIVEKIT_API_KEY | ✅ | ✅ | **獨立** |
| `{name}-livekit-api-secret` | LIVEKIT_API_SECRET | ✅ | ✅ | **獨立** |
| gemini-api-key | GEMINI_API_KEY | ✅ | ✅ | 可共用 |
| jwt-secret-key | JWT_SECRET_KEY | ✅ | ❌ | 可共用 |
| minimax-api-key | MINIMAX_API_KEY | ✅ | ✅ | 可共用（LLM+TTS） |
| minimax-group-id | MINIMAX_GROUP_ID | ✅ | ✅ | 可共用 |
| minimax-voice-id | MINIMAX_VOICE_ID | ✅ | ✅ | 代碼裡硬編碼更安全 |
| anthropic-api-key | ANTHROPIC_API_KEY | ❌ | ✅ | fallback 用 |
| deepgram-api-key | DEEPGRAM_API_KEY | ❌ | ✅ | STT |

### 5.2 環境變數（非 Secret）

| 變數 | API | Agent | 值 |
|------|:---:|:-----:|-----|
| DATABASE_URL | ✅ | ✅ | `postgresql://{name}:{pass}@/{name}?host=/cloudsql/...` |
| TTS_PROVIDER | ❌ | ✅ | `minimax` |
| ELEVENLABS_MODEL_ID | ✅ | ❌ | `eleven_multilingual_v2`（歷史遺留） |

---

## 六、換人格 SOP（萬用版）

### Step 0：建基礎設施（~15 分鐘）

```bash
# 1. LiveKit Cloud：到 cloud.livekit.io 建新 project
#    記下 URL, API_KEY, API_SECRET

# 2. GCP Secret Manager：建獨立 secrets
echo -n "wss://..." | gcloud secrets create {name}-livekit-url --data-file=- --replication-policy=automatic
echo -n "API..." | gcloud secrets create {name}-livekit-api-key --data-file=- --replication-policy=automatic
echo -n "..." | gcloud secrets create {name}-livekit-api-secret --data-file=- --replication-policy=automatic

# 3. Cloud SQL：建新 DB（或共用）
gcloud sql databases create {name} --instance=jackma-db

# 4. Cloud Storage
gcloud storage buckets create gs://{name}-images --location=asia-east1

# 5. Artifact Registry
gcloud artifacts repositories create {name}-repo --repository-format=docker --location=asia-east1
```

### Step 1：代碼改動清單

| 檔案 | 改什麼 | 必改 |
|------|--------|:----:|
| `app/services/llm.py` | SYSTEM_PROMPT（靈魂檔） | ✅ |
| `app/services/tts.py` | JACKMA_VOICE_ID → 新 voice_id | ✅ |
| `agent/{name}_agent.py` | JACKMA_VOICE_ID + STT keywords + 開場白 | ✅ |
| `agent/context_builder.py` | 函數名 + 角色標籤（「馬雲」→ 新名） | ✅ |
| `voice-chat-rwd/src/pages/Call.tsx` | 健康面板模型名稱 | ✅ |
| `voice-chat-rwd/vite.config.ts` | PWA name/description | ✅ |
| `voice-chat-rwd/index.html` | title, meta | ✅ |
| `.github/workflows/deploy-gcp.yml` | SERVICE_NAME + secrets 指向 | ✅ |
| 頭像圖片 | icon.png, pwa-*.png | ✅ |

### Step 2：驗證清單（GATE）

```bash
# 1. 語法檢查
python -m py_compile app/services/llm.py
python -m py_compile agent/{name}_agent.py

# 2. 殘留搜索
grep -rni "{舊名}" agent/ app/ voice-chat-rwd/src/ --include="*.py" --include="*.ts" --include="*.tsx"

# 3. Voice ID 確認
grep "moss_audio\|voice_id" agent/{name}_agent.py app/services/tts.py

# 4. 部署後驗證
curl -s https://{domain}/health
# LiveKit Dashboard: Agents → 確認有 registered worker
```

---

## 七、踩坑教訓（12 條，全部來自實戰）

| # | 教訓 | 規則 |
|---|------|------|
| 1 | LiveKit secrets 被共用，Agent 互搶 dispatch | 每人格用 `{name}-livekit-*` 獨立 secrets |
| 2 | 只改 Agent TTS，忘了改 API TTS | 聲音相關改動必須改兩處 |
| 3 | API 服務沒注入 MiniMax secrets | deploy-gcp.yml 的 API 和 Agent 都要有 |
| 4 | MiniMax URL 不一致（chat vs io） | 統一用 `api.minimax.io` |
| 5 | voice_id 從環境變數讀被污染 | 硬編碼在代碼裡 |
| 6 | module-level 預載超時 Agent crash | VAD 預載帶 fallback，heavy 模組不能阻塞 |
| 7 | Dockerfile COPY 已刪除的檔案 | 改代碼同時更新 Dockerfile |
| 8 | 部署失敗沒有檢查 CI/CD logs | 每次 push 後確認 `gh run list` |
| 9 | Gemini module-level 初始化拖慢 Agent | 惰性載入（`_get_model()`） |
| 10 | DB 查詢串行拖慢連線 | `asyncio.gather` 並行化 |
| 11 | LLM 不遵守 STT 容錯規則 | 用完整段落 + ❌ 符號 + 比喻 |
| 12 | MiniMax M2.7 標準版太慢（9.2s） | 即時對話用 highspeed（100 tps） |

---

## 八、版本鎖定（重要）

```
livekit-agents==1.5.1
livekit-plugins-google==1.5.1
livekit-plugins-silero==1.5.1
livekit-plugins-anthropic==1.5.1
livekit-plugins-deepgram==1.5.1
```

> **不能用 `>=`**，LiveKit 套件版本必須完全一致，否則 API 不相容 crash。

---

## 九、成本估算（每月）

| 服務 | 用量假設 | 月費 |
|------|---------|------|
| Cloud Run API | min=0, ~1000 req/day | ~$5 |
| Cloud Run Agent | min=1, 24/7 常駐 | ~$30 |
| Cloud SQL (db-f1-micro) | 10GB HDD | ~$10 |
| MiniMax LLM | ~500K tokens/day | ~$15 |
| MiniMax TTS | ~100 req/day | ~$5 |
| Deepgram STT | ~30 min audio/day | ~$10 |
| LiveKit Cloud (Build) | 1000 分鐘免費 | $0 |
| **總計** | | **~$75/月** |

---

*語氣城出品。施工圖品質。拿著這份藍圖，任何人格 30 分鐘內可部署上線。*
