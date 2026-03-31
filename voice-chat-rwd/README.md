# 江彬 - 雙向語音對話系統 (App版)

本專案已升級為 **PWA (Progressive Web App)**，並在桌面瀏覽器中增加了 **Android 仿真外框**。

## 📱 新增功能：App 化與仿真介面

### 1. Android 手機外框 (Desktop Mode)
當您在電腦瀏覽器打開網頁時，介面會自動顯示在一個仿真的 Android 手機外框中，包含：
- **實感邊框**：帶有圓角的深色機身。
- **動態島/瀏海**：模擬前置鏡頭區域。
- **仿真狀態列**：實時顯示當前時間、WiFi、訊號與電池圖示。
- **手勢條**：底部的 Home Indicator。
> **注意**：當您在手機上瀏覽時，外框會自動消失，自動滿版呈現以符合真實手機體驗。

### 2. PWA 安裝支援
您可以將此網頁安裝為獨立應用程式 (App)：
- **電腦 (Chrome/Edge)**：點擊網址列右側的「安裝」圖示，即可將其變為桌面 App。
- **手機 (Android/iOS)**：
  1. 使用 Chrome (Android) 或 Safari (iOS) 打開網頁。
  2. 選擇「分享」或選單中的「加到主畫面 (Add to Home Screen)」。
  3. 即可在桌面看到金色的「江」字 Icon，點擊後會以全螢幕 App 模式啟動 (無網址列)。

## 🚀 啟動方式 (不變)

1. **設定環境變數** (`.env`)
   ```bash
   OPENAI_API_KEY=sk-your-api-key-here
   ```

2. **安裝與啟動**
   ```bash
   pnpm install
   pnpm start
   ```

3. **瀏覽**
   前往 `http://localhost:3000` 即可體驗 App 化介面。
