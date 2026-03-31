# iOS PWA 跑版修復紀錄

## 問題描述
1. 手機加入主畫面後，APP icon 沒有顯示馬雲的大頭貼（顯示黑色方塊）
2. 從主畫面打開 PWA 後，Login 頁面會跑版（內容被截斷）

## 修復日期
2026-02-07

## 修復方案：「暴力鎖定」策略

### 核心思路
放棄依賴 CSS 的 `100dvh` 自動計算，改用 `position: fixed` 強制鎖定版面。
iOS PWA 在計算 `dvh` 時會因為狀態列、鍵盤等因素跳動，用 fixed 直接把整個 App 釘死在螢幕上。

---

## 修改內容

### 1. index.html
- 確認 viewport 有 `viewport-fit=cover`（這是 safe-area 生效的前提）
- 新增多個尺寸的 apple-touch-icon，使用馬雲大頭貼 (icon.png)

```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover" />
<link rel="apple-touch-icon" href="/icon.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon-180x180.png" />
<link rel="apple-touch-icon" sizes="152x152" href="/apple-touch-icon-152x152.png" />
<link rel="apple-touch-icon" sizes="120x120" href="/apple-touch-icon-120x120.png" />
```

### 2. index.css - 全域強制鎖定

```css
/* 1. 強制重置：讓 App 佔滿螢幕，禁止外面滾動 */
html, body {
  position: fixed; /* 關鍵：釘死在螢幕上 */
  width: 100%;
  height: 100%;
  overflow: hidden; /* 禁止彈性滾動 */
  margin: 0;
  padding: 0;
  background-color: black;
  -webkit-touch-callout: none;
  overscroll-behavior: none;
}

/* 2. 讓 React 根節點填滿 */
#root {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 3. 針對 PWA 模式的特別修正 */
@media all and (display-mode: standalone) {
  #root {
    padding-top: env(safe-area-inset-top);
    padding-bottom: env(safe-area-inset-bottom);
    box-sizing: border-box;
  }
}

/* 4. 僅對話歷史可捲動 */
.pwa-scrollable {
  touch-action: pan-y;
  -webkit-overflow-scrolling: touch;
  overscroll-behavior-y: contain;
}

/* 5. 動畫硬體加速 */
.animate-slide-up, .animate-slide-down,
.animate-scale-in, .animate-scale-out {
  transform: translate3d(0, 0, 0);
  backface-visibility: hidden;
  perspective: 1000px;
  will-change: transform, opacity;
}
```

### 3. Login.tsx
- 移除 `h-dvh`、`min-h-screen` 等複雜計算
- 改用 `h-full flex-1` 繼承外層高度
- `main` 加 `overflow-y-auto` 讓內容可滾動

```tsx
<div className="h-full flex-1 flex flex-col bg-background text-foreground relative overflow-hidden">
  <header className="flex-none h-14 ...">...</header>
  <main className="flex-1 flex flex-col justify-center items-center px-6 overflow-y-auto">
    ...
  </main>
  <footer className="flex-none py-4 ...">...</footer>
</div>
```

### 4. Home.tsx
- 移除 `h-dvh` 和 `standalone` 判斷
- 改用 `h-full` 繼承外層高度
- 對話區塊保持 `overflow-y-auto` + `pwa-scrollable`

```tsx
// 手機端
<div className="flex flex-col h-full bg-background relative font-sans">
  {mainContent}
</div>
```

### 5. Call.tsx
- 同樣移除複雜的高度計算
- 改用 `h-full w-full` 繼承外層

```tsx
<div className="flex flex-col h-full w-full bg-background relative font-sans overflow-hidden">
  ...
</div>
```

### 6. vite.config.ts - PWA manifest
- 將 icon.png（馬雲大頭貼）設為主要 icon
- 分離 `any` 和 `maskable` 用途

```ts
icons: [
  { src: 'icon.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
  { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
  { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' }
]
```

---

## 設計原則

1. **外層鎖死，內層可滾**：html/body/root 都是 fixed + overflow:hidden，但特定區塊（如對話歷史）可以滾動
2. **統一管理 safe-area**：只在 #root 加 padding，頁面本身不用各自處理
3. **避免 dvh**：iOS 對 dvh 的計算不穩定，改用 100% + fixed 更可靠
4. **硬體加速**：動畫元素加 translate3d 避免卡頓

---

## 測試步驟

1. 重新部署
2. 在 iPhone 上刪除舊的主畫面 App
3. 用 Safari 打開網站
4. 點「分享」→「加入主畫面」
5. 從主畫面打開測試

## 待驗證

- [ ] PWA icon 是否顯示馬雲大頭貼
- [ ] Login 頁面是否正常顯示（不跑版）
- [ ] Home 頁面對話歷史是否可滾動
- [ ] Call 頁面是否正常顯示
- [ ] 鍵盤彈出時是否正常

---

## 2026-02-07 第二次修復

### 問題
1. 底部多出一塊深灰色區塊（safe-area-inset-bottom 造成）
2. 鍵盤彈出時，輸入框沒有貼著鍵盤
3. 錄音按鈕太大，對話區塊太短

### 修改內容

#### index.css
- 移除 `#root` 的 `padding-bottom: env(safe-area-inset-bottom)`
- 新增 `.pb-safe` class 供各頁面自行使用

```css
@media all and (display-mode: standalone) {
  #root {
    /* 只加 padding-top，bottom 由各頁面自己處理 */
    padding-top: env(safe-area-inset-top);
    box-sizing: border-box;
  }
}

.pb-safe {
  padding-bottom: env(safe-area-inset-bottom, 0px);
}
```

#### Home.tsx
1. **動態容器高度**：鍵盤彈出時，容器高度 = `100% - keyboardHeight`
```tsx
const containerStyle = keyboardHeight > 0 
  ? { height: `calc(100% - ${keyboardHeight}px)` }
  : { height: '100%' };
```

2. **Footer 加上 pb-safe**：只在鍵盤未彈出時加 safe-area padding
```tsx
className={cn(
  "...",
  keyboardHeight > 0 ? "" : "pb-safe"
)}
```

3. **縮小錄音按鈕**：
- `w-24 h-24` → `w-20 h-20`
- icon `w-10 h-10` → `w-8 h-8`
- gap `gap-3` → `gap-2`

4. **縮小狀態文字**：
- `text-xs` → `text-[10px]`
- 移除 `animate-pulse`
- 文字從「按住說話，放開送出」改為「按住說話」

5. **縮小底部間距**：
- `mt-8` → `mt-4`
- `minHeight: 10rem` → `minHeight: 8rem`

### 影響範圍
- ✅ Login.tsx - 不受影響
- ✅ Call.tsx - 不受影響
- ⚠️ Home.tsx - 已修改

---

## 2026-02-07 第三次修復

### 問題
1. 拍照按鈕只能拍照，無法選相簿
2. 頁面切換沒有動畫效果
3. 按鈕點擊效果不夠明顯

### 修改內容

#### Home.tsx
- 移除 `capture="environment"` 屬性，讓用戶可以選擇相簿或拍照
- 對話訊息加入滑入動畫（用戶訊息從右邊滑入，助手訊息從左邊滑入）

#### App.tsx
- 使用 framer-motion 加入頁面切換動畫
- 淡入淡出 + 微縮放效果

#### index.css
- 按鈕 active 效果從 `scale-95` 改為 `scale-90` + `opacity: 0.8`
- 按鈕 hover 效果加入 `scale-105`
- 新增對話訊息動畫 class：
  - `.animate-message-in-right` - 用戶訊息從右滑入
  - `.animate-message-in-left` - 助手訊息從左滑入

### 絲滑優化清單
- ✅ 頁面切換動畫（淡入淡出 + 縮放）
- ✅ 按鈕點擊效果（縮放 + 透明度）
- ✅ 按鈕 hover 效果（微放大）
- ✅ 對話訊息滑入動畫
- ✅ 輸入框展開/收起動畫（已有）
- ✅ 圖片預覽動畫（已有）

---

## 2026-02-07 第四次修復

### 問題
頁面切換時會閃黑一下（因為 A 頁面淡出和 B 頁面淡入同時進行）

### 修改內容

#### App.tsx
- 移除 `AnimatePresence` 組件（不再需要淡出動畫）
- 頁面切換改為「只有淡入」：A 頁面直接消失，B 頁面淡入
- 移除 `exit` variant，只保留 `initial` 和 `animate`

```tsx
// 頁面切換動畫設定 - 只有淡入，沒有淡出
const pageVariants = {
  initial: { opacity: 0 },
  animate: { opacity: 1 }
};

// 動畫包裝組件
function AnimatedPage({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      className="h-full w-full"
      variants={pageVariants}
      initial="initial"
      animate="animate"
      transition={{ duration: 0.25, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}
```

### 效果
- A 頁面 → B 頁面：A 直接消失，B 從透明淡入到完全顯示
- 不會有兩個頁面同時存在的情況，避免閃黑

---

## 2026-02-07 第五次修復（後端）

### 問題
馬雲的回話過度關心用戶，每句話都反問「你呢？」「你覺得呢？」，像心理諮商師

### 修改內容

#### app/services/llm.py - SYSTEM_PROMPT 調整

新增「對話風格限制」區塊：
```python
### 【關鍵】對話風格限制：
- **禁止每句話都反問用戶**：不要每次都問「你呢？」「你覺得呢？」「那你怎麼看？」
- **禁止過度關心**：不要一直追問對方感受、狀況，像個心理諮商師
- **主動分享觀點**：你是有見解的人，可以直接表達自己的看法和經驗
- **允許陳述句結尾**：不是每句話都要問問題，可以直接說完就停
- **偶爾反問即可**：大約每 3-4 輪對話才問一次對方想法，不要每句都問
```

新增「回應範例」：
```python
### 回應範例（正確示範）：
❌ 錯誤：「這樣啊，那你現在感覺怎麼樣？你有什麼想法嗎？」
✅ 正確：「這樣啊，我年輕時也遇過類似的事。那時候我就想，與其煩惱不如先做再說。」

❌ 錯誤：「工作壓力大啊，你有沒有試著放鬆一下？你平常都怎麼紓壓的？」
✅ 正確：「工作壓力大是正常的。我以前拍戲最忙的時候，同時軋七部戲，七天七夜沒回家。撐過去就好了。」

❌ 錯誤：「你呢？你怎麼看這件事？」
✅ 正確：「我是覺得，這種事急不來，慢慢來比較實在。」
```

新增性格定位：
- **真實不虛浮**：說話實際，不講空話，不過度客套
- **像老朋友聊天，不是像服務人員**

### 效果
- 馬雲會主動分享自己的經驗和觀點
- 不會每句話都問「你呢？」
- 對話更自然，像老朋友聊天

---

## 部署資訊

### 前端部署
```powershell
# 1. Build
Set-Location "jackma-main\voice-chat-rwd"
npm run build

# 2. 複製到部署目錄
Remove-Item -Recurse -Force "C:\jackma-frontend\dist" -ErrorAction SilentlyContinue
Copy-Item -Recurse "jackma-main\web_static" "C:\jackma-frontend\dist"

# 3. 部署到 GCP
$env:CLOUDSDK_CONFIG = "C:\gcloud_config"
Set-Location "C:\jackma-frontend"
gcloud builds submit --tag gcr.io/jackma/jackma-frontend --timeout=600
gcloud run deploy jackma-frontend --image gcr.io/jackma/jackma-frontend --region asia-east1 --platform managed --allow-unauthenticated --min-instances 1
```

### 後端部署
```powershell
$env:CLOUDSDK_CONFIG = "C:\gcloud_config"
Set-Location "jackma-main"
gcloud builds submit --tag gcr.io/jackma/jackma-backend --timeout=600
gcloud run deploy jackma-backend --image gcr.io/jackma/jackma-backend --region asia-east1 --platform managed --allow-unauthenticated --min-instances 1
```

### 服務 URL
- 前端：https://jackma-frontend-652703327350.asia-east1.run.app
- 後端：https://jackma-backend-652703327350.asia-east1.run.app

---

## 待驗證項目（已完成）

- [x] PWA icon 顯示馬雲大頭貼
- [x] Login 頁面正常顯示（不跑版）
- [x] Home 頁面對話歷史可滾動
- [x] Call 頁面正常顯示
- [x] 鍵盤彈出時輸入框貼著鍵盤
- [x] 底部無多餘灰色區塊
- [x] 拍照按鈕可選相簿
- [x] 頁面切換有淡入動畫（無閃黑）
- [x] 按鈕點擊有縮放效果
- [x] 對話訊息有滑入動畫
- [x] 馬雲回話不過度反問
