import asyncio
import os
import httpx
from openai import AsyncOpenAI
import google.generativeai as genai
from app.core.config import settings

async def test_openai():
    print("Testing OpenAI (Whisper)...")
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        models = await client.models.list()
        print("[OK] OpenAI API Key is VALID.")
        return True
    except Exception as e:
        print(f"[ERROR] OpenAI API Error: {e}")
        return False

async def test_gemini():
    print("Testing Gemini...")
    genai.configure(api_key=settings.GEMINI_API_KEY)
    try:
        model = genai.GenerativeModel('gemini-2.0-flash-lite')
        response = model.generate_content("Hi")
        print("[OK] Gemini API Key is VALID.")
        return True
    except Exception as e:
        print(f"[ERROR] Gemini API Error: {e}")
        return False

async def test_elevenlabs():
    print("Testing ElevenLabs...")
    url = f"https://api.elevenlabs.io/v1/voices"
    headers = {"xi-api-key": settings.ELEVENLABS_API_KEY}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
            if response.status_code == 200:
                print("[OK] ElevenLabs API Key is VALID.")
                voices = response.json().get('voices', [])
                voice_ids = [v['voice_id'] for v in voices]
                if settings.ELEVENLABS_VOICE_ID in voice_ids:
                    print(f"[OK] Voice ID '{settings.ELEVENLABS_VOICE_ID}' is FOUND.")
                else:
                    print(f"[WARN] Voice ID '{settings.ELEVENLABS_VOICE_ID}' NOT FOUND.")
                return True
            else:
                print(f"[ERROR] ElevenLabs API Error: {response.status_code}")
                return False
        except Exception as e:
            print(f"[ERROR] ElevenLabs Error: {e}")
            return False

async def main():
    print("=== API Key Health Check ===\n")
    await test_openai()
    print("-" * 30)
    await test_gemini()
    print("-" * 30)
    await test_elevenlabs()
    print("\n============================")

if __name__ == "__main__":
    asyncio.run(main())
