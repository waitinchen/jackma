# ElevenLabs Agent 發音修正替代方案

## 問題分析

ElevenLabs Conversational AI Agent 的文本生成和 TTS 合成都在 ElevenLabs 服務器端完成，我們無法直接攔截文本進行修改。

## 方案對比

### 方案 A：MCP 工具（暫勿使用）

**現狀**：MCP 尚未準備好，請勿將 TTS Cleaner MCP 關聯到 ElevenLabs Agent。

**優點**（日後若啟用）：理論上可在 TTS 前修改文本；符合 ElevenLabs 官方推薦方式。  
**缺點**：Agent 可能不主動調用工具；可靠性取決於 Agent 配合度。

### 方案 B：前端文本顯示修正（推薦）

**優點**：
- 100% 可靠，不依賴 Agent 配合
- 可以顯示正確的文本（雖然音頻無法修改）
- 實現簡單

**缺點**：
- 無法修改實際的 TTS 音頻
- 只能改善用戶體驗（顯示正確文本）

**適用場景**：目前 MCP 未就緒，可作主要補充

### 方案 C：自定義 LLM（最可靠但複雜）

**優點**：
- 完全控制文本生成
- 可以在生成後立即應用清洗

**缺點**：
- 需要配置自定義 LLM
- 可能增加成本
- 實現複雜

**適用場景**：需要完全控制時

## 推薦方案：前端文本顯示修正

目前 MCP 未就緒，建議以前端文本顯示修正為主：

### 實現步驟

1. **在前端攔截 `agent_response` 事件**
2. **發送到後端進行文本清洗**
3. **顯示清洗後的文本**

### 代碼實現

修改 `voice-chat-rwd/src/hooks/useElevenLabsConvAI.ts`：

```typescript
// 在 handleWebSocketMessage 中
if (data.type === 'agent_response') {
  const originalText = data.agent_response?.agent_response || '';
  
  // 發送到後端進行文本清洗
  try {
    const response = await fetch(`${API_BASE_URL}/api/clean_text`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: originalText }),
    });
    const { cleaned_text } = await response.json();
    setAgentResponse(cleaned_text); // 顯示清洗後的文本
  } catch (error) {
    console.error('Failed to clean text:', error);
    setAgentResponse(originalText); // 失敗時使用原始文本
  }
  
  setStatus('speaking');
  return;
}
```

添加後端 API 端點 `app/api/turn.py`：

```python
@router.post("/clean_text")
async def clean_text(payload: dict):
    """清洗文本以優化顯示"""
    text = payload.get("text", "")
    cleaned = clean_for_tts(text, use_pronunciation_fix=True)
    return {"cleaned_text": cleaned, "original_text": text}
```

## 最終建議

1. **目前**：MCP 未就緒，請勿關聯；以方案 B（前端顯示修正）為主。
2. **日後**：若 MCP 就緒，可依 `MCP_TTS_CLEANER_SETUP.md` 設置，並以前端修正為補充。

## 長期解決方案

如果 ElevenLabs 未來提供：
- **後處理 Webhook**：在 TTS 之前攔截文本
- **自定義 TTS 管道**：允許插入文本處理步驟
- **更可靠的 MCP 調用機制**：確保工具被調用

這些功能將提供更可靠的解決方案。
