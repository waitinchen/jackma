"""
Phase 2D: 資訊抽取服務
從對話中自動抽取用戶資訊、事件、馬雲的承諾等
"""
import json
import re
from typing import Optional, Dict, Any, List
import google.generativeai as genai
from app.core.config import settings
from app.services.user_profile import update_profile_field
from app.services.user_event import add_user_event, get_current_date_gmt8
from app.services.jackma_action import add_jackma_action
from app.services.user_key_note import add_key_note

# 確保 API Key 已設定
genai.configure(api_key=settings.GEMINI_API_KEY)


# 抽取用的 prompt
EXTRACTION_PROMPT = """你是一個資訊抽取助手。請從以下對話中抽取重要資訊。

對話內容：
用戶說：{user_text}
馬雲回覆：{assistant_text}

請以 JSON 格式回傳抽取結果。嚴格遵循以下格式：

{{
  "user_profile": [
    {{"field": "欄位名", "value": "值", "confidence": 0.9, "reason": "原因"}}
  ],
  "user_events": [
    {{"event_type": "類型", "summary": "摘要", "follow_up_needed": true, "confidence": 0.8}}
  ],
  "jackma_actions": [
    {{"action_type": "類型", "summary": "摘要", "confidence": 0.7}}
  ],
  "key_notes": [
    {{"category": "類型", "summary": "摘要", "details": "詳情(可選)", "confidence": 0.85}}
  ]
}}

user_profile 可抽取的欄位：name, nickname, birthday, age, gender, occupation, company, location, personality, interests
user_events 的 event_type：mood, activity, plan, health, work, relationship, other
jackma_actions 的 action_type：promise, suggestion, question, reminder, encouragement, other
key_notes 的 category：health, family, relationship, life_event, other

【key_notes 永久筆記規則】
- 只記錄重大、長期有意義的事件，例如：
  · health: 生了什麼病、住院、開刀、長期用藥
  · family: 爸媽、兄弟姊妹的名字或狀況
  · relationship: 女友/男友/老婆/老公是誰
  · life_event: 結婚、離婚、搬家、換工作等重大變化
- 日常閒聊（今天吃什麼、天氣好不好）不要記錄到 key_notes
- confidence 至少 0.8 才記錄

規則：
- 只抽取明確提到的資訊
- confidence 低於 0.6 不要回傳
- 沒有可抽取的資訊就回傳空陣列
- 只回傳 JSON，不要有其他文字或 markdown 標記

請分析以上對話並回傳 JSON："""


async def extract_info_from_conversation(
    user_id: str,
    user_text: str,
    assistant_text: str,
    source_turn_id: int = None
) -> Dict[str, Any]:
    """
    從對話中抽取資訊並儲存
    
    Args:
        user_id: 用戶 ID
        user_text: 用戶說的話
        assistant_text: 馬雲的回覆
        source_turn_id: 來源對話 ID
    
    Returns:
        抽取結果統計
    """
    if not settings.ENABLE_AUTO_EXTRACT:
        return {"skipped": True, "reason": "Auto extract disabled"}
    
    result = {
        "profile_updates": 0,
        "events_added": 0,
        "actions_added": 0,
        "errors": []
    }
    
    try:
        # 呼叫 LLM 進行抽取
        extraction = await _call_extraction_llm(user_text, assistant_text)
        
        if not extraction:
            return {"skipped": True, "reason": "No extraction result"}
        
        today = get_current_date_gmt8()
        min_confidence = settings.AUTO_EXTRACT_MIN_CONFIDENCE
        
        # 1. 處理 user_profile
        for item in extraction.get("user_profile", []):
            try:
                if item.get("confidence", 0) >= min_confidence:
                    success = update_profile_field(
                        user_id=user_id,
                        field_name=item["field"],
                        new_value=item["value"],
                        change_reason=item.get("reason", f"從對話中抽取：{user_text[:50]}"),
                        confidence=item["confidence"]
                    )
                    if success:
                        result["profile_updates"] += 1
            except Exception as e:
                result["errors"].append(f"Profile update error: {e}")
        
        # 2. 處理 user_events
        for item in extraction.get("user_events", []):
            try:
                if item.get("confidence", 0) >= min_confidence:
                    event_id = add_user_event(
                        user_id=user_id,
                        event_type=item.get("event_type", "other"),
                        summary=item["summary"],
                        event_date=today,
                        follow_up_needed=item.get("follow_up_needed", False),
                        source="conversation",
                        source_turn_id=source_turn_id,
                        confidence=item["confidence"]
                    )
                    if event_id:
                        result["events_added"] += 1
            except Exception as e:
                result["errors"].append(f"Event add error: {e}")
        
        # 3. 處理 jackma_actions
        for item in extraction.get("jackma_actions", []):
            try:
                if item.get("confidence", 0) >= min_confidence:
                    action_id = add_jackma_action(
                        user_id=user_id,
                        action_type=item.get("action_type", "other"),
                        summary=item["summary"],
                        original_text=assistant_text[:200] if assistant_text else None,
                        action_date=today,
                        source_turn_id=source_turn_id,
                        confidence=item["confidence"]
                    )
                    if action_id:
                        result["actions_added"] += 1
            except Exception as e:
                result["errors"].append(f"Action add error: {e}")
        
        # 4. 處理 key_notes（永久筆記）
        for item in extraction.get("key_notes", []):
            try:
                if item.get("confidence", 0) >= 0.8:
                    note_id = add_key_note(
                        user_id=user_id,
                        category=item.get("category", "other"),
                        summary=item["summary"],
                        details=item.get("details"),
                        source="conversation",
                        source_turn_id=source_turn_id,
                        confidence=item["confidence"]
                    )
                    if note_id:
                        result["key_notes_added"] = result.get("key_notes_added", 0) + 1
            except Exception as e:
                result["errors"].append(f"Key note add error: {e}")
        
        print(f"[INFO] Extraction complete for user {user_id}: {result}")
        return result
        
    except Exception as e:
        print(f"[WARNING] extract_info_from_conversation failed: {e}")
        return {"error": str(e)}


async def _call_extraction_llm(user_text: str, assistant_text: str) -> Optional[Dict]:
    """呼叫 LLM 進行資訊抽取"""
    try:
        prompt = EXTRACTION_PROMPT.format(
            user_text=user_text,
            assistant_text=assistant_text
        )
        
        print(f"[DEBUG] Calling extraction LLM...")
        model = genai.GenerativeModel(model_name="gemini-2.5-flash")
        
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(
                candidate_count=1,
                max_output_tokens=1500,  # 增加 token 數避免截斷
                temperature=0.1,  # 低溫度確保穩定輸出
            )
        )
        
        if not response.candidates or not response.candidates[0].content.parts:
            print(f"[WARNING] Extraction LLM returned no content")
            return None
        
        text = response.text.strip()
        print(f"[DEBUG] Extraction LLM raw response: {text[:500]}...")
        
        # 嘗試解析 JSON
        # 移除可能的 markdown 標記
        text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\s*```$', '', text)
        
        return json.loads(text)
        
    except json.JSONDecodeError as e:
        print(f"[WARNING] JSON parse error in extraction: {e}")
        return None
    except Exception as e:
        print(f"[WARNING] Extraction LLM call failed: {e}")
        return None


def extract_info_sync(
    user_id: str,
    user_text: str,
    assistant_text: str,
    source_turn_id: int = None
):
    """
    同步版本的資訊抽取（用於背景任務）
    """
    import asyncio
    
    print(f"[INFO] extract_info_sync called for user {user_id}")
    print(f"[INFO] User text: {user_text[:100]}...")
    
    try:
        # 在新的事件循環中執行異步函數
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                extract_info_from_conversation(
                    user_id, user_text, assistant_text, source_turn_id
                )
            )
            print(f"[INFO] extract_info_sync result: {result}")
            return result
        finally:
            loop.close()
    except Exception as e:
        print(f"[WARNING] extract_info_sync failed: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}
