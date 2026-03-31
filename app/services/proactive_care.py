"""
Phase 2E: 主動關心機制
根據用戶資料和事件，生成馬雲應該主動關心的提示
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from app.services.user_profile import get_user_profile
from app.services.user_event import get_events_needing_followup, get_recent_events, get_current_date_gmt8
from app.services.jackma_action import get_unfulfilled_promises
from app.core.config import settings


def check_birthday(user_id: str) -> Optional[str]:
    """檢查是否是用戶生日或即將生日"""
    profile = get_user_profile(user_id)
    if not profile or not profile.get("birthday"):
        return None
    
    birthday = profile["birthday"]
    today = get_current_date_gmt8()
    
    # 解析生日 (支援 MM-DD 或 YYYY-MM-DD 格式)
    try:
        if len(birthday) == 5:  # MM-DD
            birthday_mmdd = birthday
        else:  # YYYY-MM-DD
            birthday_mmdd = birthday[5:]  # 取 MM-DD
        
        today_mmdd = today[5:]  # 取 MM-DD
        
        # 今天是生日
        if birthday_mmdd == today_mmdd:
            name = profile.get("name") or profile.get("nickname") or "朋友"
            return f"今天是{name}的生日！記得祝福他。"
        
        # 計算距離生日還有幾天
        today_date = datetime.strptime(today, "%Y-%m-%d")
        birthday_this_year = datetime.strptime(f"{today[:4]}-{birthday_mmdd}", "%Y-%m-%d")
        
        # 如果今年生日已過，看明年
        if birthday_this_year < today_date:
            birthday_this_year = datetime.strptime(f"{int(today[:4])+1}-{birthday_mmdd}", "%Y-%m-%d")
        
        days_until = (birthday_this_year - today_date).days
        
        if days_until <= 3:
            name = profile.get("name") or profile.get("nickname") or "朋友"
            return f"{name}的生日快到了（{days_until}天後），可以提前祝福。"
        
    except Exception as e:
        print(f"[WARNING] Birthday check failed: {e}")
    
    return None


def get_followup_reminders(user_id: str) -> List[str]:
    """取得需要追蹤關心的事項"""
    reminders = []
    
    # 1. 需要追蹤的用戶事件
    events = get_events_needing_followup(user_id, limit=5)
    for e in events:
        days_ago = _days_since(e.get("event_date"))
        if days_ago is not None:
            if days_ago == 0:
                reminders.append(f"今天他提到：{e['summary']}，可以關心一下後續")
            elif days_ago == 1:
                reminders.append(f"昨天他說{e['summary']}，可以問問現在怎麼樣了")
            else:
                reminders.append(f"{days_ago}天前他說{e['summary']}，可以追蹤一下")
    
    # 2. 未履行的承諾
    promises = get_unfulfilled_promises(user_id, limit=3)
    for p in promises:
        days_ago = _days_since(p.get("action_date"))
        if days_ago is not None and days_ago >= 1:
            reminders.append(f"我之前答應過：{p['summary']}，記得兌現")
    
    return reminders


def get_mood_context(user_id: str) -> Optional[str]:
    """取得用戶最近的心情狀況"""
    events = get_recent_events(user_id, days=3, event_type="mood", include_resolved=False, limit=3)
    
    if not events:
        return None
    
    today = get_current_date_gmt8()
    mood_notes = []
    
    for e in events:
        days_ago = _days_since(e.get("event_date"))
        if days_ago == 0:
            mood_notes.append(f"今天{e['summary']}")
        elif days_ago == 1:
            mood_notes.append(f"昨天{e['summary']}")
        else:
            mood_notes.append(f"{days_ago}天前{e['summary']}")
    
    if mood_notes:
        return "、".join(mood_notes)
    
    return None


def generate_proactive_care_context(user_id: str, max_length: int = 150) -> str:
    """
    生成主動關心的上下文提示
    這會被加入到 LLM 的 prompt 中
    
    Args:
        user_id: 用戶 ID
        max_length: 最大字元數（精簡版，避免 context 過長）
    
    Returns:
        格式化的主動關心提示，如果沒有則回傳空字串
    """
    if not settings.ENABLE_PROACTIVE_CARE:
        return ""
    
    care_items = []
    
    # 1. 生日檢查
    birthday_note = check_birthday(user_id)
    if birthday_note:
        care_items.append(birthday_note)
    
    # 2. 追蹤事項（最多 2 項，精簡版）
    followups = get_followup_reminders(user_id)
    care_items.extend(followups[:2])
    
    # 3. 心情狀況
    mood = get_mood_context(user_id)
    if mood:
        care_items.append(f"心情：{mood}")
    
    if not care_items:
        return ""
    
    # 精簡格式，不加標題
    result = " | ".join(care_items)
    
    if len(result) > max_length:
        result = result[:max_length - 3] + "..."
    
    return result


def _days_since(date_str: str) -> Optional[int]:
    """計算距離某日期過了幾天"""
    if not date_str:
        return None
    try:
        today = datetime.strptime(get_current_date_gmt8(), "%Y-%m-%d")
        target = datetime.strptime(date_str, "%Y-%m-%d")
        return (today - target).days
    except:
        return None
