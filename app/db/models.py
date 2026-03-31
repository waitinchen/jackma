from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Boolean, Float, JSON
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector
from .base import Base


# ============================================
# Phase 2A: UserProfile 用戶基本資料
# ============================================

class UserProfile(Base):
    """用戶基本資料 - 從對話中學習的靜態資訊"""
    __tablename__ = "user_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), unique=True, index=True)
    
    # 基本資料
    name = Column(String, nullable=True)  # 用戶姓名/暱稱
    nickname = Column(String, nullable=True)  # 馬雲對用戶的稱呼
    birthday = Column(String, nullable=True)  # 生日 (格式: MM-DD 或 YYYY-MM-DD)
    age = Column(Integer, nullable=True)  # 年齡
    gender = Column(String, nullable=True)  # 性別
    
    # 職業與生活
    occupation = Column(String, nullable=True)  # 職業
    company = Column(String, nullable=True)  # 公司/單位
    location = Column(String, nullable=True)  # 所在地
    
    # 個性與偏好
    personality = Column(Text, nullable=True)  # 個性描述
    interests = Column(JSON, nullable=True)  # 興趣愛好 (list)
    preferences = Column(JSON, nullable=True)  # 偏好設定 (dict)
    
    # 其他自由欄位
    extra_info = Column(JSON, nullable=True)  # 其他資訊 (dict)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class UserProfileHistory(Base):
    """用戶資料變更歷史 - 保留舊資料"""
    __tablename__ = "user_profile_history"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), index=True)
    
    field_name = Column(String, index=True)  # 變更的欄位名稱
    old_value = Column(Text, nullable=True)  # 舊值
    new_value = Column(Text, nullable=True)  # 新值
    change_reason = Column(Text, nullable=True)  # 變更原因 (LLM 抽取的上下文)
    confidence = Column(Float, default=1.0)  # 信心度 (0.0 ~ 1.0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============================================
# Phase 2B: UserEvent 用戶事件/日常
# ============================================

class UserEvent(Base):
    """用戶事件/日常 - 有時間戳的動態資訊"""
    __tablename__ = "user_events"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), index=True)
    
    # 事件內容
    event_type = Column(String, index=True)  # 事件類型: mood, activity, plan, health, work, other
    summary = Column(Text)  # 事件摘要 (如: "心情不好", "去看了牙醫")
    details = Column(Text, nullable=True)  # 詳細內容
    
    # 時間資訊 (GMT+8)
    event_date = Column(String, index=True)  # 事件日期 YYYY-MM-DD
    event_time = Column(String, nullable=True)  # 事件時間 HH:MM (可選)
    
    # 追蹤狀態
    is_resolved = Column(Boolean, default=False)  # 是否已解決/過期
    follow_up_needed = Column(Boolean, default=False)  # 是否需要追蹤
    followed_up_at = Column(DateTime(timezone=True), nullable=True)  # 上次追蹤時間
    
    # 來源
    source = Column(String, default="conversation")  # conversation, manual, system
    source_turn_id = Column(Integer, nullable=True)  # 來源對話 ID
    confidence = Column(Float, default=1.0)  # 信心度
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ============================================
# Phase 2C: JackmaAction 馬雲說過的話
# ============================================

class JackmaAction(Base):
    """馬雲說過的話 - 承諾、建議、約定等需要記住的內容"""
    __tablename__ = "jackma_actions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), index=True)
    
    # 行動內容
    action_type = Column(String, index=True)  # promise, suggestion, question, reminder, other
    summary = Column(Text)  # 摘要 (如: "答應下次聊聊投資", "建議用戶多休息")
    original_text = Column(Text, nullable=True)  # 原始對話內容
    
    # 時間資訊
    action_date = Column(String, index=True)  # 發生日期 YYYY-MM-DD
    
    # 狀態追蹤
    is_fulfilled = Column(Boolean, default=False)  # 是否已履行/完成
    is_relevant = Column(Boolean, default=True)  # 是否仍然相關
    fulfilled_at = Column(DateTime(timezone=True), nullable=True)  # 履行時間
    
    # 來源
    source_turn_id = Column(Integer, nullable=True)  # 來源對話 ID
    confidence = Column(Float, default=1.0)  # 信心度
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)  # 可為空 (匿名用戶)
    password_hash = Column(String, nullable=True)  # 可為空 (匿名用戶)
    name = Column(String, nullable=True)
    is_anonymous = Column(Boolean, default=True)  # 是否為匿名用戶
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Turn(Base):
    __tablename__ = "turns"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String, ForeignKey("conversations.id"))
    speaker = Column(String)  # 'user' or 'assistant'
    stt_text = Column(Text, nullable=True)
    reply_text = Column(Text, nullable=True)
    audio_url = Column(String, nullable=True)
    image_url = Column(String, nullable=True)  # 用戶上傳的圖片 URL
    source = Column(String, default="text")  # 'text' or 'call' — 區分文字模式和通話模式
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Memory(Base):
    __tablename__ = "memories"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String, ForeignKey("conversations.id"))
    type = Column(String)  # 'preference', 'constraint', 'story', etc.
    content = Column(Text)
    embedding = Column(Vector(768))  # 向量維度 (Gemini text-embedding-004 為 768)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# ============================================
# 用戶關鍵事件永久筆記
# ============================================

class UserKeyNote(Base):
    """用戶關鍵事件永久筆記 - 重要人生事件，不會過期"""
    __tablename__ = "user_key_notes"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), index=True)
    
    category = Column(String, index=True)  # health, family, relationship, life_event, other
    summary = Column(Text)  # 摘要 (如: "因肺炎住院", "女友叫小美")
    details = Column(Text, nullable=True)  # 詳細內容
    
    source = Column(String, default="conversation")  # conversation, manual
    source_turn_id = Column(Integer, nullable=True)
    confidence = Column(Float, default=1.0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class KnowledgeBaseSyncState(Base):
    __tablename__ = "kb_sync_state"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, unique=True)
    last_synced_at = Column(DateTime(timezone=True), server_default=func.now())
    last_doc_id = Column(String, nullable=True)
    last_doc_hash = Column(String, nullable=True)

class KnowledgeBaseSyncedMemory(Base):
    __tablename__ = "kb_synced_memories"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    memory_id = Column(Integer, ForeignKey("memories.id"), index=True, unique=True)
    content_hash = Column(String, index=True)
    synced_at = Column(DateTime(timezone=True), server_default=func.now())
