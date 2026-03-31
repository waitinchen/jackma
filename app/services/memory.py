from sqlalchemy.orm import Session
from app.db.models import Memory, Turn, Conversation
from app.services.embeddings import get_embedding
from app.db.session import SessionLocal
import google.generativeai as genai
from app.core.config import settings
from app.services.elevenlabs_kb import maybe_sync_kb_for_user

def retrieve_memories(conversation_id: str, query_text: str, limit: int = 5) -> list[str]:
    """使用向量相似度從資料庫抓取相關精華記憶"""
    try:
        db = SessionLocal()
        try:
            # 1. 將查詢文字轉為向量
            query_vector = get_embedding(query_text)
            
            # 2. 進行相似度檢索 (使用 pgvector 的 <-> 算子進行 L2 距離計算)
            results = db.query(Memory.content).filter(
                Memory.conversation_id == conversation_id
            ).order_by(
                Memory.embedding.l2_distance(query_vector)
            ).limit(limit).all()
            
            return [r[0] for r in results]
        finally:
            db.close()
    except Exception as e:
        print(f"[WARNING] retrieve_memories failed: {e}")
        return []

def save_turn(conversation_id: str, speaker: str, text: str, audio_url: str = None, user_id: str = "admin", image_url: str = None, source: str = "text"):
    """保存每一輪的對話紀錄"""
    try:
        db = SessionLocal()
        try:
            # 確保會話存在
            conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not conv:
                conv = Conversation(id=conversation_id, user_id=user_id)
                db.add(conv)
                db.commit()

            new_turn = Turn(
                conversation_id=conversation_id,
                speaker=speaker,
                stt_text=text if speaker == 'user' else None,
                reply_text=text if speaker == 'assistant' else None,
                audio_url=audio_url,
                image_url=image_url if speaker == 'user' else None,
                source=source
            )
            db.add(new_turn)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"[WARNING] save_turn failed: {e}")

def extract_and_save_memory(conversation_id: str, text: str, user_id: str = "admin"):
    """(背景任務) 從對話中抽取出精華記憶並存入向量庫"""
    try:
        db = SessionLocal()
        try:
            # 確保會話存在
            conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not conv:
                conv = Conversation(id=conversation_id, user_id=user_id)
                db.add(conv)
                db.commit()

            vector = get_embedding(text)
            new_memory = Memory(
                conversation_id=conversation_id,
                type="conversation_fragment",
                content=text,
                embedding=vector
            )
            db.add(new_memory)
            db.commit()
        finally:
            db.close()

        # 低成本 KB 同步：背景觸發，受限於頻率與數量
        try:
            maybe_sync_kb_for_user(user_id)
        except Exception as sync_err:
            print(f"[WARNING] maybe_sync_kb_for_user failed: {sync_err}")
    except Exception as e:
        print(f"[WARNING] extract_and_save_memory failed: {e}")
