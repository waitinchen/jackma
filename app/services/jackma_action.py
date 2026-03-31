"""
Phase 2C: JackmaAction 服務
馬雲說過的話 - 承諾、建議、約定等
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.db.models import JackmaAction
from app.db.session import SessionLocal
from app.core.config import settings


# GMT+8 時區偏移
TZ_OFFSET_HOURS = 8


def get_current_date_gmt8() -> str:
    """取得當前 GMT+8 日期 (YYYY-MM-DD)"""
    utc_now = datetime.utcnow()
    gmt8_now = utc_now + timedelta(hours=TZ_OFFSET_HOURS)
    return gmt8_now.strftime("%Y-%m-%d")


def add_jackma_action(
    user_id: str,
    action_type: str,
    summary: str,
    original_text: str = None,
    action_date: str = None,
    source_turn_id: int = None,
    confidence: float = 1.0
) -> Optional[int]:
    """
    新增馬雲的行動記錄

    Args:
        user_id: 用戶 ID
        action_type: 行動類型 (promise, suggestion, question, reminder, other)
        summary: 行動摘要
        original_text: 原始對話內容
        action_date: 發生日期 YYYY-MM-DD (預設今天)
        source_turn_id: 來源對話 ID
        confidence: 信心度

    Returns:
        新增的記錄 ID，失敗則回傳 None
    """
    if not settings.ENABLE_JACKMA_ACTIONS:
        return None

    # 驗證 action_type
    valid_types = {'promise', 'suggestion', 'question', 'reminder', 'encouragement', 'other'}
    if action_type not in valid_types:
        action_type = 'other'

    # 預設日期為今天
    if not action_date:
        action_date = get_current_date_gmt8()

    try:
        db = SessionLocal()
        try:
            action = JackmaAction(
                user_id=user_id,
                action_type=action_type,
                summary=summary,
                original_text=original_text,
                action_date=action_date,
                source_turn_id=source_turn_id,
                confidence=confidence
            )
            db.add(action)
            db.commit()
            db.refresh(action)

            print(f"[INFO] Added JackMa action for user {user_id}: [{action_type}] {summary}")
            return action.id
        finally:
            db.close()
    except Exception as e:
        print(f"[WARNING] add_jackma_action failed: {e}")
        return None


def get_recent_actions(
    user_id: str,
    days: int = None,
    action_type: str = None,
    include_fulfilled: bool = False,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    取得馬雲最近對這位用戶說過的話

    Args:
        user_id: 用戶 ID
        days: 查詢最近幾天 (預設使用設定值)
        action_type: 篩選行動類型 (可選)
        include_fulfilled: 是否包含已履行的
        limit: 最多回傳幾筆

    Returns:
        行動記錄列表
    """
    if not settings.ENABLE_JACKMA_ACTIONS:
        return []

    if days is None:
        days = settings.JACKMA_ACTIONS_LOOKBACK_DAYS

    # 計算日期範圍
    today = get_current_date_gmt8()
    cutoff_date = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        db = SessionLocal()
        try:
            query = db.query(JackmaAction).filter(
                JackmaAction.user_id == user_id,
                JackmaAction.action_date >= cutoff_date,
                JackmaAction.is_relevant == True
            )

            if action_type:
                query = query.filter(JackmaAction.action_type == action_type)

            if not include_fulfilled:
                query = query.filter(JackmaAction.is_fulfilled == False)

            results = query.order_by(
                JackmaAction.action_date.desc(),
                JackmaAction.created_at.desc()
            ).limit(limit).all()

            return [
                {
                    "id": a.id,
                    "action_type": a.action_type,
                    "summary": a.summary,
                    "original_text": a.original_text,
                    "action_date": a.action_date,
                    "is_fulfilled": a.is_fulfilled,
                    "created_at": a.created_at.isoformat() if a.created_at else None
                }
                for a in results
            ]
        finally:
            db.close()
    except Exception as e:
        print(f"[WARNING] get_recent_actions failed: {e}")
        return []


def get_unfulfilled_promises(user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """取得尚未履行的承諾"""
    if not settings.ENABLE_JACKMA_ACTIONS:
        return []

    try:
        db = SessionLocal()
        try:
            results = db.query(JackmaAction).filter(
                JackmaAction.user_id == user_id,
                JackmaAction.action_type == 'promise',
                JackmaAction.is_fulfilled == False,
                JackmaAction.is_relevant == True
            ).order_by(
                JackmaAction.action_date.desc()
            ).limit(limit).all()

            return [
                {
                    "id": a.id,
                    "summary": a.summary,
                    "action_date": a.action_date
                }
                for a in results
            ]
        finally:
            db.close()
    except Exception as e:
        print(f"[WARNING] get_unfulfilled_promises failed: {e}")
        return []


def mark_action_fulfilled(action_id: int) -> bool:
    """標記行動為已履行"""
    if not settings.ENABLE_JACKMA_ACTIONS:
        return False

    try:
        db = SessionLocal()
        try:
            action = db.query(JackmaAction).filter(JackmaAction.id == action_id).first()
            if action:
                action.is_fulfilled = True
                action.fulfilled_at = datetime.utcnow()
                db.commit()
                return True
            return False
        finally:
            db.close()
    except Exception as e:
        print(f"[WARNING] mark_action_fulfilled failed: {e}")
        return False


def mark_action_irrelevant(action_id: int) -> bool:
    """標記行動為不再相關"""
    if not settings.ENABLE_JACKMA_ACTIONS:
        return False

    try:
        db = SessionLocal()
        try:
            action = db.query(JackmaAction).filter(JackmaAction.id == action_id).first()
            if action:
                action.is_relevant = False
                db.commit()
                return True
            return False
        finally:
            db.close()
    except Exception as e:
        print(f"[WARNING] mark_action_irrelevant failed: {e}")
        return False


def format_actions_for_prompt(user_id: str) -> str:
    """
    將馬雲的行動記錄格式化為 LLM prompt 可用的文字

    Returns:
        格式化的行動字串，如果沒有記錄則回傳空字串
    """
    actions = get_recent_actions(user_id, include_fulfilled=False)

    if not actions:
        return ""

    today = get_current_date_gmt8()
    lines = []

    for a in actions:
        # 計算相對時間
        action_date = a["action_date"]
        if action_date == today:
            date_str = "今天"
        else:
            days_ago = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(action_date, "%Y-%m-%d")).days
            if days_ago == 1:
                date_str = "昨天"
            elif days_ago == 2:
                date_str = "前天"
            else:
                date_str = f"{days_ago}天前"

        # 組合描述
        type_labels = {
            'promise': '我答應過',
            'suggestion': '我建議過',
            'question': '我問過',
            'reminder': '我提醒過',
            'encouragement': '我鼓勵過',
            'other': '我說過'
        }
        type_label = type_labels.get(a["action_type"], "我說過")

        lines.append(f"- {date_str}{type_label}：{a['summary']}")

    if not lines:
        return ""

    return "【我對這位朋友說過的話】\n" + "\n".join(lines)


def format_actions_for_voice(user_id: str, max_length: int = 150, limit: int = 2) -> str:
    """
    將馬雲的行動記錄格式化為通話模式 (ElevenLabs) 可用的精簡文字

    Args:
        user_id: 用戶 ID
        max_length: 最大字元數（精簡版，避免 context 過長）
        limit: 最多取幾筆記錄（精簡版只取 2 筆）

    Returns:
        精簡格式的行動字串，如果沒有記錄則回傳空字串
    """
    actions = get_recent_actions(user_id, include_fulfilled=False, limit=limit)

    if not actions:
        return ""

    today = get_current_date_gmt8()
    parts = []

    type_labels = {
        'promise': '我答應過',
        'suggestion': '我建議過',
        'question': '我問過',
        'reminder': '我提醒過',
        'encouragement': '我鼓勵過',
        'other': '我說過'
    }

    for a in actions:
        action_date = a["action_date"]
        if action_date == today:
            date_str = "今天"
        else:
            days_ago = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(action_date, "%Y-%m-%d")).days
            if days_ago == 1:
                date_str = "昨天"
            elif days_ago == 2:
                date_str = "前天"
            else:
                date_str = f"{days_ago}天前"

        type_label = type_labels.get(a["action_type"], "我說過")

        # 精簡格式：日期+類型：摘要
        parts.append(f"{date_str}{type_label}：{a['summary']}")

    if not parts:
        return ""

    result = " | ".join(parts)

    if len(result) > max_length:
        result = result[:max_length - 3] + "..."

    return result
