import { useState, useRef, useEffect } from "react";
import { Mic, MicOff, Phone, PhoneOff, Volume2, VolumeX, Radio, ArrowLeft, Menu, X } from "lucide-react";
import { useLocation } from "wouter";
import { cn } from "@/lib/utils";
import { DeviceFrame, StatusBar } from "@/components/DeviceFrame";
import { useIsMobile } from "@/hooks/use-mobile";
import { useStandalone } from "@/hooks/useStandalone";
import { useLivekitCall } from "@/hooks/useLivekitCall";
import { PWAInstallPrompt } from "@/components/PWAInstallPrompt";
import { PWAStandaloneLock } from "@/components/PWAStandaloneLock";
import { useAuth } from "@/contexts/AuthContext";
import { saveCallTranscript } from "@/lib/api";
import { s2t } from "@/lib/s2t";

type CallPhase = 'idle' | 'ringing' | 'connected';

/** 打字機效果組件：文字逐字出現 */
function TypewriterText({ text, className }: { text: string; className?: string }) {
  const [displayed, setDisplayed] = useState('');
  const prevTextRef = useRef('');

  useEffect(() => {
    // 如果是全新的文字（不是追加），重新打字
    if (!text.startsWith(prevTextRef.current) || prevTextRef.current === '') {
      setDisplayed('');
      let i = 0;
      const timer = setInterval(() => {
        i++;
        if (i <= text.length) {
          setDisplayed(text.slice(0, i));
        } else {
          clearInterval(timer);
        }
      }, 50); // 每 50ms 出一個字
      prevTextRef.current = text;
      return () => clearInterval(timer);
    } else {
      // 文字是追加的（interim results），直接顯示新增部分
      const newPart = text.slice(prevTextRef.current.length);
      let i = 0;
      const timer = setInterval(() => {
        i++;
        if (i <= newPart.length) {
          setDisplayed(prevTextRef.current + newPart.slice(0, i));
        } else {
          clearInterval(timer);
        }
      }, 50);
      prevTextRef.current = text;
      return () => clearInterval(timer);
    }
  }, [text]);

  return (
    <div className={cn(className, "transition-all")}>
      {displayed}
      {displayed.length < text.length && (
        <span className="inline-block w-0.5 h-3 bg-current animate-pulse ml-0.5" />
      )}
    </div>
  );
}

export default function Call() {
  const { user } = useAuth();  // 取得當前登入用戶
  
  // LiveKit：用戶 context 由 Agent 端載入，前端不需要
  const contextLoaded = true;
  
  const [muted, setMuted] = useState(false);
  const [speakerOn, setSpeakerOn] = useState(true);
  const [callSeconds, setCallSeconds] = useState(0);
  const [callPhase, setCallPhase] = useState<CallPhase>('idle');
  const [callActive, setCallActive] = useState(false);
  const [ringCount, setRingCount] = useState(0);
  const [showConnected, setShowConnected] = useState(false);
  const [showHealthPanel, setShowHealthPanel] = useState(false);

  const audioCtxRef = useRef<AudioContext | null>(null);
  const animationRef = useRef<number | null>(null);
  const ringTimerRef = useRef<number | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const waveRingRef = useRef<HTMLDivElement | null>(null);
  const ringAudioRef = useRef<HTMLAudioElement | null>(null);
  const outputLevelRef = useRef(0);
  const waveFrameRef = useRef(0);
  const callPhaseRef = useRef<CallPhase>('idle');
  const callStartRef = useRef(false);
  const [location, setLocation] = useLocation();
  const isMobile = useIsMobile();
  const standalone = useStandalone();

  const {
    isConnected,
    isConnecting,
    error: convError,
    userTranscript,
    agentResponse,
    status: convStatus,
    startConversation,
    stopConversation,
    inputLevelRef,
    outputAnalyser,
    setMuted: setConvMuted,
    setSpeakerOn: setConvSpeakerOn,
    // Push-to-Talk
    pushToTalkMode,
    pttRecording,
    enablePushToTalk,
    startPttRecording,
    stopPttRecording,
    // 自適應音質
    qualityLevel,
    // 網路狀態
    networkLatency,
    reconnectAttempt,
    suggestPTT,
    health,
    lastLatencyMs,
    avgLatencyMs,
  } = useLivekitCall();
  
  // Debug: 顯示連線狀態
  useEffect(() => {
    console.log("🔍 LiveKit 通話狀態:", { isConnected, isConnecting, convStatus });
  }, [isConnected, isConnecting, convStatus]);

  useEffect(() => {
    setConvMuted(muted);
  }, [muted, setConvMuted]);

  useEffect(() => {
    setConvSpeakerOn(speakerOn);
  }, [speakerOn, setConvSpeakerOn]);

  useEffect(() => {
    callPhaseRef.current = callPhase;
  }, [callPhase]);

  useEffect(() => {
    if (!callActive) {
      setCallSeconds(0);
      return;
    }
    const startedAt = Date.now();
    const timer = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startedAt) / 1000);
      setCallSeconds(elapsed);
    }, 1000);
    return () => clearInterval(timer);
  }, [callActive]);

  const resolveAutoDial = () => {
    // 檢查 URL 路徑：/realtime 或 /call 都支援自動撥號
    const path = window.location.pathname;
    const isRealtimePath = path === "/realtime" || path.includes("/realtime");
    const isCallPath = path === "/call" || window.location.hash.includes("/call");
    
    // 檢查 autodial 參數
    const search = window.location.search || "";
    let query = search;
    if (!query && window.location.hash.includes("?")) {
      query = window.location.hash.split("?")[1] || "";
    }
    const params = query ? new URLSearchParams(query.startsWith("?") ? query.slice(1) : query) : null;
    const autodial = params?.get("autodial");
    
    // /realtime 路徑或 autodial=1 都觸發自動撥號
    return isRealtimePath || (autodial === "1" || autodial?.toLowerCase() === "true");
  };

  useEffect(() => {
    if (callStartRef.current) return;
    const shouldAutoDial = resolveAutoDial();
    if (!shouldAutoDial) return;
    
    // 等待 user 和 context 都載入完成再自動撥號
    if (user === null || !contextLoaded) {
      console.log("⏳ 等待用戶資料和 context 載入...");
      return;
    }
    
    console.log("✅ 用戶資料和 context 已載入，準備自動撥號:", {
      name: user?.name,
      contextLoaded,
    });
    callStartRef.current = true;
    setTimeout(() => {
      startCall();
    }, 100);
  }, [user, contextLoaded]);

  const ensureAudioContext = () => {
    if (!audioCtxRef.current) {
      audioCtxRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
    }
    const ctx = audioCtxRef.current;
    if (ctx.state === "suspended") {
      ctx.resume().catch(() => {});
    }
  };

  const stopVisualization = () => {
    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
    if (waveRingRef.current) {
      waveRingRef.current.style.transform = "scale(1)";
      waveRingRef.current.style.opacity = "0.2";
    }
  };

  const drawWaveform = () => {
    const canvas = canvasRef.current;
    if (!canvas) {
      animationRef.current = requestAnimationFrame(drawWaveform);
      return;
    }
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      animationRef.current = requestAnimationFrame(drawWaveform);
      return;
    }
    

    const width = canvas.clientWidth || 300;
    const height = canvas.clientHeight || 48;
    if (width <= 0 || height <= 0) {
      animationRef.current = requestAnimationFrame(drawWaveform);
      return;
    }
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }

    // 麥克風輸入音量：直接從 hook 的 inputLevelRef 讀取（由 scriptProcessor 計算）
    // 不再依賴 AnalyserNode（瀏覽器會優化掉 gain=0 的音頻路徑）

    if (outputAnalyser) {
      const dataArray = new Uint8Array(outputAnalyser.frequencyBinCount);
      outputAnalyser.getByteTimeDomainData(dataArray);
      let sumSquares = 0;
      let maxAmplitude = 0;
      for (let i = 0; i < dataArray.length; i += 1) {
        const v = (dataArray[i] - 128) / 128;
        const absV = Math.abs(v);
        sumSquares += v * v;
        maxAmplitude = Math.max(maxAmplitude, absV);
      }
      const rms = Math.sqrt(sumSquares / dataArray.length);
      // 使用 RMS 和峰值振幅的組合，讓可視化更敏感
      outputLevelRef.current = Math.min(1, Math.max(rms * 3.0, maxAmplitude * 1.5));
    } else {
      outputLevelRef.current = Math.max(0, outputLevelRef.current * 0.92);
    }

    const inputLevel = Math.min(1, inputLevelRef.current * 6.0);   // 用戶麥克風靈敏度 ×6
    const outputLevel = Math.min(1, outputLevelRef.current * 5.0); // 馬雲聲音靈敏度 ×5
    const isCallConnected = callPhaseRef.current === 'connected' && isConnected;
    const timeBasedLevel = isCallConnected ? 0.15 + Math.sin(waveFrameRef.current * 0.04) * 0.08 : 0;
    const level = Math.min(1, Math.max(inputLevel, outputLevel, timeBasedLevel));
    const timeOffset = waveFrameRef.current * 0.1;
    waveFrameRef.current += 1;
    const baseAmplitude = (height / 2) * 0.15;
    const inputAmplitude = baseAmplitude + (height / 2) * (Math.max(inputLevel, timeBasedLevel) * 0.65);  // 波幅更大
    const outputAmplitude = baseAmplitude + (height / 2) * (Math.max(outputLevel, timeBasedLevel) * 0.65);
    const midY = height / 2;

    if (waveRingRef.current) {
      waveRingRef.current.style.transform = `scale(${1 + level * 0.6})`;
      waveRingRef.current.style.opacity = `${0.2 + level * 0.7}`;
    }

    ctx.clearRect(0, 0, width, height);
    const points = 64;
    const drawLine = (amp: number, color: string, phaseShift: number, lineWidth: number) => {
      ctx.lineWidth = lineWidth;
      ctx.strokeStyle = color;
      ctx.beginPath();
      for (let i = 0; i <= points; i += 1) {
        const x = (width * i) / points;
        const phase = (i / points) * Math.PI * 2 + phaseShift + timeOffset;
        const y = midY + Math.sin(phase * 2) * amp;
        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
    };

    drawLine(outputAmplitude, `rgba(56, 189, 248, ${0.5 + outputLevel * 0.5})`, 0, 2.0 + outputLevel * 2.5);
    drawLine(inputAmplitude, `rgba(234, 179, 8, ${0.5 + inputLevel * 0.5})`, Math.PI / 3, 2.0 + inputLevel * 2.5);

    animationRef.current = requestAnimationFrame(drawWaveform);
  };

  const startVisualization = () => {
    stopVisualization();
    drawWaveform();
  };

  useEffect(() => {
    return () => {
      stopVisualization();
      if (audioCtxRef.current) {
        audioCtxRef.current.close();
        audioCtxRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    
    if (callPhase === 'connected' && isConnected) {
      const checkAndStart = () => {
        if (canvasRef.current) {
          if (!animationRef.current) {
            startVisualization();
          }
        } else {
          setTimeout(checkAndStart, 50);
        }
      };
      checkAndStart();
      const retryTimer = setTimeout(() => {
        if (!animationRef.current && canvasRef.current) {
          startVisualization();
        }
      }, 200);
      return () => clearTimeout(retryTimer);
    } else {
      stopVisualization();
    }
  }, [callPhase, isConnected, outputAnalyser]);

  const stopRingtone = () => {
    if (ringAudioRef.current) {
      ringAudioRef.current.pause();
      ringAudioRef.current.currentTime = 0;
      ringAudioRef.current = null;
    }
  };

  const startRingtone = (): Promise<boolean> => {
    stopRingtone();
    const url = "/static/22129.wav";
    const audio = new Audio(url);
    audio.loop = true;
    audio.volume = 0.6;
    ringAudioRef.current = audio;
    return audio.play().then(() => true).catch(() => false);
  };

  const startRingTimer = (autoConnect: boolean) => {
    if (ringTimerRef.current) return;
    ringTimerRef.current = window.setInterval(() => {
      setRingCount((prev) => {
        const next = prev + 1;
        if (next >= 3) {
          if (ringTimerRef.current) {
            window.clearInterval(ringTimerRef.current);
            ringTimerRef.current = null;
          }
          stopRingtone();
          if (autoConnect) {
            try {
              callPhaseRef.current = "connected";
              setCallPhase("connected");
              setShowConnected(true);
              window.setTimeout(() => setShowConnected(false), 1200);
              setCallActive(true);
              // 確保 startConversation 被調用
              setTimeout(() => {
                startConversation().catch((err) => {
                  console.error("Failed to start conversation:", err);
                  setCallPhase("idle");
                  callPhaseRef.current = "idle";
                });
              }, 100);
            } catch (err) {
              console.error("Error connecting call:", err);
              setCallPhase("idle");
              callPhaseRef.current = "idle";
            }
          }
        }
        return next;
      });
    }, 1000);
  };

  const startCall = async () => {
    if (callPhase !== "idle") {
      return;
    }
    try {
      setRingCount(0);
      callPhaseRef.current = "ringing";
      setCallPhase("ringing");
      const played = await startRingtone();
      if (!played) {
        console.warn("Ringtone blocked, proceeding anyway");
      }
      startRingTimer(true); // 自動接通
    } catch (err) {
      console.error("Error starting call:", err);
      setCallPhase("idle");
      callPhaseRef.current = "idle";
    }
  };


  const handleHangup = () => {
    if (ringTimerRef.current) {
      window.clearInterval(ringTimerRef.current);
      ringTimerRef.current = null;
    }
    stopRingtone();
    stopVisualization();
    const transcript = stopConversation();
    // 掛斷後把通話記錄送回後端儲存（背景執行，不阻擋 UI）
    if (transcript && transcript.length > 0) {
      console.log(`📝 儲存通話記錄 (${transcript.length} 則訊息)`);
      saveCallTranscript(transcript);
    }
    callPhaseRef.current = 'idle';
    setCallPhase('idle');
    setRingCount(0);
    setCallActive(false);
    const baseUrl = `${window.location.origin}${window.location.pathname}`;
    window.history.replaceState(null, "", `${baseUrl}#/`);
    setLocation("/");
  };

  const handleMainButton = () => {
    if (callPhase === 'idle') {
      // 綠色狀態：啟動撥號
      startCall();
    } else {
      // 紅色狀態：掛斷
      handleHangup();
    }
  };

  const toggleMute = () => {
    // 在 PTT 模式下，不使用靜音功能
    if (pushToTalkMode) return;
    setMuted(prev => !prev);
  };

  const togglePushToTalk = () => {
    enablePushToTalk(!pushToTalkMode);
    // 開啟 PTT 時自動取消靜音
    if (!pushToTalkMode) {
      setMuted(false);
    }
  };

  // PTT 按鈕事件處理
  const handlePttDown = () => {
    if (pushToTalkMode && isConnected) {
      startPttRecording();
    }
  };

  const handlePttUp = () => {
    if (pushToTalkMode && isConnected) {
      stopPttRecording();
    }
  };

  const toggleSpeaker = () => {
    setSpeakerOn(prev => {
      const next = !prev;
      // TODO: 控制輸出音量（目前 ElevenLabs 直接播放，需要通過 AudioContext gain 控制）
      return next;
    });
  };

  const formatTime = (totalSeconds: number) => {
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
  };

  const connectionText = callPhase === 'ringing'
    ? `響鈴中 ${ringCount}/3`
    : callActive && isConnected
      ? '連線中'
      : '未連線';

  // 系統是否就緒：勿用 health.llm —— 該旗標依賴客戶端轉錄事件，Agent 未轉送時會永遠 false，導致 UI 卡在「聽到鈴聲」。
  // 以「已連線 + 網路 + 已訂閱 Agent 音訊軌」為通話可進行條件（與實際 STT/LLM 管線一致）。
  const systemReady = isConnected && health.net && health.tts;

  // 12 種狀態文字
  const statusText = isConnecting
    ? '連線中...'
    : isConnected
      ? !systemReady
        ? '馬雲大哥聽到鈴聲了...'
        : convStatus === 'auto_hangup'
          ? '馬雲掛了電話'
          : convStatus === 'silence_warning'
            ? '馬雲正在確認你是否還在...'
            : convStatus === 'reconnecting'
              ? '重新連線中...'
              : convStatus === 'interrupted'
                ? '好，你說'
                : muted
                  ? '已靜音'
                  : convStatus === 'transcribing'
                    ? '聽到了...'
                    : convStatus === 'thinking'
                      ? '思考中'
                      : convStatus === 'speaking'
                        ? '說話中'
                        : convStatus === 'listening'
                          ? '聆聽中'
                          : '準備中'
      : convError
        ? '連線失敗'
        : '';

  // 狀態對應顏色
  const statusColor =
    convStatus === 'speaking' ? 'text-sky-400' :
    convStatus === 'thinking' || convStatus === 'transcribing' ? 'text-amber-400' :
    convStatus === 'interrupted' ? 'text-orange-400' :
    convStatus === 'reconnecting' ? 'text-orange-400' :
    convStatus === 'silence_warning' ? 'text-muted-foreground' :
    convStatus === 'auto_hangup' ? 'text-red-400' :
    'text-muted-foreground';

  const frameContent = (
    <div className="flex flex-col h-full w-full bg-background relative font-sans overflow-hidden">
      <header className="flex-none h-16 flex items-center justify-center relative">
        <button
          onClick={handleHangup}
          className="absolute left-4 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full flex items-center justify-center bg-card/50 border border-white/10 text-foreground hover:bg-card/80 transition-colors"
          aria-label="返回"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="text-primary text-xl tracking-widest">馬雲 | 即時對話</div>
        {/* 漢堡選單 — 健康監控面板 */}
        <button
          onClick={() => setShowHealthPanel(prev => !prev)}
          className="absolute right-3 top-1/2 -translate-y-1/2 w-10 h-10 rounded-full flex items-center justify-center bg-card/50 border border-white/10 text-foreground hover:bg-card/80 transition-colors"
          aria-label="系統狀態"
        >
          {showHealthPanel ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          {/* 迷你指示燈（摺疊時顯示整體狀態） */}
          {!showHealthPanel && (
            <div className={cn(
              "absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border border-background",
              health.net && health.mic && health.stt && health.llm && health.tts
                ? "bg-emerald-400"
                : health.net
                  ? "bg-amber-400"
                  : "bg-red-400"
            )} />
          )}
        </button>
      </header>

      {/* 健康監控面板 */}
      {showHealthPanel && (
        <div className="absolute right-2 top-16 z-50 w-56 bg-zinc-900/95 backdrop-blur-md border border-white/10 rounded-xl p-3 shadow-2xl animate-in slide-in-from-top-2 fade-in duration-200">
          <div className="text-[10px] text-muted-foreground/50 uppercase tracking-widest mb-2">系統狀態</div>

          {/* 未連線時顯示提示 */}
          {!isConnected && callPhase === 'idle' && (
            <div className="text-[11px] text-muted-foreground/40 text-center py-4">撥號後顯示系統狀態</div>
          )}

          {/* 第一層：核心 6 燈（真實偵測）— 撥號後才顯示 */}
          {(isConnected || callPhase !== 'idle') && (<><div className="space-y-1.5">
            {([
              { key: 'MIC', ok: health.mic && !muted, detail: muted ? '已靜音' : health.micDevice || (health.mic ? '收到音訊' : '無訊號') },
              { key: 'STT', ok: health.stt || health.llm, detail: health.stt ? health.sttDetail : (health.llm ? '就緒' : health.sttDetail) },
              { key: 'LLM', ok: health.llm, detail: health.llmDetail },
              { key: 'TTS', ok: health.tts, detail: health.tts ? (health.ttsProvider || health.ttsDetail) : health.ttsDetail },
              { key: 'NET', ok: health.net, detail: health.netDetail },
              { key: 'SPK', ok: health.spk && speakerOn, detail: speakerOn ? (health.spk ? '正常' : '無輸出') : '已關閉' },
            ] as const).map(({ key, ok, detail }) => (
              <div key={key} className="flex items-center gap-2">
                <div className={cn(
                  "w-2 h-2 rounded-full flex-shrink-0 transition-colors",
                  ok ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]" : "bg-red-400 shadow-[0_0_6px_rgba(248,113,113,0.4)]"
                )} />
                <span className="text-[11px] text-foreground/80 flex-1">{key}</span>
                <span className="text-[10px] text-muted-foreground/60 truncate max-w-[140px]">{detail}</span>
              </div>
            ))}
          </div>

          {/* 分隔線 */}
          <div className="border-t border-white/5 my-2" />

          {/* 第二層：進階（真實偵測） */}
          <div className="text-[10px] text-muted-foreground/40 uppercase tracking-widest mb-1.5">進階</div>
          <div className="space-y-1.5">
            {([
              { key: 'MEM', ok: health.mem, detail: health.mem ? '已載入' : '未載入' },
              { key: 'INT', ok: health.interrupt, detail: health.interrupt ? '已啟用' : '未啟用' },
            ] as const).map(({ key, ok, detail }) => (
              <div key={key} className="flex items-center gap-2">
                <div className={cn(
                  "w-2 h-2 rounded-full flex-shrink-0 transition-colors",
                  ok ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.5)]" : "bg-red-400 shadow-[0_0_6px_rgba(248,113,113,0.4)]"
                )} />
                <span className="text-[11px] text-foreground/80 flex-1">{key}</span>
                <span className="text-[10px] text-muted-foreground/60">{detail}</span>
              </div>
            ))}
          </div>
          </>)}

          {/* 延遲摘要 */}
          {isConnected && (
            <>
              <div className="border-t border-white/5 my-2" />
              <div className="flex justify-between text-[10px] text-muted-foreground/50">
                <span>通話品質</span>
                <span className={cn(
                  qualityLevel === 'high' ? 'text-emerald-400' :
                  qualityLevel === 'medium' ? 'text-amber-400' : 'text-red-400'
                )}>
                  {qualityLevel === 'high' ? '優良' : qualityLevel === 'medium' ? '普通' : '較差'}
                </span>
              </div>
            </>
          )}
        </div>
      )}

      <main className="flex-1 flex flex-col items-center justify-center px-6 gap-6">
        <div className="relative">
          {callPhase === 'ringing' && (
            <>
              <div className="absolute -inset-2 rounded-full border-2 border-primary/60 animate-ping" />
              <div className="absolute -inset-6 rounded-full border border-primary/30 animate-pulse" />
              <div className="absolute -inset-10 rounded-full border border-primary/20 animate-pulse" />
            </>
          )}
          {callPhase === 'connected' && isConnected && convStatus === 'speaking' && (
            <>
              <div className="absolute -inset-3 rounded-full border-2 border-sky-400/50 animate-pulse" />
              <div className="absolute -inset-6 rounded-full border border-sky-400/25 animate-pulse" style={{ animationDelay: '150ms' }} />
            </>
          )}
          {callPhase === 'connected' && isConnected && convStatus === 'thinking' && (
            <div className="absolute -inset-3 rounded-full border-2 border-amber-400/40 animate-pulse" />
          )}
          <div className="w-28 h-28 rounded-full bg-gradient-to-br from-zinc-700 to-zinc-900 flex items-center justify-center text-3xl text-primary shadow-[0_0_30px_rgba(0,0,0,0.5)] overflow-hidden">
            <img src="/icon.png" alt="馬雲" className="w-full h-full object-cover" />
          </div>
        </div>
        <div className="text-lg font-semibold">馬雲</div>
        {statusText && (
          <div className={cn("text-sm", statusColor)}>{statusText}</div>
        )}
        {/* 即時轉錄文字（打字機效果） */}
        {callPhase === 'connected' && isConnected && (userTranscript || agentResponse) && (
          <div className="max-w-xs text-center space-y-1 min-h-[2.5rem]">
            {agentResponse && (
              <TypewriterText text={s2t(agentResponse)} className="text-xs text-sky-400/80" />
            )}
            {userTranscript && (
              <TypewriterText text={s2t(userTranscript)} className="text-xs text-amber-400/60" />
            )}
          </div>
        )}
        <div className="text-xs text-muted-foreground/80 flex items-center gap-2">
          <span>通話時間 {callActive ? formatTime(callSeconds) : "--:--"}</span>
          <span className="text-muted-foreground/40">|</span>
          {lastLatencyMs > 0 && (
            <>
              <span className="text-emerald-400/80">{(lastLatencyMs / 1000).toFixed(1)}s{avgLatencyMs > 0 && ` · avg ${(avgLatencyMs / 1000).toFixed(1)}s`}</span>
              <span className="text-muted-foreground/40">|</span>
            </>
          )}
          <span className="flex items-center gap-1">
            {connectionText}
            {callPhase === 'connected' && isConnected && (
              <span className="inline-flex gap-1">
                <span className="w-1 h-1 rounded-full bg-primary/70 animate-bounce" style={{ animationDelay: "0ms" }} />
                <span className="w-1 h-1 rounded-full bg-primary/70 animate-bounce" style={{ animationDelay: "150ms" }} />
                <span className="w-1 h-1 rounded-full bg-primary/70 animate-bounce" style={{ animationDelay: "300ms" }} />
              </span>
            )}
          </span>
        </div>

        {callPhase === 'ringing' && (
          <div className="flex items-center gap-2 text-primary animate-pulse">
            <span className="text-sm font-semibold">正在撥號</span>
            <div className="flex gap-1">
              {[1, 2, 3].map(step => (
                <span
                  key={step}
                  className={cn(
                    "w-2.5 h-2.5 rounded-full border",
                    ringCount >= step ? "bg-primary border-primary" : "border-primary/40"
                  )}
                />
              ))}
            </div>
          </div>
        )}


        {showConnected && (
          <div className="text-sm text-emerald-400 animate-in fade-in zoom-in duration-300">
            已連線
          </div>
        )}

        <div className="relative w-full max-w-md h-16 min-h-[4rem] flex items-center justify-center select-none">
          <div
            ref={waveRingRef}
            className={cn(
              "absolute inset-0 rounded-full blur-2xl transition-transform duration-75",
              isConnected ? "bg-sky-400/30" : "bg-amber-400/25",
              isConnected ? "opacity-100" : "opacity-20"
            )}
          />
          <canvas ref={canvasRef} className="relative w-full h-12 min-h-[3rem] opacity-90" />
        </div>

        {convError && (
          <div className="text-destructive text-xs p-2 bg-destructive/10 rounded border border-destructive/20">
            <div>{convError}</div>
          </div>
        )}
      </main>

      <footer className="flex-none h-40 flex flex-col items-center justify-center gap-4 pb-4">
        {/* PTT 模式切換 */}
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <button
            onClick={togglePushToTalk}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-full transition-colors",
              pushToTalkMode 
                ? "bg-amber-500/20 text-amber-400 border border-amber-500/30" 
                : "bg-card/50 text-muted-foreground border border-white/10 hover:bg-card/80"
            )}
          >
            <Radio className="w-3.5 h-3.5" />
            <span>{pushToTalkMode ? "對講機模式" : "自動偵測"}</span>
          </button>
          {pushToTalkMode && (
            <span className="text-amber-400/70 text-[10px]">按住說話，放開送出</span>
          )}
        </div>

        <div className="flex items-center gap-8">
          {/* 麥克風按鈕：PTT 模式下變成按住說話按鈕 */}
          <button
            onClick={pushToTalkMode ? undefined : toggleMute}
            onPointerDown={pushToTalkMode ? handlePttDown : undefined}
            onPointerUp={pushToTalkMode ? handlePttUp : undefined}
            onPointerLeave={pushToTalkMode ? handlePttUp : undefined}
            className={cn(
              "w-12 h-12 rounded-full flex items-center justify-center border border-white/10 transition-all select-none",
              pushToTalkMode
                ? pttRecording
                  ? "bg-red-500 text-white scale-110 shadow-[0_0_15px_rgba(239,68,68,0.5)]"
                  : "bg-amber-500/20 text-amber-400 border-amber-500/30"
                : muted 
                  ? "bg-red-500/20 text-red-400" 
                  : "bg-card/80 text-foreground"
            )}
            aria-label={pushToTalkMode ? "按住說話" : "靜音"}
          >
            {pushToTalkMode ? (
              pttRecording ? <Mic className="w-5 h-5 animate-pulse" /> : <Radio className="w-5 h-5" />
            ) : (
              muted ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />
            )}
          </button>

          <button
            onClick={handleMainButton}
            className={cn(
              "w-16 h-16 rounded-full flex items-center justify-center text-white shadow-[0_0_20px_rgba(0,0,0,0.3)] transition-colors",
              callPhase === 'idle' 
                ? "bg-green-500 hover:bg-green-600" 
                : "bg-red-500 hover:bg-red-600"
            )}
            aria-label={callPhase === 'idle' ? "啟動撥號" : "掛斷"}
          >
            {callPhase === 'idle' ? (
              <Phone className="w-6 h-6" />
            ) : (
              <PhoneOff className="w-6 h-6" />
            )}
          </button>

          <button
            onClick={toggleSpeaker}
            className={cn(
              "w-12 h-12 rounded-full flex items-center justify-center border border-white/10",
              speakerOn ? "bg-card/80 text-foreground" : "bg-slate-700/40 text-slate-300"
            )}
            aria-label="喇叭"
          >
            {speakerOn ? <Volume2 className="w-5 h-5" /> : <VolumeX className="w-5 h-5" />}
          </button>
        </div>
        <div className="text-[10px] text-muted-foreground/40 tracking-[0.2em] font-light">
          -超智能-
        </div>
      </footer>
    </div>
  );

  if (isMobile) {
    return (
      <>
        <PWAStandaloneLock />
        {frameContent}
      </>
    );
  }

  return (
    <DeviceFrame>
      <StatusBar />
      <PWAInstallPrompt />
      {frameContent}
    </DeviceFrame>
  );
}
