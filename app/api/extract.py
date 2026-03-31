"""
Phase 2D: 資訊抽取 API 端點
手動觸發抽取或測試抽取功能
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from app.services.info_extractor import extract_info_from_conversation
from app.core.config import settings
from app.core.deps import get_current_user
from app.db.models import User
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class ExtractRequest(BaseModel):
    """
    資訊抽取請求格式
    
    Attributes:
        user_text: 用戶說的話，1-2000 字
        assistant_text: 馬雲的回覆，1-2000 字
    """
    user_text: str = Field(..., min_length=1, max_length=2000, description="用戶說的話")
    assistant_text: str = Field(..., min_length=1, max_length=2000, description="馬雲的回覆")


class ExtractConfigResponse(BaseModel):
    enabled: bool
    min_confidence: float
    profile_enabled: bool
    events_enabled: bool
    actions_enabled: bool


@router.get("/extract/config")
async def get_extract_config(request: Request):
    """取得資訊抽取功能的設定狀態"""
    return ExtractConfigResponse(
        enabled=settings.ENABLE_AUTO_EXTRACT,
        min_confidence=settings.AUTO_EXTRACT_MIN_CONFIDENCE,
        profile_enabled=settings.ENABLE_USER_PROFILE,
        events_enabled=settings.ENABLE_USER_EVENTS,
        actions_enabled=settings.ENABLE_JIANGBIN_ACTIONS
    )


@router.post("/extract/test")
@limiter.limit("20/minute")
async def test_extraction(
    request: Request,
    req: ExtractRequest,
    current_user: User = Depends(get_current_user)
):
    """
    測試資訊抽取功能（需要登入，不會實際儲存）
    用於 debug 或預覽抽取結果
    """
    from app.services.info_extractor import _call_extraction_llm
    
    try:
        result = await _call_extraction_llm(
            req.user_text,
            req.assistant_text
        )
        
        if not result:
            return {"success": False, "message": "No extraction result", "data": None}
        
        return {
            "success": True,
            "message": "Extraction test complete",
            "data": result,
            "min_confidence": settings.AUTO_EXTRACT_MIN_CONFIDENCE
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")


@router.post("/extract/manual")
@limiter.limit("20/minute")
async def manual_extraction(
    request: Request,
    req: ExtractRequest,
    current_user: User = Depends(get_current_user)
):
    """
    手動觸發資訊抽取（需要登入，會實際儲存）
    即使 ENABLE_AUTO_EXTRACT=false 也可以使用
    """
    if not settings.ENABLE_USER_PROFILE and not settings.ENABLE_USER_EVENTS and not settings.ENABLE_JIANGBIN_ACTIONS:
        raise HTTPException(
            status_code=503, 
            detail="All memory features are disabled"
        )
    
    user_id = current_user.id
    
    # 暫時啟用抽取功能
    original_setting = settings.ENABLE_AUTO_EXTRACT
    try:
        # 強制啟用以執行抽取
        settings.ENABLE_AUTO_EXTRACT = True
        
        result = await extract_info_from_conversation(
            user_id=user_id,
            user_text=req.user_text,
            assistant_text=req.assistant_text
        )
        
        return {
            "success": True,
            "message": "Manual extraction complete",
            "result": result
        }
    finally:
        # 恢復原始設定
        settings.ENABLE_AUTO_EXTRACT = original_setting
