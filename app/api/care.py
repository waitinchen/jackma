"""
Phase 2E: 主動關心 API 端點
查看主動關心的提示內容
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from app.services.proactive_care import (
    generate_proactive_care_context,
    check_birthday,
    get_followup_reminders,
    get_mood_context
)
from app.core.config import settings
from app.core.deps import get_current_user
from app.db.models import User
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class CareConfigResponse(BaseModel):
    enabled: bool
    profile_enabled: bool
    events_enabled: bool
    actions_enabled: bool


@router.get("/care/config")
async def get_care_config(request: Request):
    """取得主動關心功能的設定狀態"""
    return CareConfigResponse(
        enabled=settings.ENABLE_PROACTIVE_CARE,
        profile_enabled=settings.ENABLE_USER_PROFILE,
        events_enabled=settings.ENABLE_USER_EVENTS,
        actions_enabled=settings.ENABLE_JIANGBIN_ACTIONS
    )


@router.get("/care/preview")
@limiter.limit("20/minute")
async def preview_care_context(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    預覽主動關心的內容（需要登入）
    即使 ENABLE_PROACTIVE_CARE=false 也可以查看
    """
    user_id = current_user.id
    
    # 暫時啟用以取得預覽
    original_setting = settings.ENABLE_PROACTIVE_CARE
    try:
        settings.ENABLE_PROACTIVE_CARE = True
        
        context = generate_proactive_care_context(user_id)
        birthday = check_birthday(user_id)
        followups = get_followup_reminders(user_id)
        mood = get_mood_context(user_id)
        
        return {
            "formatted_context": context,
            "details": {
                "birthday_note": birthday,
                "followup_reminders": followups,
                "mood_context": mood
            }
        }
    finally:
        settings.ENABLE_PROACTIVE_CARE = original_setting


@router.get("/care/birthday")
@limiter.limit("20/minute")
async def check_user_birthday(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """檢查用戶生日狀態（需要登入）"""
    user_id = current_user.id
    
    birthday_note = check_birthday(user_id)
    
    return {
        "has_birthday_note": birthday_note is not None,
        "note": birthday_note
    }


@router.get("/care/followups")
@limiter.limit("20/minute")
async def get_user_followups(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """取得需要追蹤的事項（需要登入）"""
    user_id = current_user.id
    
    followups = get_followup_reminders(user_id)
    
    return {
        "count": len(followups),
        "items": followups
    }
