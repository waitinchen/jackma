# 江彬系統 開發日誌

## 2026-03-22 代碼審查發現

### 已修復
- [x] #1 — `key_notes` 沒傳到通話模式 ElevenLabs Agent（前端 UserContextForVoice 缺 key_notes 欄位）
- [x] #7 — `turn()` / `chatText()` 沒有 401 自動導向登入（未使用 authFetch）
- [x] #11 — `_load_conversation_context` 同步 DB 阻塞 async event loop
- [x] #9 — TTS 音檔無清理機制（static/audio/ 會持續累積）

### 待處理（低優先）
- [ ] #2 — `stopConversation` 掛斷時被呼叫兩次（handleHangup + unmount cleanup）
- [ ] #3 — `inputAnalyser` 仍在 hook return 中暴露但 Call.tsx 不再使用
- [ ] #4 — `audioContextRef` 重連時未 close，可能累積多個 AudioContext
- [ ] #5 — `seenAudioSignaturesRef` 長通話累積大量 string，建議 LRU 或定期清理
- [ ] #6 — `wsRef.current = ws` 在 onopen 和 try 區塊末尾重複設定
- [ ] #8 — `Home.tsx` handleEnd 語音模式無 debounce
- [ ] #10 — `ENABLE_AUTO_EXTRACT` config.py 預設 False 但 .env 為 true（靠 .env 覆蓋）
- [ ] #12 — `get_recent_conversation_history` limit 命名混淆（limit=輪數，非條數）
- [ ] #13 — `proactive_care` max_length=150 可能截斷重要資訊
