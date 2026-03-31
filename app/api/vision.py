"""
Phase 3: 圖片辨識 API 端點
上傳圖片讓馬雲看並回應
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks, Request
from pydantic import BaseModel
from app.services.vision import (
    analyze_image,
    analyze_image_from_base64,
    get_supported_mime_types
)
from app.services.storage import upload_image
from app.services.memory import save_turn
from app.services.tts_cleaner import clean_for_tts
from app.services.tts import synthesize_speech
from app.core.config import settings
from app.core.deps import get_current_user
from app.db.models import User
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

def get_or_create_conversation_id(user_id: str) -> str:
    """取得或建立用戶的對話 ID"""
    try:
        from app.db.session import SessionLocal
        from app.db.models import Conversation
        db = SessionLocal()
        try:
            conv = db.query(Conversation).filter(Conversation.user_id == user_id).order_by(Conversation.created_at.desc()).first()
            if conv:
                return conv.id
            new_id = f"conv_{user_id}"
            conv = Conversation(id=new_id, user_id=user_id)
            db.add(conv)
            db.commit()
            return new_id
        finally:
            db.close()
    except Exception as e:
        print(f"[WARNING] get_or_create_conversation_id failed: {e}")
        return f"conv_{user_id}"


class VisionBase64Request(BaseModel):
    image: str  # Base64 encoded image
    message: Optional[str] = None  # 用戶附帶的文字訊息


class VisionConfigResponse(BaseModel):
    enabled: bool
    max_size_mb: float
    supported_formats: list


@router.get("/vision/config")
async def get_vision_config(request: Request):
    """取得圖片辨識功能的設定狀態"""
    return VisionConfigResponse(
        enabled=settings.ENABLE_VISION,
        max_size_mb=settings.VISION_MAX_IMAGE_SIZE_MB,
        supported_formats=get_supported_mime_types()
    )


@router.post("/vision/analyze")
@limiter.limit("20/minute")
async def analyze_uploaded_image(
    request: Request,
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...),
    message: Optional[str] = Form(None),
    with_audio: bool = Form(True),
    current_user: User = Depends(get_current_user)
):
    """
    上傳圖片讓馬雲看並回應（需要登入）
    
    Args:
        image: 上傳的圖片檔案
        message: 用戶附帶的文字訊息（可選）
        with_audio: 是否生成語音回應
    
    Returns:
        馬雲的回應（文字 + 可選語音 + 圖片 URL）
    """
    if not settings.ENABLE_VISION:
        raise HTTPException(status_code=503, detail="Vision feature is disabled")
    
    # 檢查檔案類型
    content_type = image.content_type or "image/jpeg"
    supported = get_supported_mime_types()
    
    if content_type not in supported:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported image format: {content_type}. Supported: {supported}"
        )
    
    # 讀取圖片資料
    try:
        image_data = await image.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read image: {e}")
    
    # 取得用戶 ID 和對話 ID
    user_id = current_user.id
    conversation_id = get_or_create_conversation_id(user_id)
    
    # 上傳圖片到 Cloud Storage
    upload_success, image_url = await upload_image(
        image_data=image_data,
        mime_type=content_type,
        user_id=user_id
    )
    
    if not upload_success:
        logger.warning(f"Failed to upload image to Cloud Storage: {image_url}")
        image_url = None  # 上傳失敗時不返回 URL
    
    # 分析圖片
    success, response_text = await analyze_image(
        image_data=image_data,
        mime_type=content_type,
        user_message=message or ""
    )
    
    # 用戶訊息內容
    user_text = message if message else "傳送了一張圖片"
    
    # 生成語音（如果需要）
    audio_url = None
    if success and with_audio:
        try:
            tts_text = clean_for_tts(response_text, use_pronunciation_fix=True)
            audio_url = await synthesize_speech(tts_text)
        except Exception as e:
            logger.warning(f"TTS failed for vision response: {e}")
    
    # 背景保存對話記錄
    background_tasks.add_task(save_turn, conversation_id, "user", user_text, None, user_id, image_url)
    background_tasks.add_task(save_turn, conversation_id, "assistant", response_text, audio_url, user_id, None)
    
    return {
        "success": success,
        "text": response_text,
        "audio_url": audio_url,
        "image_url": image_url
    }


@router.post("/vision/analyze_base64")
@limiter.limit("20/minute")
async def analyze_base64_image(
    request: Request,
    req: VisionBase64Request,
    with_audio: bool = True,
    current_user: User = Depends(get_current_user)
):
    """
    分析 Base64 編碼的圖片（需要登入）
    
    Args:
        req.image: Base64 編碼的圖片（可包含 data URL 前綴）
        req.message: 用戶附帶的文字訊息（可選）
        with_audio: 是否生成語音回應
    
    Returns:
        馬雲的回應（文字 + 可選語音）
    """
    if not settings.ENABLE_VISION:
        raise HTTPException(status_code=503, detail="Vision feature is disabled")
    
    # 分析圖片
    success, response_text = await analyze_image_from_base64(
        base64_data=req.image,
        user_message=req.message or ""
    )
    
    if not success:
        return {
            "success": False,
            "text": response_text,
            "audio_url": None
        }
    
    # 生成語音（如果需要）
    audio_url = None
    if with_audio:
        try:
            tts_text = clean_for_tts(response_text, use_pronunciation_fix=True)
            audio_url = await synthesize_speech(tts_text)
        except Exception as e:
            logger.warning(f"TTS failed for vision response: {e}")
    
    return {
        "success": True,
        "text": response_text,
        "audio_url": audio_url
    }
