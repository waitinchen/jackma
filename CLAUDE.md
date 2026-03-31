# CLAUDE.md — JackMa V2 專案指南

## 架構
- **jackma-api**: FastAPI 後端 + 前端靜態檔，Cloud Run，port 8080
- **jackma-agent**: LiveKit Agent（語音通話），Cloud Run，port 8081（Agent 內建 HTTP server）
- **前端**: React + Vite PWA，build 後由 jackma-api 的 `/web_static` 靜態服務
- **資料庫**: Cloud SQL PostgreSQL（jackma-db），pgvector 擴展
- **網域**: https://jianbin3.tonetown.ai（CNAME → ghs.googlehosted.com）
- **GCP 專案**: jianbinv3（project number: 1058272605064）

## 部署
- push to main → GitHub Actions（`.github/workflows/deploy-gcp.yml`）自動部署
- 同時部署 jackma-api + jackma-agent 兩個 Cloud Run 服務
- 部署時間約 7 分鐘
- **不要用 `gcloud run services update --update-env-vars`**，會建立新 revision 但用舊 image
- Agent **必須** `min-instances=1`（常駐），否則縮到 0 無法接聽通話
- Agent 設定 `no-cpu-throttling`
- 注意：`gcloud run services update` 會重設 min-instances，每次 update 後要確認

## 已知限制
- **Gemini 只有 `gemini-2.5-flash` 可用**（gemini-2.0-flash / 1.5-flash / 2.0-flash-lite 全部 404）
- **PORT 是 Cloud Run 保留變數**，不能手動設
- Google Cloud Speech-to-Text: `latest_short` 和 `latest_long` 不支援 zh-TW，Agent STT 用預設值
- Google Cloud STT 串流模式有 305 秒超時限制 — **已修：改用 batch 模式（`use_streaming=False`）迴避，無時間限制**
- MiniMax TTS: 官方 LiveKit plugin 不支援自訂克隆聲紋 ID，用自訂 wrapper（`agent/minimax_tts.py`）
- LiveKit Cloud: Build 免費方案，包含 Agent deployment

## 環境變數（Secret Manager）
- gemini-api-key, elevenlabs-api-key, elevenlabs-voice-id
- jwt-secret-key, livekit-url, livekit-api-key, livekit-api-secret
- minimax-api-key, minimax-group-id, minimax-voice-id
- Agent 額外需要 GOOGLE_API_KEY（= gemini-api-key，給 LiveKit Google plugin 用）

## 常用除錯指令（Cloud Shell）
```bash
# 看 API logs
gcloud run services logs read jackma-api --region=asia-east1 --limit=50

# 看 Agent logs
gcloud run services logs read jackma-agent --region=asia-east1 --limit=50

# 篩選錯誤
gcloud run services logs read jackma-agent --region=asia-east1 --limit=50 2>&1 | grep -iE "error|speech|stt|llm|tts"

# 強制 Agent 重啟（用 GitHub push 觸發，不要手動 update）
# 在代碼加一行註解 push 即可

# 連接 Cloud SQL
gcloud sql connect jackma-db --user=postgres --database=jackma
# 密碼: JackMa2026Secure
```

## 檔案結構
```
app/                    # FastAPI 後端
  api/                  # API endpoints (auth, turn, livekit, etc.)
  services/             # 業務邏輯 (stt, tts, llm, memory, etc.)
  core/                 # 設定、安全、依賴注入
  db/                   # SQLAlchemy models
agent/                  # LiveKit Agent
  jackma_agent.py       # Agent 主邏輯
  context_builder.py    # 組裝系統提示
  minimax_tts.py        # MiniMax TTS 自訂 wrapper
  transcript_saver.py   # 通話記錄儲存
voice-chat-rwd/         # React 前端
  src/hooks/useLivekitCall.ts  # LiveKit 通話 hook
  src/pages/Call.tsx    # 通話頁面
  src/pages/Home.tsx    # 文字聊天頁面
web_static/             # 前端 build 輸出（靜態檔）
```

## 版本鎖定（重要！）
- **LiveKit 套件必須鎖定同系列版本**，不能用 `>=1.0.0`
- 當前鎖定：`livekit-agents==1.5.1` + plugins 全部 `==1.5.1`
- **已移除 `livekit-plugins-minimax`**（與 1.5.x 不兼容，改用自訂 `agent/minimax_tts.py`）
- `livekit`（核心 SDK）和 `livekit-agents` 是不同套件，版本號不同

## 解題原則（必讀）

### 禁止的行為
- ❌ 用 prompt workaround 掩蓋底層 bug
- ❌ 修症狀而不修根因
- ❌ 同時改超過一個地方
- ❌ 沒驗證假設就動手

### 必須的行為
- ✅ 每次先問：「這是根因還是症狀？」
- ✅ 列出所有可能根因，從最根本的開始處理
- ✅ 改之前說假設，驗證後才動手
- ✅ 修完要說「根因已消除」或「這是暫時方案，根因是 XXX」

### 範例
TTS 念錯字：
- ❌ 在 prompt 加「請在影帝中間加空格」
- ✅ 修好 MiniMax TTS wrapper，用中文原生引擎

## 除錯原則
- **先看完整 traceback**，不要只看最後一行錯誤
- **先告訴假設 → 怎麼驗證 → 再動手**，不要跳過診斷直接改 code
- **Log 要看完整**，`TypeError: ChunkedStream.__init__()` 這類才是根本原因
- 遇到鬼打牆時停下來，列出根本原因再繼續
- **改完 code 後第一件事：查 CI/CD 是否部署成功**，失敗就代表改動沒上線

## 開發歷史（最近決策）
- v2.6.1 (03-28): 加入自然短句確認詞（嗯對、懂了、這樣啊）
- v2.6.0 (03-28): STT 換 Deepgram Nova-2（中文 Tier1、無串流限制、成本降 68%）
- v2.5.4 (03-28): 撥號前健康面板顯示提示文字
- v2.5.3 (03-28): PWA 版本更新通知 banner
- v2.5.2 (03-28): 健康指示燈撥號前可查看
- v2.5.1 (03-28): 通話延遲指標（thinking→speaking 計時）
- v2.5.0 (03-28): STT 改串流模式（省 0.5-1.5s，內建 240s 重連）
- v2.4.9 (03-28): SYSTEM_PROMPT 精簡 25%（2807→2100 字）
- v2.4.8 (03-28): TTS VoiceSettings stability=0.75, speed=1.05
- v2.4.7 (03-28): 藍色波浪修復（clone track + gain 0.001）
- v2.4.6 (03-28): close_on_disconnect=False（網路斷線不重建通話）
- v2.4.5 (03-28): events/actions context limit 20→5, days 30→7
- v2.4.4 (03-28): silence_watchdog RuntimeError 安全退出
- v2.4.3 (03-28): 簡繁轉換改用 opencc-js（3,500+ 字）
- v2.4.2 (03-28): context_builder 分層精簡（history 6, memories 2, notes 5）

## QA 結果（2026-03-28）
- P0: 11/11 全部通過
- P1: 11/11 全部通過
- 端到端延遲: ~1.2s avg

## 踩坑紀錄（血淚教訓，不可再犯）

### 1. LiveKit Plugin API 不要亂猜參數
- `google.STT(keywords=["字串"])` → crash！plugin 的 `PhraseSet.Phrase` 需要 `(value, boost)` tuple，boost 必須是 float
- `elevenlabs.TTS(model_id=...)` → 參數名是 `model` 不是 `model_id`
- `minimax.TTS(voice=...)` → 參數名是 `voice_id`，而且只接受預設列表，不接受自訂克隆 ID
- **教訓：改任何 plugin 參數前，先用 `inspect.signature()` 查實際參數名和型別**

### 2. TypeScript 重複 key 會導致整個部署失敗
- `s2t.ts` 的 object literal 有重複 key → TS 編譯失敗 → Docker build 失敗 → 部署失敗
- 而且是**靜默失敗** — 不看 CI/CD logs 根本不知道
- **教訓：改 object literal 後，搜尋重複 key 再 commit**

### 3. `gcloud run services update` 不會換 Docker image
- 只改環境變數，用的還是舊 image（舊代碼）
- 每次 update 會建新 revision，但 `min-instances` 等設定可能被重設
- **教訓：要更新代碼只能 push 觸發 CI/CD，不要手動 update**

### 4. Gemini 模型可用性
- `gemini-2.0-flash` → 404「no longer available to new users」
- `gemini-1.5-flash` → 404「not found for API version v1beta」
- `gemini-2.0-flash-lite` → 404
- **只有 `gemini-2.5-flash` 可用**
- **教訓：不要猜模型名，先用 API 驗證可用性**

### 5. Google Cloud STT 語言+模型組合
- `model="latest_short"` + `languages=["zh-TW"]` → 400 不支援
- `model="latest_long"` + `languages=["zh-TW"]` → 400 不支援
- 預設 model + `languages=["cmn-Hans-CN"]` → ✅ 可用
- **教訓：zh-TW 不能用，改用 cmn-Hans-CN**

### 6. LiveKit 套件版本必須完全一致
- `livekit-agents==1.5.1` + `livekit-plugins-minimax==1.3.0` → `ChunkedStream.__init__() missing conn_options`
- `livekit>=1.0.0`（不鎖版本）→ pip 裝最新版，各 plugin 版本不一致 → crash
- `livekit`（核心 SDK）最高只有 `1.1.3`，跟 `livekit-agents` 版本號不同
- **教訓：全部鎖同版本 `==1.5.1`，移除不相容的 minimax plugin 用自訂 wrapper**

### 7. ChunkedStream API 在不同版本不同
- 1.3.x: `super().__init__(tts=tts, input_text=text)`
- 1.5.x: `super().__init__(tts=tts, input_text=text, conn_options=conn_options)`
- 1.5.x 的 `_run()` 多了 `output_emitter` 參數
- **教訓：升版後查 `inspect.signature()` 確認 API 變化**

### 8. 部署失敗了但不知道
- 最近 3 次部署全部因為 s2t.ts 重複 key 失敗
- Cloud Run 繼續用舊版代碼
- 開發者以為新代碼已上線，一直在舊版上 debug
- **教訓：每次 push 後都要確認 `gh run list` 的結果是 success**

### 9. Cloud Run Agent 的 min-instances
- Agent 是 LiveKit worker，需要持續連線等待通話
- `min-instances=0` → Agent 閒置就縮到 0 → 通話進來沒人接
- `gcloud run services update` 會把 min-instances 重設
- **教訓：min-instances=1 必須寫在 CI/CD workflow 裡，不能只手動設**

### 10. 前端健康燈號 vs 實際狀態
- TTS 綠燈只代表「收到音訊軌道」，不代表 Agent 的 STT/LLM 在動
- STT 紅燈可能是 Agent 端 crash 了（如 keywords TypeError），但前端不知道
- **教訓：前端不能只靠被動事件判斷健康，需要 Agent 主動回報狀態**

### 11. LiveKit Room Name 必須唯一
- 固定 room name（`jackma-{user_id}`）→ 舊 session 不關閉 → 新撥號連到同一個 room
- LiveKit 認為已有 Agent → 不 dispatch 新 job → Agent READY 但永遠等不到通話
- **教訓：room name 必須加 timestamp（`jackma-{user_id}-{timestamp}`），每次通話建新 room**

### 12. ElevenLabs eleven_v3 不支援 WebSocket 串流
- LiveKit ElevenLabs plugin 預設用 WebSocket（`multi-stream-input` 端點）
- `eleven_v3`（Alpha）對此端點回傳 **403 Forbidden**
- REST API（`/text-to-speech/{voice_id}`）可以用
- **解法：用 `NonStreamingElevenLabs` wrapper（`agent/elevenlabs_rest_tts.py`）強制走 REST API**
- **教訓：REST API 測試通過 ≠ WebSocket 串流可用，Alpha 模型要驗證串流端點**

### 13. 環境變數 vs 硬寫在代碼裡
- `gcloud run services update --update-env-vars ELEVENLABS_MODEL=xxx` 對硬寫在代碼裡的值無效
- 只有代碼中用 `os.environ.get("ELEVENLABS_MODEL")` 才會讀環境變數
- **教訓：要改行為只能改代碼 + push，不能靠環境變數覆蓋硬寫值**

### 14. Deepgram Nova-3 中文不支援
- `model="nova-3"` + `language="zh"` → 400「No such model/language/tier combination」
- Nova-3 中文尚未上線，只有 Nova-2 支援
- Nova-2 的 keywords 格式是 `list[tuple[str, float]]`（跟 Google STT 一樣）
- Nova-3 改用 `keyterms`（`list[str]`），不相容 keywords
- 語言代碼用 `"zh"`，不是 `"zh-CN"`
- **教訓：新模型先用 API 驗證 model+language 組合，不要猜**

## 已確認的技術決策
- **STT 引擎選 Deepgram Nova-2**（`language="zh"`，無串流時間限制，延遲 ~200ms，成本降 68%）
- Google Cloud STT 作為 fallback（DEEPGRAM_API_KEY 未設時自動切換）
- **TTS 模型選 `eleven_flash_v2_5`**（WebSocket 串流、低延遲、克隆聲紋還原度高）
- eleven_v3 中文發音更準但：WebSocket 403 需走 REST、REST 無串流導致延遲大增、克隆聲紋失真
- `NonStreamingElevenLabs` wrapper（`agent/elevenlabs_rest_tts.py`）技術上可行但體驗差，不採用
- flash_v2_5 部分字發音不準，用 `pronunciation_transform` 替換修正

## TTS 發音替換（已驗證）
- `"老本行"` → `"老本杭"` ✅ flash_v2_5 正確
- `"影帝"` → 無解，flash_v2_5 系統性念錯「影」這個音
- **原則：找只有單一讀音的同音字，避免多音字歧義**
- 替換表在 `agent/jackma_agent.py` 的 `PRONUNCIATION_FIXES` dict
- 替換發生在 LLM 串流送進 TTS 之前（`pronunciation_transform`），不影響前端顯示文字

## eleven_v3 現況（2026-03-28）
- WebSocket 串流：不支援（403），v3 架構需整行上下文生成語音
- REST API：可用但延遲高（1.3-1.9s）、克隆聲紋失真（同一 Voice ID 在 v3 詮釋不同，暫不可用）
- LiveKit 官方修復：PR #4936 未 merge
- 等 PR merge 後升級 livekit-plugins-elevenlabs 即可解決
- 關注：https://github.com/livekit/agents/pull/4936
- eleven_v3 已 GA（不再是 Alpha）：https://elevenlabs.io/blog/eleven-v3-is-now-generally-available

## 待辦
- 訂閱 PR #4936，merge 後立刻升級 plugin
- 升級後切回 eleven_v3，中文發音問題全部解決

## Push 前必做（違反必死）
- **Python 檔案**：`python -m py_compile <改動的檔案>`，有錯就修，不能跳過
- **TypeScript 檔案**：`npx tsc --noEmit`，編譯失敗不能 push
- **踩坑教訓**：context_builder.py 加了重複 `from datetime import datetime`，沒驗證就 push，Agent 全面 crash

## 注意事項
- 修改 Agent 代碼後，必須 push 觸發 CI/CD 重建 Docker image 才會生效
- 前端 build 是在 Dockerfile 裡做的，不是本地 build
- `.env` 只用於本地開發，Cloud Run 用 Secret Manager
