# ElevenLabs Agent 通話問題排查

即時通話（`/#/call`）使用 **ElevenLabs Conversational AI**，馬雲的人設、開場白、TTS 皆由 **ElevenLabs 後台** 的 Agent 設定決定。本專案只提供連線（signed URL），不控制 Agent 內容。

**MCP 尚未準備好**：請勿將 TTS Cleaner MCP 關聯到 Agent；若已關聯，請先行解除。

---

## 1. 「一直說 TEST」／開場白不是馬雲

**原因**：Agent 的 **First Message**（第一句話／開場白）或 **Greeting** 在 ElevenLabs 後台被設成 `TEST` 或測試用文案。

**處理**：

1. 登入 [ElevenLabs](https://elevenlabs.io) → **Conversational AI** → 選擇 **馬雲 Agent**。
2. 在 **Agent** 設定中找 **First Message** / **Greeting** / **Opening**。
3. 改成正式開場，例如：  
   `我是馬雲。我聽得見，你說吧！`
4. 儲存後重新撥打通話測試。

**本地檢查**：專案內有 `check_agent.py`，可查看目前 Agent 的 `first_message`：

```bash
python check_agent.py
```

輸出中的 `first_message` 即為現有開場白。

---

## 2. 「一直說 clean TEST TEST」

**原因**：多半是 **First Message** 含 `TEST` 或 `clean`；或 **System Prompt** 裡有「調用 clean_tts_text」「清洗」等字眼，Agent 把它們**講出來**。

**處理**：

1. **改 First Message**  
   ElevenLabs 後台 → Agent → **First Message**：改成正式開場（如 `我是馬雲。我聽得見，你說吧！`），**不要**含 `TEST`、`clean`。

2. **改 System Prompt**  
   若有提到「clean」「clean_tts_text」「清洗」等，刪除或改寫；勿讓 Agent 說出這些字。

3. **確認設定**  
   ```bash
   python check_agent.py
   ```  
   看完整 `first_message`；若出現 `test` / `clean`，依上步驟改掉。

**說明**：MCP 尚未準備好，請勿關聯；若曾接過 TTS Cleaner MCP，建議先解除關聯。

**罐頭語（每句開頭都說 clean TEST）**：若判斷是**寫死的罐頭語**、與 system prompt 無關，前端已對 **agent_response 文字** 做過濾：依句號／問號／驚嘆號／換行分句，每句開頭若有 `clean TEST`、`clean TEST TEST`… 一律移除後再顯示。**音訊**仍由 ElevenLabs 直出，無法在前端刪除；若需從根本消除，須在 ElevenLabs 後台或 MCP／工具設定找出罐頭語來源並關閉。

**一鍵修復**：專案內 `fix_clean_test.py` 會透過 API 將 **First Message** 改為「我是馬雲。我聽得見，你說吧!」，並自 **System Prompt** 移除含 `clean_tts_text`、`清洗文本` 的整行。執行後請重撥測試：

```bash
python fix_clean_test.py          # 直接修復
python fix_clean_test.py --dry-run  # 僅預覽，不送出
python fix_clean_test.py --dump     # 傾印含 test/clean 的欄位
```

---

## 3. 「相同的話說兩次」

**可能原因**：

- **前端**：已對收到的 **audio** 做 `event_id` 去重，同一 `event_id` 只播放一次，避免重複播放。
- **Agent 端**：若 ElevenLabs 重複送出相同內容的 audio，或同一段話被生成兩次，仍可能聽起來「說兩次」。

**建議**：

1. 更新到最新前端，確認已包含 event_id 去重。
2. 若仍發生，到 ElevenLabs 後台檢查：
   - Agent 的 **System Prompt** 是否導致重複回答。
   - **Knowledge Base** 有無重複、矛盾的內容。
3. 仍無法排除時，可紀錄發生情境（例如：第一句話、特定問題後）回報 ElevenLabs 或專案維護者。

---

## 4. 解除 MCP 關聯（若曾添加）

1. 登入 [ElevenLabs](https://elevenlabs.io) → **Conversational AI** → 選擇 **馬雲 Agent**。
2. 進入 **Tools** 或 **Integrations**，找到 **TTS Cleaner** / **MCP** 相關項目。
3. 移除或關閉該 MCP 服務器與 Agent 的關聯。
4. 檢查 **System Prompt**：刪除任何「調用 clean_tts_text」「清洗文本」等指示。
5. 儲存後重新通話測試。

---

## 5. 相關檔案與 API

| 項目 | 說明 |
|------|------|
| Agent 設定 | ElevenLabs 後台 → Conversational AI → 馬雲 Agent |
| 連線 API | `GET /api/elevenlabs/signed-url`（依 `ELEVENLABS_AGENT_ID` 取得 signed URL） |
| 健康檢查 | `python check_agent.py`（讀取 Agent 基本資訊與 `first_message`） |
| 前端 hook | `voice-chat-rwd/src/hooks/useElevenLabsConvAI.ts`（WebSocket、audio 佇列、event_id 去重） |

---

## 6. 快速檢查清單

- [ ] **已解除 MCP 關聯**（若曾添加 TTS Cleaner MCP）。
- [ ] ElevenLabs Agent **First Message** 已改成正式開場，沒有 `TEST`、`clean`。
- [ ] System Prompt **不要**讓 Agent 說出「clean」或工具名。
- [ ] 前端已更新，包含 audio **event_id 去重**。
- [ ] 執行 `check_agent.py` 確認 `first_message` 正確。
- [ ] 仍「說兩次」時，已檢查 Agent System Prompt / Knowledge Base。
