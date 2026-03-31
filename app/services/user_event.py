"""
Phase 2B: UserEvent 服務
用戶事件/日常的 CRUD 操作
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.db.models import UserEvent
from app.db.session import SessionLocal
from app.core.config import settings


# GMT+8 時區偏移
TZ_OFFSET_HOURS = 8


def get_current_date_gmt8() -> str:
    """取得當前 GMT+8 日期 (YYYY-MM-DD)"""
    utc_now = datetime.utcnow()
    gmt8_now = utc_now + timedelta(hours=TZ_OFFSET_HOURS)
    return gmt8_now.strftime("%Y-%m-%d")


def get_current_time_gmt8() -> str:
    """取得當前 GMT+8 時間 (HH:MM)"""
    utc_now = datetime.utcnow()
    gmt8_now = utc_now + timedelta(hours=TZ_OFFSET_HOURS)
    return gmt8_now.strftime("%H:%M")


def add_user_event(
    user_id: str,
    event_type: str,
    summary: str,
    details: str = None,
    event_date: str = None,
    event_time: str = None,
    follow_up_needed: bool = False,
    source: str = "conversation",
    source_turn_id: int = None,
    confidence: float = 1.0
) -> Optional[int]:
    """
    新增用戶事件
    
    Args:
        user_id: 用戶 ID
        event_type: 事件類型 (mood, activity, plan, health, work, other)
        summary: 事件摘要
        details: 詳細內容 (可選)
        event_date: 事件日期 YYYY-MM-DD (預設今天)
        event_time: 事件時間 HH:MM (可選)
        follow_up_needed: 是否需要追蹤
        source: 來源 (conversation, manual, system)
        source_turn_id: 來源對話 ID
        confidence: 信心度
    
    Returns:
        新增的事件 ID，失敗則回傳 None
    """
    if not settings.ENABLE_USER_EVENTS:
        return None
    
    # 驗證 event_type
    valid_types = {'mood', 'activity', 'plan', 'health', 'work', 'relationship', 'other'}
    if event_type not in valid_types:
        event_type = 'other'
    
    # 預設日期為今天
    if not event_date:
        event_date = get_current_date_gmt8()
    
    try:
        db = SessionLocal()
        try:
            event = UserEvent(
                user_id=user_id,
                event_type=event_type,
                summary=summary,
                details=details,
                event_date=event_date,
                event_time=event_time,
                follow_up_needed=follow_up_needed,
                source=source,
                source_turn_id=source_turn_id,
                confidence=confidence
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            
            print(f"[INFO] Added event for user {user_id}: [{event_type}] {summary}")
            return event.id
        finally:
            db.close()
    except Exception as e:
        print(f"[WARNING] add_user_event failed: {e}")
        return None


def get_recent_events(
    user_id: str,
    days: int = None,
    event_type: str = None,
    include_resolved: bool = False,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    取得用戶最近的事件
    
    Args:
        user_id: 用戶 ID
        days: 查詢最近幾天 (預設使用設定值)
        event_type: 篩選事件類型 (可選)
        include_resolved: 是否包含已解決的事件
        limit: 最多回傳幾筆
    
    Returns:
        事件列表
    """
    if not settings.ENABLE_USER_EVENTS:
        return []
    
    if days is None:
        days = settings.USER_EVENTS_LOOKBACK_DAYS
    
    # 計算日期範圍
    today = get_current_date_gmt8()
    cutoff_date = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")
    
    try:
        db = SessionLocal()
        try:
            query = db.query(UserEvent).filter(
                UserEvent.user_id == user_id,
                UserEvent.event_date >= cutoff_date
            )
            
            if event_type:
                query = query.filter(UserEvent.event_type == event_type)
            
            if not include_resolved:
                query = query.filter(UserEvent.is_resolved == False)
            
            results = query.order_by(
                UserEvent.event_date.desc(),
                UserEvent.created_at.desc()
            ).limit(limit).all()
            
            return [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "summary": e.summary,
                    "details": e.details,
                    "event_date": e.event_date,
                    "event_time": e.event_time,
                    "is_resolved": e.is_resolved,
                    "follow_up_needed": e.follow_up_needed,
                    "created_at": e.created_at.isoformat() if e.created_at else None
                }
                for e in results
            ]
        finally:
            db.close()
    except Exception as e:
        print(f"[WARNING] get_recent_events failed: {e}")
        return []


def get_events_needing_followup(user_id: str, limit: int = 10, max_days: int = 7) -> List[Dict[str, Any]]:
    """取得需要追蹤的事件（限制在 max_days 天內，避免過舊事件干擾 LLM）"""
    if not settings.ENABLE_USER_EVENTS:
        return []

    try:
        db = SessionLocal()
        try:
            # 計算截止日期，超過 max_days 天的事件自動標記為已解決
            today = get_current_date_gmt8()
            cutoff_date = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=max_days)).strftime("%Y-%m-%d")

            # 先把過舊的 follow_up 事件自動標記為已解決
            old_events = db.query(UserEvent).filter(
                UserEvent.user_id == user_id,
                UserEvent.follow_up_needed == True,
                UserEvent.is_resolved == False,
                UserEvent.event_date < cutoff_date
            ).all()
            for old_event in old_events:
                old_event.is_resolved = True
                print(f"[INFO] Auto-resolved old event #{old_event.id}: {old_event.summary} (date: {old_event.event_date})")
            if old_events:
                db.commit()

            # 只取 max_days 天內的未解決追蹤事件
            results = db.query(UserEvent).filter(
                UserEvent.user_id == user_id,
                UserEvent.follow_up_needed == True,
                UserEvent.is_resolved == False,
                UserEvent.event_date >= cutoff_date
            ).order_by(
                UserEvent.event_date.desc()
            ).limit(limit).all()

            return [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "summary": e.summary,
                    "event_date": e.event_date,
                    "followed_up_at": e.followed_up_at.isoformat() if e.followed_up_at else None
                }
                for e in results
            ]
        finally:
            db.close()
    except Exception as e:
        print(f"[WARNING] get_events_needing_followup failed: {e}")
        return []



def mark_event_resolved(event_id: int) -> bool:
    """標記事件為已解決"""
    if not settings.ENABLE_USER_EVENTS:
        return False
    
    try:
        db = SessionLocal()
        try:
            event = db.query(UserEvent).filter(UserEvent.id == event_id).first()
            if event:
                event.is_resolved = True
                db.commit()
                return True
            return False
        finally:
            db.close()
    except Exception as e:
        print(f"[WARNING] mark_event_resolved failed: {e}")
        return False


def mark_event_followed_up(event_id: int) -> bool:
    """標記事件已追蹤"""
    if not settings.ENABLE_USER_EVENTS:
        return False
    
    try:
        db = SessionLocal()
        try:
            event = db.query(UserEvent).filter(UserEvent.id == event_id).first()
            if event:
                event.followed_up_at = datetime.utcnow()
                db.commit()
                return True
            return False
        finally:
            db.close()
    except Exception as e:
        print(f"[WARNING] mark_event_followed_up failed: {e}")
        return False


def format_events_for_prompt(user_id: str) -> str:
    """
    將用戶事件格式化為 LLM prompt 可用的文字
    
    Returns:
        格式化的事件字串，如果沒有事件則回傳空字串
    """
    events = get_recent_events(user_id, include_resolved=False)
    
    if not events:
        return ""
    
    today = get_current_date_gmt8()
    lines = []
    
    for e in events:
        # 計算相對時間
        event_date = e["event_date"]
        if event_date == today:
            date_str = "今天"
        else:
            days_ago = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(event_date, "%Y-%m-%d")).days
            if days_ago == 1:
                date_str = "昨天"
            elif days_ago == 2:
                date_str = "前天"
            else:
                date_str = f"{days_ago}天前"
        
        # 組合事件描述
        type_labels = {
            'mood': '心情',
            'activity': '活動',
            'plan': '計畫',
            'health': '健康',
            'work': '工作',
            'relationship': '人際',
            'other': ''
        }
        type_label = type_labels.get(e["event_type"], "")
        
        if type_label:
            lines.append(f"- {date_str}（{type_label}）：{e['summary']}")
        else:
            lines.append(f"- {date_str}：{e['summary']}")
    
    if not lines:
        return ""
    
    return "【這位朋友最近的狀況】\n" + "\n".join(lines)


def format_events_for_voice(user_id: str, max_length: int = 150, limit: int = 3) -> str:
    """
    將用戶事件格式化為通話模式 (ElevenLabs) 可用的精簡文字
    
    Args:
        user_id: 用戶 ID
        max_length: 最大字元數（精簡版，避免 context 過長）
        limit: 最多取幾筆事件（精簡版只取 3 筆）
    
    Returns:
        精簡格式的事件字串，如果沒有事件則回傳空字串
    """
    events = get_recent_events(user_id, include_resolved=False, limit=limit)
    
    if not events:
        return ""
    
    today = get_current_date_gmt8()
    parts = []
    
    type_labels = {
        'mood': '心情',
        'activity': '活動',
        'plan': '計畫',
        'health': '健康',
        'work': '工作',
        'relationship': '人際',
        'other': ''
    }
    
    for e in events:
        event_date = e["event_date"]
        if event_date == today:
            date_str = "今天"
        else:
            days_ago = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(event_date, "%Y-%m-%d")).days
            if days_ago == 1:
                date_str = "昨天"
            elif days_ago == 2:
                date_str = "前天"
            else:
                date_str = f"{days_ago}天前"
        
        type_label = type_labels.get(e["event_type"], "")
        
        # 精簡格式：日期（類型）：摘要
        if type_label:
            parts.append(f"{date_str}（{type_label}）：{e['summary']}")
        else:
            parts.append(f"{date_str}：{e['summary']}")
    
    if not parts:
        return ""
    
    result = " | ".join(parts)
    
    if len(result) > max_length:
        result = result[:max_length - 3] + "..."
    
    return result
