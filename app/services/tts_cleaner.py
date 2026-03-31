import json
import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

RULES_PATH = Path("app/tts_rules.json")

def load_rules():
    if RULES_PATH.exists():
        with RULES_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "phrase_replace": {},
        "char_alert": [],
        "max_len": 50
    }

def clean_for_tts(text: str, use_pronunciation_fix: bool = True) -> str:
    """
    清洗文本以優化 TTS 發音
    """
    logger.info(f"[TTS清洗] 原始文本: {text}")
    
    rules = load_rules()
    
    # 0) 移除括號內的動作詞
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'（.*?）', '', text)
    
    # 0.5) 移除各種引號（會影響 TTS 判讀）
    text = text.replace('「', '').replace('」', '')
    text = text.replace('『', '').replace('』', '')
    text = text.replace('"', '').replace('"', '')
    text = text.replace('「', '').replace('」', '')
    text = text.replace("'", '').replace("'", '')
    text = text.replace('"', '').replace("'", '')
    
    # 1) 詞組替換（從 JSON 規則文件）
    phrase_replace = rules.get("phrase_replace", {})
    sorted_replacements = sorted(
        phrase_replace.items(),
        key=lambda x: len(x[0]),
        reverse=True
    )
    for src, tgt in sorted_replacements:
        text = text.replace(src, tgt)
    
    # 1.5) 使用 pronunciation_fix 模組進行發音修正
    if use_pronunciation_fix:
        try:
            from app.services.pronunciation_fix import fix_pronunciation
            text = fix_pronunciation(text, strategy="any")
            logger.info(f"[TTS清洗] 發音修正後: {text}")
        except ImportError as e:
            logger.warning(f"[TTS清洗] pronunciation_fix 模組載入失敗: {e}")
        except Exception as e:
            logger.error(f"[TTS清洗] 發音修正錯誤: {e}")

    # 2) 單字警示  拆句
    for char in rules.get("char_alert", []):
        if char in text:
            text = text.replace("，", "。\n")
            break

    # 3) 長句拆段
    if len(text) > rules.get("max_len", 50):
        text = text.replace("，", "。\n")

    logger.info(f"[TTS清洗] 最終文本: {text}")
    return text
