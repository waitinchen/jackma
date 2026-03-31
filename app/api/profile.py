"""
Phase 2A: UserProfile API 端點
用戶基本資料的查詢與更新
"""
import logging
from typing import Optional, List, Any, Literal
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from app.services.user_profile import (
    get_user_profile,
    update_profile_field,
    get_profile_history,
    format_profile_for_prompt
)
from app.core.config import settings
from app.core.deps import get_current_user
from app.db.models import User
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class ProfileUpdateRequest(BaseModel):
    """
    更新用戶資料的請求格式
    
    Attributes:
        field_name: 要更新的欄位名稱，限定為特定值
        value: 新的值
        reason: 變更原因（可選）
    """
    field_name: Literal[
        "name", "nickname", "birthday", "age", "gender",
        "occupation", "company", "location", "personality",
        "interests", "preferences", "extra_info"
    ]
    value: Any = Field(..., description="新的值")
    reason: Optional[str] = Field(None, max_length=500, description="變更原因")


class ProfileResponse(BaseModel):
    name: Optional[str] = None
    nickname: Optional[str] = None
    birthday: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    personality: Optional[str] = None
    interests: Optional[List[str]] = None
    preferences: Optional[dict] = None
    extra_info: Optional[dict] = None


@router.get("/profile")
@limiter.limit("20/minute")
async def get_my_profile(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """取得當前用戶的基本資料（需要登入）"""
    if not settings.ENABLE_USER_PROFILE:
        raise HTTPException(status_code=503, detail="User profile feature is disabled")
    
    user_id = current_user.id
    profile = get_user_profile(user_id)
    
    if not profile:
        return ProfileResponse()
    
    return ProfileResponse(**profile)


@router.put("/profile")
@limiter.limit("20/minute")
async def update_my_profile(
    request: Request,
    req: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user)
):
    """更新當前用戶的基本資料（需要登入）"""
    if not settings.ENABLE_USER_PROFILE:
        raise HTTPException(status_code=503, detail="User profile feature is disabled")
    
    user_id = current_user.id
    
    success = update_profile_field(
        user_id=user_id,
        field_name=req.field_name,
        new_value=req.value,
        change_reason=req.reason,
        confidence=1.0  # 用戶手動更新，信心度為 1.0
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update profile")
    
    return {"success": True, "message": f"Updated {req.field_name}"}


@router.get("/profile/history")
@limiter.limit("20/minute")
async def get_my_profile_history(
    request: Request,
    field_name: Optional[str] = None,
    limit: int = 10,
    current_user: User = Depends(get_current_user)
):
    """取得用戶資料變更歷史（需要登入）"""
    if not settings.ENABLE_USER_PROFILE:
        raise HTTPException(status_code=503, detail="User profile feature is disabled")
    
    user_id = current_user.id
    history = get_profile_history(user_id, field_name, limit)
    
    return {"history": history}


@router.get("/profile/formatted")
@limiter.limit("20/minute")
async def get_formatted_profile(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """取得格式化的用戶資料（需要登入）"""
    if not settings.ENABLE_USER_PROFILE:
        raise HTTPException(status_code=503, detail="User profile feature is disabled")
    
    user_id = current_user.id
    formatted = format_profile_for_prompt(user_id)
    
    return {"formatted_profile": formatted}
