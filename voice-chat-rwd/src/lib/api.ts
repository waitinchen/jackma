// API Base URL - 設定遠端伺服器位址
// 開發時可用本地，正式環境需設定 VITE_API_URL
const envBaseUrl = import.meta.env.VITE_API_URL || '';
const isBrowser = typeof window !== 'undefined';
const isLocalHost = isBrowser && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');
const envLooksLocal = /localhost|127\.0\.0\.1/i.test(envBaseUrl);
// 同源策略：localhost 一律用相對路徑，避免與後端 port (8000/8080) 不一致
// 正式環境若 env 指向 localhost 也改用 ''，避免部署站打本地
export const API_BASE_URL = (isLocalHost || envLooksLocal) ? '' : envBaseUrl;

// Token 管理 (從 auth.ts 引入)
import { getStoredToken, clearStoredToken } from './auth';

// 帶認證的 fetch helper（401 時自動清除 token 並導向登入頁）
async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = getStoredToken();
  const headers: HeadersInit = {
    'ngrok-skip-browser-warning': 'true',
    ...(options.headers || {}),
  };
  
  if (token) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
  }
  
  const response = await fetch(url, { ...options, headers });
  
  if (response.status === 401) {
    console.warn('⚠️ Token 過期或無效，導向登入頁');
    clearStoredToken();
    window.location.hash = '#/login';
  }
  
  return response;
}

// === 新 API：一站式對話 (配合 Python 後端 /api/turn) ===
export interface TurnResponse {
  user_text: string;
  assistant_text: string;
  assistant_audio_url: string | null;
}

export interface ChatTextResponse {
  user_text: string;
  assistant_text: string;
  assistant_audio_url: string | null;
}

export function getUserId(): string {
  const key = "jackma_user_id";
  let userId = localStorage.getItem(key);
  if (!userId) {
    userId = typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `user_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    localStorage.setItem(key, userId);
  }
  return userId;
}

export function getConversationId(userId: string): string {
  return `conv_${userId}`;
}

export async function turn(audioBlob: Blob, userId?: string, conversationId?: string): Promise<TurnResponse> {
  const resolvedUserId = userId || getUserId();
  const resolvedConversationId = conversationId || getConversationId(resolvedUserId);
  const formData = new FormData();
  const mimeType = audioBlob.type || '';
  const extension = mimeType.includes('mp4')
    ? 'm4a'
    : mimeType.includes('ogg')
      ? 'ogg'
      : mimeType.includes('mpeg')
        ? 'mp3'
        : 'webm';
  formData.append('audio', audioBlob, `audio.${extension}`);
  formData.append('user_id', resolvedUserId);
  formData.append('conversation_id', resolvedConversationId);
  
  // 使用 authFetch（自動帶 token + 401 處理）
  // 注意：FormData 不需要手動設定 Content-Type，瀏覽器會自動加 multipart boundary
  const response = await authFetch(`${API_BASE_URL}/api/turn`, {
    method: 'POST',
    body: formData,
  });
  
  if (!response.ok) {
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `對話失敗 (HTTP ${response.status})`);
    }
    const text = await response.text().catch(() => '');
    throw new Error(text || `對話失敗 (HTTP ${response.status})`);
  }
  
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    const text = await response.text().catch(() => '');
    throw new Error(text || '回傳格式錯誤');
  }
  return response.json();
}

/**
 * 串流版 turn — SSE 逐字回傳 LLM 回覆
 * 前端可以即時顯示打字效果，不用等整段回完
 */
export async function turnStream(
  audioBlob: Blob,
  callbacks: {
    onStt?: (text: string) => void;
    onChunk?: (chunk: string, accumulated: string) => void;
    onTts?: (audioUrl: string) => void;
    onDone?: (result: { assistantText: string; latencyMs: number }) => void;
    onError?: (error: string) => void;
  },
  userId?: string,
  conversationId?: string,
): Promise<void> {
  const resolvedUserId = userId || getUserId();
  const resolvedConversationId = conversationId || getConversationId(resolvedUserId);
  const formData = new FormData();
  const mimeType = audioBlob.type || '';
  const extension = mimeType.includes('mp4') ? 'm4a'
    : mimeType.includes('ogg') ? 'ogg'
    : mimeType.includes('mpeg') ? 'mp3'
    : 'webm';
  formData.append('audio', audioBlob, `audio.${extension}`);
  formData.append('conversation_id', resolvedConversationId);

  const response = await authFetch(`${API_BASE_URL}/api/turn-stream`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    callbacks.onError?.(errorData.detail || `串流失敗 (HTTP ${response.status})`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    callbacks.onError?.('瀏覽器不支援串流');
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';
  let accumulated = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        const data = JSON.parse(line.slice(6));
        switch (data.type) {
          case 'stt':
            callbacks.onStt?.(data.text);
            break;
          case 'chunk':
            accumulated += data.text;
            callbacks.onChunk?.(data.text, accumulated);
            break;
          case 'tts':
            callbacks.onTts?.(data.audio_url);
            break;
          case 'done':
            callbacks.onDone?.({ assistantText: data.assistant_text, latencyMs: data.latency_ms });
            break;
          case 'error':
            callbacks.onError?.(data.message);
            break;
        }
      } catch {
        // 非 JSON，忽略
      }
    }
  }
}

export async function getConversationToken(userId?: string): Promise<string> {
  const resolvedUserId = userId || getUserId();
  const params = new URLSearchParams();
  params.set("participant_name", resolvedUserId);
  
  const response = await authFetch(`${API_BASE_URL}/api/elevenlabs/token?${params.toString()}`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || '取得連線權杖失敗');
  }
  const data = await response.json().catch(() => ({}));
  if (typeof data.token === 'string') return data.token;
  if (typeof data === 'string') return data;
  throw new Error('連線權杖回傳格式錯誤');
}

export async function getConversationSignedUrl(): Promise<string> {
  const response = await authFetch(`${API_BASE_URL}/api/elevenlabs/signed-url`);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || '取得連線網址失敗');
  }
  const data = await response.json().catch(() => ({}));
  if (typeof data.signed_url === 'string') return data.signed_url;
  if (typeof data === 'string') return data;
  throw new Error('連線網址回傳格式錯誤');
}

// === 儲存通話 transcript API ===
export async function saveCallTranscript(messages: { role: string; content: string }[]): Promise<void> {
  if (!messages || messages.length === 0) return;
  try {
    const response = await authFetch(`${API_BASE_URL}/api/call/save-transcript`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages }),
    });
    if (!response.ok) {
      console.warn('儲存通話記錄失敗:', response.status);
    }
  } catch (err) {
    console.warn('儲存通話記錄失敗:', err);
  }
}

// === LiveKit Token API ===
export interface LivekitTokenResponse {
  token: string;
  url: string;
  room: string;
}

export async function getLivekitToken(): Promise<LivekitTokenResponse> {
  const response = await authFetch(`${API_BASE_URL}/api/livekit/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || '取得 LiveKit Token 失敗');
  }
  return response.json();
}

// === 通話模式用戶 Context API ===
export interface UserContextForVoice {
  user_profile: string;
  upcoming_events: string;
  my_promises: string;
  recent_chat_summary: string;
  proactive_care: string;  // 主動關心提示
  key_notes: string;       // 永久筆記
}

export async function getUserContextForVoice(): Promise<UserContextForVoice> {
  try {
    const response = await authFetch(`${API_BASE_URL}/api/elevenlabs/user-context`);
    if (!response.ok) {
      // 失敗時回傳空值，不阻擋通話
      console.warn('取得用戶 context 失敗，使用空值');
      return { user_profile: '', upcoming_events: '', my_promises: '', recent_chat_summary: '', proactive_care: '', key_notes: '' };
    }
    return response.json();
  } catch (e) {
    console.warn('取得用戶 context 發生錯誤，使用空值:', e);
    return { user_profile: '', upcoming_events: '', my_promises: '', recent_chat_summary: '', proactive_care: '', key_notes: '' };
  }
}

// 播放遠端音訊
export function playRemoteAudio(audioUrl: string): HTMLAudioElement {
  // 如果是相對路徑，需要加上正確的 base URL
  let fullUrl = audioUrl;
  if (!audioUrl.startsWith('http')) {
    // 音檔存在後端 API 伺服器，需要使用 API_BASE_URL
    // 如果 API_BASE_URL 為空（本地開發），則使用當前 origin
    const baseUrl = API_BASE_URL || (isBrowser ? window.location.origin : '');
    fullUrl = `${baseUrl}${audioUrl}`;
  }
  console.log('Playing audio from:', fullUrl);
  const audio = new Audio(fullUrl);
  return audio;
}

// === 舊 API (保留相容性，用於 Node.js 後端) ===
export async function transcribeAudio(audioBlob: Blob): Promise<string> {
  const formData = new FormData();
  formData.append('file', audioBlob, 'audio.webm');
  
  const response = await fetch(`${API_BASE_URL}/api/whisper`, {
    method: 'POST',
    headers: { 'ngrok-skip-browser-warning': 'true' },
    body: formData,
  });
  
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.error || 'Transcription failed');
  }
  const data = await response.json();
  return data.text;
}

export async function textToSpeech(text: string): Promise<HTMLAudioElement> {
  const response = await fetch(`${API_BASE_URL}/api/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true' },
    body: JSON.stringify({ text }),
  });
  
  if (!response.ok) throw new Error('TTS failed');
  
  const blob = await response.blob();
  const audio = new Audio(URL.createObjectURL(blob));
  return audio;
}

export async function chatText(text: string, userId?: string, conversationId?: string): Promise<ChatTextResponse> {
  const resolvedUserId = userId || getUserId();
  const resolvedConversationId = conversationId || getConversationId(resolvedUserId);
  
  // 使用 authFetch（自動帶 token + 401 處理）
  const response = await authFetch(`${API_BASE_URL}/api/chat_text`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text,
      user_id: resolvedUserId,
      conversation_id: resolvedConversationId
    }),
  });

  if (!response.ok) {
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `文字對話失敗 (HTTP ${response.status})`);
    }
    const respText = await response.text().catch(() => '');
    throw new Error(respText || `文字對話失敗 (HTTP ${response.status})`);
  }

  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    const respText = await response.text().catch(() => '');
    throw new Error(respText || '回傳格式錯誤');
  }
  return response.json();
}

export async function chatStream(
  messages: { role: string; content: string }[],
  onChunk: (chunk: string) => void
): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true' },
    body: JSON.stringify({ messages }),
  });

  if (!response.ok || !response.body) throw new Error('Chat failed');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let fullText = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    const chunk = decoder.decode(value);
    const lines = chunk.split('\n');
    
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const dataStr = line.slice(6);
        if (dataStr === '[DONE]') continue;
        
        try {
          const data = JSON.parse(dataStr);
          if (data.content) {
            fullText += data.content;
            onChunk(data.content);
          }
        } catch (e) {
          console.error('Error parsing SSE:', e);
        }
      }
    }
  }
  
  return fullText;
}

// === 圖片辨識 API ===
export interface VisionResponse {
  success: boolean;
  text: string;
  audio_url: string | null;
  image_url: string | null;  // 雲端圖片 URL
}

export async function analyzeImage(
  imageFile: File,
  message?: string,
  withAudio: boolean = true
): Promise<VisionResponse> {
  const formData = new FormData();
  formData.append('image', imageFile);
  if (message) {
    formData.append('message', message);
  }
  formData.append('with_audio', withAudio.toString());
  
  const token = getStoredToken();
  const headers: HeadersInit = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  const response = await fetch(`${API_BASE_URL}/api/vision/analyze`, {
    method: 'POST',
    headers: {
      ...headers,
      'ngrok-skip-browser-warning': 'true',
    },
    body: formData,
  });
  
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `圖片分析失敗 (HTTP ${response.status})`);
  }
  
  return response.json();
}

// === 對話歷史 API ===
export interface ConversationMessage {
  role: 'user' | 'assistant';
  content: string;
  created_at?: string;
  image_url?: string;  // 用戶上傳的圖片 URL
}

export interface ConversationHistoryResponse {
  messages: ConversationMessage[];
  total: number;
  has_more: boolean;
}

export async function getConversationHistory(
  limit: number = 50,
  offset: number = 0
): Promise<ConversationHistoryResponse> {
  const params = new URLSearchParams();
  params.set('limit', limit.toString());
  params.set('offset', offset.toString());
  
  const response = await authFetch(`${API_BASE_URL}/api/conversation/history?${params.toString()}`);
  
  if (!response.ok) {
    // 如果未登入或發生錯誤，返回預設訊息
    if (response.status === 401) {
      return {
        messages: [{ role: 'assistant', content: '「你好，我是馬雲。」' }],
        total: 1,
        has_more: false
      };
    }
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || '取得對話紀錄失敗');
  }

  return response.json();
}

// === 暱稱更新 ===
export async function updateNickname(name: string): Promise<{ name: string }> {
  const response = await authFetch(`${API_BASE_URL}/api/auth/me`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || '更新暱稱失敗');
  }
  return response.json();
}
