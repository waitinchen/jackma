"""
馬雲語氣靈 — LiveKit Voice Agent
核心 Agent：Silero VAD → Deepgram STT → Claude LLM → MiniMax TTS
透過 LiveKit WebRTC 實現低延遲即時語音通話
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
        """移除 LLM 輸出的 stage directions：（思考）（笑）（停頓）等"""
        # 移除中文括號內容：（思考）（停頓）（笑）
        text = re.sub(r'[（(][^）)]{1,10}[）)]', '', text)
        # 移除星號動作：*思考* *笑*
        text = re.sub(r'\*[^*]{1,10}\*', '', text)
        return text.strip()

    def on_user_speech(self, text: str):
        """用戶說話時收集 transcript"""
        if text and text.strip():
            self.transcript.append({"role": "user", "content": text.strip()})
            self.metrics["turns"] += 1
            logger.info(f"[User] {text.strip()[:80]}")

    def on_agent_speech(self, text: str):
        """Agent 回覆時收集 transcript（自動移除 stage directions）"""
        if text and text.strip():
            cleaned = clean_reply_text(text.strip())
            cleaned = self.clean_stage_directions(cleaned)
            if cleaned:
                self.transcript.append({"role": "assistant", "content": cleaned})
                logger.info(f"[Agent] {cleaned[:80]}")

    def log_metrics_summary(self):
        """通話結束時輸出延遲指標摘要"""
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


async def entrypoint(ctx: JobContext):
    """LiveKit Agent 入口點"""
    logger.info(f"🚀 Received job dispatch! room: {ctx.room.name}")
    logger.info(f"Agent entrypoint called, room: {ctx.room.name}")

    jackma = JackMaAgent()

    # 等待用戶加入房間
    await ctx.connect()
    logger.info("Connected to room, waiting for participant...")

    # 等一下讓 participant 加入
    participant = await ctx.wait_for_participant()
    logger.info(f"Participant joined: {participant.identity}")

    # 從 participant metadata 取得 user_id
    user_id = participant.identity  # identity 就是 user_id
    jackma.user_id = user_id

    if participant.metadata:
        try:
            meta = json.loads(participant.metadata)
            user_id = meta.get("user_id", user_id)
            jackma.user_id = user_id
            logger.info(f"User metadata: {meta}")
        except (json.JSONDecodeError, TypeError):
            pass

    # 組裝馬雲系統提示（包含用戶上下文）
    logger.info(f"Building JackMa prompt for user {user_id}...")
    system_prompt = build_jackma_prompt(user_id)
    logger.info(f"System prompt built: {len(system_prompt)} chars")

    # P1: 配置 VAD 參數 — 優化 turn detection
    # min_silence_duration: 停頓多久才判定為「講完」（越長越不容易搶話）
    # prefix_padding_duration: 保留語音開頭的靜音段（避免截斷開頭字）
    vad = silero.VAD.load(
        min_silence_duration=0.4,       # 400ms 靜音才判定講完（降低 200ms 體感延遲）
        prefix_padding_duration=0.3,    # 保留 300ms 開頭
        min_speech_duration=0.1,        # 最短語音長度
        activation_threshold=0.5,       # 語音偵測門檻
    )

    # ===== 馬雲語氣靈 TTS — 只用 MiniMax，無 fallback =====
    JACKMA_VOICE_ID = "moss_audio_062371e7-2c0c-11f1-a44a-c658cff0ef65"

    if not HAS_MINIMAX or not settings.MINIMAX_API_KEY:
        logger.error("MiniMax TTS 不可用！HAS_MINIMAX=%s, KEY=%s", HAS_MINIMAX, bool(settings.MINIMAX_API_KEY))
        raise RuntimeError("MiniMax TTS unavailable — no fallback for JackMa agent")

    tts = MiniMaxCustomTTS(
        api_key=settings.MINIMAX_API_KEY,
        group_id=settings.MINIMAX_GROUP_ID,
        voice_id=JACKMA_VOICE_ID,
        model="speech-02-turbo",
        speed=1.0,
    )
    logger.info(f"TTS: MiniMax Custom (voice_id={JACKMA_VOICE_ID})")
    tts_info = {"provider": "MiniMax", "model": "speech-02-turbo"}

    # 確保 GOOGLE_API_KEY 環境變數存在（LiveKit Google plugin 需要）
    gemini_key = settings.GEMINI_API_KEY or os.environ.get("GOOGLE_API_KEY", "")
    if gemini_key and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = gemini_key
        logger.info("Set GOOGLE_API_KEY from GEMINI_API_KEY")

    # P3: Deepgram Nova-2 STT — 中文支援，無串流時間限制
    # Nova-3 中文尚未支援（400 error），用 Nova-2
    stt_keywords = [("马云", 10.0)]
    deepgram_key = os.environ.get("DEEPGRAM_API_KEY", "")
    if deepgram_key:
        logger.info(f"STT: Deepgram Nova-2 (keywords: {stt_keywords})")
        stt = deepgram.STT(
            model="nova-2",
            language="zh",
            interim_results=True,
            keywords=stt_keywords,
            api_key=deepgram_key,
        )
    else:
        # Fallback to Google STT
        logger.info(f"STT: Google (Deepgram key not set, fallback)")
        stt = google.STT(
            languages=["cmn-Hans-CN"],
            interim_results=True,
            keywords=stt_keywords,
        )

    # Claude LLM（Haiku 4.5 — 快速、低延遲）
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        logger.info("LLM: Claude Haiku 4.5")
        llm = anthropic.LLM(
            model="claude-haiku-4-5-20251001",
            api_key=anthropic_key,
            temperature=0.7,
        )
    else:
        # Fallback to Gemini
        logger.info("LLM: Gemini 2.5 Flash (Anthropic key not set)")
        llm = google.LLM(
            model="gemini-2.5-flash",
            temperature=0.7,
            api_key=gemini_key,
        )

    # 房間斷線時儲存 transcript 和指標
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

    # 記錄通話開始時間
    jackma.call_start_time = time.time()

    # TTS 語言指令：LLM 用簡體中文回覆（TTS 發音正確），前端做簡→繁顯示
    tts_language_instruction = (
        "\n\n【重要：语音输出规则】\n"
        "你的回复会被语音合成（TTS）朗读出来。为了让发音自然：\n"
        "1. 所有回复必须使用**简体中文**（不是繁体）\n"
        "2. 避免使用书面语，用口语化的表达\n"
        "3. 绝对不要在回复中包含括号、引号、星号、stage directions\n"
        "4. 绝对不要写「（思考）」「（停顿）」「（笑）」这类括号内的动作描述\n"
        "5. 数字用中文念法（例如「三百五」不是「350」）\n"
        "6. 回复要简短有力，像真人说话，不要长篇大论\n"
    )
    full_prompt = system_prompt + tts_language_instruction

    # TTS 發音修正：自訂 async generator 替換容易唸錯的詞
    # 不依賴 livekit.agents.voice.text_transforms（Docker 容器沒有這個模組）
    PRONUNCIATION_FIXES = {
        "老本行": "老本杭",  # 多音字消歧：「行」háng 被念成 xíng
        # "影帝": 無解，flash_v2_5 系統性念錯「影」，等 eleven_v3 支援
    }

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

    logger.info(f"TTS 發音修正表: {len(PRONUNCIATION_FIXES)} 組")

    session = AgentSession(
        stt=stt,
        llm=llm,
        tts=tts,
        vad=vad,
        tts_text_transforms=[pronunciation_transform],
    )

    # 事件監聽：收集 transcript + 計時
    _last_user_speech_time = [0.0]  # 用 list 讓 closure 可修改

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
        agent=Agent(
            instructions=full_prompt,
        ),
        room_input_options=RoomInputOptions(close_on_disconnect=False),
    )

    # 生成開場白（簡體中文）
    await session.generate_reply(
        instructions="用户刚接通电话。用马云的语气自然地打个招呼，像跟一个创业者朋友接电话一样。不要太正式，不要自我介绍。用简体中文回复。"
    )

    # 通知前端 TTS 資訊
    try:
        await ctx.room.local_participant.publish_data(
            json.dumps({"type": "tts_info", **tts_info}).encode(),
        )
    except Exception:
        pass

    logger.info("Agent started and greeting sent.")

    # 靜默檢測：240 秒無新對話 → 詢問 → 再 60 秒無回應 → 掛斷
    import asyncio
    _last_activity_time = [time.time()]  # 追蹤最後一次互動

    # 在 STT 回調中更新最後互動時間
    _orig_on_transcribed = on_transcribed
    @session.on("user_input_transcribed")
    def on_transcribed_with_activity(event):
        _last_activity_time[0] = time.time()
        _orig_on_transcribed(event)

    async def silence_watchdog():
        """監控用戶靜默，超時自動掛斷"""
        SILENCE_THRESHOLD = 240  # 秒
        FINAL_WAIT = 60          # 詢問後再等幾秒

        while True:
            await asyncio.sleep(10)  # 每 10 秒檢查一次
            # 檢查房間是否還連線
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
                # 通知前端：靜默提醒
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
                # 等 60 秒看有沒有回應
                turns_before = jackma.metrics["turns"]
                await asyncio.sleep(FINAL_WAIT)
                if jackma.metrics["turns"] == turns_before:
                    logger.info("⏰ 用戶無回應，自動掛斷")
                    # 通知前端：自動掛斷
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
                    await asyncio.sleep(5)  # 等 TTS 播完
                    await ctx.room.disconnect()
                    return
                else:
                    logger.info("✅ 用戶回應了，繼續通話")
                    _last_activity_time[0] = time.time()  # 重置靜默計時

    # 啟動靜默監控
    asyncio.create_task(silence_watchdog())
# trigger rebuild 1774420420
# force agent restart 1774482745
# rebuild 1774520514
# claude haiku 1774525729
# deepgram key fix 1774703400
# trigger deploy 1774947183
# livekit secrets updated 1775004458
# force livekit secrets reload 1775062196
