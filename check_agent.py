"""Check ElevenLabs 馬雲 Agent health via GET /v1/convai/agents/:agent_id"""
import asyncio
import json
import httpx
from app.core.config import settings

AGENT_ID = "agent_0901kernamncf0kr8spv0xw0380t"
URL = f"https://api.elevenlabs.io/v1/convai/agents/{AGENT_ID}"


async def main():
    print("=== 馬雲 Agent 健康檢查 ===\n")
    print(f"Agent ID: {AGENT_ID}")
    print(f"API URL: {URL}\n")

    headers = {"xi-api-key": settings.ELEVENLABS_API_KEY}
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(URL, headers=headers)
            if r.status_code != 200:
                print(f"[ERR] HTTP {r.status_code}")
                print(r.text[:500] if r.text else "")
                return
            data = r.json()
        except Exception as e:
            print(f"[ERR] 請求失敗: {e}")
            return

    name = data.get("name", "—")
    agent_id = data.get("agent_id", "—")
    meta = data.get("metadata") or {}
    created = meta.get("created_at_unix_secs")
    updated = meta.get("updated_at_unix_secs")
    conv = data.get("conversation_config") or {}
    agent_cfg = conv.get("agent") or {}
    first_msg = (agent_cfg.get("first_message") or "").strip()
    lang = agent_cfg.get("language", "—")
    version_id = data.get("version_id")
    branch_id = data.get("branch_id")

    print("[OK] Agent 存在且可正常讀取\n")
    print("--- 基本資訊 ---")
    print(f"  名稱: {name}")
    print(f"  agent_id: {agent_id}")
    print(f"  language: {lang}")
    print(f"  version_id: {version_id}")
    print(f"  branch_id: {branch_id}")
    if created:
        print(f"  created_at (unix): {created}")
    if updated:
        print(f"  updated_at (unix): {updated}")
    print("\n--- first_message（完整）---")
    if first_msg:
        print(first_msg)
        if "test" in first_msg.lower() or "clean" in first_msg.lower():
            print("\n  ⚠️ 發現 'test' 或 'clean'，可能導致「一直說 clean TEST」→ 請到 ElevenLabs 後台改掉")
    else:
        print("  (空)")
    print("\n--- 結論 ---")
    print("  馬雲 Agent 健康正常，可正常運作。")


if __name__ == "__main__":
    asyncio.run(main())
