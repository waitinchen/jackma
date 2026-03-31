# 本地測試指南

## 🚀 快速啟動

### 方式一：使用後端服務器（推薦）

後端會自動服務前端靜態文件，這是**最簡單的方式**：

#### 1. 啟動後端服務器

```bash
# 在項目根目錄
cd C:\Users\waiti\jackma

# 啟動 FastAPI 後端（會自動服務前端）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 2. 訪問網址

**主頁（語音錄製模式）**：
```
http://localhost:8000/
```

**即時通話頁面**：
```
http://localhost:8000/#/call
```

**自動撥號模式**：
```
http://localhost:8000/?autodial=1#/call
```

---

### 方式二：前端開發模式（熱重載）

如果需要修改前端代碼並實時看到效果：

#### 1. 啟動後端 API（終端 1）

```bash
cd C:\Users\waiti\jackma
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 2. 啟動前端開發服務器（終端 2）

```bash
cd C:\Users\waiti\jackma\voice-chat-rwd
npm run dev
```

前端會自動啟動在 `http://localhost:5173`（Vite 默認端口）

#### 3. 訪問網址

**主頁**：
```
http://localhost:5173/
```

**即時通話頁面**：
```
http://localhost:5173/#/call
```

**注意**：前端會自動連接到 `http://localhost:8000` 的後端 API（因為檢測到 localhost）

---

## 📋 測試網址列表

### 後端服務器模式（端口 8000）

| 頁面 | 網址 |
|------|------|
| 主頁 | `http://localhost:8000/` |
| 即時通話 | `http://localhost:8000/#/call` |
| 自動撥號 | `http://localhost:8000/?autodial=1#/call` |
| 健康檢查 | `http://localhost:8000/api/health` |

### 前端開發模式（端口 5173）

| 頁面 | 網址 |
|------|------|
| 主頁 | `http://localhost:5173/` |
| 即時通話 | `http://localhost:5173/#/call` |
| 自動撥號 | `http://localhost:5173/?autodial=1#/call` |

---

## 🔧 環境變數設置

確保 `.env` 文件包含必要的 API 密鑰：

```env
OPENAI_API_KEY=sk-your-key-here
ELEVENLABS_API_KEY=your-elevenlabs-key
ELEVENLABS_AGENT_ID=your-agent-id
ELEVENLABS_VOICE_ID=your-voice-id
```

---

## ✅ 測試檢查清單

### 基本功能測試

- [ ] 主頁可以正常打開
- [ ] 語音錄製按鈕可以點擊
- [ ] 文字對話功能正常
- [ ] 即時通話頁面可以打開
- [ ] 自動撥號功能正常

### PWA 功能測試

- [ ] Service Worker 已註冊（檢查瀏覽器開發者工具 > Application > Service Workers）
- [ ] Manifest 文件可以訪問（`http://localhost:8000/manifest.webmanifest`）
- [ ] PWA 安裝提示出現（3 秒後）
- [ ] 圖標文件可以訪問（`http://localhost:8000/pwa-192x192.png`）

### 音頻功能測試

- [ ] 麥克風權限請求正常
- [ ] 語音錄製波形顯示正常
- [ ] 音頻發送無錯誤
- [ ] 馬雲回覆音頻播放正常
- [ ] 即時通話雙向音頻正常

---

## 🐛 常見問題

### 問題 1：端口被占用

**解決方案**：
```bash
# Windows 查看端口占用
netstat -ano | findstr :8000

# 或者使用其他端口
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

### 問題 2：前端無法連接後端

**檢查**：
1. 確認後端服務器正在運行
2. 檢查 `http://localhost:8000/api/health` 是否返回 `{"status": "ok"}`
3. 檢查瀏覽器控制台是否有 CORS 錯誤

### 問題 3：PWA 功能不工作

**檢查**：
1. 確認使用 HTTPS 或 localhost（PWA 需要）
2. 檢查 Service Worker 是否註冊成功
3. 清除瀏覽器緩存並重新載入

---

## 📝 測試建議

1. **先測試基本功能**：確保語音和文字對話都正常
2. **測試 PWA 安裝**：在 Chrome/Edge 中測試安裝流程
3. **測試音頻穩定性**：長時間對話（5-10 分鐘）檢查是否有聲音變形
4. **測試不同瀏覽器**：Chrome、Edge、Firefox、Safari

---

**最後更新**：2026-01-26
