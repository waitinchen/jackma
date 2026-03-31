# PWA 手機端說明與修復紀錄

## 為何手機端沒有生效？

### 1. **Service Worker 無法載入（後端 Workbox 路徑錯誤）**

- **現象**：SW 註冊失敗，PWA 離線/快取失效，部分環境下「加入主畫面」也不穩定。
- **原因**：`sw.js` 會載入 `workbox-<hash>.js`，檔名隨每次 build 變動（如 `workbox-b51dd497.js`），後端卻固定提供 `workbox-8c29f6e4.js`，導致 404。
- **修復**：`app/main.py` 改為依 `web_static/workbox-*.js` 動態註冊路由，每次部署後自動對應實際檔名。

### 2. **iOS Safari：安裝提示從來不出現**

- **現象**：在 iPhone/iPad 上沒有「安裝到主畫面」的提示。
- **原因**：iOS Safari **不支援** `beforeinstallprompt`。安裝 PWA 僅能透過 **Safari → 分享 → 加入主畫面** 手動操作，無法像 Android 一樣由網頁觸發安裝流程。
- **修復**：`PWAInstallPrompt` 偵測 iOS 時，改顯示**教學式橫幅**：「Safari → 分享 → 加入主畫面」，不再依賴 `beforeinstallprompt`。

### 3. **已加入主畫面仍顯示安裝提示（iOS）**

- **現象**：從主畫面開啟 App 後，依舊出現「加入主畫面」提示。
- **原因**：僅用 `(display-mode: standalone)` 判斷，iOS 從主畫面開啟時可能無法完全反映；需一併檢查 `navigator.standalone`。
- **修復**：`checkInstalled()` 同時檢查 `display-mode: standalone` 與 `navigator.standalone`，通過任一時視為已安裝，不再顯示提示。

## 手機端使用方式

| 平台 | 安裝方式 | 說明 |
|------|----------|------|
| **Android** | 瀏覽器出現「安裝」按鈕時點擊，或選單「新增至主畫面」 | 支援 `beforeinstallprompt`，可顯示一鍵安裝提示 |
| **iOS** | **Safari** 開啟網址 → **分享** → **加入主畫面** | 必須用 Safari；Chrome/Firefox 等無法「加入主畫面」 |

## 必要條件

- **HTTPS**：PWA 與 Service Worker 僅在 HTTPS（或 localhost）下有效，手機請以 HTTPS 網址存取。
- **iOS**：僅 Safari 支援「加入主畫面」；請勿在 Chrome/Firefox iOS 版期待相同行為。

## 仿 app 狀態（加入主畫面後）

**加入主畫面**後以 PWA 開啟時，會切換為「仿 app」模式：

- **鎖住瀏覽器原生上下滑動**：`html` / `body` 設 `overflow: hidden`、`overscroll-behavior: none`、`touch-action: none`，不再觸發下拉重整、橡皮筋等。
- **僅對話歷史可上下滑動**：首頁（Home）的聊天區 `main` 加上 `pwa-scrollable`，`touch-action: pan-y`、`-webkit-overflow-scrolling: touch`、`overscroll-behavior-y: contain`，只有該區可捲動查看歷史。
- **Call 頁**：整頁固定視窗高度（`h-dvh`）、`overflow-hidden`，不捲動。
- **DeviceFrame**：standalone 時外層 `h-dvh overflow-hidden`，避免整體頁面產生捲動。

偵測方式：`display-mode: standalone` 或 `navigator.standalone`（iOS）。  
相關樣式與邏輯：`index.css`（`.pwa-standalone`、`.pwa-scrollable`）、`useStandalone`、`PWAStandaloneLock`、`DeviceFrame`、`Home`、`Call`。

## 相關檔案

- `app/main.py`：Workbox 動態路由、manifest / SW / 圖示等 PWA 靜態資源。
- `voice-chat-rwd/src/components/PWAInstallPrompt.tsx`：安裝提示與 iOS 教學橫幅。
- `voice-chat-rwd/src/components/PWAStandaloneLock.tsx`：standalone 時在 `<html>` 加上 `pwa-standalone`。
- `voice-chat-rwd/src/hooks/useStandalone.ts`：偵測是否為 PWA standalone。
- `voice-chat-rwd/src/index.css`：`.pwa-standalone`、`.pwa-scrollable` 樣式。
- `voice-chat-rwd/vite.config.ts`：`vite-plugin-pwa`、manifest、workbox 設定。
