# 開場語只聽到最後6個字的問題診斷與解決

## 問題描述

馬雲的開場語是「我是馬雲。我聽得見，你說吧!」，但只能聽到最後6個字「我聽得見，你說吧!」。

## 可能原因分析

### 1. **Interruptible 設置（最可能）**

從 ElevenLabs Agent 設置界面可以看到，**Interruptible 開關是開啟的**。

**問題**：
- 如果用戶在 Agent 開始說話後立即說話（或發出聲音）
- ElevenLabs Agent 會檢測到用戶輸入
- 觸發 `interruption` 事件，切斷當前播放的音頻
- 導致只聽到後半部分

**解決方案**：
1. 在 ElevenLabs Agent 設置中，將 **Interruptible** 設置為 **關閉（OFF）**
2. 這樣 Agent 的開場語會完整播放，不會被打斷

### 2. **音頻隊列處理時機問題**

**問題**：
- 第一個音頻 chunk 可能在 AudioContext 還沒完全準備好時就開始播放
- 導致第一個 chunk 播放失敗或被跳過

**已修復**：
- 在接收音頻事件時，確保 AudioContext 已經 resume
- 添加了第一個音頻 chunk 的特殊標記和日誌

### 3. **自動撥號干擾**

**問題**：
- 如果使用 `autodial=1`，撥號聲可能會干擾第一個音頻 chunk

**解決方案**：
- 確保撥號聲完全結束後再開始對話
- 或者在 Call 頁面添加延遲，確保音頻系統完全準備好

## 診斷步驟

### 步驟 1：檢查 Interruptible 設置

1. 進入 ElevenLabs Agent 設置頁面
2. 找到 **"First message"** 設置區域
3. 檢查 **"Interruptible"** 開關狀態
4. 如果開啟，**關閉它**

### 步驟 2：檢查瀏覽器控制台

打開瀏覽器開發者工具（F12），查看 Console 日誌：

1. 查找 `🎯 First audio chunk received!` 日誌
   - 確認第一個音頻 chunk 是否被正確接收
2. 查找 `🔊 Audio event received` 日誌
   - 確認所有音頻 chunk 是否都被接收
3. 查找 `interruption` 相關日誌
   - 確認是否有 interruption 事件被觸發

### 步驟 3：測試不同場景

1. **測試 1：完全靜音**
   - 打開 Call 頁面後，完全不要說話
   - 等待馬雲說完開場語
   - 檢查是否能聽到完整的開場語

2. **測試 2：檢查麥克風輸入**
   - 打開 Call 頁面後，觀察黃色波形（用戶輸入）
   - 如果黃色波形有活動，說明有聲音輸入
   - 這可能觸發 interruption

## 解決方案

### 方案 1：關閉 Interruptible（推薦）

**在 ElevenLabs Agent 設置中**：
1. 找到 **"First message"** 區域
2. 將 **"Interruptible"** 開關設置為 **關閉（OFF）**
3. 保存設置
4. 重新測試

### 方案 2：修改開場語

如果關閉 Interruptible 後仍有問題，可以嘗試：
1. 將開場語改為更簡短：「我是馬雲，你說吧！」
2. 或者分兩段：「我是馬雲。」（停頓）「我聽得見，你說吧！」

### 方案 3：前端延遲處理（如果問題持續）

如果以上方案都無效，可以在前端添加延遲：

```typescript
// 在 startConversation 中，確保 AudioContext 完全準備好
const ctx = ensureAudioContext();
if (ctx && ctx.state === 'suspended') {
  await ctx.resume();
}
// 等待一小段時間，確保音頻系統完全初始化
await new Promise(resolve => setTimeout(resolve, 500));
```

## 代碼修復

已添加以下改進：

1. **確保 AudioContext 準備好**：
   - 在接收音頻事件時，檢查 AudioContext 狀態
   - 如果 suspended，立即 resume

2. **第一個音頻 chunk 特殊處理**：
   - 添加日誌標記第一個音頻 chunk
   - 確保第一個 chunk 不會被跳過

## 測試建議

1. **關閉 Interruptible 後測試**：
   - 打開 Call 頁面
   - 完全不要說話或發出聲音
   - 等待馬雲說完開場語
   - 檢查是否能聽到完整的「我是馬雲。我聽得見，你說吧!」

2. **檢查瀏覽器控制台**：
   - 查看是否有 `interruption` 相關日誌
   - 查看第一個音頻 chunk 的處理日誌

3. **檢查音頻隊列**：
   - 查看 `🔊 Audio event received` 日誌
   - 確認所有音頻 chunk 都被正確接收和播放

## 相關文件

- `voice-chat-rwd/src/hooks/useElevenLabsConvAI.ts` - 音頻處理邏輯
- `voice-chat-rwd/src/pages/Call.tsx` - Call 頁面組件
