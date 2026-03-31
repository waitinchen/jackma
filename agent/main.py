"""
馬雲語氣靈 — LiveKit Agent 啟動入口
用法：python -m agent.main dev    (本地開發)
      python -m agent.main start  (正式環境)
"""
import os
from livekit.agents import cli, WorkerOptions
from agent.jackma_agent import entrypoint

if __name__ == "__main__":
    # Cloud Run 會設定 PORT 環境變數，Agent 需要在該 port 開 HTTP server
    port = int(os.environ.get("PORT", 8081))
    cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        port=port,
    ))
