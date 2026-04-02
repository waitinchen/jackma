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
    # 馬雲克隆聲紋 — 硬編碼，防止被 Secret Manager 污染
    JACKMA_VOICE_ID = "moss_audio_062371e7-2c0c-11f1-a44a-c658cff0ef65"
    payload = {
        "model": "speech-02-turbo",
        "text": text,
        "stream": False,
        "voice_setting": {
            "voice_id": JACKMA_VOICE_ID,
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


async def synthesize_speech(text: str) -> str:
    """合成馬雲的聲音 — 只用 MiniMax，無 ElevenLabs fallback"""

    # 清理舊音檔
    _cleanup_old_audio_files()

    if not (settings.MINIMAX_API_KEY and settings.MINIMAX_GROUP_ID and settings.MINIMAX_VOICE_ID):
        raise ValueError("MiniMax TTS 未設定，馬雲語氣靈不支援其他 TTS")

    logger.info(f"TTS: MiniMax speech-02-turbo, text={len(text)} chars")
    audio_bytes = await _minimax_synthesize(text)

    # 儲存音訊檔案
    audio_dir = BASE_DIR / "static" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    filename = f"reply_{os.urandom(4).hex()}.mp3"
    file_path = audio_dir / filename

    with open(file_path, "wb") as f:
        f.write(audio_bytes)

    logger.info(f"TTS 完成: {filename} ({len(audio_bytes)} bytes)")
    return f"/static/audio/{filename}"
