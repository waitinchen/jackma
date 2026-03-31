"""
Phase 2B: UserEvent API 端點
用戶事件/日常的查詢與管理
"""
import logging
import re
from typing import Optional, List, Literal
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field, field_validator
from app.services.user_event import (
    add_user_event,
    get_recent_events,
    get_events_needing_followup,
    mark_event_resolved,
    mark_event_followed_up,
    format_events_for_prompt,
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


class EventCreateRequest(BaseModel):
    """
    建立事件的請求格式
    
    Attributes:
        event_type: 事件類型，限定為特定值
        summary: 事件摘要，1-500 字
        details: 詳細內容（可選），最多 2000 字
        event_date: 事件日期，格式 YYYY-MM-DD（可選，預設今天）
        event_time: 事件時間，格式 HH:MM（可選）
        follow_up_needed: 是否需要追蹤
    """
    event_type: Literal["mood", "activity", "plan", "health", "work", "relationship", "other"]
    summary: str = Field(..., min_length=1, max_length=500, description="事件摘要")
    details: Optional[str] = Field(None, max_length=2000, description="詳細內容")
    event_date: Optional[str] = Field(None, description="事件日期 YYYY-MM-DD")
    event_time: Optional[str] = Field(None, description="事件時間 HH:MM")
    follow_up_needed: bool = False
    
    @field_validator('event_date')
    @classmethod
    def validate_date_format(cls, v):
        """驗證日期格式為 YYYY-MM-DD"""
        if v is None:
            return v
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', v):
            raise ValueError('日期格式必須為 YYYY-MM-DD')
        return v
    
    @field_validator('event_time')
    @classmethod
    def validate_time_format(cls, v):
        """驗證時間格式為 HH:MM"""
        if v is None:
            return v
        if not re.match(r'^\d{2}:\d{2}$', v):
            raise ValueError('時間格式必須為 HH:MM')
        return v


class EventResponse(BaseModel):
    id: int
    event_type: str
    summary: str
    details: Optional[str] = None
    event_date: str
    event_time: Optional[str] = None
    is_resolved: bool
    follow_up_needed: bool
    created_at: Optional[str] = None


@router.get("/events")
@limiter.limit("20/minute")
async def get_my_events(
    request: Request,
    days: Optional[int] = None,
    event_type: Optional[str] = None,
    include_resolved: bool = False,
    limit: int = 20,
    current_user: User = Depends(get_current_user)
):
    """取得當前用戶的最近事件（需要登入）"""
    if not settings.ENABLE_USER_EVENTS:
        raise HTTPException(status_code=503, detail="User events feature is disabled")
    
    user_id = current_user.id
    events = get_recent_events(
        user_id=user_id,
        days=days,
        event_type=event_type,
        include_resolved=include_resolved,
        limit=limit
    )
    
    return {"events": events, "today": get_current_date_gmt8()}


@router.post("/events")
@limiter.limit("20/minute")
async def create_event(
    request: Request,
    req: EventCreateRequest,
    current_user: User = Depends(get_current_user)
):
    """手動新增用戶事件（需要登入）"""
    if not settings.ENABLE_USER_EVENTS:
        raise HTTPException(status_code=503, detail="User events feature is disabled")
    
    user_id = current_user.id
    
    event_id = add_user_event(
        user_id=user_id,
        event_type=req.event_type,
        summary=req.summary,
        details=req.details,
        event_date=req.event_date,
        event_time=req.event_time,
        follow_up_needed=req.follow_up_needed,
        source="manual",
        confidence=1.0
    )
    
    if not event_id:
        raise HTTPException(status_code=400, detail="Failed to create event")
    
    return {"success": True, "event_id": event_id}


@router.get("/events/followup")
@limiter.limit("20/minute")
async def get_followup_events(
    request: Request,
    limit: int = 10,
    current_user: User = Depends(get_current_user)
):
    """取得需要追蹤的事件（需要登入）"""
    if not settings.ENABLE_USER_EVENTS:
        raise HTTPException(status_code=503, detail="User events feature is disabled")
    
    user_id = current_user.id
    events = get_events_needing_followup(user_id, limit)
    
    return {"events": events}


@router.post("/events/{event_id}/resolve")
@limiter.limit("20/minute")
async def resolve_event(
    request: Request,
    event_id: int,
    current_user: User = Depends(get_current_user)
):
    """標記事件為已解決（需要登入）"""
    if not settings.ENABLE_USER_EVENTS:
        raise HTTPException(status_code=503, detail="User events feature is disabled")
    
    success = mark_event_resolved(event_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Event not found")
    
    return {"success": True}


@router.post("/events/{event_id}/followup")
@limiter.limit("20/minute")
async def followup_event(
    request: Request,
    event_id: int,
    current_user: User = Depends(get_current_user)
):
    """標記事件已追蹤（需要登入）"""
    if not settings.ENABLE_USER_EVENTS:
        raise HTTPException(status_code=503, detail="User events feature is disabled")
    
    success = mark_event_followed_up(event_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Event not found")
    
    return {"success": True}


@router.get("/events/formatted")
@limiter.limit("20/minute")
async def get_formatted_events(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """取得格式化的事件（需要登入）"""
    if not settings.ENABLE_USER_EVENTS:
        raise HTTPException(status_code=503, detail="User events feature is disabled")
    
    user_id = current_user.id
    formatted = format_events_for_prompt(user_id)
    
    return {"formatted_events": formatted}
