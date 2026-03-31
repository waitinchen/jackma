"""
Phase 2A: UserProfile 服務
用戶基本資料的 CRUD 操作與歷史記錄
"""
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.db.models import UserProfile, UserProfileHistory
from app.db.session import SessionLocal
from app.core.config import settings


def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """取得用戶基本資料"""
    if not settings.ENABLE_USER_PROFILE:
        return None
    
    try:
        db = SessionLocal()
        try:
            profile = db.query(UserProfile).filter(
                UserProfile.user_id == user_id
            ).first()
            
            if not profile:
                return None
            
            return {
                "name": profile.name,
                "nickname": profile.nickname,
                "birthday": profile.birthday,
                "age": profile.age,
                "gender": profile.gender,
                "occupation": profile.occupation,
                "company": profile.company,
                "location": profile.location,
                "personality": profile.personality,
                "interests": profile.interests or [],
                "preferences": profile.preferences or {},
                "extra_info": profile.extra_info or {},
            }
        finally:
            db.close()
    except Exception as e:
        print(f"[WARNING] get_user_profile failed: {e}")
        return None


def get_or_create_profile(user_id: str) -> UserProfile:
    """取得或建立用戶 Profile"""
    db = SessionLocal()
    try:
        profile = db.query(UserProfile).filter(
            UserProfile.user_id == user_id
        ).first()
        
        if not profile:
            profile = UserProfile(user_id=user_id)
            db.add(profile)
            db.commit()
            db.refresh(profile)
        
        return profile
    finally:
        db.close()


def update_profile_field(
    user_id: str,
    field_name: str,
    new_value: Any,
    change_reason: str = None,
    confidence: float = 1.0
) -> bool:
    """
    更新用戶資料的單一欄位，並記錄歷史
    
    Args:
        user_id: 用戶 ID
        field_name: 欄位名稱 (如 'name', 'occupation')
        new_value: 新值
        change_reason: 變更原因 (從哪段對話抽取的)
        confidence: 信心度 (LLM 自動抽取時使用)
    
    Returns:
        是否更新成功
    """
    if not settings.ENABLE_USER_PROFILE:
        return False
    
    # 允許更新的欄位白名單
    allowed_fields = {
        'name', 'nickname', 'birthday', 'age', 'gender',
        'occupation', 'company', 'location',
        'personality', 'interests', 'preferences', 'extra_info'
    }
    
    if field_name not in allowed_fields:
        print(f"[WARNING] Invalid field name: {field_name}")
        return False
    
    try:
        db = SessionLocal()
        try:
            # 取得或建立 profile
            profile = db.query(UserProfile).filter(
                UserProfile.user_id == user_id
            ).first()
            
            if not profile:
                profile = UserProfile(user_id=user_id)
                db.add(profile)
                db.commit()
                db.refresh(profile)
            
            # 取得舊值
            old_value = getattr(profile, field_name, None)
            
            # 如果值相同，不更新
            if old_value == new_value:
                return True
            
            # 記錄歷史
            history = UserProfileHistory(
                user_id=user_id,
                field_name=field_name,
                old_value=str(old_value) if old_value is not None else None,
                new_value=str(new_value) if new_value is not None else None,
                change_reason=change_reason,
                confidence=confidence
            )
            db.add(history)
            
            # 更新欄位
            setattr(profile, field_name, new_value)
            db.commit()
            
            print(f"[INFO] Updated {field_name} for user {user_id}: {old_value} -> {new_value}")
            return True
        finally:
            db.close()
    except Exception as e:
        print(f"[WARNING] update_profile_field failed: {e}")
        return False


def get_profile_history(user_id: str, field_name: str = None, limit: int = 10) -> list:
    """
    取得用戶資料變更歷史
    
    Args:
        user_id: 用戶 ID
        field_name: 欄位名稱 (可選，不指定則取得所有欄位)
        limit: 最多回傳幾筆
    
    Returns:
        歷史記錄列表
    """
    if not settings.ENABLE_USER_PROFILE:
        return []
    
    try:
        db = SessionLocal()
        try:
            query = db.query(UserProfileHistory).filter(
                UserProfileHistory.user_id == user_id
            )
            
            if field_name:
                query = query.filter(UserProfileHistory.field_name == field_name)
            
            results = query.order_by(
                UserProfileHistory.created_at.desc()
            ).limit(limit).all()
            
            return [
                {
                    "field_name": r.field_name,
                    "old_value": r.old_value,
                    "new_value": r.new_value,
                    "change_reason": r.change_reason,
                    "confidence": r.confidence,
                    "created_at": r.created_at.isoformat() if r.created_at else None
                }
                for r in results
            ]
        finally:
            db.close()
    except Exception as e:
        print(f"[WARNING] get_profile_history failed: {e}")
        return []


def format_profile_for_prompt(user_id: str) -> str:
    """
    將用戶資料格式化為 LLM prompt 可用的文字
    
    Returns:
        格式化的用戶資料字串，如果沒有資料則回傳空字串
    """
    profile = get_user_profile(user_id)
    
    if not profile:
        return ""
    
    lines = []
    
    # 基本資料
    if profile.get("name"):
        lines.append(f"用戶姓名：{profile['name']}")
    if profile.get("nickname"):
        lines.append(f"我叫他：{profile['nickname']}")
    if profile.get("birthday"):
        lines.append(f"生日：{profile['birthday']}")
    if profile.get("age"):
        lines.append(f"年齡：{profile['age']} 歲")
    if profile.get("gender"):
        lines.append(f"性別：{profile['gender']}")
    
    # 職業與生活
    if profile.get("occupation"):
        lines.append(f"職業：{profile['occupation']}")
    if profile.get("company"):
        lines.append(f"公司：{profile['company']}")
    if profile.get("location"):
        lines.append(f"所在地：{profile['location']}")
    
    # 個性
    if profile.get("personality"):
        lines.append(f"個性：{profile['personality']}")
    
    # 興趣
    if profile.get("interests"):
        interests_str = "、".join(profile["interests"])
        lines.append(f"興趣：{interests_str}")
    
    if not lines:
        return ""
    
    return "【我對這位朋友的了解】\n" + "\n".join(lines)


def format_profile_for_voice(user_id: str, max_length: int = 100) -> str:
    """
    將用戶資料格式化為通話模式 (ElevenLabs) 可用的精簡文字
    
    Args:
        user_id: 用戶 ID
        max_length: 最大字元數（精簡版，避免 context 過長）
    
    Returns:
        精簡格式的用戶資料字串，如果沒有資料則回傳空字串
    """
    profile = get_user_profile(user_id)
    
    if not profile:
        return ""
    
    parts = []
    
    # 優先順序：職業 > 生日 > 興趣 > 所在地 > 個性
    if profile.get("occupation"):
        parts.append(f"職業：{profile['occupation']}")
    if profile.get("birthday"):
        parts.append(f"生日：{profile['birthday']}")
    if profile.get("interests") and len(profile["interests"]) > 0:
        # 最多取 3 個興趣
        interests = profile["interests"][:3]
        parts.append(f"興趣：{'、'.join(interests)}")
    if profile.get("location"):
        parts.append(f"所在地：{profile['location']}")
    if profile.get("personality"):
        parts.append(f"個性：{profile['personality']}")
    
    if not parts:
        return ""
    
    result = " | ".join(parts)
    
    # 確保不超過最大長度
    if len(result) > max_length:
        result = result[:max_length - 3] + "..."
    
    return result
