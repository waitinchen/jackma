/**
 * 馬雲語氣靈 — LiveKit 通話 Hook
 * 取代 useElevenLabsConvAI，介面保持一致讓 Call.tsx 最小改動
 */
import { useState, useRef, useCallback, useEffect } from 'react';
import {
  Room,
  RoomEvent,
  Track,
  RemoteTrack,
  RemoteTrackPublication,
  RemoteParticipant,
  LocalParticipant,
  DisconnectReason,
} from 'livekit-client';
import { getLivekitToken } from '@/lib/api';

/** LiveKit Agents 預設透過此 topic 轉送 STT／Agent 語音轉寫（見官方 multimodal text 文件） */
const LK_TOPIC_TRANSCRIPTION = 'lk.transcription';

export type ConvStatus =
  | 'listening'        // 聆聽中 — 等待用戶說話
  | 'transcribing'     // 轉錄中 — STT 正在處理用戶語音
  | 'thinking'         // 思考中 — LLM 生成中
  | 'speaking'         // 說話中 — TTS 播放 Agent 回覆
  | 'interrupted'      // 被打斷 — 用戶插話
  | 'reconnecting'     // 重新連線中 — 網路波動
  | 'silence_warning'  // 靜默提醒 — Agent 詢問用戶是否還在
  | 'auto_hangup';     // 自動掛斷 — Agent 掛電話

export interface UseLivekitCallReturn {
  isConnected: boolean;
  isConnecting: boolean;
  isPreparing: boolean;  // 預連結中（進入頁面自動觸發）
  isPrepared: boolean;   // 預連結完成，可以按撥號
  error: string | null;
  userTranscript: string;
  agentResponse: string;
  status: ConvStatus;
  prepareConnection: () => Promise<void>;  // 預連結（進入頁面就呼叫）
  startConversation: () => Promise<void>;  // 開始對話（按綠色鈕）
  stopConversation: () => { role: string; content: string }[];
  inputLevelRef: React.MutableRefObject<number>;
  outputAnalyser: AnalyserNode | null;
  setMuted: (muted: boolean) => void;
  setSpeakerOn: (on: boolean) => void;
  // 相容 Call.tsx 介面（Phase 0 簡化版）
  pushToTalkMode: boolean;
  pttRecording: boolean;
  enablePushToTalk: (v: boolean) => void;
  startPttRecording: () => void;
  stopPttRecording: () => void;
  qualityLevel: string;
  networkLatency: number | null;
  reconnectAttempt: number;
  suggestPTT: boolean;
  // 延遲指標
  lastLatencyMs: number;
  avgLatencyMs: number;
  // 真實健康狀態
  health: {
    mic: boolean;      // 麥克風有收到音訊
    micDevice: string; // 麥克風設備名稱
    stt: boolean;      // 最近 STT 有成功
    llm: boolean;      // LLM 有回應
    tts: boolean;      // TTS 有產生音訊
    net: boolean;      // WebRTC 連線正常
    spk: boolean;      // 喇叭有輸出
    mem: boolean;      // Memory 已載入
    interrupt: boolean; // Interrupt 已啟用
    sttDetail: string;
    llmDetail: string;
    ttsDetail: string;
    ttsProvider: string;
    netDetail: string;
  };
}

export function useLivekitCall(): UseLivekitCallReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isPreparing, setIsPreparing] = useState(false);
  const [isPrepared, setIsPrepared] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [userTranscript, setUserTranscript] = useState('');
  const [agentResponse, setAgentResponse] = useState('');
  const [status, setStatusRaw] = useState<ConvStatus>('listening');
  const [outputAnalyser, setOutputAnalyser] = useState<AnalyserNode | null>(null);

  // 延遲計時：thinking → speaking
  const thinkingStartRef = useRef(0);
  const [latencies, setLatencies] = useState<number[]>([]);
  const lastLatencyRef = useRef(0);

  const setStatus = useCallback((newStatus: ConvStatus) => {
    setStatusRaw(prev => {
      if (newStatus === 'thinking' && prev !== 'thinking') {
        thinkingStartRef.current = Date.now();
      } else if (newStatus === 'speaking' && prev === 'thinking' && thinkingStartRef.current > 0) {
        const ms = Date.now() - thinkingStartRef.current;
        lastLatencyRef.current = ms;
        setLatencies(arr => [...arr.slice(-4), ms]); // 保留最近 5 筆
        thinkingStartRef.current = 0;
      }
      return newStatus;
    });
  }, []);

  // 真實健康狀態追蹤
  const [health, setHealth] = useState({
    mic: false, stt: false, llm: false, tts: false,
    net: false, spk: false, mem: false, interrupt: true,
    micDevice: '', sttDetail: '等待中', llmDetail: '等待中', ttsDetail: '等待中', ttsProvider: '', netDetail: '未連線',
  });
  const lastSttTime = useRef(0);
  const lastLlmTime = useRef(0);
  const lastTtsTime = useRef(0);
  const micActiveRef = useRef(false);

  const inputLevelRef = useRef(0);
  const roomRef = useRef<Room | null>(null);
  const transcriptRef = useRef<{ role: string; content: string }[]>([]);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const inputAnalyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number | null>(null);
  // 監控麥克風音量
  const startInputMonitor = useCallback((stream: MediaStream) => {
    try {
      const ctx = new AudioContext();
      audioCtxRef.current = ctx;
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      inputAnalyserRef.current = analyser;

      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      let micCheckCounter = 0;
      const tick = () => {
        analyser.getByteTimeDomainData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
          const v = (dataArray[i] - 128) / 128;
          sum += v * v;
        }
        const level = Math.sqrt(sum / dataArray.length);
        inputLevelRef.current = level;
        // 每 30 幀檢查一次麥克風健康（~0.5 秒）
        micCheckCounter++;
        if (micCheckCounter % 30 === 0) {
          const micOk = level > 0.001; // 有任何音訊訊號
          if (micOk !== micActiveRef.current) {
            micActiveRef.current = micOk;
            setHealth(h => ({ ...h, mic: micOk }));
          }
        }
        animFrameRef.current = requestAnimationFrame(tick);
      };
      tick();
    } catch (e) {
      console.warn('Input monitor failed:', e);
    }
  }, []);

  // 監控 Agent 音訊輸出（僅分析用，播放由 track.attach() 負責）
  // 用 clone track + gain 0.001 確保 analyser 能持續收到數據
  const attachOutputAnalyser = useCallback((track: RemoteTrack) => {
    try {
      const ctx = audioCtxRef.current || new AudioContext();
      audioCtxRef.current = ctx;
      if (ctx.state === 'suspended') {
        ctx.resume().catch(() => {});
      }

      const clonedTrack = track.mediaStreamTrack.clone();
      const mediaStream = new MediaStream([clonedTrack]);
      const source = ctx.createMediaStreamSource(mediaStream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      // 極小音量連到 destination，讓瀏覽器不優化掉 analyser 管線
      const silentGain = ctx.createGain();
      silentGain.gain.value = 0.001;

      source.connect(analyser);
      analyser.connect(silentGain);
      silentGain.connect(ctx.destination);

      setOutputAnalyser(analyser);
      console.log('🔵 Agent audio: analyser attached (clone + gain 0.001)');
    } catch (e) {
      console.warn('Output analyser failed:', e);
    }
  }, []);

  // ===== 預連結：進入通話頁面就建 Room + Connect（麥克風關著） =====
  const prepareConnection = useCallback(async () => {
    if (roomRef.current || isPreparing || isPrepared) return; // 避免重複呼叫
    setIsPreparing(true);
    setError(null);
    transcriptRef.current = [];

    try {
      console.log('🔧 預連結：取得 token...');
      const { token, url } = await getLivekitToken();

      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
      });
      roomRef.current = room;

      // 設定所有事件監聽（跟原本一樣）
      const onTranscriptionTextStream = async (
        reader: { readAll: () => Promise<string>; info?: { attributes?: Record<string, string> } },
        participantInfo: { identity: string },
      ) => {
        try {
          const text = (await reader.readAll()).trim();
          if (!text) return;
          const attrs = reader.info?.attributes ?? {};
          const isFinal = attrs['lk.transcription_final'] !== 'false';
          const localId = room.localParticipant?.identity ?? '';
          const pid = participantInfo.identity;
          if (pid === localId) {
            lastSttTime.current = Date.now();
            setHealth((h) => ({ ...h, stt: true, sttDetail: isFinal ? '轉錄成功' : '轉錄中' }));
          } else {
            lastLlmTime.current = Date.now();
            setHealth((h) => ({ ...h, llm: true, llmDetail: isFinal ? '已回應' : '回覆中' }));
          }
        } catch (e) {
          console.warn('lk.transcription stream read failed:', e);
        }
      };
      if (typeof room.registerTextStreamHandler === 'function') {
        room.registerTextStreamHandler(LK_TOPIC_TRANSCRIPTION, onTranscriptionTextStream);
      }

      room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack, pub: RemoteTrackPublication, participant: RemoteParticipant) => {
        if (track.kind === Track.Kind.Audio) {
          const el = track.attach();
          el.id = 'agent-audio';
          document.body.appendChild(el);
          attachOutputAnalyser(track);
          lastTtsTime.current = Date.now();
          setHealth(h => ({ ...h, tts: true, ttsDetail: '音訊就緒', spk: true }));
        }
      });

      room.on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => {
        track.detach().forEach((el) => el.remove());
      });

      room.on(RoomEvent.DataReceived, (payload: Uint8Array, participant?: RemoteParticipant) => {
        try {
          const msg = JSON.parse(new TextDecoder().decode(payload));
          const localId = room.localParticipant?.identity ?? '';
          const transcriptionLike =
            msg.type === 'transcription' ||
            msg.type === 'user_input_transcribed' ||
            (typeof msg.transcript === 'string' && msg.transcript.trim() !== '');
          if (transcriptionLike) {
            const text = String(msg.text ?? msg.transcript ?? '').trim();
            const pid =
              msg.participant_identity ?? msg.participantIdentity ?? msg.identity ??
              (participant && participant.identity !== localId ? participant.identity : undefined);
            if (text && pid === localId) {
              setUserTranscript(text);
              transcriptRef.current.push({ role: 'user', content: text });
              lastSttTime.current = Date.now();
              setHealth((h) => ({ ...h, stt: true, sttDetail: '轉錄成功' }));
            } else if (text && pid && pid !== localId) {
              setAgentResponse(text);
              transcriptRef.current.push({ role: 'assistant', content: text });
              lastLlmTime.current = Date.now();
              setHealth((h) => ({ ...h, llm: true, llmDetail: '已回應' }));
            } else if (text && participant && participant.identity && participant.identity !== localId) {
              setAgentResponse(text);
              transcriptRef.current.push({ role: 'assistant', content: text });
              lastLlmTime.current = Date.now();
              setHealth((h) => ({ ...h, llm: true, llmDetail: '已回應' }));
            }
          }
          if (msg.type === 'agent_state') {
            const state = msg.state;
            if (state === 'listening' || state === 'idle') setStatus('listening');
            else if (state === 'thinking') setStatus('thinking');
            else if (state === 'speaking') setStatus('speaking');
            else if (state === 'interrupted') {
              setStatus('interrupted');
              setTimeout(() => setStatus('listening'), 800);
            }
          }
          if (msg.type === 'silence_warning') setStatus('silence_warning');
          if (msg.type === 'auto_hangup') setStatus('auto_hangup');
          if (msg.type === 'tts_info') {
            setHealth(h => ({ ...h, ttsProvider: `${msg.provider} · ${msg.model}` }));
          }
        } catch { /* 非 JSON data */ }
      });

      room.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
        const text = segments.map((s) => s.text).join(' ').trim();
        if (!text) return;
        const localId = room.localParticipant?.identity ?? '';
        const seg0 = segments[0] as { participantIdentity?: string } | undefined;
        const inferredId = participant?.identity ?? seg0?.participantIdentity;
        if (inferredId === localId) {
          setUserTranscript(text);
          setStatus('thinking');
          lastSttTime.current = Date.now();
          setHealth((h) => ({ ...h, stt: true, sttDetail: '轉錄成功' }));
        } else if (inferredId && inferredId !== localId) {
          setAgentResponse(text);
          setStatus('speaking');
          transcriptRef.current.push({ role: 'assistant', content: text });
          lastLlmTime.current = Date.now();
          setHealth((h) => ({ ...h, llm: true, llmDetail: '已回應' }));
        }
      });

      room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
        const agentSpeaking = speakers.some(s => s !== room.localParticipant);
        const userSpeaking = speakers.some(s => s === room.localParticipant);
        if (agentSpeaking) setStatus('speaking');
        else if (userSpeaking) setStatus('listening');
      });

      room.on(RoomEvent.Disconnected, (reason?: DisconnectReason) => {
        console.log('Room disconnected:', reason);
        setIsConnected(false);
        setIsPrepared(false);
        setHealth(h => ({
          ...h, net: false, netDetail: '斷線',
          stt: false, sttDetail: '斷線', llm: false, llmDetail: '斷線',
          tts: false, ttsDetail: '斷線',
        }));
      });

      room.on(RoomEvent.Reconnecting, () => {
        setStatus('reconnecting');
        setHealth(h => ({ ...h, net: false, netDetail: '重新連線中' }));
      });
      room.on(RoomEvent.Reconnected, () => {
        setStatus('listening');
        setHealth(h => ({ ...h, net: true, netDetail: '已連線' }));
      });

      // 連線到 LiveKit Room（麥克風先不開）
      await room.connect(url, token);

      setIsPreparing(false);
      setIsPrepared(true);
      setHealth(h => ({ ...h, net: true, netDetail: '已連線', mem: true }));
      console.log('🔧 預連結完成！room:', room.name, '— 等待用戶按撥號鈕');

    } catch (e: any) {
      console.error('預連結失敗:', e);
      setError(e.message || '預連結失敗');
      setIsPreparing(false);
    }
  }, [isPreparing, isPrepared, attachOutputAnalyser]);

  // ===== 開始對話：用戶按綠色鈕，只開麥克風 =====
  const startConversation = useCallback(async () => {
    const room = roomRef.current;

    // 如果還沒預連結，走原本的完整流程
    if (!room || !isPrepared) {
      console.log('⚠️ 未預連結，走完整連線流程');
      setIsConnecting(true);
      if (!room) {
        await prepareConnection();
      }
    }

    setIsConnecting(true);
    try {
      const r = roomRef.current;
      if (!r) throw new Error('Room 未建立');

      // 開啟麥克風
      await r.localParticipant.setMicrophoneEnabled(true);

      // 監控麥克風音量 + 設備名稱
      const micPub = r.localParticipant.getTrackPublication(Track.Source.Microphone);
      if (micPub?.track?.mediaStream) {
        startInputMonitor(micPub.track.mediaStream);
        const audioTracks = micPub.track.mediaStream.getAudioTracks();
        if (audioTracks.length > 0) {
          const deviceLabel = audioTracks[0].label || '未知設備';
          setHealth(h => ({ ...h, micDevice: deviceLabel }));
          console.log('🎤 麥克風設備:', deviceLabel);
        }
      }

      setIsConnected(true);
      setIsConnecting(false);
      setStatus('listening');
      setHealth(h => ({ ...h, mic: true }));
      console.log('✅ 通話開始（麥克風已開啟）');

    } catch (e: any) {
      console.error('開始通話失敗:', e);
      setError(e.message || '開始通話失敗');
      setIsConnecting(false);
    }
  }, [isPrepared, prepareConnection, startInputMonitor]);

  const stopConversation = useCallback(() => {
    // 停止音量監控
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }

    // 清除 Agent 音訊元素
    const agentAudio = document.getElementById('agent-audio');
    if (agentAudio) agentAudio.remove();

    // 關閉 AudioContext
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }

    // 斷開 Room
    if (roomRef.current) {
      const r = roomRef.current;
      if (typeof r.unregisterTextStreamHandler === 'function') {
        try {
          r.unregisterTextStreamHandler(LK_TOPIC_TRANSCRIPTION);
        } catch {
          /* ignore */
        }
      }
      r.disconnect();
      roomRef.current = null;
    }

    setIsConnected(false);
    setIsConnecting(false);
    setStatus('listening');
    setOutputAnalyser(null);
    inputLevelRef.current = 0;

    // 回傳 transcript（Call.tsx 可能會用到作為 fallback）
    const transcript = [...transcriptRef.current];
    transcriptRef.current = [];
    return transcript;
  }, []);

  const setMuted = useCallback((muted: boolean) => {
    const room = roomRef.current;
    if (room) {
      room.localParticipant.setMicrophoneEnabled(!muted);
    }
  }, []);

  const setSpeakerOn = useCallback((on: boolean) => {
    const agentAudio = document.getElementById('agent-audio') as HTMLAudioElement;
    if (agentAudio) {
      agentAudio.muted = !on;
    }
  }, []);

  // 清理
  useEffect(() => {
    return () => {
      if (roomRef.current) {
        const r = roomRef.current;
        if (typeof r.unregisterTextStreamHandler === 'function') {
          try {
            r.unregisterTextStreamHandler(LK_TOPIC_TRANSCRIPTION);
          } catch {
            /* ignore */
          }
        }
        r.disconnect();
      }
      if (animFrameRef.current) {
        cancelAnimationFrame(animFrameRef.current);
      }
      if (audioCtxRef.current) {
        audioCtxRef.current.close().catch(() => {});
      }
    };
  }, []);

  return {
    isConnected,
    isConnecting,
    isPreparing,
    isPrepared,
    error,
    userTranscript,
    agentResponse,
    status,
    prepareConnection,
    startConversation,
    stopConversation,
    inputLevelRef,
    outputAnalyser,
    setMuted,
    setSpeakerOn,
    // Phase 0: PTT 和進階功能先用 stub
    pushToTalkMode: false,
    pttRecording: false,
    enablePushToTalk: () => {},
    startPttRecording: () => {},
    stopPttRecording: () => {},
    qualityLevel: 'high',
    networkLatency: null,
    reconnectAttempt: 0,
    suggestPTT: false,
    health,
    lastLatencyMs: lastLatencyRef.current,
    avgLatencyMs: latencies.length > 0 ? Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length) : 0,
  };
}
