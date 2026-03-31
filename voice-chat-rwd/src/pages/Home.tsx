import { useState, useEffect, useRef } from "react";
import { Mic, Loader2, Volume2, Phone, Send, LogOut, Camera, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAudioRecorder } from "@/hooks/useAudioRecorder";
import { useIsMobile } from "@/hooks/use-mobile";
import { useKeyboardHeight } from "@/hooks/useKeyboardHeight";
import { turn, turnStream, playRemoteAudio, chatText, getUserId, getConversationId, getConversationHistory, analyzeImage, API_BASE_URL } from "@/lib/api";
import { s2t } from "@/lib/s2t";
import { DeviceFrame, StatusBar } from "@/components/DeviceFrame";
import { PWAInstallPrompt } from "@/components/PWAInstallPrompt";
import { SplashScreen } from "@/components/SplashScreen";
import { useAuth } from "@/contexts/AuthContext";
import { useLocation } from "wouter";

interface Message {
  role: 'user' | 'assistant';
  content: string;
  imageUrl?: string; // 用於顯示圖片預覽
}

type Status = 'idle' | 'recording' | 'transcribing' | 'thinking' | 'speaking' | 'error';
type HealthStatus = 'loading' | 'ok' | 'error';

// LocalStorage 快取 key
const CHAT_CACHE_KEY = 'jackma_chat_cache';

// 快取工具函數
const getCachedMessages = (userId: string): Message[] | null => {
  try {
    const cached = localStorage.getItem(`${CHAT_CACHE_KEY}_${userId}`);
    if (cached) {
      return JSON.parse(cached);
    }
  } catch (e) {
    console.error('Failed to read cache:', e);
  }
  return null;
};

const setCachedMessages = (userId: string, messages: Message[]) => {
  try {
    localStorage.setItem(`${CHAT_CACHE_KEY}_${userId}`, JSON.stringify(messages));
  } catch (e) {
    console.error('Failed to write cache:', e);
  }
};

export default function Home() {
  const { user, isLoading, isAuthenticated, logout } = useAuth();
  
  // 使用登入用戶的 ID
  const userIdRef = useRef<string>(user?.id || getUserId());
  const conversationIdRef = useRef<string>(getConversationId(userIdRef.current));
  
  // 對話紀錄（從後端 API 載入）
  const [messages, setMessages] = useState<Message[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const initialScrollDone = useRef(false); // 追蹤首次滾動是否完成
  const [status, setStatus] = useState<Status>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const [llmStatus, setLlmStatus] = useState<HealthStatus>('loading');
  const [ttsStatus, setTtsStatus] = useState<HealthStatus>('loading');
  const [textOpen, setTextOpen] = useState(false);
  const [textClosing, setTextClosing] = useState(false); // 收回動畫狀態
  const [showNicknameDialog, setShowNicknameDialog] = useState(false);
  const [nicknameInput, setNicknameInput] = useState(user?.name || '');
  const [textValue, setTextValue] = useState('');
  const [pendingImage, setPendingImage] = useState<{ file: File; previewUrl: string } | null>(null);
  const [imageClosing, setImageClosing] = useState(false); // 圖片刪除動畫狀態
  
  const { isRecording, startRecording, stopRecording } = useAudioRecorder();
  const isMobile = useIsMobile();
  const keyboardHeight = useKeyboardHeight();
  const [, setLocation] = useLocation();
  const bottomRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLElement>(null); // 聊天容器 ref
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const textInputRef = useRef<HTMLInputElement | null>(null);
  const imageInputRef = useRef<HTMLInputElement | null>(null);
  
  // 滾動到底部的函數
  const scrollToBottom = (smooth = false) => {
    if (chatContainerRef.current) {
      if (smooth) {
        chatContainerRef.current.scrollTo({
          top: chatContainerRef.current.scrollHeight,
          behavior: 'smooth'
        });
      } else {
        chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
      }
    }
  };
  
  // 未登入用戶導向登入頁
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      setLocation('/login');
    }
  }, [isLoading, isAuthenticated, setLocation]);
  
  // 當用戶變更時更新 ID 並載入對應的對話紀錄
  useEffect(() => {
    if (user?.id) {
      userIdRef.current = user.id;
      conversationIdRef.current = getConversationId(user.id);
    }
  }, [user?.id]);
  
  // 從後端 API 載入對話歷史（SWR 策略：先顯示快取，背景更新）
  useEffect(() => {
    if (!isAuthenticated || historyLoaded || !user?.id) return;
    
    const userId = user.id;
    const cached = getCachedMessages(userId);
    const hasCache = cached && cached.length > 0;
    
    // 有快取：先設定訊息，但保持 loading 狀態直到滾動完成
    if (hasCache) {
      console.log(`Loaded ${cached.length} messages from cache`);
      setMessages(cached);
      setHistoryLoaded(true);
      // 注意：不在這裡設 historyLoading = false，等 MutationObserver 滾動完成後再設
    }
    
    // 背景呼叫 API 取得最新資料
    const loadHistory = async () => {
      try {
        console.log('Fetching conversation history from API...');
        const response = await getConversationHistory(200, 0);
        
        let newMessages: Message[];
        if (response.messages && response.messages.length > 0) {
          newMessages = response.messages.map(m => ({
            role: m.role as 'user' | 'assistant',
            content: m.content,
            imageUrl: m.image_url || undefined
          }));
        } else {
          newMessages = [{ role: 'assistant', content: '「我是馬雲。」' }];
        }
        
        const cachedStr = JSON.stringify(cached);
        const newStr = JSON.stringify(newMessages);
        
        // 永遠更新訊息（不管快取是否相同，因為可能有新訊息）
        console.log(`API returned ${newMessages.length} messages, cache had ${cached?.length || 0}`);
        setMessages(newMessages);
        setCachedMessages(userId, newMessages);
        
      } catch (err) {
        console.error('Failed to load conversation history:', err);
        if (!hasCache) {
          setMessages([{ role: 'assistant', content: '「我是馬雲。」' }]);
        }
      } finally {
        if (!hasCache) {
          setHistoryLoaded(true);
        }
      }
    };
    
    loadHistory();
  }, [isAuthenticated, historyLoaded, user?.id]);

  // 使用 MutationObserver 監聽 DOM 變化，確保滾動時機正確
  useEffect(() => {
    if (!historyLoaded || !chatContainerRef.current) return;
    
    const container = chatContainerRef.current;
    let scrollTimeout: ReturnType<typeof setTimeout> | null = null;
    
    // 首次載入：用 MutationObserver 等待 DOM 完全渲染
    if (!initialScrollDone.current) {
      const observer = new MutationObserver(() => {
        // 每次 DOM 變化都重設 timeout，等穩定後再滾動
        if (scrollTimeout) clearTimeout(scrollTimeout);
        scrollTimeout = setTimeout(() => {
          // DOM 穩定了，執行滾動
          container.scrollTop = container.scrollHeight;
          // 等滾動完成後再移除 Loading（多等幾個 frame 確保畫面穩定）
          requestAnimationFrame(() => {
            requestAnimationFrame(() => {
              setHistoryLoading(false);
              initialScrollDone.current = true;
            });
          });
          observer.disconnect();
        }, 200); // 等 200ms 沒有新的 DOM 變化才滾動
      });
      
      observer.observe(container, { 
        childList: true, 
        subtree: true,
        characterData: true 
      });
      
      // 立即觸發一次檢查（處理 DOM 已經渲染完成的情況）
      scrollTimeout = setTimeout(() => {
        container.scrollTop = container.scrollHeight;
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            setHistoryLoading(false);
            initialScrollDone.current = true;
          });
        });
        observer.disconnect();
      }, 250);
      
      return () => {
        observer.disconnect();
        if (scrollTimeout) clearTimeout(scrollTimeout);
      };
    }
  }, [historyLoaded]);

  // 新訊息時平滑滾動到底部
  useEffect(() => {
    if (!initialScrollDone.current || historyLoading) return;
    
    const timer = setTimeout(() => {
      scrollToBottom(true);
    }, 50);
    return () => clearTimeout(timer);
  }, [messages, historyLoading]);

  // 當訊息變化時，更新快取（排除初始載入）
  useEffect(() => {
    if (historyLoaded && messages.length > 0 && initialScrollDone.current && user?.id) {
      setCachedMessages(user.id, messages);
    }
  }, [messages, historyLoaded, user?.id]);

  useEffect(() => {
    if (textOpen) {
      textInputRef.current?.focus();
      // 鍵盤彈出後滾動到底部，確保輸入框可見
      setTimeout(() => {
        scrollToBottom(true);
      }, 300);
    }
  }, [textOpen]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search || "");
    if (params.get("autodial") === "1") {
      // 立即重定向，不等待渲染
      window.location.replace("/realtime");
      return;
    }
  }, []);

  // 全局捕获未处理的 Promise rejection
  useEffect(() => {
    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      console.error('Unhandled promise rejection:', event.reason);
      setStatus('error');
      setErrorMsg(event.reason?.message || '發生未預期的錯誤');
      setTimeout(() => setStatus('idle'), 3000);
      event.preventDefault(); // 防止在 console 中显示错误
    };
    window.addEventListener('unhandledrejection', handleUnhandledRejection);
    return () => {
      window.removeEventListener('unhandledrejection', handleUnhandledRejection);
    };
  }, []);

  useEffect(() => {
    let isMounted = true;
    const fetchHealth = async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/health`);
        const data = await res.json();
        if (!isMounted) return;
        setLlmStatus(data.llm === 'OK' ? 'ok' : 'error');
        setTtsStatus(data.tts === 'OK' ? 'ok' : 'error');
      } catch {
        if (!isMounted) return;
        setLlmStatus('error');
        setTtsStatus('error');
      }
    };

    fetchHealth();
    const timer = setInterval(fetchHealth, 30000);
    return () => {
      isMounted = false;
      clearInterval(timer);
    };
  }, []);

  // Loading 或未登入時顯示載入畫面
  if (isLoading || !isAuthenticated) {
    return <SplashScreen />;
  }

  const dotClass = (value: HealthStatus) => {
    if (value === 'ok') return "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.6)] health-dot-ok";
    if (value === 'error') return "bg-red-400 shadow-[0_0_6px_rgba(248,113,113,0.6)]";
    return "bg-amber-300 animate-pulse";
  };

  const handleStart = async (e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault(); // Prevent text selection or context menu
    if (status !== 'idle' && status !== 'speaking') return; // Allow interrupt speaking? Maybe.
    
    // Stop current audio if speaking
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }

    setErrorMsg('');
    try {
      const ok = await startRecording();
      if (!ok) {
        setStatus('error');
        setErrorMsg('無法存取麥克風，請確認權限設定。');
        return;
      }
      setStatus('recording');
    } catch (err: any) {
      console.error('Start recording failed:', err);
      setStatus('error');
      setErrorMsg(err.message || '無法開始錄音');
    }
  };

  const handleEnd = async (e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault();
    if (!isRecording) return;

    setStatus('transcribing');
    let blob: Blob | null = null;
    let durationMs = 0;
    try {
      const out = await stopRecording();
      blob = out.blob;
      durationMs = out.durationMs;
    } catch (err: any) {
      console.error('Stop recording failed:', err);
      setStatus('error');
      setErrorMsg('錄音停止失敗');
      setTimeout(() => setStatus('idle'), 3000);
      return;
    }
    
    if (!blob || blob.size === 0) {
      setStatus('idle');
      return;
    }

    const minDurationMs = 400;
    const minSize = 800;
    if (durationMs < minDurationMs || blob.size < minSize) {
      setStatus('error');
      setErrorMsg('語音太短，請至少按住約 0.5 秒再放開');
      setTimeout(() => setStatus('idle'), 3000);
      return;
    }

    try {
      setStatus('thinking');

      // 串流版：即時顯示文字，不用等整段回完
      let assistantMsgIndex = -1;

      await turnStream(blob, {
        onStt: (text) => {
          // STT 完成：顯示用戶訊息
          setMessages(prev => [...prev, { role: 'user', content: text }]);
          setStatus('thinking');
        },
        onChunk: (_chunk, accumulated) => {
          // LLM 逐字串流：即時更新助手回覆
          if (assistantMsgIndex === -1) {
            // 首個 chunk：新增助手訊息
            setMessages(prev => {
              assistantMsgIndex = prev.length;
              return [...prev, { role: 'assistant', content: accumulated }];
            });
          } else {
            // 後續 chunk：更新最後一條訊息
            setMessages(prev => {
              const updated = [...prev];
              if (updated[assistantMsgIndex]) {
                updated[assistantMsgIndex] = { ...updated[assistantMsgIndex], content: accumulated };
              }
              return updated;
            });
          }
        },
        onTts: (audioUrl) => {
          // TTS 完成：播放語音
          setStatus('speaking');
          const audio = playRemoteAudio(audioUrl);
          audioRef.current = audio;
          audio.onerror = () => {
            setStatus('idle');
            audioRef.current = null;
          };
          audio.onended = () => {
            setStatus('idle');
            audioRef.current = null;
          };
          audio.play().catch(() => {
            setStatus('idle');
            audioRef.current = null;
          });
        },
        onDone: (result) => {
          console.log(`串流完成，延遲: ${result.latencyMs}ms`);
          if (!audioRef.current) setStatus('idle');
        },
        onError: (error) => {
          console.error('串流錯誤:', error);
          setStatus('error');
          setErrorMsg(error);
          setTimeout(() => setStatus('idle'), 3000);
        },
      }, userIdRef.current, conversationIdRef.current);

    } catch (err: any) {
      console.error(err);
      setStatus('error');
      setErrorMsg(err.message || '發生錯誤');
      setTimeout(() => setStatus('idle'), 3000);
    }
  };

  const handleSendText = async () => {
    const text = textValue.trim();
    const hasImage = pendingImage !== null;
    
    // 如果沒有文字也沒有圖片，不發送
    if (!text && !hasImage) return;
    
    // 先保存圖片資訊到局部變數
    const imageFile = pendingImage?.file;
    const imagePreviewUrl = pendingImage?.previewUrl;
    
    // 立即清除 state（在任何異步操作之前）
    setPendingImage(null);
    setTextValue('');
    setErrorMsg('');
    setStatus('thinking');
    
    // 先用本地預覽 URL 顯示訊息，稍後會更新為雲端 URL
    const messageIndex = messages.length;
    if (hasImage && imagePreviewUrl) {
      setMessages(prev => [...prev, { 
        role: 'user', 
        content: text || '傳送了一張圖片',
        imageUrl: imagePreviewUrl
      }]);
    } else {
      setMessages(prev => [...prev, { role: 'user', content: text }]);
    }
    
    try {
      let result;
      
      if (hasImage && imageFile) {
        // 有圖片：使用 Vision API
        result = await analyzeImage(imageFile, text || undefined);
        
        // 如果有雲端 URL，更新訊息中的圖片 URL
        if (result.image_url) {
          setMessages(prev => prev.map((msg, idx) => 
            idx === messageIndex ? { ...msg, imageUrl: result.image_url } : msg
          ));
          // 釋放本地預覽 URL
          if (imagePreviewUrl) {
            URL.revokeObjectURL(imagePreviewUrl);
          }
        }
        
        if (result.success && result.text) {
          setMessages(prev => [...prev, { role: 'assistant', content: result.text }]);
        } else {
          setMessages(prev => [...prev, { role: 'assistant', content: result.text || '抱歉，我無法辨識這張圖片。' }]);
        }
        
        if (result.audio_url) {
          setStatus('speaking');
          const audio = playRemoteAudio(result.audio_url);
          audioRef.current = audio;
          audio.play().catch((playErr) => {
            console.error('Audio play failed:', playErr);
            setStatus('idle');
            audioRef.current = null;
          });
          audio.onended = () => {
            setStatus('idle');
            audioRef.current = null;
          };
          audio.onerror = () => {
            console.error('Audio playback error');
            setStatus('idle');
            audioRef.current = null;
          };
        } else {
          setStatus('idle');
        }
      } else {
        // 純文字：使用 Chat API
        result = await chatText(text, userIdRef.current, conversationIdRef.current);
        if (result.assistant_text) {
          setMessages(prev => [...prev, { role: 'assistant', content: result.assistant_text }]);
        }
        if (result.assistant_audio_url) {
          setStatus('speaking');
          const audio = playRemoteAudio(result.assistant_audio_url);
          audioRef.current = audio;
          audio.play().catch((playErr) => {
            console.error('Audio play failed:', playErr);
            setStatus('idle');
            audioRef.current = null;
            setErrorMsg('無法播放音訊，請檢查瀏覽器設定。');
          });
          audio.onended = () => {
            setStatus('idle');
            audioRef.current = null;
          };
          audio.onerror = () => {
            console.error('Audio playback error');
            setStatus('idle');
            audioRef.current = null;
          };
        } else {
          setStatus('idle');
        }
      }
    } catch (err: any) {
      console.error(err);
      setStatus('error');
      setErrorMsg(err.message || '發生錯誤');
      setTimeout(() => setStatus('idle'), 3000);
    }
  };

  const handleImageSelect = () => {
    imageInputRef.current?.click();
  };

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    // 清空 input 以便重複選擇同一檔案
    e.target.value = '';
    
    // 檢查檔案類型
    if (!file.type.startsWith('image/')) {
      setErrorMsg('請選擇圖片檔案');
      setStatus('error');
      setTimeout(() => setStatus('idle'), 3000);
      return;
    }
    
    // 檢查檔案大小 (最大 5MB)
    if (file.size > 5 * 1024 * 1024) {
      setErrorMsg('圖片太大，請選擇 5MB 以下的圖片');
      setStatus('error');
      setTimeout(() => setStatus('idle'), 3000);
      return;
    }
    
    // 建立預覽 URL
    const previewUrl = URL.createObjectURL(file);
    setPendingImage({ file, previewUrl });
    
    // 自動開啟文字輸入框
    setTextOpen(true);
  };

  const handleClearImage = () => {
    if (pendingImage) {
      setImageClosing(true);
      setTimeout(() => {
        URL.revokeObjectURL(pendingImage.previewUrl);
        setPendingImage(null);
        setImageClosing(false);
      }, 150); // 等動畫完成
    }
  };

  // 文字輸入框開關（帶動畫）
  const handleToggleTextInput = () => {
    if (textOpen) {
      // 收回：先播動畫再關閉
      setTextClosing(true);
      setTimeout(() => {
        setTextOpen(false);
        setTextClosing(false);
      }, 200); // 等動畫完成
    } else {
      // 展開
      setTextOpen(true);
    }
  };

  // 主要內容區塊（手機和桌面共用）
  const mainContent = (
    <>
      <PWAInstallPrompt />
      
      {/* Health Indicators */}
      <div className="absolute top-9 right-4 flex items-center gap-3 z-40 text-[10px]">
        <div className="flex items-center gap-1 text-muted-foreground">
          <span>LLM:</span>
          <span className={cn("w-2 h-2 rounded-full", dotClass(llmStatus))} />
          <span className="text-foreground/70">{llmStatus === 'ok' ? 'OK' : llmStatus === 'error' ? 'ERR' : '--'}</span>
        </div>
        <div className="flex items-center gap-1 text-muted-foreground">
          <span>TTS:</span>
          <span className={cn("w-2 h-2 rounded-full", dotClass(ttsStatus))} />
          <span className="text-foreground/70">{ttsStatus === 'ok' ? 'OK' : ttsStatus === 'error' ? 'ERR' : '--'}</span>
        </div>
      </div>

      {/* User Menu */}
      <div className="absolute top-9 left-4 z-40">
        {isAuthenticated && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => { setNicknameInput(user?.name || ''); setShowNicknameDialog(true); }}
              className="text-xs text-muted-foreground hover:text-foreground transition cursor-pointer"
              title="修改暱稱"
            >
              {user?.name || user?.email?.split('@')[0]}
            </button>
            <button
              onClick={logout}
              className="flex items-center gap-1 px-2 py-1 rounded-full bg-card/50 border border-white/10 text-muted-foreground text-xs hover:text-foreground transition"
              title="登出"
            >
              <LogOut className="w-3 h-3" />
            </button>
          </div>
        )}
      </div>

      {/* 暱稱修改對話框 */}
      {showNicknameDialog && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 w-72 shadow-2xl">
            <div className="text-sm text-muted-foreground mb-3">馬雲目前稱呼您</div>
            <input
              type="text"
              value={nicknameInput}
              onChange={(e) => setNicknameInput(e.target.value)}
              maxLength={20}
              className="w-full px-3 py-2 bg-zinc-800 border border-white/10 rounded-lg text-foreground text-center text-lg focus:outline-none focus:border-primary mb-4"
              autoFocus
            />
            <div className="flex gap-2">
              <button
                onClick={async () => {
                  if (nicknameInput.trim()) {
                    try {
                      const { updateNickname } = await import('@/lib/api');
                      await updateNickname(nicknameInput.trim());
                      // 重新載入用戶資訊
                      window.location.reload();
                    } catch (e: any) {
                      alert(e.message || '更新失敗');
                    }
                  }
                }}
                className="flex-1 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 transition"
              >
                按此修改
              </button>
              <button
                onClick={() => setShowNicknameDialog(false)}
                className="flex-1 py-2 bg-zinc-800 border border-white/10 text-muted-foreground rounded-lg text-sm hover:text-foreground transition"
              >
                離開
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <header className="flex-none h-28 flex flex-col items-center justify-end pt-6 pb-4 z-10">
        <h1 className="text-3xl font-bold text-primary tracking-widest drop-shadow-[0_2px_10px_rgba(234,179,8,0.2)]">
          馬雲
        </h1>
        <div className="flex items-center gap-2 mt-1">
          <span className="text-xs text-muted-foreground tracking-widest border-r border-muted-foreground/30 pr-2">語氣靈</span>
          <span className="text-xs text-muted-foreground tracking-widest">智能體</span>
        </div>
      </header>

      {/* Chat Area — 僅此區可上下滑動 */}
      <main
        ref={chatContainerRef}
        className="flex-1 min-h-0 overflow-y-auto px-4 py-6 scrollbar-none pwa-scrollable relative"
      >
        {/* Loading 遮罩 - 用絕對定位蓋在訊息上面 */}
        {historyLoading && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-background">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-primary/60 animate-bounce" style={{ animationDelay: "0ms" }} />
              <span className="w-2 h-2 rounded-full bg-primary/60 animate-bounce" style={{ animationDelay: "150ms" }} />
              <span className="w-2 h-2 rounded-full bg-primary/60 animate-bounce" style={{ animationDelay: "300ms" }} />
            </div>
            <span className="text-muted-foreground/60 text-sm mt-4">載入對話紀錄中...</span>
          </div>
        )}
        
        {/* 訊息永遠渲染（被 Loading 遮住時在背景渲染+滾動） */}
        <div className="max-w-md mx-auto space-y-6">
          {messages.map((msg, idx) => {
            // 判斷是否為新訊息（最後幾則）
            const isNewMessage = idx >= messages.length - 2 && initialScrollDone.current;
            return (
              <div
                key={idx}
                className={cn(
                  "flex w-full",
                  msg.role === 'user' ? "justify-end" : "justify-start",
                  // 新訊息才有動畫
                  isNewMessage && (msg.role === 'user' ? "animate-message-in-right" : "animate-message-in-left")
                )}
              >
                <div
                  className={cn(
                    "max-w-[85%] px-4 py-3 rounded-2xl text-base leading-relaxed shadow-sm",
                    msg.role === 'user' 
                      ? "bg-secondary text-secondary-foreground rounded-tr-sm" 
                      : "bg-card/50 backdrop-blur-sm border border-white/5 text-foreground rounded-tl-sm shadow-[0_4px_20px_rgba(0,0,0,0.2)]"
                  )}
                >
                  {msg.imageUrl && (
                    <img 
                      src={msg.imageUrl} 
                      alt="上傳的圖片" 
                      className="max-w-full max-h-48 rounded-lg mb-2 object-contain"
                    />
                  )}
                  {msg.role === 'assistant' ? s2t(msg.content) : msg.content}
                </div>
              </div>
            );
          })}
          
          {status === 'thinking' && messages[messages.length - 1]?.content === '' && (
             <div className="flex justify-start animate-message-in-left">
               <div className="bg-card/50 px-4 py-3 rounded-2xl rounded-tl-sm border border-white/5">
                 <span className="text-muted-foreground text-sm">思考中...</span>
               </div>
             </div>
          )}
          
          <div ref={bottomRef} className="h-4" />
        </div>
      </main>

      {/* Footer Controls */}
      <footer 
        className={cn(
          "flex-none bg-gradient-to-t from-black/50 to-transparent flex flex-col items-center justify-center z-20",
          keyboardHeight > 0 ? "" : "pb-safe"
        )}
        style={{ 
          minHeight: keyboardHeight > 0 ? 'auto' : '8rem',
          paddingBottom: keyboardHeight > 0 ? '8px' : undefined
        }}
      >
        
        {/* Error Message */}
        {status === 'error' && (
          <div className="absolute top-0 text-destructive text-sm bg-destructive/10 px-3 py-1 rounded-full animate-shake">
            {errorMsg}
          </div>
        )}

        {textOpen && (
          <div className={cn(
            "w-full max-w-md px-4 mb-4",
            textClosing ? "animate-slide-up" : "animate-slide-down"
          )}>
            {/* 圖片預覽 */}
            {pendingImage && (
              <div className={cn(
                "relative mb-2 inline-block",
                imageClosing ? "animate-scale-out" : "animate-scale-in"
              )}>
                <img 
                  src={pendingImage.previewUrl} 
                  alt="待發送圖片" 
                  className="max-h-24 rounded-lg object-contain border border-white/10"
                />
                <button
                  onClick={handleClearImage}
                  className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-red-500 text-white flex items-center justify-center hover:bg-red-600 transition"
                  aria-label="移除圖片"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            )}
            <div className="flex items-center gap-2 bg-card border border-white/10 rounded-full px-3 py-2 shadow-[0_8px_20px_rgba(0,0,0,0.35)]">
              {/* 相機按鈕 */}
              <button
                onClick={handleImageSelect}
                disabled={status === 'transcribing' || status === 'thinking'}
                className="w-8 h-8 rounded-full flex items-center justify-center text-emerald-400 hover:text-emerald-300 hover:bg-white/5 transition"
                aria-label="上傳圖片"
              >
                <Camera className="w-4 h-4" />
              </button>
              <input
                ref={textInputRef}
                className="flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground/60"
                placeholder={pendingImage ? "說點什麼...（可選）" : "輸入文字..."}
                value={textValue}
                onChange={(e) => setTextValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleSendText();
                  }
                }}
              />
              <button
                className="w-8 h-8 rounded-full flex items-center justify-center text-sky-400 hover:text-sky-300 hover:bg-white/5 transition"
                onClick={handleSendText}
                disabled={status === 'transcribing' || status === 'thinking'}
                aria-label="送出"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
        <input
          ref={imageInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleImageUpload}
        />

        <div className="flex items-center gap-6">
          {/* Text Button */}
          <button
            className="flex items-center justify-center w-12 h-12 rounded-full bg-card/80 border border-white/10 text-sky-400 hover:text-sky-300 hover:border-white/20 transition"
            onClick={handleToggleTextInput}
            aria-label="文字對話"
          >
            <Send className="w-4 h-4" />
          </button>

          {/* PTT Button */}
          <div className="flex flex-col items-center gap-2">
            <button
              className={cn(
                "relative w-20 h-20 rounded-full flex items-center justify-center transition-all duration-200",
                "bg-primary text-primary-foreground shadow-[0_0_30px_rgba(234,179,8,0.2)]",
                "active:scale-95 touch-none select-none", // Prevent scroll/zoom on touch
                status === 'recording' ? "scale-110 shadow-[0_0_50px_rgba(234,179,8,0.6)]" : "hover:shadow-[0_0_40px_rgba(234,179,8,0.4)]",
                (status === 'transcribing' || status === 'thinking') && "opacity-50 cursor-wait"
              )}
              onMouseDown={handleStart}
              onMouseUp={handleEnd}
              onMouseLeave={handleEnd} // Handle dragging out
              onTouchStart={handleStart}
              onTouchEnd={handleEnd}
              disabled={status === 'transcribing' || status === 'thinking'}
            >
              {status === 'transcribing' || status === 'thinking' ? (
                 <Loader2 className="w-8 h-8 animate-spin opacity-80" />
              ) : (
                 <Mic className={cn("w-8 h-8", status === 'recording' && "animate-pulse")} />
              )}
              
              {/* Ring Animation when recording */}
              {status === 'recording' && (
                <span className="absolute inset-0 rounded-full border-2 border-primary animate-ping opacity-50"></span>
              )}
            </button>
            <div className="text-center h-5">
              {status === 'idle' && <span className="text-muted-foreground/50 text-[10px] tracking-widest">按住說話</span>}
              {status === 'recording' && <span className="text-primary text-[10px] tracking-widest font-bold">正在聆聽...</span>}
              {status === 'transcribing' && <span className="text-muted-foreground text-[10px] tracking-widest">語音辨識中...</span>}
              {status === 'thinking' && <span className="text-muted-foreground text-[10px] tracking-widest">馬雲思考中...</span>}
              {status === 'speaking' && <span className="text-primary text-[10px] tracking-widest flex items-center justify-center gap-1"><Volume2 size={10}/> 正在回應</span>}
            </div>
          </div>

          {/* Call Button → 即時通話 */}
          <a href="#/call" className="flex items-center justify-center w-12 h-12 rounded-full bg-card/80 border border-white/10 text-sky-400 hover:text-sky-300 hover:border-white/20 transition hover-wiggle" aria-label="即時通話">
            <Phone className="w-6 h-6" />
          </a>
        </div>
        
        <div className="mt-3 flex items-center gap-3 text-[10px] text-muted-foreground/30">
          <span className="tracking-[0.2em] font-light">-超智能-</span>
          <a href="#/changelog" className="hover:text-muted-foreground/60 transition-colors underline">
            日誌
          </a>
        </div>
      </footer>
    </>
  );

  // 手機端：直接渲染滿版內容（與 Call.tsx 相同方式）
  if (isMobile) {
    // 計算容器高度：鍵盤彈出時縮小
    const containerStyle = keyboardHeight > 0 
      ? { height: `calc(100% - ${keyboardHeight}px)` }
      : { height: '100%' };
    
    return (
      <div className="flex flex-col bg-background relative font-sans" style={containerStyle}>
        {mainContent}
      </div>
    );
  }

  // 桌面端：使用 DeviceFrame 包裹
  return (
    <DeviceFrame>
      <StatusBar />
      <div className="flex flex-col h-full bg-background relative font-sans animate-in fade-in zoom-in-95 duration-500">
        {mainContent}
      </div>
    </DeviceFrame>
  );
}
