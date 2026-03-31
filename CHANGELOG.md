# 江彬語氣靈 — 更新日誌

## v2.1.0 (2026-03-26)
### 新功能
- 錄音模式改串流：LLM 逐字即時回傳，不用等 10 秒
- 新增 /api/turn-stream SSE 端點

### 修復
- STT keywords TypeError 導致即時通話完全無法運作
- s2t.ts 重複 key 導致部署失敗（連續 3 次）
- 江彬不再糾正 STT 轉錄錯字

### 優化
- CLAUDE.md 新增 10 條踩坑紀錄

---

## v2.0.3 (2026-03-25)
### 修復
- LiveKit 套件版本鎖定 1.5.1（解決 ChunkedStream 不相容）
- MiniMax TTS 自訂 wrapper 適配 1.5.x API
- Agent min-instances=1 寫入 CI/CD（不再被覆蓋）
- Google Cloud STT 改用 cmn-Hans-CN（zh-TW 不支援）
- Gemini LLM 改用 2.5-flash（其他版本全 404）

---

## v2.0.2 (2026-03-24)
### 修復
- Cloud Run Agent health check（port 8080）
- GOOGLE_API_KEY 環境變數設定
- Speech-to-Text API 啟用
- silence_watchdog connection_state 型別修正

### 新功能
- 健康指示燈面板（8 燈真實偵測）
- MiniMax TTS 整合（克隆聲紋）
- 簡體→繁體顯示轉換

---

## v2.0.1 (2026-03-23)
### 修復
- Call.tsx userContext 未定義
- 資料庫 users 表缺少 email 欄位
- Gemini API Key 更新
- SSL 憑證簽發（jianbin3.tonetown.ai）

### 新功能
- LiveKit Agent 部署到 Cloud Run
- GitHub Actions CI/CD 自動部署
- PWA 圖示更新

---

## v2.0.0 (2026-03-23)
### 初始版本
- FastAPI 後端 + React 前端
- LiveKit WebRTC 即時語音通話
- Gemini LLM + Google Cloud STT + MiniMax TTS
- PostgreSQL + pgvector 記憶系統
- 部署到 GCP Cloud Run
