from app.db.base import Base
from app.db.session import engine
from app.db.models import (
    User,
    Conversation,
    Turn,
    Memory,
    KnowledgeBaseSyncState,
    KnowledgeBaseSyncedMemory,
    # Phase 2A: UserProfile
    UserProfile,
    UserProfileHistory,
    # Phase 2B: UserEvent
    UserEvent,
    # Phase 2C: JackmaAction
    JackmaAction,
    # 永久筆記
    UserKeyNote,
)
from sqlalchemy import text

def init_db():
    # 1. 建立向量擴展 (需超級用戶權限，或資料庫預先安裝)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
        print("pgvector extension check complete.")

    # 2. 建立所有資料表
    Base.metadata.create_all(bind=engine)
    print("All tables created successfully.")
    
    # 3. Migration: 為 turns 表加上 source 欄位（如果不存在）
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='turns' AND column_name='source'"
        ))
        if result.fetchone() is None:
            conn.execute(text("ALTER TABLE turns ADD COLUMN source VARCHAR DEFAULT 'text'"))
            conn.commit()
            print("Migration: Added 'source' column to turns table.")
        else:
            print("Migration: 'source' column already exists in turns table.")
    
    # 4. 清理資料庫中對話內容的「文翊啊，」「文翊啊,」「文翊阿，」等開頭
    with engine.connect() as conn:
        # 清理 reply_text（馬雲的回覆）
        result = conn.execute(text(
            "UPDATE turns SET reply_text = regexp_replace(reply_text, '^文翊[啊阿][，,、]?\\s*', '', 'g') "
            "WHERE reply_text ~ '^文翊[啊阿]'"
        ))
        cleaned = result.rowcount
        # 也清理 memories 中的內容
        result2 = conn.execute(text(
            "UPDATE memories SET content = regexp_replace(content, '文翊[啊阿][，,、]?\\s*', '', 'g') "
            "WHERE content LIKE '%文翊啊%' OR content LIKE '%文翊阿%'"
        ))
        cleaned2 = result2.rowcount
        conn.commit()
        if cleaned or cleaned2:
            print(f"Migration: Cleaned '文翊啊，' from {cleaned} turns, {cleaned2} memories.")
        else:
            print("Migration: No '文翊啊，' found to clean.")

if __name__ == "__main__":
    init_db()
