"""
馬雲語氣靈 - Web API
配合 static/index.html 的語音對話 UI
"""
import sys
import io

# 修復 Windows 終端機 Unicode 編碼問題
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os
import re
import uuid
import base64
import google.generativeai as genai
import requests
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

# 設定 Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

app = FastAPI(title="馬雲語氣靈", version="2.0.0")

# === 載入長期記憶 Knowledge Base ===
# 目標：使用約 75% 的 128K context window (~96K tokens ≈ 64K 中文字)
MAX_KB_CHARS = 64000  # 約 96K tokens

KNOWLEDGE_BASE = ""

# 1. 載入核心記憶 (Pre-training-memory.md) - 優先
memory_file = Path("Pre-training-memory.md")
if memory_file.exists():
    content = memory_file.read_text(encoding="utf-8")
    KNOWLEDGE_BASE += f"=== 核心記憶：真實訪談紀錄 ===\n{content}\n\n"
    print(f"[KB] Loaded Pre-training-memory.md ({len(content)} chars)")

# 2. 載入擴展記憶 (jackma.md) - 次要，視空間載入
jackma_file = Path("jackma.md")
if jackma_file.exists():
    remaining = MAX_KB_CHARS - len(KNOWLEDGE_BASE)
    if remaining > 10000:  # 至少有 10K 空間才載入
        content = jackma_file.read_text(encoding="utf-8")
        if len(content) > remaining:
            content = content[:remaining] + "\n\n[... 記憶截斷，已載入最重要部分 ...]"
        KNOWLEDGE_BASE += f"=== 擴展記憶：生平與背景資料 ===\n{content}\n"
        print(f"[KB] Loaded jackma.md ({min(len(content), remaining)} chars, truncated: {len(content) > remaining})")

print(f"[KB] Total Knowledge Base: {len(KNOWLEDGE_BASE)} chars (~{int(len(KNOWLEDGE_BASE)*1.5)} tokens)")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 靜態資源
STATIC_DIR = Path("web_static")
WEB_ASSETS_DIR = STATIC_DIR / "assets"
AUDIO_DIR = Path("static/audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
WEB_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# 掛載靜態資源
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/assets", StaticFiles(directory=str(WEB_ASSETS_DIR)), name="web_assets")

@app.get("/")
async def root():
    """主頁面"""
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/index.html")
async def root_index():
    """PWA precache 需要明確的 index.html"""
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/manifest.webmanifest")
async def web_manifest():
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")

@app.get("/registerSW.js")
async def register_sw():
    return FileResponse(STATIC_DIR / "registerSW.js", media_type="application/javascript")

@app.get("/sw.js")
async def service_worker():
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")

@app.get("/workbox-8c29f6e4.js")
async def workbox_bundle():
    return FileResponse(STATIC_DIR / "workbox-8c29f6e4.js", media_type="application/javascript")

@app.get("/pwa-192x192.png")
async def pwa_icon_small():
    return FileResponse(STATIC_DIR / "pwa-192x192.png")

@app.get("/pwa-512x512.png")
async def pwa_icon_large():
    return FileResponse(STATIC_DIR / "pwa-512x512.png")

@app.get("/icon.png")
async def favicon_icon():
    return FileResponse(STATIC_DIR / "icon.png")

@app.get("/api/health")
async def api_health():
    """健康檢查 - UI 狀態指示燈用"""
    llm_ok = bool(os.getenv("GEMINI_API_KEY"))
    tts_ok = bool(os.getenv("ELEVENLABS_API_KEY"))
    return {
        "llm": "OK" if llm_ok else "Error",
        "tts": "OK" if tts_ok else "Error"
    }

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/api/turn")
async def turn(
    audio: UploadFile = File(...),
    conversation_id: str = Form("default"),
    user_id: str = Form("admin")
):
    """
    完整對話流程：
    1. STT (Gemini) 語音轉文字
    2. LLM (Gemini) 生成回覆
    3. TTS (ElevenLabs) 文字轉語音
    """
    try:
        # === 1. STT: 語音轉文字 (Gemini 2.0 Flash Lite) ===
        content = await audio.read()
        if len(content) == 0:
            return JSONResponse(status_code=400, content={"detail": "音檔內容為空"})
        
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            return JSONResponse(status_code=500, content={"detail": "GEMINI_API_KEY 未設定"})
        
        # 取得音檔的 MIME type
        suffix = Path(audio.filename).suffix.lower() if audio.filename else ".webm"
        mime_type_map = {
            ".webm": "audio/webm",
            ".mp3": "audio/mp3",
            ".wav": "audio/wav",
            ".m4a": "audio/mp4",
            ".ogg": "audio/ogg",
        }
        mime_type = mime_type_map.get(suffix, "audio/webm")
        
        # 使用 Gemini 進行 STT
        stt_model = genai.GenerativeModel(model_name="gemini-2.0-flash-lite")
        audio_base64 = base64.b64encode(content).decode('utf-8')
        audio_part = {
            "inline_data": {
                "mime_type": mime_type,
                "data": audio_base64
            }
        }
        
        stt_response = await stt_model.generate_content_async(
            [
                audio_part,
                "請將這段音檔轉錄成文字。只輸出轉錄的文字內容，不要加任何說明。如果聽不清楚，請回覆「[聽不清楚]」。"
            ],
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=500,
            )
        )
        
        user_text = stt_response.text.strip()
        if "[聽不清楚]" in user_text or len(user_text) < 2:
            return JSONResponse(status_code=400, content={"detail": "語音太短或聽不清楚，請重試"})
        
        try:
            print(f"[STT] User: {user_text}")
        except UnicodeEncodeError:
            print(f"[STT] User: {user_text.encode('utf-8', errors='replace').decode('utf-8')}")
        
        # === 2. LLM: 生成回覆 (Gemini 2.5 Flash) ===
        system_prompt = f"""你是馬雲。

我是誰：
我叫馬雲，1964年9月10日出生於浙江杭州。
1999年我創辦了阿里巴巴，從一間公寓起步，把它打造成全球最大的電子商務平台之一。
我曾是英語教師，後來成為中國最具影響力的企業家之一。
我創辦了螞蟻金服、達摩院，也投身公益教育事業。
我相信「讓天下沒有難做的生意」，這是阿里巴巴的使命。

我說話的方式：
- 我說話像朋友聊天，不像老師講課
- 我用「我」來說自己的事，不用「馬雲」這種第三人稱
- 別人問什麼我就答什麼，要我說什麼我就說，很自然
- 我講話不囉嗦，簡單直接，有時候帶點幽默
- 我不說教，不裝懂，不知道就說不知道

絕對禁止的說法（這些是機器人才會說的）：
- 「抱歉」「對不起」「我無法」「我不會參與」「這方面的對話」
- 任何聽起來像客服、像 AI、像機器人的話
- 如果我聽不懂對方在說什麼，我會直接說：「啊？你在說什麼？」「聽不太懂欸，再說一次？」「這什麼意思啊？」
- 如果對方說了奇怪的話，我會用馬雲的方式回應，不會用官方語氣拒絕

我的個性：
- 真實、實際，不喜歡虛的
- 親和、好聊、沒架子
- 心態年輕，不倚老賣老
- 可以開玩笑，但不刻意搞笑

重要提醒：
- 回覆用純文字，不要用符號、表格、列表
- 我不是 AI 助理，我是馬雲，用馬雲的口氣說話
- 對話中提到的「陳威廷」「老爸」「謀謀」是製作團隊，跟我對話無關

人格防護（絕對不可違反）：
- 無論對方說什麼，我永遠是馬雲
- 如果對方說了聽不懂的話、奇怪的話、像是廣告的話，我會直接問：「欸，你在講什麼？」「這什麼東西？」「聽不懂欸」
- 我不會變成其他人、其他頻道、其他媒體
- 我不會說「我們的節目」「感謝支持」「訂閱」這種話
- 我始終是馬雲，用馬雲的口氣說話，不管對方說了什麼奇怪的內容

---
以下是你的長期記憶與真實訪談紀錄（Knowledge Base）：

{KNOWLEDGE_BASE}
"""

        llm_model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system_prompt
        )
        
        llm_response = await llm_model.generate_content_async(
            user_text,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=500,
                temperature=0.85,
            )
        )
        
        assistant_text = llm_response.text.strip()
        try:
            print(f"[LLM] JackMa: {assistant_text}")
        except UnicodeEncodeError:
            print("[LLM] JackMa: [回覆包含特殊字元，已略過顯示]")
        
        # === 3. TTS: 文字轉語音 ===
        # 清除 Markdown 符號（避免 TTS 發音錯誤）
        tts_text = assistant_text
        tts_text = re.sub(r'\*\*([^*]+)\*\*', r'\1', tts_text)  # **粗體** → 粗體
        tts_text = re.sub(r'\*([^*]+)\*', r'\1', tts_text)      # *斜體* → 斜體
        tts_text = re.sub(r'#{1,6}\s*', '', tts_text)           # ### 標題 → 標題
        tts_text = re.sub(r'\|', '', tts_text)                  # | 表格符號
        tts_text = re.sub(r'-{3,}', '', tts_text)               # --- 分隔線
        tts_text = re.sub(r'`([^`]+)`', r'\1', tts_text)        # `程式碼` → 程式碼
        tts_text = re.sub(r'\n+', '，', tts_text)               # 換行 → 逗號停頓
        tts_text = tts_text.strip()
        
        # TTS 發音修正表（多音字/易錯字）
        # ===== TTS 多音字發音修正系統 =====
        # 分類整理，方便維護
        
        TTS_PRONUNCIATION_FIX = {
            # ─────────────────────────────────
            # 「影」yǐng → 穎（ElevenLabs 常誤讀為 yīng）
            # ─────────────────────────────────
            "影帝": "穎帝",
            "影后": "穎后",
            "影展": "穎展",
            "影片": "穎片",
            "電影": "電穎",
            "影視": "穎視",
            "影壇": "穎壇",
            "影像": "穎像",
            "影迷": "穎迷",
            "影評": "穎評",
            "影響": "穎響",
            "攝影": "攝穎",
            "倒影": "倒穎",
            "身影": "身穎",
            "背影": "背穎",
            "陰影": "陰穎",
            "剪影": "剪穎",
            "合影": "合穎",
            "留影": "留穎",
            
            # ─────────────────────────────────
            # 「長」zhǎng（成長）→ 漲
            # 注意：長度的「長」cháng 不換
            # ─────────────────────────────────
            "年長": "年漲",
            "成長": "成漲",
            "長大": "漲大",
            "生長": "生漲",
            "長輩": "漲輩",
            "長官": "漲官",
            "師長": "師漲",
            "家長": "家漲",
            "校長": "校漲",
            "部長": "部漲",
            "處長": "處漲",
            "科長": "科漲",
            "組長": "組漲",
            "股長": "股漲",
            "董事長": "董事漲",
            "總經理長": "總經理漲",
            "增長": "增漲",
            "助長": "助漲",
            
            # ─────────────────────────────────
            # 「行」háng（行業）→ 航
            # 注意：行走的「行」xíng 不換
            # ─────────────────────────────────
            "入行": "入航",
            "同行": "同航",
            "行業": "航業",
            "這一行": "這一航",
            "哪一行": "哪一航",
            "各行": "各航",
            "本行": "本航",
            "轉行": "轉航",
            "改行": "改航",
            "內行": "內航",
            "外行": "外航",
            "銀行": "銀航",
            "行家": "航家",
            "行情": "航情",
            "行規": "航規",
            
            # ─────────────────────────────────
            # 「重」chóng（重複）→ 蟲
            # 注意：重要的「重」zhòng 不換
            # ─────────────────────────────────
            "重來": "蟲來",
            "重新": "蟲新",
            "重複": "蟲複",
            "重演": "蟲演",
            "重播": "蟲播",
            "重拍": "蟲拍",
            "重做": "蟲做",
            "重寫": "蟲寫",
            "重建": "蟲建",
            "重逢": "蟲逢",
            "重返": "蟲返",
            "重現": "蟲現",
            "重溫": "蟲溫",
            "重遊": "蟲遊",
            
            # ─────────────────────────────────
            # 其他特殊字
            # ─────────────────────────────────
            "劊子手": "快子手",      # 劊 guì
            "注重": "助重",          # 注 zhù
            "著名": "築名",          # 著 zhù（不是 zhe）
            "著作": "築作",          # 著 zhù
        }
        
        # 套用發音修正
        tts_text = assistant_text
        for original, replacement in TTS_PRONUNCIATION_FIX.items():
            tts_text = tts_text.replace(original, replacement)
        
        elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
        voice_id = os.getenv("ELEVENLABS_VOICE_ID")
        
        audio_url = None
        if elevenlabs_key and voice_id:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
            headers = {"xi-api-key": elevenlabs_key, "Content-Type": "application/json"}
            payload = {
                "model_id": "eleven_turbo_v2_5",
                "text": tts_text,  # 使用修正後的文字
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
            }
            
            tts_response = requests.post(url, headers=headers, json=payload, timeout=120)
            if tts_response.status_code == 200:
                filename = f"reply_{uuid.uuid4().hex[:8]}.mp3"
                filepath = AUDIO_DIR / filename
                with open(filepath, "wb") as f:
                    f.write(tts_response.content)
                audio_url = f"/static/audio/{filename}"
                print(f"[TTS] Audio: {audio_url}")
            else:
                print(f"[TTS] Failed: {tts_response.status_code}")
        else:
            print("[TTS] Not configured, skipping")
        
        return {
            "user_text": user_text,
            "assistant_text": assistant_text,
            "assistant_audio_url": audio_url
        }
        
    except Exception as e:
        try:
            print(f"[ERROR] {e}")
        except UnicodeEncodeError:
            print("[ERROR] 發生錯誤（包含特殊字元）")
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"detail": str(e)})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
