import os
import re
import base64
import logging
from fastapi import UploadFile
from pathlib import Path
from app.core.config import settings

logger = logging.getLogger(__name__)

# STT 使用 Gemini 2.0 Flash Lite（速度快、成本低）
STT_MODEL = "gemini-2.5-flash"


async def transcribe_audio(audio: UploadFile) -> str:
    """使用 Gemini 2.0 Flash Lite 將音檔轉為文字（使用新版 google-genai SDK）"""
    if not settings.GEMINI_API_KEY:
        raise ValueError("伺服器未設定 GEMINI_API_KEY，無法進行語音轉文字")

    content = await audio.read()
    logger.info(f"Received audio file: {audio.filename}, size: {len(content)} bytes")

    if len(content) == 0:
        raise ValueError("音檔內容為空")

    # 取得音檔的 MIME type
    suffix = Path(audio.filename).suffix.lower() if audio.filename else ".webm"
    mime_type_map = {
        ".webm": "audio/webm",
        ".mp3": "audio/mp3",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
    }
    mime_type = mime_type_map.get(suffix, "audio/webm")

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        # 將音檔轉為 base64
        audio_base64 = base64.b64encode(content).decode('utf-8')

        response = client.models.generate_content(
            model=STT_MODEL,
            contents=[
                types.Part.from_bytes(data=content, mime_type=mime_type),
                "請將這段音檔轉錄成文字。只輸出轉錄的文字內容，不要加任何說明或標點符號修飾。如果聽不清楚或音檔太短，請回覆「[聽不清楚]」。",
            ],
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=500,
            ),
        )

        transcribed_text = response.text.strip()

        # 處理聽不清楚的情況
        if "[聽不清楚]" in transcribed_text or len(transcribed_text) < 2:
            raise ValueError("語音太短或聽不清楚，請至少按住約 0.5 秒再放開")

    except ValueError:
        raise
    except Exception as gemini_err:
        logger.error(f"Gemini STT error: {gemini_err}")
        raise ValueError("語音轉文字失敗，請重試") from gemini_err

    return transcribed_text
