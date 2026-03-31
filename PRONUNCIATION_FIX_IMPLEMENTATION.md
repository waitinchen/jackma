# ElevenLabs Agents TTS 發音優化實作摘要

## 實作完成時間
2026-01-26

## 已完成項目

### ✅ 1. TTS 清洗規則 (`app/tts_rules.json`)
- 當前規則：`"入行": "踏進這一行"`, `"重來": "再來一次"`

### ✅ 2. LLM System Prompt (`app/services/llm.py`)
- 馬雲執導電影為《玩命》；若用戶問執導什麼電影，回答「《玩命》」

### ✅ 3. 創建發音修正模組 (`app/services/pronunciation_fix.py`)
- 實現了完整的發音修正字典 (`PRONUNCIATION_FIX_DICT`)
- 提供兩種替換策略：
  - `semantic`: 改字不改意（如「影帝」→「最佳男主角」）
  - `phonetic`: 同音字替換（預留接口）
- 實現了以下功能：
  - `fix_pronunciation()`: 自動檢測並替換易錯詞彙
  - `get_replacement()`: 獲取單個詞的替換
  - `detect_problematic_chars()`: 檢測問題單字
  - `get_all_rules()`: 獲取所有規則（用於顯示）

### ✅ 4. 更新 TTS 清洗邏輯 (`app/services/tts_cleaner.py`)
- 增強了 `clean_for_tts()` 函數：
  - 按長度排序替換規則，避免部分匹配問題
  - 整合 `pronunciation_fix` 模組作為額外修正層
  - 添加 `use_pronunciation_fix` 參數（預設為 `True`）以向後兼容

### ✅ 5. 測試驗證 (`test_pronunciation_fix.py`)
- 測試腳本驗證目前規則（如「重來」→「再來一次」）

## 影響範圍

### 後端 TTS API (`/api/turn`, `/api/chat_text`)
- ✅ 自動應用發音修正規則
- ✅ LLM 生成的回應會自動避免易錯詞彙

### ElevenLabs Agents
- ✅ LLM System Prompt 的用詞替換規則會影響發送到 Agents 的文本
- ⚠️ 注意：Agents 直接生成語音，不經過後端 TTS 清洗層，主要依賴 LLM 層面的替換

## 測試建議

### 1. LLM 用詞替換測試（pron-5）
**方法**：
- 啟動後端服務
- 通過 `/api/chat_text` 或 `/api/turn` 發送包含易錯詞的對話
- 檢查 LLM 回應是否自動使用同義詞替換

**測試用例**：
```
用戶: "你執導過什麼電影？"
預期: LLM 回應中說「《玩命》」
```

### 2. ElevenLabs Agents 發音測試
**方法**：
- 在 Call 頁面進行實際語音對話
- 觀察 Agent 語音輸出；提及執導電影時應為「玩命」

**注意事項**：
- Agents 的 System Prompt 可能需要手動更新（在 ElevenLabs 控制台）
- 如果 LLM 層面的替換不夠，可能需要進一步調整 System Prompt

## 後續優化建議

1. **收集更多發音錯誤案例**：持續監控實際對話中的發音問題
2. **擴展發音修正字典**：根據實際使用情況添加更多規則
3. **考慮智能同義詞替換**：使用 LLM 進行更自然的同義詞替換
4. **ElevenLabs API 更新**：如果 ElevenLabs 提供發音控制 API，優先使用

## 文件結構

```
app/
├── tts_rules.json                    # TTS 清洗規則配置
├── services/
│   ├── llm.py                        # LLM System Prompt（已更新）
│   ├── tts_cleaner.py                # TTS 清洗邏輯（已增強）
│   └── pronunciation_fix.py          # 發音修正模組（新建）
test_pronunciation_fix.py             # 測試腳本（新建）
```

## 注意事項

1. **向後兼容**：所有更改都保持向後兼容，不會破壞現有功能
2. **LLM 配合度**：LLM 可能不完全遵循替換規則，需要實際測試和調整
3. **語意影響**：替換可能略微改變表達方式，但已選擇最接近原意的同義詞
4. **Agents 限制**：ElevenLabs Agents 直接生成語音，主要依賴 LLM 層面的替換
