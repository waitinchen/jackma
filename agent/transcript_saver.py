"""
馬雲語氣靈 — 通話結束後的 Transcript 儲存
在 LiveKit Agent 端直接存 DB，不需要前端再呼叫 API
"""
import logging
from app.services.memory import save_turn, extract_and_save_memory
from app.services.info_extractor import extract_info_sync
from app.core.config import settings

logger = logging.getLogger(__name__)


def ensure_user_and_conversation(user_id: str, conversation_id: str) -> None:
    """確保用戶與會話存在於資料庫"""
    try:
        from app.db.session import SessionLocal
        from app.db.models import User, Conversation
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                user = User(id=user_id, name="User")
                db.add(user)
                db.commit()

            conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not conv:
                conv = Conversation(id=conversation_id, user_id=user_id)
                db.add(conv)
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"ensure_user_and_conversation failed: {e}")


def save_transcript(user_id: str, transcript: list[dict]) -> int:
    """
    儲存通話 transcript 到資料庫

    Args:
        user_id: 用戶 ID
        transcript: [{"role": "user"/"assistant", "content": "..."}]

    Returns:
        儲存的訊息數
    """
    conversation_id = f"conv_{user_id}"
    ensure_user_and_conversation(user_id, conversation_id)

    saved_count = 0
    for msg in transcript:
        content = msg.get("content", "").strip()
        if not content:
            continue
        try:
            save_turn(conversation_id, msg["role"], content, None, user_id, None, "call")
            saved_count += 1
        except Exception as e:
            logger.error(f"Failed to save turn: {e}")

    # 記憶萃取：配對 user→assistant
    messages = [m for m in transcript if m.get("content", "").strip()]
    for i in range(len(messages) - 1):
        if messages[i]["role"] == "user" and messages[i + 1]["role"] == "assistant":
            user_text = messages[i]["content"].strip()
            assistant_text = messages[i + 1]["content"].strip()

            try:
                extract_and_save_memory(
                    conversation_id,
                    f"用戶問：{user_text} | 大哥答：{assistant_text}",
                    user_id
                )
            except Exception as e:
                logger.error(f"Failed to extract memory: {e}")

            if settings.ENABLE_AUTO_EXTRACT:
                try:
                    extract_info_sync(user_id, user_text, assistant_text, None)
                except Exception as e:
                    logger.error(f"Failed to extract info: {e}")

    logger.info(f"Saved {saved_count} transcript messages for user {user_id}")
    return saved_count
