/**
 * 認證相關 API 和狀態管理
 */
import { API_BASE_URL } from './api';

// ============================================
// Types
// ============================================

export interface User {
  id: string;
  email: string | null;
  name: string | null;
  is_anonymous: boolean;
}

export interface AuthToken {
  access_token: string;
  token_type: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  name?: string;
}

// ============================================
// Token 管理
// ============================================

const TOKEN_KEY = 'jackma_auth_token';
const ANONYMOUS_ID_KEY = 'jackma_anonymous_id';

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearStoredToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function getStoredAnonymousId(): string | null {
  return localStorage.getItem(ANONYMOUS_ID_KEY);
}

export function setStoredAnonymousId(id: string): void {
  localStorage.setItem(ANONYMOUS_ID_KEY, id);
}

export function clearStoredAnonymousId(): void {
  localStorage.removeItem(ANONYMOUS_ID_KEY);
}

// ============================================
// API 請求 Helper
// ============================================

async function authFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getStoredToken();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    'ngrok-skip-browser-warning': 'true',
    ...(options.headers || {}),
  };
  
  if (token) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;
  }
  
  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });
  
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `請求失敗 (${response.status})`);
  }
  
  return response.json();
}

// ============================================
// Auth API
// ============================================

/**
 * 註冊新用戶
 */
export async function register(data: RegisterRequest): Promise<AuthToken> {
  const result = await authFetch<AuthToken>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  
  setStoredToken(result.access_token);
  
  // 如果有匿名用戶資料，嘗試合併
  const anonymousId = getStoredAnonymousId();
  if (anonymousId) {
    try {
      await mergeAnonymousData(anonymousId);
      clearStoredAnonymousId();
    } catch (e) {
      console.warn('合併匿名資料失敗:', e);
    }
  }
  
  return result;
}

/**
 * 用戶登入
 */
export async function login(data: LoginRequest): Promise<AuthToken> {
  const result = await authFetch<AuthToken>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  
  setStoredToken(result.access_token);
  
  // 如果有匿名用戶資料，嘗試合併
  const anonymousId = getStoredAnonymousId();
  if (anonymousId) {
    try {
      await mergeAnonymousData(anonymousId);
      clearStoredAnonymousId();
    } catch (e) {
      console.warn('合併匿名資料失敗:', e);
    }
  }
  
  return result;
}

/**
 * 登出
 */
export function logout(): void {
  clearStoredToken();
}

/**
 * 取得當前用戶資訊
 */
export async function getCurrentUser(): Promise<User | null> {
  const token = getStoredToken();
  if (!token) {
    return null;
  }
  
  try {
    return await authFetch<User>('/api/auth/me');
  } catch (e) {
    // Token 無效，清除
    clearStoredToken();
    return null;
  }
}

/**
 * 建立匿名用戶
 */
export async function createAnonymousUser(): Promise<AuthToken> {
  const result = await authFetch<AuthToken>('/api/auth/anonymous', {
    method: 'POST',
  });
  
  setStoredToken(result.access_token);
  
  // 解析 token 取得 user_id 並儲存
  try {
    const payload = JSON.parse(atob(result.access_token.split('.')[1]));
    if (payload.sub) {
      setStoredAnonymousId(payload.sub);
    }
  } catch (e) {
    console.warn('無法解析 token:', e);
  }
  
  return result;
}

/**
 * 合併匿名用戶資料
 */
export async function mergeAnonymousData(anonymousUserId: string): Promise<{
  message: string;
  merged_conversations: number;
  merged_memories: number;
}> {
  return authFetch('/api/auth/merge-anonymous', {
    method: 'POST',
    body: JSON.stringify({ anonymous_user_id: anonymousUserId }),
  });
}

/**
 * 確保有有效的用戶身份 (登入用戶或匿名用戶)
 */
export async function ensureAuthenticated(): Promise<User | null> {
  // 先嘗試取得當前用戶
  const user = await getCurrentUser();
  if (user) {
    return user;
  }
  
  // 沒有有效 token，建立匿名用戶
  await createAnonymousUser();
  return getCurrentUser();
}

/**
 * 檢查是否已登入 (非匿名)
 */
export async function isLoggedIn(): Promise<boolean> {
  const user = await getCurrentUser();
  return user !== null && !user.is_anonymous;
}
