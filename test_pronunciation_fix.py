"""
測試發音修正功能
用於驗證 LLM System Prompt 和 TTS 清洗規則是否正確工作
"""
import sys
import io
from pathlib import Path

# 設置 UTF-8 編碼以支持中文輸出
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 添加 app 目錄到路徑
sys.path.insert(0, str(Path(__file__).parent))

from app.services.tts_cleaner import clean_for_tts
from app.services.pronunciation_fix import fix_pronunciation, get_all_rules


def test_tts_cleaner():
    """測試 TTS 清洗功能"""
    print("=== 測試 TTS 清洗功能 ===\n")
    
    test_cases = [
        ("我們重來吧", "我們再來一次吧"),
    ]
    
    all_passed = True
    for original, expected in test_cases:
        result = clean_for_tts(original)
        passed = result == expected
        status = "✅" if passed else "❌"
        print(f"{status} 原文: {original}")
        print(f"   預期: {expected}")
        print(f"   結果: {result}")
        if not passed:
            print(f"   ⚠️  不匹配！")
            all_passed = False
        print()
    
    return all_passed


def test_pronunciation_fix_module():
    """測試發音修正模組"""
    print("=== 測試發音修正模組 ===\n")
    
    test_cases = [
        ("我們重來吧", "我們再來一次吧"),
    ]
    
    all_passed = True
    for original, expected in test_cases:
        result = fix_pronunciation(original)
        passed = result == expected
        status = "✅" if passed else "❌"
        print(f"{status} 原文: {original}")
        print(f"   預期: {expected}")
        print(f"   結果: {result}")
        if not passed:
            print(f"   ⚠️  不匹配！")
            all_passed = False
        print()
    
    return all_passed


def show_all_rules():
    """顯示所有發音修正規則"""
    print("=== 所有發音修正規則 ===\n")
    rules = get_all_rules()
    for original, info in rules.items():
        print(f"原詞: {original}")
        print(f"  替換為: {info['replacement']}")
        print(f"  策略: {info['strategy']}")
        print(f"  說明: {info['description']}")
        print()


def main():
    """主測試函數"""
    print("=" * 60)
    print("發音修正功能測試")
    print("=" * 60)
    print()
    
    # 顯示所有規則
    show_all_rules()
    
    # 測試 TTS 清洗
    tts_passed = test_tts_cleaner()
    
    # 測試發音修正模組
    fix_passed = test_pronunciation_fix_module()
    
    # 總結
    print("=" * 60)
    print("測試總結")
    print("=" * 60)
    print(f"TTS 清洗測試: {'✅ 通過' if tts_passed else '❌ 失敗'}")
    print(f"發音修正模組測試: {'✅ 通過' if fix_passed else '❌ 失敗'}")
    print()
    
    if tts_passed and fix_passed:
        print("✅ 所有測試通過！")
        print("\n下一步：")
        print("1. 測試 LLM 是否遵循用詞替換規則（需要實際對話測試）")
        print("2. 在 ElevenLabs Agents 中測試發音改善效果")
        return 0
    else:
        print("❌ 部分測試失敗，請檢查規則配置")
        return 1


if __name__ == "__main__":
    sys.exit(main())
