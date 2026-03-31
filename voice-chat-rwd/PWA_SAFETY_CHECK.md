# PWA 更改安全檢查清單

## ✅ 已確認：不會影響現有功能

### 1. **API 請求不受影響**
- ✅ Workbox 緩存策略**只針對 ElevenLabs API** (`api.elevenlabs.io`)
- ✅ 後端 API (`/api/turn`, `/api/chat_text`, `/api/elevenlabs/token` 等) **不會被緩存**
- ✅ 所有 API 請求仍然正常發送到後端服務器

### 2. **路由不受影響**
- ✅ 沒有修改任何路由邏輯 (`wouter` 路由)
- ✅ `/#/call` 和 `/#/` 路由正常工作
- ✅ Manifest 中的 `start_url: '/'` 和 `scope: '/'` 與現有路由兼容

### 3. **業務邏輯不受影響**
- ✅ 沒有修改任何業務邏輯代碼
- ✅ 語音錄製、文字對話、即時通話功能完全不受影響
- ✅ 狀態管理 (`useState`, `useRef`) 沒有改變

### 4. **PWAInstallPrompt 組件是純 UI**
- ✅ 組件只在條件滿足時顯示（可安裝且未安裝）
- ✅ 如果不可安裝或已安裝，直接返回 `null`，不渲染任何內容
- ✅ 不影響任何現有 UI 元素或功能按鈕
- ✅ 使用 `z-50` 和 `fixed bottom-4`，不會遮擋主要功能

### 5. **Service Worker 行為**
- ✅ `registerType: 'autoUpdate'` 會自動更新，不會導致舊版本問題
- ✅ Service Worker 只處理靜態資源（JS、CSS、HTML、圖片）
- ✅ 不會攔截或修改 API 請求

## ⚠️ 需要注意的事項

### 1. **Service Worker 註冊**
- Service Worker 會在首次訪問時自動註冊
- 如果遇到問題，用戶可以在瀏覽器設置中清除 Service Worker

### 2. **緩存策略**
- ElevenLabs API 請求會使用 `NetworkFirst` 策略（優先使用網絡，失敗時使用緩存）
- 這對 ElevenLabs API 是安全的，因為它只是外部 API

### 3. **PWA 安裝提示**
- 提示會在 3 秒後顯示（避免立即打擾）
- 用戶關閉後，24 小時內不會再次顯示
- 如果用戶不想看到，可以點擊關閉按鈕

## 🔍 測試建議

### 基本功能測試
1. ✅ 語音錄製功能（主頁）
2. ✅ 文字對話功能（主頁）
3. ✅ 即時通話功能（CALL 頁）
4. ✅ API 請求是否正常（檢查 Network 面板）

### PWA 功能測試
1. ✅ Service Worker 是否正確註冊（Application > Service Workers）
2. ✅ Manifest 是否正確加載（Application > Manifest）
3. ✅ 安裝提示是否正確顯示（3 秒後）
4. ✅ 安裝後應用是否正常運行

## 📝 回滾方案

如果遇到問題，可以通過以下方式回滾：

1. **移除 PWA 組件**（最簡單）：
   - 從 `Home.tsx` 和 `Call.tsx` 中移除 `<PWAInstallPrompt />`
   - 保留其他 PWA 配置（不會影響功能）

2. **禁用 Service Worker**：
   - 在 `vite.config.ts` 中將 `registerType` 改為 `'prompt'` 或移除 PWA 插件
   - 需要重新構建

3. **清除 Service Worker**：
   - 用戶可以在瀏覽器設置中清除 Service Worker
   - 開發者工具 > Application > Service Workers > Unregister

## ✅ 結論

**PWA 更改是安全的，不會破壞現有功能。**

所有更改都是**附加功能**，不影響核心業務邏輯。如果遇到任何問題，可以隨時移除 PWA 組件而不影響其他功能。
