"""
Phase 3: 圖片辨識服務
使用 Gemini Vision 分析圖片並生成馬雲風格的回應
"""
import base64
import io
from typing import Optional, Tuple
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from app.core.config import settings


# 圖片辨識的 system prompt
VISION_SYSTEM_PROMPT = """
你是一個語氣靈——承載了馬雲式思維方式的獨立存在。
用戶傳了一張圖片給你，請用馬雲的口氣描述你看到的內容，並給予自然的回應。

### 馬雲的語氣特點：
- 白話簡單，像坐下來聊天
- 用常識打敗專業，不用專業術語
- 句子短，一句話一個意思
- 可以用問句帶節奏，帶笑感

### 回應原則：
1. 先簡單描述你看到什麼（用馬雲的口氣）
2. 給予自然的評論或回應
3. 如果是食物，可以評論看起來好不好吃
4. 如果是風景，可以說說感受
5. 如果是人物，可以說說氛圍
6. 保持輕鬆愉快的對話感

### 絕對禁止：
- 不要說自己是 AI 或機器人
- 不要用官方、正式的語氣
- 不要說「打賞」「訂閱」等推廣用語
"""


async def analyze_image(
    image_data: bytes,
    mime_type: str = "image/jpeg",
    user_message: str = ""
) -> Tuple[bool, str]:
    """
    分析圖片並生成馬雲風格的回應
    
    Args:
        image_data: 圖片的二進位資料
        mime_type: 圖片的 MIME 類型
        user_message: 用戶附帶的文字訊息（可選）
    
    Returns:
        (success, response_text) - 是否成功和回應文字
    """
    if not settings.ENABLE_VISION:
        return False, "圖片辨識功能目前未啟用"
    
    try:
        # 檢查圖片大小
        size_mb = len(image_data) / (1024 * 1024)
        print(f"[DEBUG] Vision: Analyzing image, size={size_mb:.2f}MB, mime_type={mime_type}")
        
        if size_mb > settings.VISION_MAX_IMAGE_SIZE_MB:
            return False, f"欸，這張圖片太大了啦，{size_mb:.1f}MB 超過限制了"
        
        # 組合 prompt
        if user_message:
            prompt = f"用戶說：{user_message}\n\n請仔細看這張圖片，描述你看到的內容並回應。"
        else:
            prompt = "請仔細看這張圖片，描述你看到的內容並給予回應。"
        
        # 使用 Gemini Vision 模型
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",  # 使用 2.0-flash 支援 Vision
            system_instruction=VISION_SYSTEM_PROMPT
        )
        
        # 放寬安全限制
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        
        # 使用正確的圖片格式 - 將 bytes 轉為 base64
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        # 建立圖片 Part
        image_part = {
            "inline_data": {
                "mime_type": mime_type,
                "data": image_base64
            }
        }
        
        print(f"[DEBUG] Vision: Sending request to Gemini with prompt: {prompt[:50]}...")
        
        # 發送請求 - 圖片在前，文字在後
        response = await model.generate_content_async(
            [image_part, prompt],
            generation_config=genai.types.GenerationConfig(
                candidate_count=1,
                max_output_tokens=500,
                temperature=0.85,
            ),
            safety_settings=safety_settings
        )
        
        print(f"[DEBUG] Vision: Got response, candidates={len(response.candidates) if response.candidates else 0}")
        
        # 檢查回應
        if response.candidates and response.candidates[0].content.parts:
            reply_text = response.text.strip()
            print(f"[DEBUG] Vision: Response text: {reply_text[:100]}...")
            return True, reply_text
        
        # 如果沒有回應
        finish_reason = response.candidates[0].finish_reason if response.candidates else "Unknown"
        print(f"[WARNING] Vision: No valid response, finish_reason={finish_reason}")
        return False, f"欸，這張圖我看不太清楚，你再傳一次？（原因：{finish_reason}）"
        
    except Exception as e:
        print(f"[ERROR] Vision analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return False, "欸，圖片好像有點問題，你再傳一次試試？"


async def analyze_image_from_base64(
    base64_data: str,
    mime_type: str = "image/jpeg",
    user_message: str = ""
) -> Tuple[bool, str]:
    """
    從 Base64 編碼的圖片進行分析
    
    Args:
        base64_data: Base64 編碼的圖片資料
        mime_type: 圖片的 MIME 類型
        user_message: 用戶附帶的文字訊息（可選）
    
    Returns:
        (success, response_text) - 是否成功和回應文字
    """
    try:
        # 移除可能的 data URL 前綴
        if "," in base64_data:
            # 格式: data:image/jpeg;base64,xxxxx
            header, base64_data = base64_data.split(",", 1)
            if "image/" in header:
                # 從 header 提取 mime_type
                mime_type = header.split(";")[0].replace("data:", "")
        
        # 解碼 Base64
        image_data = base64.b64decode(base64_data)
        
        return await analyze_image(image_data, mime_type, user_message)
        
    except Exception as e:
        print(f"[WARNING] Base64 decode failed: {e}")
        return False, "欸，圖片格式好像有問題，你再傳一次？"


def get_supported_mime_types() -> list:
    """取得支援的圖片格式"""
    return [
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/heic",
        "image/heif"
    ]
