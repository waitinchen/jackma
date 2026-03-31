# ElevenLabs MCP 設置完整教學

> **⚠️ MCP 尚未準備好，請勿關聯。**  
> 此文件僅供日後參考，目前請勿將 TTS Cleaner MCP 連接到 ElevenLabs Agent。

---

## 📋 前置準備

在開始之前，你需要：
1. ✅ MCP 服務器代碼（`mcp_server_tts_cleaner.py`）
2. ✅ Python 環境（已安裝 FastAPI、uvicorn）
3. ✅ ngrok（用於本地測試，獲取公開 URL）

---

## 🚀 步驟 1：啟動 MCP 服務器

### 1.1 打開終端，進入項目目錄

```bash
cd C:\Users\waiti\jiangbin
```

### 1.2 啟動 MCP 服務器

```bash
python mcp_server_tts_cleaner.py
```

你應該會看到：
```
🚀 Starting TTS Cleaner MCP Server on 0.0.0.0:8001
📋 Available tools:
  - clean_tts_text: 清洗文本以優化 TTS 發音
  - get_pronunciation_rules: 獲取所有發音修正規則

🌐 Server URL: http://0.0.0.0:8001
🔗 MCP Endpoint: http://0.0.0.0:8001/mcp/v1/tools/call
```

**保持這個終端窗口打開！**

---

## 🌐 步驟 2：獲取公開 URL（使用 ngrok）

因為 ElevenLabs 無法訪問 `localhost`，我們需要使用 ngrok 創建一個公開的 URL。

### 2.1 安裝 ngrok（如果還沒安裝）

1. 訪問 https://ngrok.com/download
2. 下載 Windows 版本
3. 解壓縮到任意目錄（例如 `C:\ngrok`）
4. 將 `ngrok.exe` 添加到系統 PATH，或記住完整路徑

### 2.2 啟動 ngrok

**打開新的終端窗口**（保持 MCP 服務器運行），執行：

```bash
ngrok http 8001
```

或者如果 ngrok 不在 PATH 中：
```bash
C:\ngrok\ngrok.exe http 8001
```

### 2.3 複製公開 URL

ngrok 會顯示類似這樣的輸出：
```
Forwarding   https://abc123.ngrok-free.app -> http://localhost:8001
```

**複製 `https://abc123.ngrok-free.app` 這個 URL**（你的 URL 會不同）

**重要**：ngrok 的免費版本每次重啟 URL 都會改變。如果需要固定 URL，需要付費版本。

---

## ⚙️ 步驟 3：在 ElevenLabs 中添加 MCP 服務器

### 3.1 打開 MCP 集成頁面

1. 訪問 https://elevenlabs.io/app/agents/integrations
2. 點擊 **"Add Custom MCP Server"** 按鈕

### 3.2 填寫基本信息

在 **"Basic Information"** 區域：

- **Name**: `TTS Cleaner`
- **Description**: `清洗文本以優化 TTS 發音，修正多音字發音錯誤（如「這一行」→「這個行業」）`

### 3.3 配置服務器連接

在 **"Server Configuration"** 區域：

1. **Server type**: 選擇 **"SSE"**（已默認選中）

2. **Server URL**:
   - **Type**: 選擇 **"Value"**（下拉菜單）
   - **URL**: 貼上你從 ngrok 複製的 URL
     ```
     https://abc123.ngrok-free.app
     ```
     **注意**：不需要添加 `/mcp/v1/tools/call` 等路徑，只需要基礎 URL

### 3.4 配置安全設置（可選）

在 **"Secret Token"** 區域：
- **Secret**: 留空（除非你的服務器需要認證）

在 **"HTTP Headers"** 區域：
- 點擊 **"Add header"**（如果需要）
- 通常不需要額外的 headers

### 3.5 確認並添加

1. ✅ 勾選 **"I trust this server"** 複選框
   - 這表示你信任這個自定義服務器
   - ElevenLabs 不會驗證自定義服務器

2. 點擊 **"Add Server"** 按鈕

### 3.6 測試連接

ElevenLabs 會自動測試連接並列出可用的工具。你應該看到：
- ✅ `clean_tts_text` - 清洗文本以優化 TTS 發音
- ✅ `get_pronunciation_rules` - 獲取所有發音修正規則

如果看到這些工具，說明連接成功！

---

## 🛠️ 步驟 4：配置工具設置

### 4.1 進入工具設置頁面

在 MCP 服務器添加成功後，點擊服務器名稱進入設置頁面。

### 4.2 配置工具批准模式

在 **"Tool Approval Mode"** 區域：

**推薦設置**：選擇 **"Fine-Grained Tool Approval"**

然後為每個工具設置：
- **`clean_tts_text`**: 設置為 **"Auto-approved"**（自動批准）
  - 這樣 Agent 可以自動調用，無需每次手動批准
- **`get_pronunciation_rules`**: 可以設置為 **"Disabled"**（禁用）
  - 這個工具主要用於查詢，Agent 通常不需要

### 4.3 配置執行模式

在 **"Tool Settings"** 區域：

- **Force Pre-tool Speech**: ❌ 不勾選
- **Disable Interruptions**: ❌ 不勾選
- **Execution mode**: 選擇 **"Immediate"**
  - 這確保工具在 Agent 生成文本後立即執行

### 4.4 保存設置

點擊 **"Save"** 或 **"Update"** 按鈕保存設置。

---

## 🤖 步驟 5：將 MCP 服務器添加到 Agent

### 5.1 進入 Agent 配置頁面

1. 訪問你的 Agent 頁面：
   ```
   https://elevenlabs.io/app/agents/agents/agent_0901kernamncf0kr8spv0xw0380t
   ```

2. 點擊 **"Tools"** 標籤

### 5.2 添加 MCP 服務器

1. 在工具列表中，找到 **"TTS Cleaner"** MCP 服務器
2. 點擊 **"Add"** 按鈕
3. 確認服務器已添加到 Agent

---

## 📝 步驟 6：更新 Agent System Prompt

### 6.1 進入 System Prompt 編輯頁面

1. 在 Agent 配置頁面，點擊 **"Behavior"** 或 **"System Prompt"** 標籤
2. 找到 System Prompt 編輯框

### 6.2 添加文本處理規則

在 System Prompt 的**末尾**添加以下內容：

```
### 文本處理規則（必須遵守）：
在生成任何回應之後，可視需要調用 clean_tts_text 工具清洗文本以優化 TTS 發音（例如「重來」→「再來一次」等）。

**重要**：僅指示「可調用」工具，勿要求 Agent **說出**「clean」「clean_tts_text」或「清洗」等字；否則可能出現「一直說 clean TEST」等詭異開場。
```

### 6.3 保存 System Prompt

點擊 **"Save"** 按鈕保存更改。

---

## ✅ 步驟 7：測試 MCP 功能

### 7.1 測試 MCP 服務器（本地）

在終端中測試：

```bash
# 測試健康檢查
curl http://localhost:8001/health

# 測試工具列表
curl -X POST http://localhost:8001/mcp/v1/tools/list

# 測試文本清洗
curl -X POST http://localhost:8001/mcp/v1/tools/call ^
  -H "Content-Type: application/json" ^
  -d "{\"name\": \"clean_tts_text\", \"arguments\": {\"text\": \"我進了這一行已經十年了，曾經是影帝\"}}"
```

預期輸出應該顯示清洗後的文本：
```json
{
  "isError": false,
  "content": [{
    "type": "text",
    "text": "{\n  \"original\": \"我進了這一行已經十年了，曾經是影帝\",\n  \"cleaned\": \"我進了這個行業已經十年了，曾經是最佳男主角\",\n  \"changed\": true\n}"
  }]
}
```

### 7.2 測試 Agent 集成

1. 在 Call 頁面進行對話
2. 觀察 Agent 是否調用 `clean_tts_text` 工具
3. 檢查發音是否改善

**注意**：Agent 可能不會每次都調用工具。如果發現工具沒有被調用，可能需要：
- 加強 System Prompt 中的指示
- 檢查工具批准設置是否正確
- 查看 Agent 的日誌確認是否有錯誤

---

## 🔧 故障排除

### 問題 1：連接失敗

**症狀**：ElevenLabs 無法連接到 MCP 服務器

**解決方案**：
1. ✅ 確認 MCP 服務器正在運行（端口 8001）
2. ✅ 確認 ngrok 正在運行並轉發到 8001
3. ✅ 檢查 ngrok URL 是否正確（複製完整的 HTTPS URL）
4. ✅ 確認防火牆沒有阻擋連接

### 問題 2：工具列表為空

**症狀**：連接成功但看不到工具

**解決方案**：
1. ✅ 檢查 MCP 服務器的 `/mcp/v1/tools/list` 端點是否正常
2. ✅ 查看服務器日誌確認是否有錯誤
3. ✅ 確認服務器 URL 格式正確（只需要基礎 URL，不需要路徑）

### 問題 3：Agent 不調用工具

**症狀**：工具已添加，但 Agent 從不調用

**解決方案**：
1. ✅ 確認工具批准模式設置為 "Auto-approved"
2. ✅ 加強 System Prompt 中的指示
3. ✅ 在 System Prompt 中明確說明「必須調用」
4. ✅ 測試時明確提到易錯詞彙（如「這一行」「影帝」）

### 問題 4：ngrok URL 過期

**症狀**：連接突然失敗

**解決方案**：
1. ✅ ngrok 免費版本每次重啟 URL 都會改變
2. ✅ 需要重新複製新的 URL 並更新 ElevenLabs 設置
3. ✅ 考慮使用 ngrok 付費版本獲取固定 URL
4. ✅ 或部署到 Railway/Render 獲取永久 URL

---

## 📚 進階配置

### 部署到 Railway（獲取永久 URL）

1. 創建 `railway.json` 配置文件
2. 將 MCP 服務器部署到 Railway
3. 獲取永久 URL（如 `https://your-app.railway.app`）
4. 在 ElevenLabs 中使用這個 URL

### 添加認證

如果需要保護 MCP 服務器：

1. 在服務器代碼中添加認證邏輯
2. 在 ElevenLabs 的 "Secret Token" 中設置令牌
3. 服務器驗證令牌後才處理請求

---

## 📞 需要幫助？

如果遇到問題：
1. 檢查服務器日誌（終端輸出）
2. 檢查 ngrok 日誌
3. 查看 ElevenLabs Agent 的執行日誌
4. 確認所有步驟都已正確完成

---

**最後更新**：2026-01-26
