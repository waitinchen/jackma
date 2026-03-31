# ElevenLabs MCP TTS 清洗功能設置指南

> **⚠️ MCP 尚未準備好，請勿關聯。**  
> 此指南僅供日後參考，目前請勿將 TTS Cleaner MCP 連接到 ElevenLabs Agent。

---

## 概述

這個 MCP 服務器提供 TTS 文本清洗功能，可以在 ElevenLabs Agent 生成回應後、TTS 合成前自動修正多音字發音錯誤。

## 功能

- **`clean_tts_text`**: 清洗文本，修正易錯詞彙（如「這一行」→「這個行業」，「影帝」→「最佳男主角」）
- **`get_pronunciation_rules`**: 獲取所有發音修正規則列表

## 設置步驟

### 1. 啟動 MCP 服務器

```bash
# 在項目根目錄
cd C:\Users\waiti\jiangbin

# 啟動 MCP 服務器（使用端口 8001，避免與主服務器衝突）
python mcp_server_tts_cleaner.py
```

服務器將運行在 `http://localhost:8001`

### 2. 部署到公開 URL（可選）

如果需要在生產環境使用，需要將服務器部署到公開 URL：

- **選項 A：使用 Railway/Render 等平台**
  - 部署 `mcp_server_tts_cleaner.py` 到 Railway
  - 獲取公開 URL（如 `https://your-app.railway.app`）

- **選項 B：使用 ngrok 進行本地測試**
  ```bash
  ngrok http 8001
  ```
  使用 ngrok 提供的公開 URL

### 3. 在 ElevenLabs 中添加 MCP 服務器

1. 訪問 [ElevenLabs MCP 集成頁面](https://elevenlabs.io/app/agents/integrations)
2. 點擊 "Add Custom MCP Server"
3. 填寫以下信息：
   - **Name**: `TTS Cleaner`
   - **Description**: `清洗文本以優化 TTS 發音，修正多音字發音錯誤`
   - **Server URL**: 
     - 本地測試：`http://localhost:8001`（僅限本地）
     - 生產環境：使用部署後的公開 URL（如 `https://your-app.railway.app`）
   - **Secret Token (Optional)**: 留空（或設置認證令牌）
   - **HTTP Headers (Optional)**: 留空
4. 點擊 "Add Integration" 並測試連接

### 4. 將 MCP 服務器添加到 Agent

1. 進入 Agent 配置頁面
2. 在 "Tools" 標籤中找到 "TTS Cleaner" MCP 服務器
3. 點擊 "Add" 將服務器添加到 Agent
4. 配置工具批准模式：
   - **推薦**：設置 `clean_tts_text` 為 "Auto-approved"（自動批准）
   - 這樣 Agent 可以在生成回應後自動調用清洗功能

### 5. 更新 Agent System Prompt

在 Agent 的 System Prompt 中添加以下指示（**非常重要**）：

```
### 文本處理規則（可選）：
在生成回應之後，可視需要調用 clean_tts_text 工具清洗文本以優化 TTS 發音（例如「重來」→「再來一次」等）。

**重要**：只寫「可調用」工具，勿讓 Agent **說出**「clean」「clean_tts_text」或「清洗」；否則可能「一直說 clean TEST」。

**注意**：Agent 可能不會完全遵循指示。如果 MCP 方案不可靠，請考慮使用「方案 B：前端攔截顯示」。

## 測試

### 測試 MCP 服務器

```bash
# 測試健康檢查
curl http://localhost:8001/health

# 測試工具列表
curl -X POST http://localhost:8001/mcp/v1/tools/list

# 測試文本清洗
curl -X POST http://localhost:8001/mcp/v1/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "clean_tts_text",
    "arguments": {
      "text": "我們重來吧"
    }
  }'
```

預期輸出：`cleaned` 中含「再來一次」等替換（依目前規則而定）。

### 測試 Agent 集成

1. 在 Call 頁面進行對話
2. 觀察 Agent 是否自動調用 `clean_tts_text` 工具
3. 檢查發音是否正確

## 注意事項

1. **本地測試限制**：`localhost` URL 只能在本地使用。ElevenLabs 服務器無法訪問本地 URL，需要部署到公開 URL。

2. **自動調用**：Agent 不會自動調用工具，需要在 System Prompt 中明確指示。

3. **工具批准**：建議將 `clean_tts_text` 設置為 "Auto-approved"，避免每次都需要手動批准。

4. **性能**：MCP 調用會增加延遲，但通常 < 100ms。

## 故障排除

### 問題：Agent 沒有調用工具

**解決方案**：
- 檢查 System Prompt 是否包含調用指示
- 確認工具已添加到 Agent
- 檢查工具批准設置

### 問題：連接失敗

**解決方案**：
- 確認服務器正在運行
- 檢查 URL 是否正確（必須是公開 URL）
- 檢查防火牆設置

### 問題：清洗無效

**解決方案**：
- 檢查 `app/tts_rules.json` 是否包含正確的規則
- 查看服務器日誌確認工具是否被調用
- 測試工具是否正常工作

## 進階配置

### 添加更多發音規則

編輯 `app/tts_rules.json`：

```json
{
  "phrase_replace": {
    "入行": "踏進這一行",
    "重來": "再來一次",
    "你的新規則": "替換詞"
  }
}
```

### 自定義 MCP 服務器端口

設置環境變數：

```bash
export MCP_SERVER_PORT=8002
python mcp_server_tts_cleaner.py
```

## 相關文件

- `mcp_server_tts_cleaner.py` - MCP 服務器實現
- `app/services/tts_cleaner.py` - TTS 清洗邏輯
- `app/services/pronunciation_fix.py` - 發音修正模組
- `app/tts_rules.json` - 發音修正規則配置
