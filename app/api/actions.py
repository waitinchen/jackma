"""
Phase 2C: JackmaAction API 端點
馬雲說過的話 - 承諾、建議、約定等
"""
import logging
import re
from typing import Optional, List, Literal
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field, field_validator
from app.services.jackma_action import (
    add_jackma_action,
    get_recent_actions,
    get_unfulfilled_promises,
    mark_action_fulfilled,
    mark_action_irrelevant,
    format_actions_for_prompt,
    get_current_date_gmt8
)
from app.core.config import settings
from app.core.deps import get_current_user
from app.db.models import User
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class ActionCreateRequest(BaseModel):
    """
    建立馬雲行動記錄的請求格式
    
    Attributes:
        action_type: 行動類型，限定為特定值
        summary: 行動摘要，1-500 字
        original_text: 原始對話內容（可選），最多 1000 字
        action_date: 行動日期，格式 YYYY-MM-DD（可選，預設今天）
    """
    action_type: Literal["promise", "suggestion", "question", "reminder", "encouragement", "other"]
    summary: str = Field(..., min_length=1, max_length=500, description="行動摘要")
    original_text: Optional[str] = Field(None, max_length=1000, description="原始對話內容")
    action_date: Optional[str] = Field(None, description="行動日期 YYYY-MM-DD")
    
    @field_validator('action_date')
    @classmethod
    def validate_date_format(cls, v):
        """驗證日期格式為 YYYY-MM-DD"""
        if v is None:
            return v
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', v):
            raise ValueError('日期格式必須為 YYYY-MM-DD')
        return v


class ActionResponse(BaseModel):
    id: int
    action_type: str
    summary: str
    original_text: Optional[str] = None
    action_date: str
    is_fulfilled: bool
    created_at: Optional[str] = None


@router.get("/actions")
@limiter.limit("20/minute")
async def get_my_actions(
    request: Request,
    days: Optional[int] = None,
    action_type: Optional[str] = None,
    include_fulfilled: bool = False,
    limit: int = 20,
    current_user: User = Depends(get_current_user)
):
    """取得馬雲對當前用戶說過的話（需要登入）"""
    if not settings.ENABLE_JACKMA_ACTIONS:
        raise HTTPException(status_code=503, detail="JackMa actions feature is disabled")
    
    user_id = current_user.id
    actions = get_recent_actions(
        user_id=user_id,
        days=days,
        action_type=action_type,
        include_fulfilled=include_fulfilled,
        limit=limit
    )
    
    return {"actions": actions, "today": get_current_date_gmt8()}


@router.post("/actions")
@limiter.limit("20/minute")
async def create_action(
    request: Request,
    req: ActionCreateRequest,
    current_user: User = Depends(get_current_user)
):
    """手動新增馬雲的行動記錄（需要登入）"""
    if not settings.ENABLE_JACKMA_ACTIONS:
        raise HTTPException(status_code=503, detail="JackMa actions feature is disabled")
    
    user_id = current_user.id
    
    action_id = add_jackma_action(
        user_id=user_id,
        action_type=req.action_type,
        summary=req.summary,
        original_text=req.original_text,
        action_date=req.action_date,
        confidence=1.0
    )
    
    if not action_id:
        raise HTTPException(status_code=400, detail="Failed to create action")
    
    return {"success": True, "action_id": action_id}


@router.get("/actions/promises")
@limiter.limit("20/minute")
async def get_promises(
    request: Request,
    limit: int = 10,
    current_user: User = Depends(get_current_user)
):
    """取得馬雲尚未履行的承諾（需要登入）"""
    if not settings.ENABLE_JACKMA_ACTIONS:
        raise HTTPException(status_code=503, detail="JackMa actions feature is disabled")
    
    user_id = current_user.id
    promises = get_unfulfilled_promises(user_id, limit)
    
    return {"promises": promises}


@router.post("/actions/{action_id}/fulfill")
@limiter.limit("20/minute")
async def fulfill_action(
    request: Request,
    action_id: int,
    current_user: User = Depends(get_current_user)
):
    """標記行動為已履行（需要登入）"""
    if not settings.ENABLE_JACKMA_ACTIONS:
        raise HTTPException(status_code=503, detail="JackMa actions feature is disabled")
    
    success = mark_action_fulfilled(action_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Action not found")
    
    return {"success": True}


@router.post("/actions/{action_id}/irrelevant")
@limiter.limit("20/minute")
async def mark_irrelevant(
    request: Request,
    action_id: int,
    current_user: User = Depends(get_current_user)
):
    """標記行動為不再相關（需要登入）"""
    if not settings.ENABLE_JACKMA_ACTIONS:
        raise HTTPException(status_code=503, detail="JackMa actions feature is disabled")
    
    success = mark_action_irrelevant(action_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Action not found")
    
    return {"success": True}


@router.get("/actions/formatted")
@limiter.limit("20/minute")
async def get_formatted_actions(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """取得格式化的行動記錄（需要登入）"""
    if not settings.ENABLE_JACKMA_ACTIONS:
        raise HTTPException(status_code=503, detail="JackMa actions feature is disabled")
    
    user_id = current_user.id
    formatted = format_actions_for_prompt(user_id)
    
    return {"formatted_actions": formatted}
