"""
馬雲語氣靈 — LiveKit Voice Agent
核心 Agent：Silero VAD → Deepgram STT → Claude LLM → MiniMax TTS
透過 LiveKit WebRTC 實現低延遲即時語音通話

架構：所有 heavy 模組（VAD, STT, LLM, TTS）在 Agent 啟動時預載，
通話連線時只做輕量操作（查 DB 組裝 prompt + 建 session）。
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
# 預載 Heavy 模組（Agent 啟動時執行一次）
# ============================================

logger.info("🔧 預載 heavy 模組...")
_preload_start = time.time()

# 1. Silero VAD — ML 模型，載入需 3-5 秒
_vad = silero.VAD.load(
    min_silence_duration=0.4,
    prefix_padding_duration=0.3,
    min_speech_duration=0.1,
    activation_threshold=0.5,
)
logger.info(f"  VAD 預載完成 ({time.time() - _preload_start:.1f}s)")

# 2. MiniMax TTS — 馬雲克隆聲紋（唯一選項）
if not HAS_MINIMAX or not settings.MINIMAX_API_KEY:
    logger.error("MiniMax TTS 不可用！HAS_MINIMAX=%s, KEY=%s", HAS_MINIMAX, bool(settings.MINIMAX_API_KEY))
    raise RuntimeError("MiniMax TTS 必須可用，馬雲語氣靈不支援其他 TTS")

_tts = MiniMaxCustomTTS(
    api_key=settings.MINIMAX_API_KEY,
    group_id=settings.MINIMAX_GROUP_ID,
    voice_id=settings.MINIMAX_VOICE_ID,
    model="speech-02-turbo",
    speed=1.0,
)
logger.info(f"  TTS 預載完成: MiniMax Custom (voice={settings.MINIMAX_VOICE_ID[:20]}...)")

# 3. Deepgram STT
_deepgram_key = os.environ.get("DEEPGRAM_API_KEY", "")
_stt_keywords = [("马云", 10.0)]
if _deepgram_key:
    _stt = deepgram.STT(
        model="nova-2",
        language="zh",
        interim_results=True,
        keywords=_stt_keywords,
        api_key=_deepgram_key,
    )
    logger.info(f"  STT 預載完成: Deepgram Nova-2")
else:
    _gemini_key = settings.GEMINI_API_KEY or os.environ.get("GOOGLE_API_KEY", "")
    if _gemini_key and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = _gemini_key
    _stt = google.STT(
        languages=["cmn-Hans-CN"],
        interim_results=True,
        keywords=_stt_keywords,
    )
    logger.info(f"  STT 預載完成: Google (fallback)")

# 4. Claude LLM
_anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
if _anthropic_key:
    _llm = anthropic.LLM(
        model="claude-haiku-4-5-20251001",
        api_key=_anthropic_key,
        temperature=0.7,
    )
    logger.info(f"  LLM 預載完成: Claude Haiku 4.5")
else:
    _gemini_key = settings.GEMINI_API_KEY or os.environ.get("GOOGLE_API_KEY", "")
    _llm = google.LLM(
        model="gemini-2.5-flash",
        temperature=0.7,
        api_key=_gemini_key,
    )
    logger.info(f"  LLM 預載完成: Gemini 2.5 Flash (fallback)")

# 5. 確保 GOOGLE_API_KEY 環境變數存在
_gemini_key = settings.GEMINI_API_KEY or os.environ.get("GOOGLE_API_KEY", "")
if _gemini_key and not os.environ.get("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = _gemini_key

# TTS 發音修正表
PRONUNCIATION_FIXES = {
    "老本行": "老本杭",
}

logger.info(f"🔧 所有 heavy 模組預載完成！總耗時 {time.time() - _preload_start:.1f}s")


# ============================================
# TTS 發音修正 transform
# ============================================

async def pronunciation_transform(text_stream):
    """在 LLM 串流送進 TTS 前，替換發音錯誤的詞"""
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
            "stt_latency_ms": [],
            "llm_ttft_ms": [],
            "tts_ttfb_ms": [],
            "total_response_ms": [],
            "interruptions": 0,
            "turns": 0,
        }

    @staticmethod
    def clean_stage_directions(text: str) -> str:
        """移除 LLM 輸出的 stage directions"""
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
        def avg(lst):
            return round(sum(lst) / len(lst)) if lst else 0
        logger.info(
            f"📊 通話指標摘要:\n"
            f"  通話時長: {duration:.0f}s\n"
            f"  總 turns: {m['turns']}\n"
            f"  插話次數: {m['interruptions']}\n"
            f"  STT 平均延遲: {avg(m['stt_latency_ms'])}ms\n"
            f"  LLM 首 token: {avg(m['llm_ttft_ms'])}ms\n"
            f"  TTS 首音訊: {avg(m['tts_ttfb_ms'])}ms\n"
            f"  端到端回應: {avg(m['total_response_ms'])}ms"
        )


# ============================================
# TTS 語言指令（固定，不用每次組裝）
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
# Entrypoint — 通話建立時只做輕量操作
# ============================================

async def entrypoint(ctx: JobContext):
    """LiveKit Agent 入口點 — 使用預載的 VAD/STT/LLM/TTS"""
    logger.info(f"🚀 Received job dispatch! room: {ctx.room.name}")

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

    # 組裝馬雲系統提示（唯一需要查 DB 的步驟）
    logger.info(f"Building JackMa prompt for user {user_id}...")
    system_prompt = build_jackma_prompt(user_id)
    logger.info(f"System prompt built: {len(system_prompt)} chars")

    full_prompt = system_prompt + TTS_LANGUAGE_INSTRUCTION

    # 房間斷線時儲存 transcript
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

    # 建立 session — 使用預載的元件
    session = AgentSession(
        stt=_stt,
        llm=_llm,
        tts=_tts,
        vad=_vad,
        tts_text_transforms=[pronunciation_transform],
    )

    # 事件監聽
    _last_user_speech_time = [0.0]

    @session.on("user_input_transcribed")
    def on_transcribed(event):
        if hasattr(event, 'text') and event.text:
            _last_user_speech_time[0] = time.time()
            stt_lag = time.time() - jackma.call_start_time
            logger.info(f"⏱️ [STT] 用戶說: {event.text[:40]} (通話 {stt_lag:.1f}s)")
            jackma.on_user_speech(event.text)

    @session.on("agent_speech_committed")
    def on_committed(event):
        if hasattr(event, 'text') and event.text:
            if _last_user_speech_time[0] > 0:
                response_time = time.time() - _last_user_speech_time[0]
                logger.info(f"⏱️ [LLM+TTS] 回覆: {event.text[:40]} (延遲 {response_time:.1f}s)")
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

    # 生成開場白
    await session.generate_reply(
        instructions="用户刚接通电话。用马云的语气自然地打个招呼，像跟一个创业者朋友接电话一样。不要太正式，不要自我介绍。用简体中文回复。"
    )

    # 通知前端 TTS 資訊
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
                logger.info(f"⏰ 靜默 {silence_duration:.0f}s，詢問用戶是否在線...")
                try:
                    await ctx.room.local_participant.publish_data(
                        json.dumps({"type": "silence_warning"}).encode(),
                    )
                except Exception:
                    pass
                try:
                    await session.generate_reply(
                        instructions="用户已经很久没说话了。用马云的语气自然地问一下对方还在不在，例如「喂，还在吗？怎么不说话了？」用简体中文。"
                    )
                except RuntimeError as e:
                    logger.warning(f"⏰ silence_watchdog: session 已結束，安全退出 ({e})")
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
                            instructions="用户还是没回应。用马云的语气简短说一句再见，然后挂电话。例如「好吧，那先这样，有事再打给我。」用简体中文。"
                        )
                    except RuntimeError as e:
                        logger.warning(f"⏰ silence_watchdog: session 已結束，安全退出 ({e})")
                        break
                    await asyncio.sleep(5)
                    await ctx.room.disconnect()
                    return
                else:
                    logger.info("✅ 用戶回應了，繼續通話")
                    _last_activity_time[0] = time.time()

    asyncio.create_task(silence_watchdog())
