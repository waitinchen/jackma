"""
發音修正模組
提供完整的發音修正字典和自動檢測替換功能
支持「改字不改意」和「同音字替換」兩種策略
"""
import re
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# 發音修正字典
# 格式：{原詞: (替換詞, 策略類型, 說明)}
# 策略類型：'semantic' = 改字不改意, 'phonetic' = 同音字替換
PRONUNCIATION_FIX_DICT: Dict[str, Tuple[str, str, str]] = {
    # 多音字問題 - 用語義替換
    "入行": ("踏進這一行", "semantic", "行(hang) vs 行(xing)"),
    "重來": ("再來一次", "semantic", "重(chong) vs 重(zhong)"),
    
    # ========== 影 相關 ==========
    # ElevenLabs 把「影」「穎」「映」都念成「因」，改用「贏」
    "影帝": ("贏帝", "phonetic", "影->贏"),
    "影后": ("贏后", "phonetic", "影->贏"),
    "影展": ("贏展", "phonetic", "影->贏"),
    "電影": ("電贏", "phonetic", "影->贏"),
    "拍電影": ("拍電贏", "phonetic", "影->贏"),
    
    # ========== 得 相關 ==========
    "得獎": ("德獎", "phonetic", "得->德"),
    "得到": ("德到", "phonetic", "得->德"),
    "獲得": ("獲德", "phonetic", "得->德"),
    "得了": ("德了", "phonetic", "得->德"),
    "覺得": ("覺德", "phonetic", "得->德"),
    
    # ========== 行 相關 ==========
    "行業": ("航業", "phonetic", "行->航"),
    "銀行": ("銀航", "phonetic", "行->航"),
    "同行": ("同航", "phonetic", "行->航"),
    "這一行": ("這一航", "phonetic", "行->航"),
    
    # ========== 發/展/髮 相關 ==========
    "發展": ("發斬", "phonetic", "展->斬"),
    "頭髮": ("頭法", "phonetic", "髮->法"),
    
    # ========== 長 相關 ==========
    "長大": ("漲大", "phonetic", "長->漲"),
    "成長": ("成漲", "phonetic", "長->漲"),
    
    # ========== 動 相關 ==========
    "動一動": ("洞一洞", "phonetic", "動->洞"),
    "動動": ("洞洞", "phonetic", "動->洞"),
    "運動": ("運洞", "phonetic", "動->洞"),
    "活動": ("活洞", "phonetic", "動->洞"),
    
    # ========== 累 相關 ==========
    "累不累": ("類不類", "phonetic", "累->類"),
    "好累": ("好類", "phonetic", "累->類"),
    "很累": ("很類", "phonetic", "累->類"),
    "太累": ("太類", "phonetic", "累->類"),
    "不累": ("不類", "phonetic", "累->類"),
    
    # ========== 特殊詞彙 ==========
    "鬼見愁": ("軌件仇", "phonetic", "鬼見愁->軌件仇"),
    "百萬小生": ("百萬曉生", "phonetic", "小->曉"),
    "小生": ("曉生", "phonetic", "小->曉"),
    
    # ========== 演/戲 相關 ==========
    # 注意：「眼」可能被念成「菸」，改用「沿」
    "演一種戲": ("沿一種係", "phonetic", "演戲->沿係"),
    "演戲": ("沿係", "phonetic", "演戲->沿係"),
    "導戲": ("導係", "phonetic", "戲->係"),
    "拍戲": ("拍係", "phonetic", "戲->係"),
    "這齣戲": ("這齣係", "phonetic", "戲->係"),
    "那齣戲": ("那齣係", "phonetic", "戲->係"),
    "演員": ("沿員", "phonetic", "演->沿"),
    "表演": ("表沿", "phonetic", "演->沿"),
}

# 單字警示列表（用於拆句）
CHAR_ALERT: List[str] = ["重", "行", "得", "當", "發", "長"]


def get_replacement(original: str, strategy: str = "semantic") -> Tuple[str, str]:
    """獲取替換詞"""
    if original in PRONUNCIATION_FIX_DICT:
        replacement, fix_strategy, _ = PRONUNCIATION_FIX_DICT[original]
        if strategy == "any" or fix_strategy == strategy:
            return replacement, fix_strategy
    return original, ""


def fix_pronunciation(text: str, strategy: str = "any") -> str:
    """
    自動檢測並替換文本中的易錯詞彙
    
    Args:
        text: 原始文本
        strategy: 替換策略 ('semantic', 'phonetic', 或 'any')
    
    Returns:
        修正後的文本
    """
    result = text
    replacements_made = []
    
    # 按長度排序，先替換長詞組（避免部分匹配）
    sorted_items = sorted(
        PRONUNCIATION_FIX_DICT.items(),
        key=lambda x: len(x[0]),
        reverse=True
    )
    
    for original, (replacement, fix_strategy, _) in sorted_items:
        if strategy == "any" or fix_strategy == strategy:
            if original in result:
                result = result.replace(original, replacement)
                replacements_made.append(f"{original}->{replacement}")
    
    # Debug log
    if replacements_made:
        logger.info(f"[發音修正] 替換: {', '.join(replacements_made)}")
    
    return result


def detect_problematic_chars(text: str) -> List[str]:
    """檢測文本中可能導致發音問題的單字"""
    found = []
    for char in CHAR_ALERT:
        if char in text:
            found.append(char)
    return found


def get_all_rules() -> Dict[str, Dict[str, str]]:
    """獲取所有發音修正規則"""
    return {
        original: {
            "replacement": replacement,
            "strategy": strategy,
            "description": description
        }
        for original, (replacement, strategy, description) in PRONUNCIATION_FIX_DICT.items()
    }
