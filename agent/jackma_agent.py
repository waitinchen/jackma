"""
馬雲語氣靈 — LiveKit Voice Agent
核心 Agent：Silero VAD → Deepgram STT → Claude LLM → MiniMax TTS
透過 LiveKit WebRTC 實現低延遲即時語音通話

架構：使用 lazy initialization — 首次通話時初始化 heavy 模組並 cache，
後續通話直接重用，避免 module-level 預載導致 worker 超時。
"""
import json
import logging
import os
import sys
import time
from pathlib import Path

# 確保專案根目錄在 Python 路徑中
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

from livekit import agents, rtc
from livekit.agents import AgentSession, Agent, RoomInputOptions, JobContext, WorkerOptions
from livekit.agents.voice import MetricsCollectedEvent
from livekit.plugins import google, silero, anthropic, deepgram

# MiniMax TTS — 自訂 wrapper 支援克隆聲紋
try:
    from agent.minimax_tts import MiniMaxCustomTTS
    HAS_MINIMAX = True
    logging.getLogger("jackma-agent").info("✅ MiniMax TTS wrapper imported successfully")
except Exception as e:
    HAS_MINIMAX = False
    logging.getLogger("jackma-agent").error(f"❌ MiniMax TTS import failed: {e}")

from app.core.config import settings
from app.services.llm import clean_reply_text
import re
from agent.context_builder import build_jackma_prompt
from agent.transcript_saver import save_transcript

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("jackma-agent")


# ============================================
# Lazy Cache — 首次通話初始化，後續重用
# ============================================
_cached = {
    "vad": None,
    "tts": None,
    "stt": None,
    "llm": None,
    "initialized": False,
}


def _ensure_initialized():
    """Lazy initialization — 首次呼叫時初始化所有 heavy 模組"""
    if _cached["initialized"]:
        return

    start = time.time()
    logger.info("🔧 首次初始化 heavy 模組...")

    # 1. Silero VAD
    _cached["vad"] = silero.VAD.load(
        min_silence_duration=0.4,
        prefix_padding_duration=0.3,
        min_speech_duration=0.1,
        activation_threshold=0.5,
    )
    logger.info(f"  VAD 初始化完成 ({time.time() - start:.1f}s)")

    # 2. MiniMax TTS — 馬雲克隆聲紋
    if not HAS_MINIMAX or not settings.MINIMAX_API_KEY:
        logger.error("MiniMax TTS 不可用！")
        raise RuntimeError("MiniMax TTS 必須可用")
    _cached["tts"] = MiniMaxCustomTTS(
        api_key=settings.MINIMAX_API_KEY,
        group_id=settings.MINIMAX_GROUP_ID,
        voice_id=settings.MINIMAX_VOICE_ID,
        model="speech-02-turbo",
        speed=1.0,
    )
    logger.info(f"  TTS: MiniMax Custom (voice={settings.MINIMAX_VOICE_ID})")

    # 3. Deepgram STT
    deepgram_key = os.environ.get("DEEPGRAM_API_KEY", "")
    stt_keywords = [("马云", 10.0)]
    if deepgram_key:
        _cached["stt"] = deepgram.STT(
            model="nova-2", language="zh", interim_results=True,
            keywords=stt_keywords, api_key=deepgram_key,
        )
        logger.info("  STT: Deepgram Nova-2")
    else:
        gemini_key = settings.GEMINI_API_KEY or os.environ.get("GOOGLE_API_KEY", "")
        if gemini_key and not os.environ.get("GOOGLE_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = gemini_key
        _cached["stt"] = google.STT(
            languages=["cmn-Hans-CN"], interim_results=True, keywords=stt_keywords,
        )
        logger.info("  STT: Google (fallback)")

    # 4. Claude LLM
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        _cached["llm"] = anthropic.LLM(
            model="claude-haiku-4-5-20251001", api_key=anthropic_key, temperature=0.7,
        )
        logger.info("  LLM: Claude Haiku 4.5")
    else:
        gemini_key = settings.GEMINI_API_KEY or os.environ.get("GOOGLE_API_KEY", "")
        _cached["llm"] = google.LLM(
            model="gemini-2.5-flash", temperature=0.7, api_key=gemini_key,
        )
        logger.info("  LLM: Gemini 2.5 Flash (fallback)")

    # 確保 GOOGLE_API_KEY
    gemini_key = settings.GEMINI_API_KEY or os.environ.get("GOOGLE_API_KEY", "")
    if gemini_key and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = gemini_key

    _cached["initialized"] = True
    logger.info(f"🔧 所有模組初始化完成！耗時 {time.time() - start:.1f}s")


# ============================================
# TTS 發音修正
# ============================================

PRONUNCIATION_FIXES = {"老本行": "老本杭"}

async def pronunciation_transform(text_stream):
    buffer = ""
    max_key_len = max(len(k) for k in PRONUNCIATION_FIXES) if PRONUNCIATION_FIXES else 0
    async for chunk in text_stream:
        buffer += chunk
        if len(buffer) <= max_key_len:
            continue
        for old, new in PRONUNCIATION_FIXES.items():
            buffer = buffer.replace(old, new)
        flush_to = len(buffer) - max_key_len
        yield buffer[:flush_to]
        buffer = buffer[flush_to:]
    if buffer:
        for old, new in PRONUNCIATION_FIXES.items():
            buffer = buffer.replace(old, new)
        yield buffer


# ============================================
# Agent 類別
# ============================================

class JackMaAgent:
    """馬雲語氣靈 Agent — 管理通話生命周期與指標"""

    def __init__(self):
        self.transcript: list[dict] = []
        self.user_id: str | None = None
        self.call_start_time: float = 0
        self.metrics: dict = {
            "stt_latency_ms": [], "llm_ttft_ms": [], "tts_ttfb_ms": [],
            "total_response_ms": [], "interruptions": 0, "turns": 0,
        }

    @staticmethod
    def clean_stage_directions(text: str) -> str:
        text = re.sub(r'[（(][^）)]{1,10}[）)]', '', text)
        text = re.sub(r'\*[^*]{1,10}\*', '', text)
        return text.strip()

    def on_user_speech(self, text: str):
        if text and text.strip():
            self.transcript.append({"role": "user", "content": text.strip()})
            self.metrics["turns"] += 1
            logger.info(f"[User] {text.strip()[:80]}")

    def on_agent_speech(self, text: str):
        if text and text.strip():
            cleaned = clean_reply_text(text.strip())
            cleaned = self.clean_stage_directions(cleaned)
            if cleaned:
                self.transcript.append({"role": "assistant", "content": cleaned})
                logger.info(f"[Agent] {cleaned[:80]}")

    def log_metrics_summary(self):
        m = self.metrics
        duration = time.time() - self.call_start_time if self.call_start_time else 0
        def avg(lst): return round(sum(lst) / len(lst)) if lst else 0
        logger.info(
            f"📊 通話指標摘要:\n  通話時長: {duration:.0f}s\n  總 turns: {m['turns']}\n"
            f"  插話次數: {m['interruptions']}\n  STT: {avg(m['stt_latency_ms'])}ms\n"
            f"  LLM: {avg(m['llm_ttft_ms'])}ms\n  TTS: {avg(m['tts_ttfb_ms'])}ms\n"
            f"  端到端: {avg(m['total_response_ms'])}ms"
        )


# ============================================
# TTS 語言指令
# ============================================

TTS_LANGUAGE_INSTRUCTION = (
    "\n\n【重要：语音输出规则】\n"
    "你的回复会被语音合成（TTS）朗读出来。为了让发音自然：\n"
    "1. 所有回复必须使用**简体中文**（不是繁体）\n"
    "2. 避免使用书面语，用口语化的表达\n"
    "3. 绝对不要在回复中包含括号、引号、星号、stage directions\n"
    "4. 绝对不要写「（思考）」「（停顿）」「（笑）」这类括号内的动作描述\n"
    "5. 数字用中文念法（例如「三百五」不是「350」）\n"
    "6. 回复要简短有力，像真人说话，不要长篇大论\n"
)


# ============================================
# Entrypoint
# ============================================

async def entrypoint(ctx: JobContext):
    """LiveKit Agent 入口點"""
    logger.info(f"🚀 Received job dispatch! room: {ctx.room.name}")

    # Lazy init — 首次通話初始化，後續重用
    _ensure_initialized()

    jackma = JackMaAgent()

    await ctx.connect()
    logger.info("Connected to room, waiting for participant...")

    participant = await ctx.wait_for_participant()
    logger.info(f"Participant joined: {participant.identity}")

    user_id = participant.identity
    jackma.user_id = user_id

    if participant.metadata:
        try:
            meta = json.loads(participant.metadata)
            user_id = meta.get("user_id", user_id)
            jackma.user_id = user_id
            logger.info(f"User metadata: {meta}")
        except (json.JSONDecodeError, TypeError):
            pass

    # 組裝馬雲系統提示
    logger.info(f"Building JackMa prompt for user {user_id}...")
    system_prompt = build_jackma_prompt(user_id)
    logger.info(f"System prompt built: {len(system_prompt)} chars")

    full_prompt = system_prompt + TTS_LANGUAGE_INSTRUCTION

    # 斷線時儲存 transcript
    @ctx.room.on("disconnected")
    def on_disconnected():
        jackma.log_metrics_summary()
        logger.info(f"Room disconnected. Saving transcript ({len(jackma.transcript)} messages)...")
        if jackma.transcript and jackma.user_id:
            try:
                saved = save_transcript(jackma.user_id, jackma.transcript)
                logger.info(f"Transcript saved: {saved} messages")
            except Exception as e:
                logger.error(f"Failed to save transcript: {e}")

    jackma.call_start_time = time.time()

    # 建立 session — 使用 cached 元件
    session = AgentSession(
        stt=_cached["stt"],
        llm=_cached["llm"],
        tts=_cached["tts"],
        vad=_cached["vad"],
        tts_text_transforms=[pronunciation_transform],
    )

    # 事件監聽
    _last_user_speech_time = [0.0]

    @session.on("user_input_transcribed")
    def on_transcribed(event):
        if hasattr(event, 'text') and event.text:
            _last_user_speech_time[0] = time.time()
            logger.info(f"⏱️ [STT] 用戶說: {event.text[:40]}")
            jackma.on_user_speech(event.text)

    @session.on("agent_speech_committed")
    def on_committed(event):
        if hasattr(event, 'text') and event.text:
            if _last_user_speech_time[0] > 0:
                rt = time.time() - _last_user_speech_time[0]
                logger.info(f"⏱️ [LLM+TTS] 回覆: {event.text[:40]} (延遲 {rt:.1f}s)")
            else:
                logger.info(f"⏱️ [LLM+TTS] 回覆: {event.text[:40]}")
            jackma.on_agent_speech(event.text)

    @session.on("agent_speech_interrupted")
    def on_interrupted(event):
        jackma.metrics["interruptions"] += 1
        logger.info(f"🔇 Agent 被插話打斷（第 {jackma.metrics['interruptions']} 次）")

    # 啟動 Agent
    await session.start(
        room=ctx.room,
        agent=Agent(instructions=full_prompt),
        room_input_options=RoomInputOptions(close_on_disconnect=False),
    )

    # 開場白
    await session.generate_reply(
        instructions="用户刚接通电话。用马云的语气自然地打个招呼，像跟一个创业者朋友接电话一样。不要太正式，不要自我介绍。用简体中文回复。"
    )

    try:
        await ctx.room.local_participant.publish_data(
            json.dumps({"type": "tts_info", "provider": "MiniMax", "model": "speech-02-turbo"}).encode(),
        )
    except Exception:
        pass

    logger.info("Agent started and greeting sent.")

    # 靜默檢測
    import asyncio
    _last_activity_time = [time.time()]

    _orig_on_transcribed = on_transcribed
    @session.on("user_input_transcribed")
    def on_transcribed_with_activity(event):
        _last_activity_time[0] = time.time()
        _orig_on_transcribed(event)

    async def silence_watchdog():
        SILENCE_THRESHOLD = 240
        FINAL_WAIT = 60
        while True:
            await asyncio.sleep(10)
            try:
                state = ctx.room.connection_state
                if isinstance(state, int) and state != 1:
                    break
                elif hasattr(state, 'value') and state.value != 1:
                    break
            except Exception:
                break

            silence_duration = time.time() - _last_activity_time[0]
            if silence_duration > SILENCE_THRESHOLD:
                logger.info(f"⏰ 靜默 {silence_duration:.0f}s")
                try:
                    await ctx.room.local_participant.publish_data(
                        json.dumps({"type": "silence_warning"}).encode(),
                    )
                except Exception:
                    pass
                try:
                    await session.generate_reply(
                        instructions="用户已经很久没说话了。用马云的语气自然地问一下对方还在不在。用简体中文。"
                    )
                except RuntimeError:
                    break
                turns_before = jackma.metrics["turns"]
                await asyncio.sleep(FINAL_WAIT)
                if jackma.metrics["turns"] == turns_before:
                    logger.info("⏰ 用戶無回應，自動掛斷")
                    try:
                        await ctx.room.local_participant.publish_data(
                            json.dumps({"type": "auto_hangup"}).encode(),
                        )
                    except Exception:
                        pass
                    try:
                        await session.generate_reply(
                            instructions="用户还是没回应。用马云的语气简短说一句再见。用简体中文。"
                        )
                    except RuntimeError:
                        break
                    await asyncio.sleep(5)
                    await ctx.room.disconnect()
                    return
                else:
                    _last_activity_time[0] = time.time()

    asyncio.create_task(silence_watchdog())
