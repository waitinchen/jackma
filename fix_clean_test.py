"""透過 ElevenLabs PATCH API 移除 Agent 開場的「clean TEST」，
   將 first_message 改為正式開場，並自 System Prompt 移除 clean_tts_text／清洗 相關指示。
   執行後請重新撥打通話測試。
"""
from __future__ import annotations

import argparse
import asyncio
import sys

import httpx

from app.core.config import settings

AGENT_ID = "agent_0901kernamncf0kr8spv0xw0380t"
GET_URL = f"https://api.elevenlabs.io/v1/convai/agents/{AGENT_ID}"
PATCH_URL = GET_URL

REPLACEMENT_FIRST_MESSAGE = "我是馬雲。我聽得見，你說吧!"

# 欲從 prompt 刪除的關鍵字（該行整行刪除，避免 Agent 說出 clean）
PROMPT_DROP_PATTERNS = ["clean_tts_text", "清洗文本"]


def _clean_prompt_lines(text: str) -> str:
    """Remove lines containing clean_tts_text or 清洗文本."""
    if not text:
        return text
    kept = [ln for ln in text.splitlines() if not any(p in ln for p in PROMPT_DROP_PATTERNS)]
    return "\n".join(kept).strip()


def _find_test_clean(obj: dict, path: str = "") -> list[tuple[str, str]]:
    """Recursively find string values containing 'test' or 'clean'."""
    out: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if isinstance(v, str) and ("test" in v.lower() or "clean" in v.lower()):
                out.append((p, v))
            else:
                out.extend(_find_test_clean(v, p))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(_find_test_clean(v, f"{path}[{i}]"))
    return out


async def main() -> int:
    parser = argparse.ArgumentParser(description="移除馬雲 Agent 開場的 clean TEST")
    parser.add_argument("--dry-run", action="store_true", help="只顯示將要修改的內容，不送出 PATCH")
    parser.add_argument("--dump", action="store_true", help="傾印 Agent 設定中含 test/clean 的欄位後結束")
    parser.add_argument("--first-message", default=REPLACEMENT_FIRST_MESSAGE, help="欲設定的 first_message")
    args = parser.parse_args()

    headers = {"xi-api-key": settings.ELEVENLABS_API_KEY, "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(GET_URL, headers=headers)
        except Exception as e:
            print(f"[ERR] GET 請求失敗: {e}", file=sys.stderr)
            return 1
        if r.status_code != 200:
            print(f"[ERR] GET HTTP {r.status_code}: {r.text[:500]}", file=sys.stderr)
            return 1

    data = r.json()
    conv = data.get("conversation_config") or {}
    agent_cfg = conv.get("agent") or {}
    current = (agent_cfg.get("first_message") or "").strip()

    if args.dump:
        hits = _find_test_clean(data)
        if not hits:
            print("未發現任何含 'test' 或 'clean' 的欄位。")
        else:
            for path, val in hits:
                print(f"{path}: {repr(val)[:200]}")
        return 0

    prompt_obj = agent_cfg.get("prompt")
    prompt_txt = ""
    if isinstance(prompt_obj, dict):
        prompt_txt = (prompt_obj.get("prompt") or "").strip()
    elif isinstance(prompt_obj, str):
        prompt_txt = prompt_obj.strip()
    cleaned_prompt = _clean_prompt_lines(prompt_txt)
    prompt_changed = cleaned_prompt != prompt_txt

    print(f"目前 first_message: {repr(current)}")
    print(f"欲改為: {repr(args.first_message)}")
    if prompt_txt:
        print(f"Prompt 含 clean_tts_text/清洗文本 行數: {sum(1 for ln in prompt_txt.splitlines() if any(p in ln for p in PROMPT_DROP_PATTERNS))}")
    if prompt_changed:
        print("將自 System Prompt 移除含 clean_tts_text／清洗文本 之整行。")

    # 若 first_message 為空或含 test/clean，一律改為正式開場
    should_patch_fm = not current or "test" in current.lower() or "clean" in current.lower()
    should_patch = should_patch_fm or prompt_changed
    if not should_patch:
        print("[OK] first_message 與 prompt 均無須修改。")
        return 0

    if args.dry_run:
        print("[DRY-RUN] 將送出 PATCH，但未實際執行。")
        return 0

    agent_payload: dict = {}
    if should_patch_fm:
        agent_payload["first_message"] = args.first_message
    if prompt_changed:
        agent_payload["prompt"] = {"prompt": cleaned_prompt}

    payload = {"conversation_config": {"agent": agent_payload}}

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            pr = await client.patch(PATCH_URL, headers=headers, json=payload)
        except Exception as e:
            print(f"[ERR] PATCH 請求失敗: {e}", file=sys.stderr)
            return 1

    if pr.status_code != 200:
        print(f"[ERR] PATCH HTTP {pr.status_code}: {pr.text[:800]}", file=sys.stderr)
        return 1

    print("[OK] first_message / System Prompt 已更新。請重新撥打通話測試。")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
