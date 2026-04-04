import os
import re
import logging
from datetime import datetime, timezone, timedelta
import anthropic
from app.core.config import settings

logger = logging.getLogger(__name__)

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

### 【最重要】語音轉文字容錯（STT）：
你正在語音通話中。用戶的話經過語音辨識（STT），轉錄品質不穩定，經常出現：
- 同音字錯誤（例：「馬雲」被轉成「嗎暈」「螞蟻」）
- 斷句錯誤（一句話被拆成碎片）
- 完全聽錯的詞（無意義的音節組合）

你必須做的：
1. **猜測用戶真正想說什麼**，根據對話上下文推斷意圖
2. **直接回應推斷出的意思**，不要回應字面上的錯字
3. 如果實在猜不到，用自然的方式問「你剛才說的是？」，不要提到「聽不清」「含糊」「語音品質」

你絕對不能做的：
- ❌ 不要說「聽不清楚」「聲音含糊」「你再說一次」「我沒聽懂」
- ❌ 不要糾正用戶的發音或用詞
- ❌ 不要重複用戶的 STT 錯字（例：不要說「你說的'萬一大哥'是什麼意思？」）
- ❌ 不要提及語音品質、收音、麥克風等技術問題
- ❌ 不要把 STT 錯字當成用戶真的在說那個詞

把 STT 輸入當作「寫了錯字的簡訊」——你不會跟朋友說「你這簡訊打得有點含糊」，你會直接理解他的意思然後回覆。
"""

# MiniMax M2.7 — 透過 Anthropic 兼容 API
_client = None

def _get_client():
    """惰性載入 MiniMax M2.7 client"""
    global _client
    if _client is None:
        api_key = settings.MINIMAX_API_KEY
        if not api_key:
            raise ValueError("MINIMAX_API_KEY 未設定")
        _client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url="https://api.minimax.io/anthropic",
        )
        print("DEBUG: Initializing LLM with MiniMax M2.7 (Anthropic-compatible)")
    return _client

MINIMAX_MODEL = "MiniMax-M2.7"


def clean_reply_text(text: str, user_names: list[str] = None) -> str:
    """清理 LLM 回覆中的語氣詞和重複稱呼"""
    if user_names:
        for name in user_names:
            if name:
                text = re.sub(rf'^[喔噢嗯啊唉欸哎][，,、]?\s*{re.escape(name)}[啊阿呀]?[，,、]?\s*', '', text)
                text = re.sub(rf'^{re.escape(name)}[啊阿呀][，,、]?\s*', '', text)
                text = re.sub(rf'^{re.escape(name)}[，,、]\s*', '', text)
    text = re.sub(r'^[喔噢嗯啊唉欸哎][，,、]?\s*文翊[啊阿呀]?[，,、]?\s*', '', text)
    text = re.sub(r'^文翊[啊阿][，,、]?\s*', '', text)
    text = re.sub(r'^欸[，,、]?\s*[^\s，,]{1,10}(啊|呀|喔)?[，,、]?\s*', '', text)
    text = re.sub(r'^欸[，,、]\s*', '', text)
    text = re.sub(r'哈哈+|呵呵+|嘿嘿+|哈+', '', text)
    text = re.sub(r'哎呀[，,]?\s*', '', text)
    text = re.sub(r'哎喲[，,]?\s*', '', text)
    text = re.sub(r'^[欸唉誒哎喔噢啊呀嗯][？?，,、]?\s*', '', text)
    text = re.sub(r'^[欸唉誒哎喔噢啊呀嗯][？?，,、]?\s*', '', text)
    text = re.sub(r'[，,]{2,}', '，', text)
    text = re.sub(r'^[，,、\s！!？?]+', '', text)
    return text.strip()


async def generate_reply(
    user_text: str,
    memories: list[str],
    user_id: str = None,
    user_profile_context: str = "",
    user_events_context: str = "",
    jackma_actions_context: str = "",
    proactive_care_context: str = "",
    key_notes_context: str = "",
    conversation_history: list[dict] = None
) -> str:
    """呼叫 MiniMax M2.7 生成回覆"""

    suspicious_patterns = [r'打賞', r'明鏡', r'點點']
    is_suspicious = any(re.search(p, user_text) for p in suspicious_patterns)

    if is_suspicious and len(user_text.strip()) < 15:
        return "我沒聽清楚，你再說一次好嗎？"

    memory_context = "\n".join([f"- {m}" for m in memories]) if memories else ""
    prompt_parts = []

    user_names = []
    if user_profile_context:
        for line in user_profile_context.split('\n'):
            if '用戶姓名：' in line:
                user_names.append(line.split('用戶姓名：')[-1].strip())
            elif '我叫他：' in line:
                user_names.append(line.split('我叫他：')[-1].strip())

    tw_tz = timezone(timedelta(hours=8))
    now = datetime.now(tw_tz)
    weekday_names = ['一', '二', '三', '四', '五', '六', '日']
    time_str = now.strftime(f"%Y年%m月%d日 星期{weekday_names[now.weekday()]} %H:%M")
    prompt_parts.append(f"【當前時間】{time_str}\n（請根據對話紀錄的時間戳判斷時間遠近：同一天內的事用「剛才」「剛剛」，昨天的用「昨天」，超過兩天才用「前幾天」「上次」。絕對不要把幾分鐘前的事說成「上次」「之前」。）")

    if user_profile_context:
        prompt_parts.append(user_profile_context)
    if key_notes_context:
        prompt_parts.append(key_notes_context)
    if user_events_context:
        prompt_parts.append(user_events_context)
    if jackma_actions_context:
        prompt_parts.append(jackma_actions_context)
    if proactive_care_context:
        prompt_parts.append(proactive_care_context)
    if memory_context:
        prompt_parts.append(f"【記憶參考】\n{memory_context}")

    if conversation_history:
        history_lines = []
        for msg in conversation_history:
            role_label = "用戶" if msg["role"] == "user" else "馬雲"
            content = msg['content']
            if role_label == "馬雲":
                content = clean_reply_text(content, user_names=user_names)
            time_prefix = ""
            if msg.get("created_at"):
                time_prefix = f"[{msg['created_at']}] "
            history_lines.append(f"{time_prefix}{role_label}：{content}")
        if history_lines:
            prompt_parts.append(f"【對話紀錄】\n" + "\n".join(history_lines))

    prompt_parts.append(f"【用戶說】\n{user_text}")
    user_input = "\n\n".join(prompt_parts)

    try:
        client = _get_client()
        response = await client.messages.create(
            model=MINIMAX_MODEL,
            max_tokens=2048,
            temperature=0.7,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_input}],
        )

        reply_text = response.content[0].text.strip()
    except Exception as e:
        logger.error(f"MiniMax M2.7 error: {e}")
        return "我這邊剛才沒接收到完整回覆，你再說一次好嗎？"

    print(f"[DEBUG] LLM原始: {reply_text[:80]}...")
    reply_text = clean_reply_text(reply_text, user_names=user_names)
    print(f"[DEBUG] 清理後: {reply_text[:80]}...")
    return reply_text


async def generate_reply_stream(
    user_text: str,
    memories: list[str],
    user_id: str = None,
    user_profile_context: str = "",
    user_events_context: str = "",
    jackma_actions_context: str = "",
    proactive_care_context: str = "",
    key_notes_context: str = "",
    conversation_history: list[dict] = None
):
    """串流版 LLM — 逐 chunk yield 文字"""

    suspicious_patterns = [r'打賞', r'明鏡', r'點點']
    is_suspicious = any(re.search(p, user_text) for p in suspicious_patterns)
    if is_suspicious and len(user_text.strip()) < 15:
        yield "我沒聽清楚，你再說一次好嗎？"
        return

    memory_context = "\n".join([f"- {m}" for m in memories]) if memories else ""
    prompt_parts = []

    tw_tz = timezone(timedelta(hours=8))
    now = datetime.now(tw_tz)
    weekday_names = ['一', '二', '三', '四', '五', '六', '日']
    time_str = now.strftime(f"%Y年%m月%d日 星期{weekday_names[now.weekday()]} %H:%M")
    prompt_parts.append(f"【當前時間】{time_str}")

    if user_profile_context:
        prompt_parts.append(user_profile_context)
    if key_notes_context:
        prompt_parts.append(key_notes_context)
    if user_events_context:
        prompt_parts.append(user_events_context)
    if jackma_actions_context:
        prompt_parts.append(jackma_actions_context)
    if proactive_care_context:
        prompt_parts.append(proactive_care_context)
    if memory_context:
        prompt_parts.append(f"【記憶參考】\n{memory_context}")

    if conversation_history:
        history_lines = []
        for msg in conversation_history:
            role_label = "用戶" if msg["role"] == "user" else "馬雲"
            content = msg['content']
            time_prefix = f"[{msg.get('created_at', '')}] " if msg.get("created_at") else ""
            history_lines.append(f"{time_prefix}{role_label}：{content}")
        if history_lines:
            prompt_parts.append(f"【對話紀錄】\n" + "\n".join(history_lines))

    prompt_parts.append(f"【用戶說】\n{user_text}")
    user_input = "\n\n".join(prompt_parts)

    try:
        client = _get_client()
        async with client.messages.stream(
            model=MINIMAX_MODEL,
            max_tokens=2048,
            temperature=0.7,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_input}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
    except Exception as e:
        logger.error(f"MiniMax M2.7 streaming error: {e}")
        yield "我這邊剛才沒接收到完整回覆，你再說一次好嗎？"
