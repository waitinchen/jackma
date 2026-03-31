import os

# Use absolute paths for everything
target_path = r'C:\Users\waiti\.cursor\worktrees\jackma\und\web_chat_api.py'

web_chat_api_content = r'''"""
Backend API for JackMa Voice Spirit Web Interface
"""
# Version: 1.1.8 (Absolute Path Fix)
import os, uuid, time, requests, sys, traceback
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy.orm import Session

load_dotenv()
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from modules.llm_emotion_router import llm_emotion_route
from modules.autonomous_emotion import autonomous_emotion_route, get_global_agent
from modules.speech_tag_mapper import extract_tags_from_text, map_tags_to_voice_settings
from modules.soft_ling import process_with_soft_ling, detect_soft_ling_invocation, get_soft_ling_opening, generate_soft_ling_reply
from modules.jackma import generate_jackma_reply
from eleven_tts import generate_speech, API_KEY, VOICE_ID
from app.db.session import SessionLocal, engine
from app.db.models import Base, Turn, Conversation, MemorySummary, User as DBUser

# Initialize database schema
Base.metadata.create_all(bind=engine)

app = FastAPI(title="\u99ac\u96f2\u8a9e\u6c23\u9748\u667a\u80fd\u5206\u8eab API", version="1.1.8")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

AUDIO_DIR = Path("public/audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR = Path("web_static")
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

class ChatRequest(BaseModel):
    text: str
    use_llm: bool = True
    provider: str = "openai"
    autonomy_mode: bool = True
    autonomy_level: float = 0.7
    use_soft_ling: bool = True

class ChatResponse(BaseModel):
    status: str
    text: str
    tagged_text: str
    audio_url: str
    message: str
    autonomy_stats: Optional[Dict] = None
    is_invocation: bool = False
    agent_name: str = "JackMa"
    opening: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    status: str
    message: str
    token: Optional[str] = None

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/api/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    if request.username == "jackma" and request.password == "1688":
        return LoginResponse(status="success", message="OK", token="jackma_master_token")
    return LoginResponse(status="error", message="Invalid credentials")

@app.get("/api/history")
async def get_history(db: Session = Depends(get_db)):
    history = db.query(Turn).order_by(Turn.timestamp.desc()).limit(100).all()
    return [{"role": t.role, "content": t.content, "timestamp": t.timestamp.isoformat()} for t in history]

@app.get("/api/summaries")
async def get_summaries(db: Session = Depends(get_db)):
    summaries = db.query(MemorySummary).order_by(MemorySummary.created_at.desc()).all()
    return [{"content": s.content, "timestamp": s.created_at.isoformat()} for s in summaries]

@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, db: Session = Depends(get_db)):
    try:
        conv_id = "default_conv"
        conv = db.query(Conversation).filter(Conversation.id == conv_id).first()
        if not conv:
            conv = Conversation(id=conv_id)
            db.add(conv); db.commit()

        # Save user input
        user_turn = Turn(role="user", content=request.text, conversation_id=conv_id)
        db.add(user_turn); db.commit()

        is_invocation = detect_soft_ling_invocation(request.text) if request.use_soft_ling else False
        reply_text = request.text
        agent_name = "\u99ac\u96f2" # JackMa
        
        if request.use_soft_ling and request.use_llm:
            reply_text = generate_soft_ling_reply(request.text, provider=request.provider)
            agent_name = "\u82b1\u5c0f\u8edf" # Xiaoruan
        elif request.use_llm:
            reply_text = generate_jackma_reply(request.text, provider=request.provider)
            agent_name = "\u99ac\u96f2"

        if request.use_soft_ling:
            res = process_with_soft_ling(reply_text, use_llm=request.use_llm)
            tagged_text = res["tagged_text"]; voice_settings = res["voice_settings"]
        elif request.autonomy_mode:
            agent = get_global_agent(autonomy_level=request.autonomy_level)
            tagged_text = autonomous_emotion_route(reply_text, autonomy_level=request.autonomy_level, use_llm=request.use_llm, agent=agent)
            tags = extract_tags_from_text(tagged_text); voice_settings = map_tags_to_voice_settings(tags)
        else:
            tagged_text = llm_emotion_route(reply_text, provider=request.provider, fallback_to_rule=True)
            tags = extract_tags_from_text(tagged_text); voice_settings = map_tags_to_voice_settings(tags)
        
        filename = f"chat_{uuid.uuid4().hex[:8]}.mp3"
        filepath = AUDIO_DIR / filename
        
        if not VOICE_ID: raise HTTPException(status_code=500, detail="Voice ID not set")
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream"
        headers = {"xi-api-key": API_KEY, "Content-Type": "application/json"}
        payload = {"model_id": "eleven_turbo_v2_5", "text": tagged_text, "voice_settings": voice_settings}
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code != 200: raise HTTPException(status_code=response.status_code, detail=f"TTS Error: {response.text}")
        
        with open(filepath, "wb") as f: f.write(response.content)
        
        # Save assistant turn
        assistant_turn = Turn(role="assistant", content=reply_text, conversation_id=conv_id)
        db.add(assistant_turn); db.commit()

        # Trigger summary every 20 turns
        total_turns = db.query(Turn).count()
        if total_turns > 0 and total_turns % 20 == 0:
            recent = db.query(Turn).order_by(Turn.timestamp.desc()).limit(20).all()
            recent.reverse()
            ctx = "\n".join([f"{t.role}: {t.content}" for t in recent])
            summary_prompt = "\u8acb\u4ee5\u99ac\u96f2\u5927\u54e5\u89d2\u5ea6\uff0c\u7e3d\u7d50\u6700\u8fd1\u5c0d\u8a71\u7cbe\u83ef\uff1a\n\n" + ctx
            summary_text = generate_jackma_reply(summary_prompt)
            db.add(MemorySummary(content=summary_text)); db.commit()

        return ChatResponse(status="success", text=reply_text, tagged_text=tagged_text, audio_url=f"/audio/{filename}", message="OK", agent_name=agent_name, is_invocation=is_invocation)
        
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
@app.get("/healthz")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
'''

try:
    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(web_chat_api_content)
    print("Success: web_chat_api.py written with absolute path.")
except Exception as e:
    print(f"Error writing to {target_path}: {e}")
