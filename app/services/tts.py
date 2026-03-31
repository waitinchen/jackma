import os
import asyncio
import time
import logging
import httpx
from pathlib import Path
from app.core.config import settings

logger = logging.getLogger(__name__)

# 取得專案根目錄的絕對路徑
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# TTS 音檔保留時間（秒），超過即清理
AUDIO_MAX_AGE_SECONDS = 600  # 10 分鐘

# MiniMax TTS API
MINIMAX_TTS_URL = "https://api.minimax.chat/v1/t2a_v2"


def _cleanup_old_audio_files():
    """清理超過 AUDIO_MAX_AGE_SECONDS 的舊 TTS 音檔"""
    audio_dir = BASE_DIR / "static" / "audio"
    if not audio_dir.exists():
        return
    now = time.time()
    try:
        for f in audio_dir.glob("reply_*.mp3"):
            if now - f.stat().st_mtime > AUDIO_MAX_AGE_SECONDS:
                f.unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"清理舊音檔失敗: {e}")


async def _minimax_synthesize(text: str) -> bytes:
    """使用 MiniMax T2A v2 API 合成語音"""
    url = f"{MINIMAX_TTS_URL}?GroupId={settings.MINIMAX_GROUP_ID}"
    headers = {
        "Authorization": f"Bearer {settings.MINIMAX_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "speech-02-turbo",
        "text": text,
        "stream": False,
        "voice_setting": {
            "voice_id": settings.MINIMAX_VOICE_ID,
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    if data.get("base_resp", {}).get("status_code", 0) != 0:
        err_msg = data.get("base_resp", {}).get("status_msg", "未知錯誤")
        raise ValueError(f"MiniMax TTS 失敗: {err_msg}")

    # 取得音訊 hex 資料
    audio_hex = data.get("data", {}).get("audio", "")
    if not audio_hex:
        raise ValueError("MiniMax TTS 回傳空音訊")

    return bytes.fromhex(audio_hex)


async def _elevenlabs_synthesize(text: str) -> bytes:
    """使用 ElevenLabs 合成語音（備用）"""
    from elevenlabs.client import ElevenLabs

    voice_id = settings.ELEVENLABS_VOICE_ID or "Sq1lHWmu0YA3mqMCyaCk"
    model_id = settings.ELEVENLABS_MODEL_ID or "eleven_multilingual_v2"
    client = ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)

    voice_settings = {
        "stability": 0.70,
        "similarity_boost": 0.60,
        "style": 0.30,
        "use_speaker_boost": True,
        "speed": 1.10,
    }

    def _convert() -> bytes:
        audio = client.text_to_speech.convert(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
            output_format="mp3_44100_64",
            voice_settings=voice_settings,
        )
        if isinstance(audio, (bytes, bytearray)):
            return bytes(audio)
        return b"".join(audio)

    return await asyncio.to_thread(_convert)


async def synthesize_speech(text: str) -> str:
    """合成馬雲的聲音 — MiniMax 優先，ElevenLabs 備用"""

    # 清理舊音檔
    _cleanup_old_audio_files()

    # MiniMax 優先
    if settings.MINIMAX_API_KEY and settings.MINIMAX_GROUP_ID and settings.MINIMAX_VOICE_ID:
        try:
            logger.info(f"TTS: MiniMax speech-02-turbo, text={len(text)} chars")
            audio_bytes = await _minimax_synthesize(text)
        except Exception as e:
            logger.warning(f"MiniMax TTS 失敗，fallback 到 ElevenLabs: {e}")
            audio_bytes = await _elevenlabs_synthesize(text)
    elif settings.ELEVENLABS_API_KEY:
        logger.info(f"TTS: ElevenLabs, text={len(text)} chars")
        audio_bytes = await _elevenlabs_synthesize(text)
    else:
        raise ValueError("沒有可用的 TTS 服務（MiniMax 和 ElevenLabs 都未設定）")

    # 儲存音訊檔案
    audio_dir = BASE_DIR / "static" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    filename = f"reply_{os.urandom(4).hex()}.mp3"
    file_path = audio_dir / filename

    with open(file_path, "wb") as f:
        f.write(audio_bytes)

    logger.info(f"TTS 完成: {filename} ({len(audio_bytes)} bytes)")
    return f"/static/audio/{filename}"
