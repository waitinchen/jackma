"""
ElevenLabs REST TTS Wrapper — 強制走 REST API（不走 WebSocket）

eleven_v3 不支援 WebSocket 串流端點（multi-stream-input 回傳 403），
但 REST API（/text-to-speech/{voice_id}）可正常使用。
此 wrapper 將 streaming capability 設為 False，
強制 LiveKit AgentSession 走 synthesize()（REST）而非 stream()（WebSocket）。
"""
from livekit.agents import tts


class NonStreamingElevenLabs(tts.TTS):
    """包裝 ElevenLabs TTS，強制用 REST API"""

    def __init__(self, wrapped: tts.TTS):
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=wrapped.sample_rate,
            num_channels=wrapped.num_channels,
        )
        self._wrapped = wrapped

    def synthesize(self, text: str, *, conn_options=None):
        return self._wrapped.synthesize(text, conn_options=conn_options)

    async def aclose(self):
        await self._wrapped.aclose()
