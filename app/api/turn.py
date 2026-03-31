"""
核心對話 API 端點
處理語音對話 (/turn) 和文字對話 (/chat_text)
"""
import time
import asyncio
import logging
from typing import Optional, List
from dataclasses import dataclass
from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from app.services.stt import transcribe_audio
from app.services.llm import generate_reply, generate_reply_stream
from app.services.tts_cleaner import clean_for_tts
from app.services.tts import synthesize_speech
from app.services.memory import retrieve_memories, save_turn, extract_and_save_memory
from app.services.user_profile import format_profile_for_prompt, format_profile_for_voice
from app.services.user_event import format_events_for_prompt, format_events_for_voice
from app.services.jackma_action import format_actions_for_prompt, format_actions_for_voice
from app.services.info_extractor import extract_info_sync
from app.services.proactive_care import generate_proactive_care_context
from app.services.user_key_note import format_key_notes_for_prompt, format_key_notes_for_voice
from app.core.config import settings
from app.core.deps import get_current_user, get_current_user_optional
from app.db.models import User
from slowapi import Limiter
from slowapi.util import get_remote_address
import httpx

logger = logging.getLogger(__name__)

router = APIRouter()

# Rate Limiter (每分鐘 20 次)
limiter = Limiter(key_func=get_remote_address)


# ============================================
# 資料類別定義
# ============================================

@dataclass
class ConversationContext:
    """
    對話所需的所有上下文資料
    """
    memories: list
    user_profile_context: str
    user_events_context: str
    jackma_actions_context: str
    proactive_care_context: str
    key_notes_context: str
    conversation_history: list


@dataclass
class ConversationResult:
    """
    對話處理結果
    
    Attributes:
        user_text: 用戶輸入的文字
        assistant_text: 馬雲的回覆
        assistant_audio_url: 語音檔案 URL
        memories_used: 使用的記憶
    """
    user_text: str
    assistant_text: str
    assistant_audio_url: str
    memories_used: list


class ChatTextRequest(BaseModel):
    """
    文字對話請求格式
    
    Attributes:
        text: 用戶輸入的文字，1-2000 字
        user_id: 用戶 ID（已棄用，會使用登入用戶的 ID）
        conversation_id: 對話 ID（可選）
    """
    text: str = Field(..., min_length=1, max_length=2000, description="用戶輸入的文字")
    user_id: Optional[str] = "admin"
    conversation_id: Optional[str] = None


class ConversationMessage(BaseModel):
    """對話訊息格式"""
    role: str  # 'user' or 'assistant'
    content: str
    created_at: Optional[str] = None
    image_url: Optional[str] = None


class ConversationHistoryResponse(BaseModel):
    """對話歷史回應格式"""
    messages: List[ConversationMessage]
    total: int
    has_more: bool


class UserContextResponse(BaseModel):
    """通話模式用的用戶 context（精簡版）"""
    user_profile: str = ""
    upcoming_events: str = ""
    my_promises: str = ""
    recent_chat_summary: str = ""
    proactive_care: str = ""
    key_notes: str = ""  # 永久筆記


class CallTranscriptMessage(BaseModel):
    """通話 transcript 單則訊息"""
    role: str  # 'user' or 'assistant'
    content: str


class SaveCallTranscriptRequest(BaseModel):
    """儲存通話 transcript 的請求"""
    messages: List[CallTranscriptMessage] = Field(..., min_length=1, description="通話對話記錄")


# ============================================
# 共用工具函數
# ============================================

def get_or_create_conversation_id(user_id: str) -> str:
    """
    取得或建立用戶的對話 ID
    
    Args:
        user_id: 用戶 ID
    
    Returns:
        對話 ID (格式: conv_{user_id})
    """
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
        logger.warning(f"get_or_create_conversation_id failed: {e}")
        return f"conv_{user_id}"


def get_recent_conversation_history(conversation_id: str, limit: int = 10) -> list[dict]:
    """
    取得最近 N 輪對話歷史，供 LLM 參考上下文
    
    Args:
        conversation_id: 對話 ID
        limit: 最多取幾輪（預設 10 輪，即 20 條訊息）
    
    Returns:
        [{"role": "user"/"assistant", "content": "..."}]
    """
    try:
        from app.db.session import SessionLocal
        from app.db.models import Turn
        
        db = SessionLocal()
        try:
            turns = db.query(Turn).filter(
                Turn.conversation_id == conversation_id
            ).order_by(Turn.created_at.desc()).limit(limit * 2).all()
            
            turns = list(reversed(turns))
            
            history = []
            for turn in turns:
                role = turn.speaker if turn.speaker in ['user', 'assistant'] else 'assistant'
                content = turn.stt_text if role == 'user' else turn.reply_text
                if content:
                    # 加上時間戳，讓 LLM 知道每則對話的時間
                    created_at_str = ""
                    if turn.created_at:
                        from datetime import timezone, timedelta
                        tw_tz = timezone(timedelta(hours=8))
                        tw_time = turn.created_at.astimezone(tw_tz) if turn.created_at.tzinfo else turn.created_at.replace(tzinfo=timezone.utc).astimezone(tw_tz)
                        created_at_str = tw_time.strftime("%m/%d %H:%M")
                    history.append({"role": role, "content": content, "created_at": created_at_str})
            
            return history
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"get_recent_conversation_history failed: {e}")
        return []


def _ensure_user_and_conversation_exist(user_id: str, conversation_id: str) -> None:
    """
    確保用戶與會話存在於資料庫（資料庫斷線時優雅降級）
    
    Args:
        user_id: 用戶 ID
        conversation_id: 對話 ID
    """
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
    except Exception as db_err:
        logger.warning(f"Database check failed, continuing without DB: {db_err}")


# ============================================
# 核心對話處理邏輯（共用）
# ============================================

def _load_conversation_context(user_id: str, conversation_id: str, user_text: str) -> ConversationContext:
    """
    載入對話所需的所有上下文資料
    
    這是 /turn 和 /chat_text 共用的邏輯，包含：
    - 記憶檢索
    - 用戶基本資料
    - 用戶事件
    - 馬雲說過的話
    - 主動關心提示
    - 對話歷史
    
    Args:
        user_id: 用戶 ID
        conversation_id: 對話 ID
        user_text: 用戶輸入的文字（用於記憶檢索）
    
    Returns:
        ConversationContext 包含所有上下文資料
    """
    # 1. 檢索相關記憶
    logger.info("Retrieving memories...")
    memories = retrieve_memories(conversation_id, user_text)
    logger.info(f"Memories found: {len(memories)}")
    
    # 2. 載入用戶基本資料
    user_profile_context = ""
    if settings.ENABLE_USER_PROFILE:
        logger.info("Loading user profile...")
        user_profile_context = format_profile_for_prompt(user_id)
        if user_profile_context:
            logger.info(f"User profile loaded for {user_id}")
    
    # 3. 載入用戶最近事件
    user_events_context = ""
    if settings.ENABLE_USER_EVENTS:
        logger.info("Loading user events...")
        user_events_context = format_events_for_prompt(user_id)
        if user_events_context:
            logger.info(f"User events loaded for {user_id}")
    
    # 4. 載入馬雲說過的話
    jackma_actions_context = ""
    if settings.ENABLE_JACKMA_ACTIONS:
        logger.info("Loading JackMa actions...")
        jackma_actions_context = format_actions_for_prompt(user_id)
        if jackma_actions_context:
            logger.info(f"JackMa actions loaded for {user_id}")
    
    # 5. 載入主動關心提示
    proactive_care_context = ""
    if settings.ENABLE_PROACTIVE_CARE:
        logger.info("Loading proactive care context...")
        proactive_care_context = generate_proactive_care_context(user_id)
        if proactive_care_context:
            logger.info(f"Proactive care context loaded for {user_id}")
    
    # 6. 載入永久筆記
    key_notes_context = ""
    logger.info("Loading key notes...")
    key_notes_context = format_key_notes_for_prompt(user_id)
    if key_notes_context:
        logger.info(f"Key notes loaded for {user_id}")
    
    # 7. 載入對話歷史
    logger.info("Loading recent conversation history...")
    conversation_history = get_recent_conversation_history(conversation_id, limit=30)
    logger.info(f"Loaded {len(conversation_history)} recent messages")
    
    return ConversationContext(
        memories=memories,
        user_profile_context=user_profile_context,
        user_events_context=user_events_context,
        jackma_actions_context=jackma_actions_context,
        proactive_care_context=proactive_care_context,
        key_notes_context=key_notes_context,
        conversation_history=conversation_history
    )


async def _generate_response(user_text: str, context: ConversationContext) -> tuple[str, str]:
    """
    生成馬雲的回覆並合成語音
    
    Args:
        user_text: 用戶輸入的文字
        context: 對話上下文
    
    Returns:
        (assistant_text, assistant_audio_url) 回覆文字和語音 URL
    """
    # 1. LLM 生成回覆
    logger.info("Generating LLM reply...")
    assistant_text = await generate_reply(
        user_text, 
        context.memories,
        user_profile_context=context.user_profile_context,
        user_events_context=context.user_events_context,
        jackma_actions_context=context.jackma_actions_context,
        proactive_care_context=context.proactive_care_context,
        key_notes_context=context.key_notes_context,
        conversation_history=context.conversation_history
    )
    logger.info(f"LLM Reply: {assistant_text}")

    # 2. TTS 清洗（含發音修正）
    logger.info(f"[TTS] 清洗前: {assistant_text}")
    tts_text = clean_for_tts(assistant_text, use_pronunciation_fix=True)
    logger.info(f"[TTS] 清洗後: {tts_text}")

    # 3. 語音合成
    logger.info("Starting TTS synthesis...")
    assistant_audio_url = await synthesize_speech(tts_text)
    logger.info(f"TTS Complete: {assistant_audio_url}")
    
    return assistant_text, assistant_audio_url


def _schedule_background_tasks(
    background_tasks: BackgroundTasks,
    conversation_id: str,
    user_id: str,
    user_text: str,
    assistant_text: str,
    assistant_audio_url: str
) -> None:
    """
    排程背景任務：儲存對話、更新記憶、抽取資訊
    
    Args:
        background_tasks: FastAPI 背景任務管理器
        conversation_id: 對話 ID
        user_id: 用戶 ID
        user_text: 用戶輸入
        assistant_text: 馬雲回覆
        assistant_audio_url: 語音 URL
    """
    # 儲存對話紀錄
    background_tasks.add_task(save_turn, conversation_id, "user", user_text, None, user_id)
    background_tasks.add_task(save_turn, conversation_id, "assistant", assistant_text, assistant_audio_url, user_id)
    
    # 更新向量記憶
    background_tasks.add_task(
        extract_and_save_memory,
        conversation_id,
        f"用戶問：{user_text} | 大哥答：{assistant_text}",
        user_id
    )
    
    # 自動抽取資訊（如果啟用）
    if settings.ENABLE_AUTO_EXTRACT:
        background_tasks.add_task(
            extract_info_sync,
            user_id,
            user_text,
            assistant_text,
            None
        )


async def process_conversation(
    user_text: str,
    user_id: str,
    conversation_id: str,
    background_tasks: BackgroundTasks
) -> ConversationResult:
    """
    處理對話的核心邏輯（/turn 和 /chat_text 共用）
    
    流程：
    1. 載入上下文（記憶、用戶資料、事件等）
    2. 確保資料庫記錄存在
    3. 生成回覆並合成語音
    4. 排程背景任務
    
    Args:
        user_text: 用戶輸入的文字
        user_id: 用戶 ID
        conversation_id: 對話 ID
        background_tasks: 背景任務管理器
    
    Returns:
        ConversationResult 包含回覆和相關資料
    """
    # 1. 載入所有上下文（用 asyncio.to_thread 避免阻塞 event loop）
    context = await asyncio.to_thread(_load_conversation_context, user_id, conversation_id, user_text)
    
    # 2. 確保資料庫記錄存在
    logger.info("Checking DB...")
    _ensure_user_and_conversation_exist(user_id, conversation_id)
    
    # 3. 生成回覆
    assistant_text, assistant_audio_url = await _generate_response(user_text, context)
    
    # 4. 排程背景任務
    _schedule_background_tasks(
        background_tasks,
        conversation_id,
        user_id,
        user_text,
        assistant_text,
        assistant_audio_url
    )
    
    return ConversationResult(
        user_text=user_text,
        assistant_text=assistant_text,
        assistant_audio_url=assistant_audio_url,
        memories_used=context.memories
    )


# ============================================
# API 端點
# ============================================

@router.get("/conversation/history", response_model=ConversationHistoryResponse)
@limiter.limit("20/minute")
async def get_conversation_history(
    request: Request,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user)
):
    """
    取得用戶的對話歷史紀錄
    
    Args:
        limit: 每頁筆數 (預設 50，最大 100)
        offset: 跳過筆數 (用於分頁)
    
    Returns:
        對話歷史列表
    """
    user_id = current_user.id
    limit = min(limit, 200)  # 最大 200 筆
    
    try:
        from app.db.session import SessionLocal
        from app.db.models import Turn, Conversation
        
        db = SessionLocal()
        try:
            conv = db.query(Conversation).filter(
                Conversation.user_id == user_id
            ).order_by(Conversation.created_at.desc()).first()
            
            if not conv:
                return ConversationHistoryResponse(
                    messages=[ConversationMessage(role="assistant", content="「你好，我是馬雲。」")],
                    total=1,
                    has_more=False
                )
            
            # 過濾掉通話記錄（source='call'），只顯示文字模式的對話
            from sqlalchemy import or_
            text_filter = or_(Turn.source == 'text', Turn.source == None)
            
            total = db.query(Turn).filter(
                Turn.conversation_id == conv.id,
                text_filter
            ).count()
            
            # 取最新的 N 筆（降序），然後反轉成時間順序（升序）顯示
            turns = db.query(Turn).filter(
                Turn.conversation_id == conv.id,
                text_filter
            ).order_by(Turn.created_at.desc()).limit(limit).all()
            
            # 反轉成時間順序（最舊的在前面）
            turns = list(reversed(turns))
            
            messages = []
            for turn in turns:
                role = turn.speaker if turn.speaker in ['user', 'assistant'] else 'assistant'
                content = turn.stt_text if role == 'user' else turn.reply_text
                if content:
                    messages.append(ConversationMessage(
                        role=role,
                        content=content,
                        created_at=turn.created_at.isoformat() if turn.created_at else None,
                        image_url=turn.image_url if role == 'user' else None
                    ))
            
            if not messages:
                messages = [ConversationMessage(role="assistant", content="「你好，我是馬雲。」")]
            
            return ConversationHistoryResponse(
                messages=messages,
                total=total,
                has_more=(offset + limit) < total
            )
        finally:
            db.close()
    except Exception as e:
        logger.error(f"get_conversation_history failed: {e}")
        return ConversationHistoryResponse(
            messages=[ConversationMessage(role="assistant", content="「你好，我是馬雲。」")],
            total=1,
            has_more=False
        )


@router.post("/call/save-transcript")
@limiter.limit("10/minute")
async def save_call_transcript(
    request: Request,
    body: SaveCallTranscriptRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    儲存通話模式的對話記錄到資料庫
    掛斷時由前端呼叫，讓通話記憶與文字模式共通
    Turn 標記 source='call'，前端對話歷史 API 會過濾掉通話記錄
    """
    user_id = current_user.id
    conversation_id = f"conv_{user_id}"
    
    _ensure_user_and_conversation_exist(user_id, conversation_id)
    
    saved_count = 0
    for msg in body.messages:
        if not msg.content or not msg.content.strip():
            continue
        # source="call" 標記為通話來源，前端對話歷史會過濾掉
        background_tasks.add_task(
            save_turn, conversation_id, msg.role, msg.content.strip(), None, user_id, None, "call"
        )
        saved_count += 1
    
    # 將對話配對進行記憶抽取
    messages = [m for m in body.messages if m.content and m.content.strip()]
    for i in range(len(messages) - 1):
        if messages[i].role == 'user' and messages[i + 1].role == 'assistant':
            user_text = messages[i].content.strip()
            assistant_text = messages[i + 1].content.strip()
            
            background_tasks.add_task(
                extract_and_save_memory,
                conversation_id,
                f"用戶問：{user_text} | 大哥答：{assistant_text}",
                user_id
            )
            
            if settings.ENABLE_AUTO_EXTRACT:
                background_tasks.add_task(
                    extract_info_sync,
                    user_id,
                    user_text,
                    assistant_text,
                    None
                )
    
    return {"saved": saved_count, "message": "通話記錄已儲存"}


@router.get("/health")
async def health_check(request: Request):
    """檢查 API 金鑰健康狀態"""
    status = {"llm": "Unknown", "tts": "Unknown"}
    
    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        genai.get_model("models/gemini-2.5-flash")
        status["llm"] = "OK"
    except Exception:
        status["llm"] = "Error"

    try:
        async with httpx.AsyncClient() as client:
            headers = {"xi-api-key": settings.ELEVENLABS_API_KEY}
            resp = await client.get("https://api.elevenlabs.io/v1/voices", headers=headers, timeout=5.0)
            status["tts"] = "OK" if resp.status_code == 200 else "Error"
    except Exception:
        status["tts"] = "Error"
        
    return status


@router.get("/elevenlabs/token")
@limiter.limit("20/minute")
async def get_conversation_token(
    request: Request,
    participant_name: Optional[str] = None,
    agent_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """取得 ElevenLabs Conversational AI 連線 token（前端直連用）"""
    resolved_agent_id = agent_id or getattr(settings, "ELEVENLABS_AGENT_ID", None)
    if not resolved_agent_id:
        raise HTTPException(status_code=400, detail="ELEVENLABS_AGENT_ID is not configured")

    headers = {"xi-api-key": settings.ELEVENLABS_API_KEY}
    params = {"agent_id": resolved_agent_id}
    if participant_name:
        params["participant_name"] = participant_name

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.elevenlabs.io/v1/convai/conversation/token",
                headers=headers,
                params=params,
                timeout=10.0
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Failed to get conversation token")
        data = resp.json()
        token = data.get("token")
        if not token:
            raise HTTPException(status_code=502, detail="Invalid token response")
        return {"token": token}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to get conversation token")


@router.get("/elevenlabs/signed-url")
@limiter.limit("20/minute")
async def get_conversation_signed_url(
    request: Request,
    agent_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """取得 ElevenLabs Conversational AI Signed URL（WebSocket 連線用）"""
    resolved_agent_id = agent_id or getattr(settings, "ELEVENLABS_AGENT_ID", None)
    if not resolved_agent_id:
        raise HTTPException(status_code=400, detail="ELEVENLABS_AGENT_ID is not configured")

    headers = {"xi-api-key": settings.ELEVENLABS_API_KEY}
    params = {"agent_id": resolved_agent_id}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.elevenlabs.io/v1/convai/conversation/get-signed-url",
                headers=headers,
                params=params,
                timeout=10.0
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Failed to get signed URL")
        data = resp.json()
        signed_url = data.get("signed_url")
        if not signed_url:
            raise HTTPException(status_code=502, detail="Invalid signed URL response")
        return {"signed_url": signed_url}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to get signed URL")


@router.get("/elevenlabs/user-context", response_model=UserContextResponse)
@limiter.limit("20/minute")
async def get_user_context_for_voice(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    取得用戶的 context 資料，供通話模式 (ElevenLabs) 使用
    
    回傳精簡格式的用戶資料、事件、承諾、對話摘要和主動關心提示
    """
    user_id = current_user.id
    
    try:
        user_profile = ""
        upcoming_events = ""
        my_promises = ""
        recent_chat_summary = ""
        proactive_care = ""
        key_notes = ""
        
        if settings.ENABLE_USER_PROFILE:
            user_profile = format_profile_for_voice(user_id)
        
        if settings.ENABLE_USER_EVENTS:
            upcoming_events = format_events_for_voice(user_id)
        
        if settings.ENABLE_JACKMA_ACTIONS:
            my_promises = format_actions_for_voice(user_id)
        
        # 主動關心提示
        if settings.ENABLE_PROACTIVE_CARE:
            proactive_care = generate_proactive_care_context(user_id)
        
        # 永久筆記
        key_notes = format_key_notes_for_voice(user_id)
        
        conversation_id = get_or_create_conversation_id(user_id)
        # 通話模式取最近 30 條對話（與文字模式一致），讓馬雲更了解對話脈絡
        recent_history = get_recent_conversation_history(conversation_id, limit=30)
        if recent_history:
            summary_lines = []
            for msg in recent_history[-30:]:
                role_label = "用戶" if msg["role"] == "user" else "馬雲"
                # 每條最多 50 字
                content = msg["content"][:50] + "..." if len(msg["content"]) > 50 else msg["content"]
                # 加上時間戳讓馬雲有時間概念
                time_prefix = f"[{msg['created_at']}]" if msg.get("created_at") else ""
                summary_lines.append(f"{time_prefix}{role_label}：{content}")
            recent_chat_summary = " | ".join(summary_lines)
        
        return UserContextResponse(
            user_profile=user_profile,
            upcoming_events=upcoming_events,
            my_promises=my_promises,
            recent_chat_summary=recent_chat_summary,
            proactive_care=proactive_care,
            key_notes=key_notes
        )
    except Exception as e:
        logger.warning(f"get_user_context_for_voice failed: {e}")
        return UserContextResponse()


@router.post("/turn")
@limiter.limit("20/minute")
async def create_turn(
    request: Request,
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    conversation_id: Optional[str] = Form(None),
    user_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user)
):
    """
    核心 API：處理一輪語音對話
    
    流程：STT → 記憶檢索 → LLM 生成 → TTS 合成
    
    Args:
        audio: 語音檔案
        conversation_id: 對話 ID（可選）
    
    Returns:
        用戶文字、馬雲回覆、語音 URL、延遲時間
    """
    user_id = current_user.id
    start_time = time.time()

    try:
        if not conversation_id:
            conversation_id = get_or_create_conversation_id(user_id)

        logger.info(f"Processing /turn request. CID: {conversation_id}, User: {user_id}")
        # 語音轉文字
        logger.info("Starting STT...")
        user_text = await transcribe_audio(audio)
        logger.info(f"STT Result: {user_text}")

        # 處理對話（共用邏輯）
        result = await process_conversation(
            user_text=user_text,
            user_id=user_id,
            conversation_id=conversation_id,
            background_tasks=background_tasks
        )
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"/api/turn client error: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error in /api/turn: {e}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="語音或對話服務暫時不可用，請稍後再試",
        ) from e

    latency_ms = int((time.time() - start_time) * 1000)

    return {
        "user_text": result.user_text,
        "assistant_text": result.assistant_text,
        "assistant_audio_url": result.assistant_audio_url,
        "latency_ms": latency_ms,
        "memories_used": result.memories_used
    }


@router.post("/turn-stream")
@limiter.limit("20/minute")
async def create_turn_stream(
    request: Request,
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    conversation_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user)
):
    """
    串流版 /turn：SSE 逐字回傳 LLM 回覆，TTS 在最後回傳

    事件格式：
      data: {"type":"stt","text":"用戶說的話"}
      data: {"type":"chunk","text":"江"}
      data: {"type":"tts","audio_url":"/static/audio/xxx.mp3"}
      data: {"type":"done","assistant_text":"完整回覆","latency_ms":1234}
    """
    import json
    user_id = current_user.id
    start_time = time.time()

    async def event_stream():
        try:
            cid = conversation_id or get_or_create_conversation_id(user_id)

            # 1. STT（批次，通常 1-2 秒）
            user_text = await transcribe_audio(audio)
            yield f"data: {json.dumps({'type': 'stt', 'text': user_text}, ensure_ascii=False)}\n\n"

            # 2. 載入上下文
            context = await asyncio.to_thread(_load_conversation_context, user_id, cid, user_text)
            _ensure_user_and_conversation_exist(user_id, cid)

            # 3. LLM 串流
            full_text = ""
            async for chunk in generate_reply_stream(
                user_text,
                context.memories,
                user_profile_context=context.user_profile_context,
                user_events_context=context.user_events_context,
                jackma_actions_context=context.jackma_actions_context,
                proactive_care_context=context.proactive_care_context,
                key_notes_context=context.key_notes_context,
                conversation_history=context.conversation_history
            ):
                full_text += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk}, ensure_ascii=False)}\n\n"

            # 4. TTS（批次，用完整文字合成）
            tts_text = clean_for_tts(full_text, use_pronunciation_fix=True)
            audio_url = await synthesize_speech(tts_text)
            yield f"data: {json.dumps({'type': 'tts', 'audio_url': audio_url}, ensure_ascii=False)}\n\n"

            # 5. 完成
            latency_ms = int((time.time() - start_time) * 1000)
            yield f"data: {json.dumps({'type': 'done', 'assistant_text': full_text, 'latency_ms': latency_ms}, ensure_ascii=False)}\n\n"

            # 6. 背景任務
            _schedule_background_tasks(background_tasks, cid, user_id, user_text, full_text, audio_url)

        except Exception as e:
            logger.error(f"turn-stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/chat_text")
@limiter.limit("20/minute")
async def chat_text(
    request: Request,
    payload: ChatTextRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    文字對話 API
    
    Args:
        payload: 包含用戶輸入文字的請求
    
    Returns:
        用戶文字、馬雲回覆、語音 URL、延遲時間
    """
    user_id = current_user.id
    conversation_id = payload.conversation_id or get_or_create_conversation_id(user_id)
    user_text = payload.text

    logger.info(f"Processing /chat_text request. CID: {conversation_id}, User: {user_id}")
    start_time = time.time()

    try:
        # 處理對話（共用邏輯）
        result = await process_conversation(
            user_text=user_text,
            user_id=user_id,
            conversation_id=conversation_id,
            background_tasks=background_tasks
        )
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"/api/chat_text client error: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error in /api/chat_text: {e}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail="對話服務暫時不可用，請稍後再試",
        ) from e

    latency_ms = int((time.time() - start_time) * 1000)

    return {
        "user_text": result.user_text,
        "assistant_text": result.assistant_text,
        "assistant_audio_url": result.assistant_audio_url,
        "latency_ms": latency_ms,
        "memories_used": result.memories_used
    }
