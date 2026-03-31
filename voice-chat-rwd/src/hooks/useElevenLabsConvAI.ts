import { useState, useRef, useCallback, useEffect } from 'react';
import { getConversationSignedUrl } from '@/lib/api';

const SAMPLE_RATE_HIGH = 16000; // ElevenLabs standard: 16kHz
const SAMPLE_RATE_LOW = 8000;   // 低品質備援: 8kHz
const CHUNK_DURATION_MS = 100;  // Send audio chunks every 100ms

// 自適應音質配置
export type QualityLevel = 'high' | 'medium' | 'low';
interface QualityConfig {
  sampleRate: number;
  label: string;
}
const QUALITY_CONFIGS: Record<QualityLevel, QualityConfig> = {
  high: { sampleRate: SAMPLE_RATE_HIGH, label: '高品質 16kHz' },
  medium: { sampleRate: SAMPLE_RATE_HIGH, label: '中品質 16kHz' },
  low: { sampleRate: SAMPLE_RATE_LOW, label: '低品質 8kHz' },
};

// 錯誤閾值：超過此數量自動降級
const ERROR_THRESHOLD_FOR_DOWNGRADE = 3;
const ERROR_WINDOW_MS = 10000; // 10秒內的錯誤計數

// 重連配置
const MAX_RECONNECT_ATTEMPTS = 3;
const RECONNECT_BASE_DELAY_MS = 1000; // 初始延遲 1 秒
const HIGH_LATENCY_THRESHOLD_MS = 300; // 高延遲閾值：建議切換 PTT

export interface ConvAIEvent {
  type: string;
  // ElevenLabs 官方格式
  user_transcription_event?: { user_transcript: string };
  agent_response_event?: { agent_response: string };
  agent_response_correction_event?: { corrected_agent_response: string };
  // 舊格式相容
  user_transcript?: { user_transcript: string };
  agent_response?: { agent_response: string };
  audio_event?: { audio_base_64: string; event_id: number };
  interruption_event?: { reason: string };
  ping_event?: { event_id: number; ping_ms?: number };
}

/** 移除每句開頭寫死的罐頭語 "clean TEST TEST TEST"（與 system prompt 無關，罐頭語） */
const CANNED_CLEAN_TEST = /^\s*clean\s+TEST(\s+TEST)*\s*/gi;
function stripCannedCleanTest(text: string): string {
  if (!text || typeof text !== 'string') return text;
  return text
    .split(/([。.？！!?\n]+)/)
    .map((seg) =>
      /^[。.？！!?\n]+$/.test(seg) ? seg : seg.replace(CANNED_CLEAN_TEST, '').trimStart()
    )
    .join('')
    .trimStart();
}

export interface UseElevenLabsConvAIOptions {
  userNickname?: string;  // 用戶暱稱，會傳給 ElevenLabs Agent 的 dynamic_variables
  userProfile?: string;   // 用戶基本資料（精簡版）
  upcomingEvents?: string; // 近期事件
  myPromises?: string;    // 馬雲說過的話/承諾
  recentChatSummary?: string; // 最近文字對話摘要
  proactiveCare?: string; // 主動關心提示
  keyNotes?: string;      // 永久筆記
}

export function useElevenLabsConvAI(options: UseElevenLabsConvAIOptions = {}) {
  const { userNickname, userProfile, upcomingEvents, myPromises, recentChatSummary, proactiveCare, keyNotes } = options;
  const userNicknameRef = useRef<string | undefined>(userNickname);
  const userProfileRef = useRef<string | undefined>(userProfile);
  const upcomingEventsRef = useRef<string | undefined>(upcomingEvents);
  const myPromisesRef = useRef<string | undefined>(myPromises);
  const recentChatSummaryRef = useRef<string | undefined>(recentChatSummary);
  const proactiveCareRef = useRef<string | undefined>(proactiveCare);
  const keyNotesRef = useRef<string | undefined>(keyNotes);
  
  // 當 options 變化時更新 ref
  useEffect(() => {
    console.log("🔄 userNickname 變化:", userNickname);
    userNicknameRef.current = userNickname;
  }, [userNickname]);
  
  useEffect(() => {
    userProfileRef.current = userProfile;
  }, [userProfile]);
  
  useEffect(() => {
    upcomingEventsRef.current = upcomingEvents;
  }, [upcomingEvents]);
  
  useEffect(() => {
    myPromisesRef.current = myPromises;
  }, [myPromises]);
  
  useEffect(() => {
    recentChatSummaryRef.current = recentChatSummary;
  }, [recentChatSummary]);
  
  useEffect(() => {
    proactiveCareRef.current = proactiveCare;
  }, [proactiveCare]);
  
  useEffect(() => {
    keyNotesRef.current = keyNotes;
  }, [keyNotes]);
  
  // 初始化時也設定（避免時序問題）
  if (userNickname && !userNicknameRef.current) {
    userNicknameRef.current = userNickname;
  }
  if (userProfile && !userProfileRef.current) {
    userProfileRef.current = userProfile;
  }
  if (upcomingEvents && !upcomingEventsRef.current) {
    upcomingEventsRef.current = upcomingEvents;
  }
  if (myPromises && !myPromisesRef.current) {
    myPromisesRef.current = myPromises;
  }
  if (recentChatSummary && !recentChatSummaryRef.current) {
    recentChatSummaryRef.current = recentChatSummary;
  }
  if (proactiveCare && !proactiveCareRef.current) {
    proactiveCareRef.current = proactiveCare;
  }
  if (keyNotes && !keyNotesRef.current) {
    keyNotesRef.current = keyNotes;
  }

  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [userTranscript, setUserTranscript] = useState<string>('');
  const [agentResponse, setAgentResponse] = useState<string>('');
  const [status, setStatus] = useState<'listening' | 'thinking' | 'speaking'>('listening');
  const [inputAnalyser, setInputAnalyser] = useState<AnalyserNode | null>(null);
  const [outputAnalyser, setOutputAnalyser] = useState<AnalyserNode | null>(null);

  // 累積完整通話 transcript（掛斷時送回後端）
  const transcriptLogRef = useRef<{ role: 'user' | 'assistant'; content: string }[]>([]);
  const pendingAgentResponseRef = useRef<string>(''); // 暫存當前輪次的 agent response

  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const micSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const scriptProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const audioQueueRef = useRef<{ data: ArrayBuffer; eventId: number }[]>([]);
  const seenAudioSignaturesRef = useRef<Set<string>>(new Set());  // 🔧 改用 string 類型存儲音頻簽名
  const isPlayingRef = useRef(false);
  const currentAudioSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const inputAnalyserRef = useRef<AnalyserNode | null>(null);
  const outputAnalyserRef = useRef<AnalyserNode | null>(null);
  const mutedRef = useRef(false);
  const speakerOnRef = useRef(true);

  // 麥克風輸入音量（從 scriptProcessor 直接計算，不依賴 AnalyserNode）
  const inputLevelRef = useRef(0);
  
  // Push-to-Talk 模式：按住說話、放開停止
  const [pushToTalkMode, setPushToTalkMode] = useState(false);
  const [pttRecording, setPttRecording] = useState(false);
  const pushToTalkModeRef = useRef(false);
  const pttRecordingRef = useRef(false);

  // 自適應音質系統
  const [qualityLevel, setQualityLevel] = useState<QualityLevel>('high');
  const qualityLevelRef = useRef<QualityLevel>('high');
  const errorTimestampsRef = useRef<number[]>([]);

  // 網路偵測與重連
  const [networkLatency, setNetworkLatency] = useState<number | null>(null);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [suggestPTT, setSuggestPTT] = useState(false);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const shouldReconnectRef = useRef(false);

  // 🔧 音頻等待緩衝機制
  const lastAudioReceivedRef = useRef<number>(0);  // 最後一次收到音頻的時間
  const waitingForMoreAudioRef = useRef(false);    // 是否正在等待更多音頻
  const audioWaitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);  // 等待計時器
  const AUDIO_WAIT_TIMEOUT_MS = 2000;  // 等待緩衝時間（2 秒）

  // 🔧 防止 React StrictMode 導致重複連線
  const hasConnectedRef = useRef(false);

  // 取得當前採樣率
  const getCurrentSampleRate = () => QUALITY_CONFIGS[qualityLevelRef.current].sampleRate;

  // 測試網路延遲（ping ElevenLabs API）
  const measureNetworkLatency = async (): Promise<number> => {
    const startTime = performance.now();
    try {
      // 使用 no-cors 模式測試延遲，不需要實際回應內容
      // 改用 elevenlabs.io 首頁，避免 API 端點返回 404
      await fetch('https://elevenlabs.io/favicon.ico', { method: 'HEAD', mode: 'no-cors' });
      const latency = Math.round(performance.now() - startTime);
      setNetworkLatency(latency);
      
      // 檢查是否建議使用 PTT
      if (latency > HIGH_LATENCY_THRESHOLD_MS) {
        console.warn(`⚠️ 網路延遲較高 (${latency}ms)，建議使用對講機模式`);
        setSuggestPTT(true);
      } else {
        setSuggestPTT(false);
      }
      
      return latency;
    } catch {
      // 如果請求失敗，假設延遲很高
      const fallbackLatency = 500;
      setNetworkLatency(fallbackLatency);
      setSuggestPTT(true);
      console.warn(`⚠️ 無法測量網路延遲，建議使用對講機模式`);
      return fallbackLatency;
    }
  };

  // 記錄錯誤並檢查是否需要降級
  const recordErrorAndCheckDowngrade = () => {
    const now = Date.now();
    // 移除過期的錯誤記錄
    errorTimestampsRef.current = errorTimestampsRef.current.filter(
      t => now - t < ERROR_WINDOW_MS
    );
    // 添加新錯誤
    errorTimestampsRef.current.push(now);
    
    // 檢查是否達到降級閾值
    if (errorTimestampsRef.current.length >= ERROR_THRESHOLD_FOR_DOWNGRADE) {
      const currentLevel = qualityLevelRef.current;
      let newLevel: QualityLevel = currentLevel;
      
      if (currentLevel === 'high') {
        newLevel = 'medium';
      } else if (currentLevel === 'medium') {
        newLevel = 'low';
      }
      
      if (newLevel !== currentLevel) {
        console.warn(`⚠️ 偵測到頻繁錯誤，自動降級音質: ${currentLevel} → ${newLevel}`);
        qualityLevelRef.current = newLevel;
        setQualityLevel(newLevel);
        // 清空錯誤記錄，重新開始計數
        errorTimestampsRef.current = [];
      }
    }
  };

  const ensureAudioContext = () => {
    if (!audioContextRef.current) {
      // 不強制設置 sampleRate，讓瀏覽器使用默認值（通常是 44.1kHz 或 48kHz）
      // 重採樣會在播放時自動處理
      audioContextRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
    }
    const ctx = audioContextRef.current;
    if (ctx.state === 'suspended') {
      ctx.resume().catch(() => {});
    }
    return ctx;
  };

  const arrayBufferToBase64 = (buffer: ArrayBuffer): string => {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  };

  const base64ToArrayBuffer = (base64: string): ArrayBuffer => {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
  };

  const convertFloat32ToPCM16 = (float32Array: Float32Array): Int16Array => {
    const pcm16 = new Int16Array(float32Array.length);
    
    // 簡化處理：不再手動調整增益，因為已啟用 autoGainControl
    // 瀏覽器的 AGC 會自動處理音量，我們只做格式轉換
    for (let i = 0; i < float32Array.length; i++) {
      // Clamp to [-1, 1] and convert to signed 16-bit integer
      const s = Math.max(-1, Math.min(1, float32Array[i]));
      
      // 轉換為 PCM16
      pcm16[i] = Math.round(s * 32767);
    }
    return pcm16;
  };

  const playAudioChunk = async (audioBase64: string, eventId: number) => {
    console.log(`🔊 [DEBUG] playAudioChunk 開始, eventId: ${eventId}, base64 長度: ${audioBase64.length}`);
    
    const ctx = ensureAudioContext();
    if (!ctx) {
      console.error("❌ [DEBUG] AudioContext 為 null");
      return;
    }

    // 確保 AudioContext 處於 running 狀態
    if (ctx.state === 'suspended') {
      console.log("⚠️ [DEBUG] AudioContext suspended, 嘗試 resume...");
      try {
        await ctx.resume();
        console.log("✅ [DEBUG] AudioContext resumed 成功");
      } catch (err) {
        console.error("❌ Failed to resume AudioContext:", err);
      }
    }
    
    console.log(`📊 [DEBUG] AudioContext 狀態: ${ctx.state}, sampleRate: ${ctx.sampleRate}`);

    try {
      // 解碼 base64
      const binary = atob(audioBase64);
      const audioData = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) {
        audioData[i] = binary.charCodeAt(i);
      }
      
      // 正確解碼 PCM16 little-endian
      const sampleCount = audioData.length / 2;
      const audioBuffer = ctx.createBuffer(1, sampleCount, SAMPLE_RATE_HIGH);
      const channelData = audioBuffer.getChannelData(0);
      
      // 使用 DataView 正確解碼 little-endian PCM16（自動處理符號）
      const view = new DataView(audioData.buffer, audioData.byteOffset, audioData.length);
      for (let i = 0; i < sampleCount; i++) {
        // getInt16(offset, littleEndian) - true 表示 little-endian
        const pcm16 = view.getInt16(i * 2, true);
        // 轉換為 Float32 [-1, 1]，使用 32768.0 作為標準範圍
        channelData[i] = Math.max(-1, Math.min(1, pcm16 / 32768.0));
      }

      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      
      const gainNode = ctx.createGain();
      gainNode.gain.value = speakerOnRef.current ? 1.0 : 0.0; // 恢復正常音量，因為解碼已修正
      source.connect(gainNode);
      
      // 確保 outputAnalyser 存在並正確設置（只在第一次創建時連接到 destination）
      let analyser = outputAnalyserRef.current;
      if (!analyser) {
        analyser = ctx.createAnalyser();
        analyser.fftSize = 2048;
        analyser.smoothingTimeConstant = 0.8; // 平滑處理
        analyser.minDecibels = -90;
        analyser.maxDecibels = -10;
        // 只在創建時連接到 destination，避免重複連接
        analyser.connect(ctx.destination);
        outputAnalyserRef.current = analyser;
        setOutputAnalyser(analyser);
        
      }
      
      // 連接：source -> gain -> analyser (analyser 已連接到 destination)
      gainNode.connect(analyser);
      

      currentAudioSourceRef.current = source;
      isPlayingRef.current = true;


      await new Promise<void>((resolve) => {
        source.onended = () => {
          const playDuration = audioBuffer.duration;
          console.log(`✅ [DEBUG] 音頻 ${eventId} 播放完成, 時長: ${playDuration.toFixed(3)}s`);
          
          // 清理音頻連接，避免累積導致詭異聲音
          try {
            gainNode.disconnect();
            source.disconnect();
          } catch {}
          
          currentAudioSourceRef.current = null;
          
          // 繼續處理隊列中的下一個音頻塊
          const remainingQueueLength = audioQueueRef.current.length;
          console.log(`📊 [DEBUG] 剩餘隊列長度: ${remainingQueueLength}, isPlaying 將設為 false`);
          
          // 🔧 關鍵：先設置 isPlayingRef = false，再處理下一個
          isPlayingRef.current = false;
          
          // 🔧 修復：如果隊列還有音頻，繼續播放
          if (remainingQueueLength > 0) {
            console.log("⏭️ [DEBUG] 繼續處理下一個音頻塊");
            processAudioQueue();
            resolve();
            return;
          }
          
          // 🔧 修復：隊列空了，但不要立刻切換到 listening
          // 等待一段時間，看看是否有新的音頻 chunk 進來
          console.log(`🥣 [DEBUG] 隊列空了，等待 ${AUDIO_WAIT_TIMEOUT_MS}ms 看是否有更多音頻...`);
          waitingForMoreAudioRef.current = true;
          
          // 清除之前的等待計時器
          if (audioWaitTimerRef.current) {
            clearTimeout(audioWaitTimerRef.current);
          }
          
          // 設定等待計時器
          audioWaitTimerRef.current = setTimeout(() => {
            // 檢查是否還在等待狀態，且隊列仍然為空
            if (waitingForMoreAudioRef.current && audioQueueRef.current.length === 0) {
              console.log("✅ [DEBUG] 等待超時，確認說話結束，切換到 listening");
              waitingForMoreAudioRef.current = false;
              setStatus('listening');
            } else if (audioQueueRef.current.length > 0) {
              console.log("🎵 [DEBUG] 等待期間收到新音頻，繼續播放");
              waitingForMoreAudioRef.current = false;
              // 🔧 如果等待期間收到新音頻但沒有在播放，要觸發播放
              if (!isPlayingRef.current) {
                processAudioQueue();
              }
            }
          }, AUDIO_WAIT_TIMEOUT_MS);
          
          resolve();
        };
        
        console.log(`▶️ [DEBUG] 開始播放音頻 ${eventId}, buffer 時長: ${audioBuffer.duration.toFixed(3)}s`);
        source.start(0);
        
      });
    } catch (err) {
      console.error('Error playing audio chunk:', err);
      isPlayingRef.current = false;
      currentAudioSourceRef.current = null;
    }
  };

  const processAudioQueue = async () => {
    console.log(`📋 [DEBUG] processAudioQueue 被調用, isPlaying: ${isPlayingRef.current}, 隊列長度: ${audioQueueRef.current.length}, 等待中: ${waitingForMoreAudioRef.current}`);
    
    // 🔧 如果正在等待更多音頻，取消等待計時器（因為新音頻來了）
    if (waitingForMoreAudioRef.current) {
      console.log("🎉 [DEBUG] 等待期間收到新音頻，取消等待計時器");
      waitingForMoreAudioRef.current = false;
      if (audioWaitTimerRef.current) {
        clearTimeout(audioWaitTimerRef.current);
        audioWaitTimerRef.current = null;
      }
    }
    
    // 如果正在播放，直接返回（音頻會在 onended 時繼續處理）
    if (isPlayingRef.current) {
      console.log("⏸️ [DEBUG] 正在播放中，跳過");
      return;
    }
    
    if (audioQueueRef.current.length === 0) {
      // 🔧 不要在這裡切換到 listening，讓 onended 的等待機制處理
      console.log("📭 [DEBUG] 隊列為空，等待 onended 處理");
      return;
    }
    
    const chunk = audioQueueRef.current.shift();
    if (chunk) {
      console.log(`🎵 [DEBUG] 取出音頻塊 eventId: ${chunk.eventId}, 剩餘: ${audioQueueRef.current.length}`);
      await playAudioChunk(
        arrayBufferToBase64(chunk.data),
        chunk.eventId
      );
      // 注意：processAudioQueue 會在 playAudioChunk 的 onended 回調中被調用
      // 這裡不需要再次調用，避免重複處理
    }
  };

  const handleWebSocketMessage = async (event: MessageEvent) => {
    try {
      const data: ConvAIEvent = JSON.parse(event.data);

      if (data.type === 'ping') {
        const pingId = data.ping_event?.event_id;
        const pingMs = data.ping_event?.ping_ms;
        
        if (pingId && wsRef.current?.readyState === WebSocket.OPEN) {
          try {
            wsRef.current.send(JSON.stringify({ type: 'pong', event_id: pingId }));
            // 每 10 次 ping 記錄一次
            if (Math.random() < 0.1) {
            }
          } catch (err) {
            console.error("❌ Failed to send pong:", err);
            // 如果發送失敗，可能是連接已斷開
            if (wsRef.current?.readyState !== WebSocket.OPEN) {
              console.error("⚠️ WebSocket connection lost during pong");
              setIsConnected(false);
            }
          }
        } else {
          console.warn("⚠️ Received ping but WebSocket not open, readyState:", wsRef.current?.readyState);
          // 如果收到 ping 但連接已關閉，更新狀態
          // WebSocket.CLOSED = 3
          if (wsRef.current?.readyState === 3) {
            console.warn("⚠️ WebSocket is closed, connection may have been lost");
            setIsConnected(false);
          }
        }
        return;
      }

      if (data.type === 'user_transcript') {
        const transcript = data.user_transcription_event?.user_transcript
          || data.user_transcript?.user_transcript || '';
        console.log("🎤 User transcript:", transcript, "| raw keys:", Object.keys(data));
        setUserTranscript(transcript);
        // 先把上一輪的 agent response 存入 log（如果有的話）
        if (pendingAgentResponseRef.current) {
          transcriptLogRef.current.push({ role: 'assistant', content: pendingAgentResponseRef.current });
          pendingAgentResponseRef.current = '';
        }
        if (transcript.trim()) {
          transcriptLogRef.current.push({ role: 'user', content: transcript.trim() });
          console.log("📝 Transcript log 新增 user:", transcript.trim(), "| 總計:", transcriptLogRef.current.length);
        }
        setStatus('thinking');
        return;
      }

      if (data.type === 'agent_response') {
        const raw = data.agent_response_event?.agent_response
          || data.agent_response?.agent_response || '';
        const cleaned = stripCannedCleanTest(raw);
        console.log("🤖 Agent response:", cleaned.substring(0, 80), "| raw keys:", Object.keys(data));
        // ElevenLabs 可能會多次更新 agent_response（streaming/tentative/correction），保留較長或更新的版本
        setAgentResponse((prev) => {
          const newText = cleaned.trim();
          const prevText = prev.trim();
          // 如果新回應比舊的長，或舊的回應很短（可能是 tentative），或新回應完全不同（correction），則更新
          const isLonger = newText.length > prevText.length;
          const isPrevShort = prevText.length < 10;
          const isDifferent = newText !== prevText && !newText.startsWith(prevText) && !prevText.startsWith(newText);
          if (isLonger || isPrevShort || isDifferent) {
            // 暫存最新版本，等下一輪 user_transcript 或掛斷時再存入 log
            pendingAgentResponseRef.current = newText;
            return newText;
          }
          // 否則保留舊的（可能是最終版本）
          return prev;
        });
        setStatus('speaking'); // 馬雲開始說話
        return;
      }

      if (data.type === 'agent_response_correction') {
        const corrected = (data as any).agent_response_correction_event?.corrected_agent_response || '';
        if (corrected.trim()) {
          const cleaned = stripCannedCleanTest(corrected);
          console.log("🔄 Agent response correction:", cleaned.substring(0, 80));
          setAgentResponse(cleaned.trim());
          pendingAgentResponseRef.current = cleaned.trim();
        }
        return;
      }

      if (data.type === 'interruption') {
        console.log("🛑 [DEBUG] 收到 interruption 事件");
        
        // 🔧 清除等待計時器
        if (audioWaitTimerRef.current) {
          clearTimeout(audioWaitTimerRef.current);
          audioWaitTimerRef.current = null;
        }
        waitingForMoreAudioRef.current = false;
        
        if (currentAudioSourceRef.current) {
          currentAudioSourceRef.current.stop();
          currentAudioSourceRef.current = null;
        }
        isPlayingRef.current = false;
        audioQueueRef.current = [];
        seenAudioSignaturesRef.current.clear();
        setStatus('listening'); // 被打斷，回到聆聽狀態
        return;
      }

      if (data.type === 'audio' && data.audio_event) {
        const { audio_base_64, event_id } = data.audio_event;
        
        console.log(`📨 [DEBUG] 收到音頻事件, event_id: ${event_id}, base64 長度: ${audio_base_64.length}`);
        
        // 🔧 記錄最後收到音頻的時間
        lastAudioReceivedRef.current = Date.now();
        
        // 🔧 智慧去重：用 base64 的前 50 字元 + 長度 組合來識別
        // 這樣可以精確識別完全相同的封包，同時允許同 event_id 的不同封包通過
        const audioSignature = `${audio_base_64.substring(0, 50)}_${audio_base_64.length}`;
        if (seenAudioSignaturesRef.current.has(audioSignature)) {
          console.log(`⏭️ [DEBUG] 跳過重複的音頻封包 (event_id: ${event_id})`);
          return;
        }
        seenAudioSignaturesRef.current.add(audioSignature);
        
        const audioData = base64ToArrayBuffer(audio_base_64);
        
        // 確保 AudioContext 在處理第一個音頻之前已經準備好
        const ctx = ensureAudioContext();
        if (ctx && ctx.state === 'suspended') {
          console.log("⚠️ [DEBUG] AudioContext suspended, 嘗試 resume...");
          try {
            await ctx.resume();
            console.log("✅ [DEBUG] AudioContext resumed");
          } catch (err) {
            console.error("❌ Failed to resume AudioContext:", err);
          }
        }
        
        audioQueueRef.current.push({ data: audioData, eventId: event_id });
        console.log(`📥 [DEBUG] 音頻加入隊列, event_id: ${event_id}, 隊列長度: ${audioQueueRef.current.length}, isPlaying: ${isPlayingRef.current}, 等待中: ${waitingForMoreAudioRef.current}`);
        
        // 特別標記第一個音頻 chunk（event_id 通常從 0 或 1 開始）
        if (event_id === 0 || event_id === 1 || audioQueueRef.current.length === 1) {
          console.log(`🎯 [DEBUG] 第一個音頻塊! event_id: ${event_id}`);
        }
        
        setStatus('speaking'); // 收到音頻，馬雲正在說話
        
        // 如果當前沒有播放音頻，立即開始處理隊列
        if (!isPlayingRef.current) {
          console.log("▶️ [DEBUG] 開始處理音頻隊列");
          processAudioQueue();
        } else {
          console.log("⏸️ [DEBUG] 正在播放中，音頻已加入隊列等待");
        }
        return;
      }
    } catch (err) {
      console.error('Error handling WebSocket message:', err);
    }
  };

  const startConversation = useCallback(async () => {
    // 🔧 防止 React StrictMode 導致重複連線
    if (hasConnectedRef.current) {
      console.log("⚠️ [DEBUG] 已經連線過，跳過重複連線");
      return;
    }
    
    if (isConnecting || isConnected) {
      return;
    }
    
    // 🔧 標記為已連線（在任何異步操作之前）
    hasConnectedRef.current = true;
    
    // 🔧 強制清空上一場的記憶，避免殘留音頻
    audioQueueRef.current = [];
    isPlayingRef.current = false;
    seenAudioSignaturesRef.current.clear();
    waitingForMoreAudioRef.current = false;
    if (audioWaitTimerRef.current) {
      clearTimeout(audioWaitTimerRef.current);
      audioWaitTimerRef.current = null;
    }
    
    setStatus('listening'); // 初始狀態為聆聽中

    // 啟用自動重連
    shouldReconnectRef.current = true;

    setIsConnecting(true);
    setError(null);

    try {
      // 首次連接時測量網路延遲
      if (reconnectAttemptRef.current === 0) {
        const latency = await measureNetworkLatency();
      }

      const signedUrl = await getConversationSignedUrl();
      const ws = new WebSocket(signedUrl);

      ws.onopen = async () => {
        setIsConnected(true);
        setIsConnecting(false);
        setError(null); // 清除之前的錯誤
        
        // 重連成功，重置計數器
        if (reconnectAttemptRef.current > 0) {
        }
        reconnectAttemptRef.current = 0;
        setReconnectAttempt(0);
        
        // 保存 WebSocket 引用
        wsRef.current = ws;
        
        try {
          // VAD 參數調整：減少誤判，提高語音識別準確度
          // 同時傳入用戶暱稱作為動態變數
          const initMessage: {
            type: string;
            dynamic_variables?: Record<string, string>;
            conversation_config_override: {
              turn_detection: {
                mode: string;
                threshold: number;
                prefix_padding_ms: number;
                silence_duration_ms: number;
              };
            };
          } = {
            type: 'conversation_initiation_client_data',
            conversation_config_override: {
              turn_detection: {
                mode: 'server_vad',
                threshold: 0.6,           // 提高閾值，減少誤觸發（默認 0.5）
                prefix_padding_ms: 400,   // 增加前置緩衝，捕捉說話開頭
                silence_duration_ms: 1000 // 增加靜音判定時長，減少「說到一半被打斷」
              }
            }
          };
          
          // 傳入動態變數（用戶 context）
          const dynamicVars: Record<string, string> = {
            user_nickname: userNicknameRef.current || '',
          };
          
          // 加入其他 context（如果有的話）
          if (userProfileRef.current) {
            dynamicVars.user_profile = userProfileRef.current;
          }
          if (upcomingEventsRef.current) {
            dynamicVars.upcoming_events = upcomingEventsRef.current;
          }
          if (myPromisesRef.current) {
            dynamicVars.my_promises = myPromisesRef.current;
          }
          if (recentChatSummaryRef.current) {
            dynamicVars.recent_chat_summary = recentChatSummaryRef.current;
          }
          if (proactiveCareRef.current) {
            dynamicVars.proactive_care = proactiveCareRef.current;
          }
          if (keyNotesRef.current) {
            dynamicVars.key_notes = keyNotesRef.current;
          }
          
          initMessage.dynamic_variables = dynamicVars;
          console.log("📝 傳入 dynamic_variables:", dynamicVars);
          
          ws.send(JSON.stringify(initMessage));
          
        } catch (err) {
          console.error("❌ Failed to send initiation message:", err);
          setError('發送初始化訊息失敗');
          
        }

        const ctx = ensureAudioContext();
        if (!ctx) {
          console.error("❌ Failed to create audio context");
          setError('無法初始化音頻上下文');
          return;
        }

        try {
          // 先創建 outputAnalyser 並連接到 destination，確保可視化正常工作
          if (!outputAnalyserRef.current) {
            const outputAnalyser = ctx.createAnalyser();
            outputAnalyser.fftSize = 2048;
            outputAnalyser.smoothingTimeConstant = 0.8;
            outputAnalyser.minDecibels = -90;
            outputAnalyser.maxDecibels = -10;
            // 創建一個空的 GainNode 作為輸出節點，連接到 analyser
            const outputGain = ctx.createGain();
            outputGain.gain.value = 0; // 初始為靜音
            outputGain.connect(outputAnalyser);
            outputAnalyser.connect(ctx.destination);
            outputAnalyserRef.current = outputAnalyser;
            setOutputAnalyser(outputAnalyser);
          }

          // 麥克風配置優化：啟用回聲消除、降噪、自動增益控制
          const stream = await navigator.mediaDevices.getUserMedia({
            audio: {
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
              sampleRate: getCurrentSampleRate(), // 根據音質設定調整
              channelCount: 1,
            }
          });
          streamRef.current = stream;

          const source = ctx.createMediaStreamSource(stream);
          micSourceRef.current = source;

          // 先創建 analyser 用於可視化
          const analyser = ctx.createAnalyser();
          analyser.fftSize = 2048;
          analyser.smoothingTimeConstant = 0.8;
          analyser.minDecibels = -90;
          analyser.maxDecibels = -10;
          
          // 使用較小的緩衝區以減少延遲和音頻不連續
          const bufferSize = 2048; // 減少緩衝區大小
          const scriptProcessor = ctx.createScriptProcessor(bufferSize, 1, 1);
          scriptProcessorRef.current = scriptProcessor;

          scriptProcessor.onaudioprocess = (e) => {
            const inputData = e.inputBuffer.getChannelData(0);
            const inputRms = Math.sqrt(inputData.reduce((sum, v) => sum + v * v, 0) / inputData.length);
            const maxAmplitude = Math.max(...Array.from(inputData).map(Math.abs));

            // 更新麥克風輸入音量（供波浪線可視化使用）
            inputLevelRef.current = Math.min(1, Math.max(inputRms * 5.0, maxAmplitude * 3.0));
            
            // 使用 wsRef.current 而不是閉包中的 ws，確保使用最新的 WebSocket 實例
            const currentWs = wsRef.current;
            
            // 每 100 次調用記錄一次，避免日誌過多
            const shouldLog = Math.random() < 0.01;
            if (shouldLog) {
            }
            
            if (!currentWs || currentWs.readyState !== WebSocket.OPEN) {
              if (shouldLog) {
                console.warn("⚠️ WebSocket not open, readyState:", currentWs?.readyState);
                // 如果連接已關閉，更新狀態
                // WebSocket.CLOSED = 3, WebSocket.CLOSING = 2, WebSocket.OPEN = 1
                if (currentWs) {
                  const readyState: number = currentWs.readyState as number;
                  if (readyState === 3 || readyState === 2) {
                    console.error("❌ WebSocket connection lost during audio processing");
                    setIsConnected(false);
                  }
                }
              }
              return;
            }
            
            if (mutedRef.current) {
              if (shouldLog) {
              }
              return;
            }
            
            // Push-to-Talk 模式：只有按住時才發送音頻
            if (pushToTalkModeRef.current && !pttRecordingRef.current) {
              if (shouldLog) {
              }
              return;
            }
            
            // 如果音頻太安靜，跳過發送（但記錄日誌）
            if (inputRms < 0.01 && maxAmplitude < 0.01) {
              if (shouldLog) {
              }
              // 仍然發送，讓 ElevenLabs 處理靜音檢測
            }
            
            // 重採樣：從瀏覽器採樣率轉換為目標採樣率
            // 簡化處理，不再做額外的濾波（瀏覽器 noiseSuppression 已處理）
            const ctxSampleRate = ctx.sampleRate;
            let processedData: Float32Array;
            
            const targetSampleRate = getCurrentSampleRate();
            if (ctxSampleRate !== targetSampleRate) {
              // 簡單線性插值重採樣
              const ratio = targetSampleRate / ctxSampleRate;
              const newLength = Math.floor(inputData.length * ratio);
              processedData = new Float32Array(newLength);
              
              for (let i = 0; i < newLength; i++) {
                const srcIndex = i / ratio;
                const srcIndexFloor = Math.floor(srcIndex);
                const srcIndexCeil = Math.min(srcIndexFloor + 1, inputData.length - 1);
                const t = srcIndex - srcIndexFloor;
                // 線性插值
                processedData[i] = inputData[srcIndexFloor] * (1 - t) + inputData[srcIndexCeil] * t;
              }
            } else {
              // 採樣率相同，直接使用原始數據
              processedData = inputData;
            }
            
            // 不再在這裡應用靜音閾值，讓 convertFloat32ToPCM16 處理
            // 這樣可以保持音頻的完整性，避免過度過濾
            
            const pcm16 = convertFloat32ToPCM16(processedData);
            const buffer = pcm16.buffer instanceof ArrayBuffer ? pcm16.buffer : new ArrayBuffer(pcm16.byteLength);
            if (!(pcm16.buffer instanceof ArrayBuffer)) {
              new Uint8Array(buffer).set(new Uint8Array(pcm16.buffer));
            }
            const base64 = arrayBufferToBase64(buffer);
            
            try {
              const message = {
                user_audio_chunk: base64,
              };
              currentWs.send(JSON.stringify(message));
              
              // 每 100 次發送記錄一次
              if (shouldLog) {
              }
            } catch (err) {
              console.error("❌ Failed to send audio chunk:", err);
              console.error("WebSocket state:", currentWs?.readyState);
              // 記錄錯誤，可能觸發音質降級
              recordErrorAndCheckDowngrade();
              // 如果發送失敗且連接已關閉，更新狀態
              // WebSocket.CLOSED = 3, WebSocket.CLOSING = 2, WebSocket.OPEN = 1
              if (currentWs) {
                const readyState: number = currentWs.readyState as number;
                if (readyState === 3 || readyState === 2) {
                  console.error("❌ WebSocket connection lost, stopping audio processing");
                  setIsConnected(false);
                }
              }
            }
          };

          // scriptProcessor 需要連接到 destination（通過 gain=0）才能觸發 onaudioprocess
          const scriptProcessorOutputGain = ctx.createGain();
          scriptProcessorOutputGain.gain.value = 0;
          
          // 連接 analyser 用於可視化
          // 關鍵修正：gain 設為極小值 0.001 而非 0，避免瀏覽器優化掉音頻路徑導致 analyser 讀不到數據
          const analyserOutputGain = ctx.createGain();
          analyserOutputGain.gain.value = 0.001; // 幾乎聽不到，但保持音頻路徑活躍
          source.connect(analyser);
          analyser.connect(analyserOutputGain);
          analyserOutputGain.connect(ctx.destination);
          
          inputAnalyserRef.current = analyser;
          setInputAnalyser(analyser);
          
          // 連接 scriptProcessor 用於音頻處理和發送
          source.connect(scriptProcessor);
          scriptProcessor.connect(scriptProcessorOutputGain);
          scriptProcessorOutputGain.connect(ctx.destination);
          
          
          
        } catch (err) {
          console.error('Error accessing microphone:', err);
          const errorMsg = err instanceof Error ? err.message : String(err);
          if (errorMsg.includes('Permission denied') || errorMsg.includes('NotAllowedError')) {
            setError('無法存取麥克風：請允許瀏覽器使用麥克風權限');
          } else if (errorMsg.includes('NotFoundError') || errorMsg.includes('DevicesNotFoundError')) {
            setError('無法存取麥克風：未找到麥克風設備');
          } else {
            setError(`無法存取麥克風：${errorMsg}`);
          }
          ws.close();
        }
      };

      ws.onmessage = handleWebSocketMessage;
      
      ws.onerror = (error) => {
        console.error("❌ WebSocket error:", error);
        setError('WebSocket 連接錯誤');
        setIsConnected(false);
        setIsConnecting(false);
        // 記錄錯誤，可能觸發音質降級
        recordErrorAndCheckDowngrade();
      };
      
      ws.onclose = (event) => {
        setIsConnected(false);
        setIsConnecting(false);
        
        // 非正常關閉時嘗試重連
        if (event.code !== 1000 && shouldReconnectRef.current) { // 1000 = normal closure
          const attempt = reconnectAttemptRef.current;
          
          if (attempt < MAX_RECONNECT_ATTEMPTS) {
            // 指數退避：1s, 2s, 4s
            const delay = RECONNECT_BASE_DELAY_MS * Math.pow(2, attempt);
            setError(`連接已斷開，${Math.round(delay/1000)}秒後重連 (${attempt + 1}/${MAX_RECONNECT_ATTEMPTS})`);
            
            reconnectTimerRef.current = setTimeout(() => {
              reconnectAttemptRef.current = attempt + 1;
              setReconnectAttempt(attempt + 1);
              // 清理並重新連接
              cleanup();
              startConversation();
            }, delay);
          } else {
            // 超過重連次數
            console.error(`❌ 已達最大重連次數 (${MAX_RECONNECT_ATTEMPTS})，停止重連`);
            setError(`連接失敗，請檢查網路後重試`);
            shouldReconnectRef.current = false;
            reconnectAttemptRef.current = 0;
            setReconnectAttempt(0);
          }
        } else if (event.code !== 1000) {
          setError(`連接已斷開 (code: ${event.code})`);
        }
      };

      // 注意：上面的 ws.onerror 和 ws.onclose 已經處理了，這裡不需要重複

      wsRef.current = ws;
    } catch (err) {
      console.error('❌ Error starting conversation:', err);
      const errorMsg = err instanceof Error ? err.message : String(err);
      console.error('Error details:', {
        message: errorMsg,
        stack: err instanceof Error ? err.stack : undefined,
        name: err instanceof Error ? err.name : undefined
      });
      
      if (errorMsg.includes('signed-url') || errorMsg.includes('連線網址')) {
        setError('無法取得 WebSocket 連線網址，請檢查後端服務是否正常運行');
      } else if (errorMsg.includes('Failed to fetch')) {
        setError('無法連接到後端服務，請檢查網路連線');
      } else {
        setError(`啟動對話失敗: ${errorMsg}`);
      }
      setIsConnecting(false);
      setIsConnected(false);
    }
  }, [isConnecting, isConnected]);

  const stopConversation = useCallback(() => {
    // 🔧 重置連線鎖，允許下次重新連線
    hasConnectedRef.current = false;
    
    // 把最後一輪的 agent response 存入 log
    if (pendingAgentResponseRef.current) {
      transcriptLogRef.current.push({ role: 'assistant', content: pendingAgentResponseRef.current });
      pendingAgentResponseRef.current = '';
    }
    
    // 取出完整 transcript 並清空
    const fullTranscript = [...transcriptLogRef.current];
    transcriptLogRef.current = [];
    
    console.log(`📞 掛斷 - transcript 共 ${fullTranscript.length} 則:`, fullTranscript.map(m => `[${m.role}] ${m.content.substring(0, 30)}`));
    
    // 停止自動重連
    shouldReconnectRef.current = false;
    reconnectAttemptRef.current = 0;
    setReconnectAttempt(0);
    
    // 清除重連計時器
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    cleanup();
    setIsConnected(false);
    setIsConnecting(false);
    setError(null);
    setUserTranscript('');
    setAgentResponse('');
    
    return fullTranscript;
  }, []);

  const cleanup = () => {
    // 🔧 清除音頻等待計時器
    if (audioWaitTimerRef.current) {
      clearTimeout(audioWaitTimerRef.current);
      audioWaitTimerRef.current = null;
    }
    waitingForMoreAudioRef.current = false;
    
    // 🔧 注意：不在 cleanup 中重置 hasConnectedRef
    // 因為 cleanup 可能在重連時被調用，我們只在 stopConversation 中重置
    
    if (scriptProcessorRef.current) {
      scriptProcessorRef.current.disconnect();
      scriptProcessorRef.current = null;
    }
    if (micSourceRef.current) {
      micSourceRef.current.disconnect();
      micSourceRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    if (currentAudioSourceRef.current) {
      currentAudioSourceRef.current.stop();
      currentAudioSourceRef.current = null;
    }
    isPlayingRef.current = false;
    audioQueueRef.current = [];
    seenAudioSignaturesRef.current.clear();
  };

  useEffect(() => {
    return () => {
      // 🔧 組件卸載時重置連線鎖
      hasConnectedRef.current = false;
      stopConversation();
      if (audioContextRef.current) {
        audioContextRef.current.close().catch(() => {});
        audioContextRef.current = null;
      }
    };
  }, [stopConversation]);

  const setMuted = useCallback((muted: boolean) => {
    mutedRef.current = muted;
  }, []);

  const setSpeakerOn = useCallback((on: boolean) => {
    speakerOnRef.current = on;
  }, []);

  // Push-to-Talk 模式控制
  const enablePushToTalk = useCallback((enabled: boolean) => {
    pushToTalkModeRef.current = enabled;
    setPushToTalkMode(enabled);
    if (!enabled) {
      // 關閉 PTT 模式時，重置錄音狀態
      pttRecordingRef.current = false;
      setPttRecording(false);
    }
  }, []);

  // PTT 錄音控制（按下/放開）
  const startPttRecording = useCallback(() => {
    if (!pushToTalkModeRef.current) return;
    pttRecordingRef.current = true;
    setPttRecording(true);
  }, []);

  const stopPttRecording = useCallback(() => {
    if (!pushToTalkModeRef.current) return;
    pttRecordingRef.current = false;
    setPttRecording(false);
  }, []);

  // 手動調整音質（向上升級）
  const upgradeQuality = useCallback(() => {
    const currentLevel = qualityLevelRef.current;
    let newLevel: QualityLevel = currentLevel;
    
    if (currentLevel === 'low') {
      newLevel = 'medium';
    } else if (currentLevel === 'medium') {
      newLevel = 'high';
    }
    
    if (newLevel !== currentLevel) {
      qualityLevelRef.current = newLevel;
      setQualityLevel(newLevel);
      // 清空錯誤記錄
      errorTimestampsRef.current = [];
    }
  }, []);

  // 手動調整音質（向下降級）
  const downgradeQuality = useCallback(() => {
    const currentLevel = qualityLevelRef.current;
    let newLevel: QualityLevel = currentLevel;
    
    if (currentLevel === 'high') {
      newLevel = 'medium';
    } else if (currentLevel === 'medium') {
      newLevel = 'low';
    }
    
    if (newLevel !== currentLevel) {
      qualityLevelRef.current = newLevel;
      setQualityLevel(newLevel);
    }
  }, []);

  // 重置音質到高
  const resetQuality = useCallback(() => {
    qualityLevelRef.current = 'high';
    setQualityLevel('high');
    errorTimestampsRef.current = [];
  }, []);

  return {
    isConnected,
    isConnecting,
    error,
    userTranscript,
    agentResponse,
    status,
    startConversation,
    stopConversation,
    inputAnalyser,
    outputAnalyser,
    inputLevelRef,
    setMuted,
    setSpeakerOn,
    // Push-to-Talk
    pushToTalkMode,
    pttRecording,
    enablePushToTalk,
    startPttRecording,
    stopPttRecording,
    // 自適應音質
    qualityLevel,
    upgradeQuality,
    downgradeQuality,
    resetQuality,
    // 網路狀態與重連
    networkLatency,
    reconnectAttempt,
    suggestPTT,
  };
}
