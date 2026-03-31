"""
LiveKit 即時語音通話 API 端點
提供 Room Token 生成，供前端建立 WebRTC 連線
"""
import json
import logging
import time
from fastapi import APIRouter, Depends, HTTPException
from livekit.api import AccessToken, VideoGrants
from app.core.config import settings
from app.core.deps import get_current_user
from app.db.models import User

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/token")
async def create_livekit_token(current_user: User = Depends(get_current_user)):
    """
    為已認證用戶生成 LiveKit Room Token
    前端拿到 token 後用 livekit-client 建立 WebRTC 連線
    """
    if not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        raise HTTPException(status_code=500, detail="LiveKit 未設定")

    # 每次通話建新 room（避免殭屍 session 阻擋 dispatch）
    room_name = f"jackma-{current_user.id}-{int(time.time())}"
    participant_identity = current_user.id
    participant_metadata = json.dumps({
        "user_id": current_user.id,
        "user_name": current_user.name or "用戶",
    })

    token = (
        AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(participant_identity)
        .with_name(current_user.name or "用戶")
        .with_metadata(participant_metadata)
        .with_grants(VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        ))
    )

    jwt_token = token.to_jwt()
    logger.info(f"LiveKit token generated for user {current_user.id}, room {room_name}")

    return {
        "token": jwt_token,
        "url": settings.LIVEKIT_URL,
        "room": room_name,
    }
