"""
用戶關鍵事件永久筆記服務
記錄重要人生事件（疾病、家人、伴侶等），永不過期
"""
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from app.db.models import UserKeyNote
from app.db.session import SessionLocal
from app.core.config import settings


VALID_CATEGORIES = {'health', 'family', 'relationship', 'life_event', 'other'}

CATEGORY_LABELS = {
    'health': '健康',
    'family': '家人',
    'relationship': '感情',
    'life_event': '重大事件',
    'other': '其他',
}


def add_key_note(
    user_id: str,
    category: str,
    summary: str,
    details: str = None,
    source: str = "conversation",
    source_turn_id: int = None,
    confidence: float = 1.0
) -> Optional[int]:
    """新增一筆永久筆記，會先檢查是否已有相似摘要避免重複"""
    if category not in VALID_CATEGORIES:
        category = 'other'
    try:
        db = SessionLocal()
        try:
            # 避免重複：同用戶、同類別、摘要完全相同就跳過
            existing = db.query(UserKeyNote).filter(
                UserKeyNote.user_id == user_id,
                UserKeyNote.category == category,
                UserKeyNote.summary == summary
            ).first()
            if existing:
                print(f"[INFO] Key note already exists: {summary}")
                return existing.id

            note = UserKeyNote(
                user_id=user_id,
                category=category,
                summary=summary,
                details=details,
                source=source,
                source_turn_id=source_turn_id,
                confidence=confidence
            )
            db.add(note)
            db.commit()
            db.refresh(note)
            print(f"[INFO] Added key note for user {user_id}: [{category}] {summary}")
            return note.id
        finally:
            db.close()
    except Exception as e:
        print(f"[WARNING] add_key_note failed: {e}")
        return None


def get_key_notes(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """取得用戶所有永久筆記"""
    try:
        db = SessionLocal()
        try:
            results = db.query(UserKeyNote).filter(
                UserKeyNote.user_id == user_id
            ).order_by(UserKeyNote.created_at.desc()).limit(limit).all()
            return [
                {
                    "id": n.id,
                    "category": n.category,
                    "summary": n.summary,
                    "details": n.details,
                    "created_at": n.created_at.isoformat() if n.created_at else None
                }
                for n in results
            ]
        finally:
            db.close()
    except Exception as e:
        print(f"[WARNING] get_key_notes failed: {e}")
        return []


def format_key_notes_for_prompt(user_id: str) -> str:
    """格式化永久筆記供 LLM prompt 使用"""
    notes = get_key_notes(user_id)
    if not notes:
        return ""
    lines = []
    for n in notes:
        label = CATEGORY_LABELS.get(n["category"], "")
        if label:
            lines.append(f"- （{label}）{n['summary']}")
        else:
            lines.append(f"- {n['summary']}")
    return "【這位朋友的重要事項（永久記憶）】\n" + "\n".join(lines)


def format_key_notes_for_voice(user_id: str, max_length: int = 200) -> str:
    """格式化永久筆記供通話模式使用（精簡版）"""
    notes = get_key_notes(user_id, limit=10)
    if not notes:
        return ""
    parts = []
    for n in notes:
        label = CATEGORY_LABELS.get(n["category"], "")
        if label:
            parts.append(f"（{label}）{n['summary']}")
        else:
            parts.append(n['summary'])
    result = " | ".join(parts)
    if len(result) > max_length:
        result = result[:max_length - 3] + "..."
    return result
