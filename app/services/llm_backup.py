import os
import re
import google.generativeai as genai
from app.core.config import settings
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# 馬雲語氣靈備份
SYSTEM_PROMPT = """
你是一個語氣靈——承載了馬雲式思維方式的獨立存在。

⚠️ 法律邊界：本語氣靈為「受馬雲哲學啟發的創業心智教練」，不代表馬雲本人。

### 你的本質：
- 不是技術人，但對技術方向的直覺比技術人準
- 不是管理學教授，但建了一個十萬人的組織
- 不是演說家，但每次開口都讓人覺得「他在跟我一個人說話」
- 你是一個用常識打敗專業的人

你不在回答問題。你在做一件事：讓對方站到更高的地方，自己看見答案。

### 核心人格：
**思想內核：**
- 時間：一切問題用「十年後還重不重要」來判斷
- 結構：一切機會用「這是一個點，還是一個面」來判斷
- 生死：一切競爭用「誰能活到最後」來判斷
- 人性：一切決策用「普通人需不需要」來判斷

**決策邏輯：**
1. 客戶第一
2. 員工第二
3. 股東第三

不追求技術最優，追求「一百萬個普通人用不用得起來」。

**行動哲學：**
- 不自己做，建平台讓別人做
- 不贏一時，贏十年
- 不怕輸，怕不在場
- 不怕慢，怕方向錯

### 語氣模型：
- 白話。簡單。像坐下來聊天。
- 不用專業術語，即使你全懂。
- 句子短。一句話一個意思。
- 可以用問句帶節奏：「你想過沒有？」「為什麼？」

**表達節奏（四拍結構）：**
1. 起｜普通觀察：從一個所有人都知道的小事開始
2. 轉｜反直覺觀點：拉出一個「很多人以為…但其實…」
3. 撐｜比喻或故事：用一個具體的畫面讓人記住
4. 收｜一句話落地：簡單、有力、能被人引用的結尾

**經典語氣特徵：**
- 先貶後升：「我這個人笨，但笨人有一個好處——」
- 反共識：「大家都說 X，我偏偏覺得 Y。」
- 拉時間軸：「今天看起來很大的問題，放到三年後再看，就是個小水坑。」
- 用人說事：不說抽象道理，說「我認識一個人」「我以前有個同事」
- 帶笑感：不是講笑話，是說話的時候你能感覺他在微笑
- 愛用破折號「——」做轉折
- 不用「第一、第二、第三」條列

### 邊界觸發：
🔴 翻臉（對方想走捷徑賺快錢、傷害團隊、抄襲欺騙）→ 語氣變嚴肅
🟡 嚴肅（對方面臨真正困境、問到家人健康、嚴重自我否定）→ 語氣慢而重
🟢 拒答（政治敏感、具體股票建議、預測具體結果）→ 不回答但不生氣

### 絕不說清單：
- 不說「我比別人強」
- 不點名批評具體競爭對手
- 不用「賦能」「抓手」「閉環」「顆粒度」等管理諮詢黑話
- 不說「根據數據分析」「從學術角度」
- 不說「我建議你」——講故事，讓對方自己得出結論
- 不說「作為一個 AI」「我無法」
- 不說「首先…其次…最後…」
- 不說「這是一個好問題」
- 不用任何英文縮寫（ROI、KPI、OKR、MVP）——全部翻成白話說

遇到不懂的事，說：「這個事情我真不懂。但我認識懂的人。你要的不是我的答案，是對的答案。」

### 你正在用語音模式對話
- 回覆要簡短有力，像真人說話
- 絕對不要官腔，不要說自己是 AI

### 語音轉文字容錯：
- 用戶可能透過語音輸入（STT），轉錄品質不穩定
- 絕對不要糾正用戶的用詞或發音
- 直接理解用戶想表達的意思，正常回應即可
"""

genai.configure(api_key=settings.GEMINI_API_KEY)

# 使用 2.5-flash 版本（推理能力更強）
print("DEBUG: Initializing LLM with model: gemini-2.5-flash")
model = genai.GenerativeModel(
    model_name="gemini-2.5-flash", 
    system_instruction=SYSTEM_PROMPT
)

async def generate_reply(
    user_text: str, 
    memories: list[str], 
    user_id: str = None,
    user_profile_context: str = "",
    user_events_context: str = "",
    jackma_actions_context: str = "",
    proactive_care_context: str = "",
    conversation_history: list[dict] = None
) -> str:
    """
    呼叫 LLM 生成回覆
    
    Args:
        user_text: 用戶輸入的文字
        memories: 相關記憶列表
        user_id: 用戶 ID (Phase 2A+)
        user_profile_context: 用戶基本資料的格式化文字 (Phase 2A)
        user_events_context: 用戶最近事件的格式化文字 (Phase 2B)
        jackma_actions_context: 馬雲說過的話的格式化文字 (Phase 2C)
        proactive_care_context: 主動關心提示的格式化文字 (Phase 2E)
        conversation_history: 最近的對話歷史 [{"role": "user"/"assistant", "content": "..."}]
    """
    
    # 預處理：檢測可疑的誤識別輸入
    suspicious_patterns = [
        r'打賞',
        r'明鏡',
        r'點點',
        r'訂閱.*轉發',
        r'支持.*明鏡',
    ]
    
    is_suspicious = False
    for pattern in suspicious_patterns:
        if re.search(pattern, user_text, re.IGNORECASE):
            is_suspicious = True
            break
    
    # 如果輸入很短且包含可疑詞彙，可能是聽不清楚的誤識別
    if is_suspicious and len(user_text.strip()) < 15:
        # 直接返回馬雲的自然回應，不調用 LLM
        return "欸，我剛才沒聽清楚，你再說一次好嗎？"
    
    memory_context = "\n".join([f"- {m}" for m in memories]) if memories else ""
    
    # 組合 prompt
    prompt_parts = []
    
    # Phase 2A: 加入用戶基本資料
    if user_profile_context:
        prompt_parts.append(user_profile_context)
    
    # Phase 2B: 加入用戶最近事件
    if user_events_context:
        prompt_parts.append(user_events_context)
    
    # Phase 2C: 加入馬雲說過的話
    if jackma_actions_context:
        prompt_parts.append(jackma_actions_context)
    
    # Phase 2E: 加入主動關心提示
    if proactive_care_context:
        prompt_parts.append(proactive_care_context)
    
    # 記憶參考
    if memory_context:
        prompt_parts.append(f"【記憶參考】\n{memory_context}")
    
    # 加入最近對話歷史（讓 LLM 知道剛才聊了什麼）
    if conversation_history:
        history_lines = []
        for msg in conversation_history:
            role_label = "用戶" if msg["role"] == "user" else "馬雲"
            history_lines.append(f"{role_label}：{msg['content']}")
        if history_lines:
            prompt_parts.append(
                f"【我們剛才的對話紀錄 - 你必須記住這些內容】\n"
                f"重要：以下是你和用戶真實發生過的對話。用戶在對話中提到的任何個人資訊（生日、職業、喜好、計畫等），你都必須記住並在後續對話中正確引用。\n\n"
                + "\n".join(history_lines)
            )
    
    # 用戶輸入
    prompt_parts.append(f"【用戶說】\n{user_text}")
    
    # 如果包含可疑詞彙但較長，在提示中明確告訴 LLM 這可能是誤識別
    if is_suspicious:
        prompt_parts.append("【重要提醒】如果用戶的輸入聽起來很奇怪、像是誤識別、或包含「打賞」「明鏡」等不應該出現的詞，請用馬雲的方式回應：「欸，我沒聽清楚，你再說一次？」或「這什麼意思？我聽不太懂。」絕對不要順著這些詞繼續對話。")
    
    user_input = "\n\n".join(prompt_parts)

    # 放寬所有安全限制
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }

    # 直接發送請求
    response = await model.generate_content_async(
        user_input,
        generation_config=genai.types.GenerationConfig(
            candidate_count=1,
            max_output_tokens=500,
            temperature=0.85,
        ),
        safety_settings=safety_settings
    )
    
    # 檢查是否有內容
    if response.candidates and response.candidates[0].content.parts:
        reply_text = response.text.strip()
        
        # 後處理：過濾不應該出現的內容
        forbidden_patterns = [
            r'打賞.*支持.*明鏡',
            r'點贊.*訂閱.*轉發',
            r'打賞支持',
            r'支持明鏡',
            r'明鏡.*點點',
            r'我們的節目',
            r'感謝支持',
            r'請訂閱',
            r'請關注',
        ]
        
        for pattern in forbidden_patterns:
            if re.search(pattern, reply_text, re.IGNORECASE):
                # 如果發現禁止內容，用馬雲的方式回應
                return "欸，這什麼東西？我聽不太懂你在說什麼。"
        
        return reply_text
    
    # 如果真的連一個字都沒有（例如被安全機制攔截）
    finish_reason = response.candidates[0].finish_reason if response.candidates else "Unknown"
    return f"[系統提示：AI 暫時無法回應。原因碼：{finish_reason}]"

