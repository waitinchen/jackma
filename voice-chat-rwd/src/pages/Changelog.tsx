import { ArrowLeft } from "lucide-react";
import { useLocation } from "wouter";
import { DeviceFrame, StatusBar } from "@/components/DeviceFrame";
import { useIsMobile } from "@/hooks/use-mobile";

const CHANGELOG = [
  {
    version: "v3.0.3",
    date: "2026-04-03 12:00",
    changes: [
      { type: "feat", text: "前端預連結：進入通話頁面就建立 LiveKit 連線，按撥號鈕只開麥克風，體感延遲大幅縮短" },
      { type: "fix", text: "強化 STT 容錯指令：LLM 不再提及「聽不清」「含糊」，改為推斷用戶意圖" },
      { type: "feat", text: "Deepgram 關鍵字擴充至 8 組（馬雲、阿里巴巴、淘寶等），提升語音辨識準確度" },
    ],
  },
  {
    version: "v3.0.2",
    date: "2026-04-02 16:00",
    changes: [
      { type: "fix", text: "Agent 架構：Gemini 惰性載入（省 3-5s）+ VAD 預載 + DB 預熱 + DB 查詢並行化" },
      { type: "fix", text: "LiveKit secrets 隔離：馬雲用 jackma-livekit-* 獨立密鑰，避免與江彬 Agent 衝突" },
      { type: "fix", text: "API 端 TTS：注入 MiniMax secrets + 修正 API URL（api.minimax.chat → api.minimax.io）" },
    ],
  },
  {
    version: "v3.0.1",
    date: "2026-04-01 09:00",
    changes: [
      { type: "fix", text: "Agent TTS：硬編碼馬雲 voice_id，刪除 ElevenLabs fallback（防止跳到江彬聲音）" },
      { type: "fix", text: "Dockerfile：移除已刪除的 jiangbin.md 引用，修復部署失敗" },
      { type: "feat", text: "LiveKit Cloud：新建 JackMa_V1 project，完全隔離江彬的 LiveKit 環境" },
      { type: "feat", text: "Domain：jackma.tonetown.ai 上線（GoDaddy CNAME + Cloud Run domain mapping + SSL）" },
    ],
  },
  {
    version: "v3.0.0",
    date: "2026-03-31 15:00",
    changes: [
      { type: "feat", text: "馬雲語氣靈 1.0 全面上線 — 江彬→馬雲全面改造" },
      { type: "feat", text: "人格：馬雲靈魂檔 v2（創業心智教練，四拍結構語氣模型）" },
      { type: "feat", text: "代碼：所有 jiangbin→jackma（class, function, variable, 72+ 檔案）" },
      { type: "feat", text: "TTS：MiniMax 馬雲克隆聲紋（voice_id: moss_audio_062371e7）" },
      { type: "feat", text: "LLM：Claude Haiku 4.5（Agent 通話）/ Gemini 2.5 Flash（文字聊天）" },
      { type: "feat", text: "STT：Deepgram Nova-2（中文）" },
      { type: "feat", text: "GCP：新建 jackma-db, jackma-repo, jackma-images" },
      { type: "feat", text: "頭像：馬雲照片替換所有 icon/PWA 圖示" },
    ],
  },
  {
    version: "v2.6.2",
    date: "2026-03-29 10:00",
    changes: [
      { type: "fix", text: "恢復 track.attach() 播放音訊，波浪分析改用 clone track + gain 0.001，修復通話無聲問題" },
    ],
  },
  {
    version: "v2.6.1",
    date: "2026-03-28 21:00",
    changes: [
      { type: "feat", text: "馬雲回覆加入自然短確認詞（嗯對、懂了、這樣啊...），更像真人對話節奏" },
    ],
  },
  {
    version: "v2.6.0",
    date: "2026-03-28 20:00",
    changes: [
      { type: "feat", text: "STT 引擎升級 Deepgram Nova-3（中文 Tier 1、無串流限制、延遲降 60%、成本降 68%）" },
    ],
  },
  {
    version: "v2.5.4",
    date: "2026-03-28 19:20",
    changes: [
      { type: "feat", text: "撥號前健康面板顯示「撥號後顯示系統狀態」提示，撥通後才顯示完整燈號" },
    ],
  },
  {
    version: "v2.5.3",
    date: "2026-03-28 19:00",
    changes: [
      { type: "feat", text: "PWA 版本更新通知：新版部署後顯示金色 banner，點擊重新載入" },
    ],
  },
  {
    version: "v2.5.2",
    date: "2026-03-28 18:30",
    changes: [
      { type: "feat", text: "健康指示燈在撥號前即可查看（漢堡選單不再隱藏）" },
    ],
  },
  {
    version: "v2.5.1",
    date: "2026-03-28 18:15",
    changes: [
      { type: "feat", text: "通話頁面顯示延遲指標：本輪延遲 + 最近 5 輪平均（純前端計算）" },
    ],
  },
  {
    version: "v2.5.0",
    date: "2026-03-28 18:00",
    changes: [
      { type: "perf", text: "STT 改串流模式（邊說邊轉錄，省 0.5-1.5 秒延遲，內建 240 秒自動重連）" },
    ],
  },
  {
    version: "v2.4.9",
    date: "2026-03-28 17:50",
    changes: [
      { type: "perf", text: "SYSTEM_PROMPT 精簡 25%（2807→2100 字）：合併重複段落、刪冗餘範例" },
    ],
  },
  {
    version: "v2.4.8",
    date: "2026-03-28 17:30",
    changes: [
      { type: "fix", text: "TTS 加入 VoiceSettings（stability 0.75、speed 1.05），減少破音提升穩定性" },
    ],
  },
  {
    version: "v2.4.7",
    date: "2026-03-28 17:00",
    changes: [
      { type: "fix", text: "藍色波浪修復：clone output track + gain 0.001，避免 attach() 搶 track" },
    ],
  },
  {
    version: "v2.4.6",
    date: "2026-03-28 16:40",
    changes: [
      { type: "fix", text: "網路短暫斷線不再重建通話（close_on_disconnect=False），由靜默偵測負責掛斷" },
    ],
  },
  {
    version: "v2.4.5",
    date: "2026-03-28 16:20",
    changes: [
      { type: "perf", text: "events/actions context 精簡：limit 20→5、days 30→7（語音模式）" },
    ],
  },
  {
    version: "v2.4.4",
    date: "2026-03-28 16:00",
    changes: [
      { type: "fix", text: "修復靜默偵測 crash：AgentSession 結束後 generate_reply 拋 RuntimeError，watchdog 安全退出" },
    ],
  },
  {
    version: "v2.4.3",
    date: "2026-03-28 15:30",
    changes: [
      { type: "feat", text: "簡繁轉換改用 opencc-js（765 字手動表 → 3,500+ 字完整字典 + 詞組級轉換）" },
    ],
  },
  {
    version: "v2.4.2",
    date: "2026-03-28 15:00",
    changes: [
      { type: "perf", text: "context_builder 分層精簡：對話歷史 8→6、記憶 5→2、筆記 20→5" },
    ],
  },
  {
    version: "v2.4.1",
    date: "2026-03-28 14:00",
    changes: [
      { type: "perf", text: "對話歷史 limit 15→8，減少 prompt token 降低 LLM 延遲" },
    ],
  },
  {
    version: "v2.4.0",
    date: "2026-03-28 13:30",
    changes: [
      { type: "fix", text: "STT 加入「馬雲」詞彙提示（keyword boost 10.0），避免被聽成「將兵」" },
    ],
  },
  {
    version: "v2.3.9",
    date: "2026-03-28 13:10",
    changes: [
      { type: "fix", text: "TTS 多音字消歧：「影帝→穎地」「老本行→老本杭」（pronunciation_transform）" },
    ],
  },
  {
    version: "v2.3.8",
    date: "2026-03-28 12:50",
    changes: [
      { type: "fix", text: "TTS 改回 flash_v2_5 WebSocket 串流（eleven_v3 REST 太慢且聲紋失真）" },
    ],
  },
  {
    version: "v2.3.7",
    date: "2026-03-28 12:40",
    changes: [
      { type: "feat", text: "TTS 升級 eleven_v3 via REST wrapper（中文發音最準，繞過 WebSocket 403）" },
      { type: "feat", text: "新增 NonStreamingElevenLabs wrapper 強制走 REST API" },
    ],
  },
  {
    version: "v2.3.6",
    date: "2026-03-28 12:15",
    changes: [
      { type: "fix", text: "TTS 改回 eleven_flash_v2_5 — eleven_v3 不支援 WebSocket 串流（403 錯誤）" },
      { type: "fix", text: "根因：eleven_v3 Alpha 模型的 multi-stream-input 端點回傳 403" },
    ],
  },
  {
    version: "v2.3.5",
    date: "2026-03-28 12:30",
    changes: [
      { type: "perf", text: "VAD min_silence_duration 0.6s → 0.4s（降低 200ms 回應延遲）" },
    ],
  },
  {
    version: "v2.3.4",
    date: "2026-03-28 12:00",
    changes: [
      { type: "feat", text: "TTS 定案 eleven_v3（發音最準，延遲差僅 0.2s，在 STT+LLM 3-7s 管線中無感）" },
      { type: "fix", text: "移除所有發音 workaround（同音字替換、空格分隔），eleven_v3 根因解決" },
    ],
  },
  {
    version: "v2.3.3",
    date: "2026-03-28 11:45",
    changes: [
      { type: "fix", text: "TTS 改回 eleven_flash_v2_5（低延遲 75ms，即時通話體驗優先）" },
      { type: "fix", text: "TTS 發音修正：「影帝→穎弟」同音字替換（flash 模型把「影」念成「因」）" },
    ],
  },
  {
    version: "v2.3.2",
    date: "2026-03-28 11:20",
    changes: [
      { type: "feat", text: "TTS 模型升級 eleven_v3（最新最強，中文發音準確，「影帝」不再念錯）" },
      { type: "feat", text: "健康燈號動態顯示實際 TTS provider + model（Agent 透過 data channel 回傳）" },
      { type: "fix", text: "移除「影帝→影 帝」空格 workaround — eleven_v3 根因解決發音問題" },
      { type: "fix", text: "TTS 燈號不再硬寫 MiniMax，改為如實顯示（如 ElevenLabs · eleven_v3）" },
    ],
  },
  {
    version: "v2.3.1",
    date: "2026-03-28 06:35",
    changes: [
      { type: "fix", text: "TTS 發音修正改用自訂 async generator（Docker 容器無 text_transforms 模組）" },
      { type: "fix", text: "TTS 切回 ElevenLabs（MiniMax 聲音品質不佳）" },
      { type: "feat", text: "TTS 發音清洗管線：tts_text_transforms 串流替換「影帝」→「影 帝」" },
    ],
  },
  {
    version: "v2.3.0",
    date: "2026-03-28 06:01",
    changes: [
      { type: "feat", text: "點擊暱稱可修改（PATCH /auth/me + 對話框）" },
      { type: "fix", text: "根因修復：MiniMax TTS wrapper output_emitter 改用 initialize→push→flush（不再用 start_segment）" },
      { type: "fix", text: "MiniMax 恢復為主要 TTS（中文原生引擎，解決「影帝」唸成「陰地」）" },
      { type: "fix", text: "STT 305 秒超時 — 改用 batch 模式（use_streaming=False）" },
      { type: "fix", text: "silence_watchdog 改追蹤最後互動時間（非只看 turns==0）" },
      { type: "fix", text: "移除 prompt workaround（空格分隔），改用根因解法" },
      { type: "fix", text: "CLAUDE.md 加入解題原則：禁止 workaround，必須修根因" },
    ],
  },
  {
    version: "v2.2.0",
    date: "2026-03-27 14:43",
    changes: [
      { type: "feat", text: "LLM 改用 Claude Haiku 4.5（低延遲、高品質中文）" },
      { type: "feat", text: "Room Name 加時間戳，每次通話建新 room" },
      { type: "feat", text: "s2t.ts 完全去重（765 唯一映射，0 重複）" },
      { type: "feat", text: "stage directions 雙層過濾（prompt + 正則）" },
      { type: "feat", text: "Agent timing log（STT/LLM+TTS 各步驟耗時）" },
      { type: "fix", text: "殭屍 session 阻擋 Agent dispatch（Room Name 固定 → 加 timestamp）" },
      { type: "fix", text: "Claude model ID 修正（20250315 → 20251001）" },
      { type: "fix", text: "藍色波浪不動（output analyser 需 connect 到 destination）" },
      { type: "fix", text: "TTS_PROVIDER 在 CI/CD 被寫死為 elevenlabs → 改 minimax" },
      { type: "fix", text: "MiniMax API speed/pitch 型別錯誤（float → int）" },
    ],
  },
  {
    version: "v2.1.0",
    date: "2026-03-26 16:56",
    changes: [
      { type: "feat", text: "即時通話 12 種狀態（聆聽/轉錄/思考/說話/被打斷/重連/靜默提醒/自動掛斷）" },
      { type: "feat", text: "錄音模式改串流：LLM 逐字即時回傳" },
      { type: "feat", text: "新增日誌頁面 + 版號系統" },
      { type: "feat", text: "Agent 靜默提醒/自動掛斷透過 data channel 通知前端" },
      { type: "fix", text: "STT keywords 格式錯誤導致即時通話完全無法運作" },
      { type: "fix", text: "s2t.ts 重複 key 導致 TypeScript 編譯失敗（3 次部署全敗）" },
      { type: "fix", text: "馬雲不再糾正 STT 轉錄錯字" },
    ],
  },
  {
    version: "v2.0.3",
    date: "2026-03-25 14:34",
    changes: [
      { type: "fix", text: "LiveKit 套件版本鎖定 1.5.1（解決 ChunkedStream 不兼容）" },
      { type: "fix", text: "MiniMax TTS 自訂 wrapper 適配 1.5.x（conn_options + output_emitter）" },
      { type: "fix", text: "Agent min-instances=1 寫入 CI/CD（不再被 gcloud update 覆蓋）" },
      { type: "fix", text: "Google Cloud STT 改用 cmn-Hans-CN（zh-TW 不支援）" },
      { type: "fix", text: "Gemini LLM 改用 2.5-flash（2.0-flash/1.5-flash 全 404）" },
    ],
  },
  {
    version: "v2.0.2",
    date: "2026-03-24 15:00",
    changes: [
      { type: "feat", text: "健康指示燈面板（8 燈真實偵測 + 漢堡選單）" },
      { type: "feat", text: "MiniMax TTS 克隆聲紋整合（繞過官方 plugin 限制）" },
      { type: "feat", text: "簡體→繁體顯示轉換（s2t.ts 1200+ 字映射）" },
      { type: "fix", text: "Cloud Run Agent health check（port 8080 + startup probe）" },
      { type: "fix", text: "GOOGLE_API_KEY 環境變數（LiveKit Google plugin 需要）" },
    ],
  },
  {
    version: "v2.0.1",
    date: "2026-03-23 13:32",
    changes: [
      { type: "feat", text: "LiveKit Agent 部署到 Cloud Run（Dockerfile.agent）" },
      { type: "feat", text: "GitHub Actions CI/CD 自動部署（API + Agent 同時）" },
      { type: "feat", text: "PWA 圖示更新（馬雲大哥頭像）" },
      { type: "fix", text: "SSL 憑證簽發（GoDaddy CNAME → ghs.googlehosted.com）" },
      { type: "fix", text: "資料庫表結構修復（users/conversations/turns/memory）" },
    ],
  },
  {
    version: "v2.0.0",
    date: "2026-03-23 09:47",
    changes: [
      { type: "feat", text: "初始版本上線" },
      { type: "feat", text: "FastAPI + React + LiveKit 架構" },
      { type: "feat", text: "Gemini LLM + Google STT + MiniMax TTS" },
      { type: "feat", text: "PostgreSQL + pgvector 記憶系統" },
    ],
  },
];

const typeLabel: Record<string, { text: string; color: string }> = {
  feat: { text: "新功能", color: "bg-emerald-500/20 text-emerald-400" },
  fix: { text: "修復", color: "bg-amber-500/20 text-amber-400" },
  perf: { text: "優化", color: "bg-sky-500/20 text-sky-400" },
};

export default function Changelog() {
  const [, setLocation] = useLocation();
  const isMobile = useIsMobile();

  const content = (
    <div className="flex flex-col h-full w-full bg-background font-sans overflow-hidden">
      <header className="flex-none h-14 flex items-center relative border-b border-white/5 z-10">
        <button
          onClick={() => setLocation("/")}
          className="absolute left-4 w-10 h-10 rounded-full flex items-center justify-center bg-card/50 border border-white/10 text-foreground hover:bg-card/80"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="w-full text-center text-primary text-lg tracking-widest">更新日誌</div>
      </header>

      <main className="flex-1 overflow-y-auto px-4 py-4 space-y-6">
        {CHANGELOG.map((release) => (
          <div key={release.version} className="space-y-2">
            <div className="flex items-baseline gap-2">
              <span className="text-sm font-bold text-foreground">{release.version}</span>
              <span className="text-xs text-muted-foreground">{release.date}</span>
            </div>
            <div className="space-y-1.5 pl-2 border-l-2 border-white/10">
              {release.changes.map((change, i) => {
                const label = typeLabel[change.type] || typeLabel.feat;
                return (
                  <div key={i} className="flex items-start gap-2 pl-3">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${label.color} flex-shrink-0 mt-0.5`}>
                      {label.text}
                    </span>
                    <span className="text-xs text-foreground/80">{change.text}</span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}

        <div className="text-center text-[10px] text-muted-foreground/40 py-4">
          馬雲語氣靈 — Powered by LiveKit + Gemini + MiniMax
        </div>
      </main>
    </div>
  );

  if (isMobile) return content;

  return (
    <DeviceFrame>
      <StatusBar />
      {content}
    </DeviceFrame>
  );
}
