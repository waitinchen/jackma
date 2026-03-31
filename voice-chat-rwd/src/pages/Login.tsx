/**
 * 登入/註冊頁面
 */
import { useState } from 'react';
import { useLocation } from 'wouter';
import { useAuth } from '@/contexts/AuthContext';
import { cn } from '@/lib/utils';
import { DeviceFrame, StatusBar } from '@/components/DeviceFrame';
import { useIsMobile } from '@/hooks/use-mobile';
import { PWAStandaloneLock } from '@/components/PWAStandaloneLock';

type AuthMode = 'login' | 'register';

export default function Login() {
  const [mode, setMode] = useState<AuthMode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  const { login, register } = useAuth();
  const [, setLocation] = useLocation();
  const isMobile = useIsMobile();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      if (mode === 'login') {
        await login({ email, password });
      } else {
        await register({ email, password, name: name || undefined });
      }
      // 登入/註冊成功，導向首頁
      setLocation('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失敗');
    } finally {
      setIsSubmitting(false);
    }
  };

  const toggleMode = () => {
    setMode(mode === 'login' ? 'register' : 'login');
    setError(null);
  };

  const content = (
    <div className="h-full flex-1 flex flex-col bg-background text-foreground relative overflow-hidden">
      {/* Header */}
      <header className="flex-none h-14 flex items-center justify-center z-10">
        <div className="text-primary text-xl tracking-widest">馬雲 | 語氣靈</div>
      </header>

      {/* Main Content - 加入 overflow-y-auto 讓內容自己在中間滾動 */}
      <main className="flex-1 flex flex-col justify-center items-center px-6 overflow-y-auto">
        <div className="w-full max-w-sm space-y-5">
          {/* Avatar */}
          <div className="flex justify-center">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-zinc-700 to-zinc-900 flex items-center justify-center shadow-lg overflow-hidden">
              <img src="/icon.png" alt="馬雲" className="w-full h-full object-cover" />
            </div>
          </div>

          {/* Title */}
          <div className="text-center">
            <h1 className="text-xl font-semibold text-foreground">
              {mode === 'login' ? '歡迎回來' : '建立帳號'}
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              {mode === 'login' 
                ? '登入後，馬雲會記得你們的對話' 
                : '註冊後，對話記憶將永久保存'}
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-3 animate-form-enter">
            {mode === 'register' && (
              <div>
                <label className="block text-sm text-muted-foreground mb-1.5">
                  暱稱 (選填)
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="你希望馬雲怎麼稱呼你？"
                  className="w-full px-4 py-3 rounded-lg bg-card border border-white/10 text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/50"
                />
              </div>
            )}

            <div>
              <label className="block text-sm text-muted-foreground mb-1.5">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="your@email.com"
                required
                className="w-full px-4 py-3 rounded-lg bg-card border border-white/10 text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
            </div>

            <div>
              <label className="block text-sm text-muted-foreground mb-1.5">
                密碼
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={mode === 'register' ? '至少 6 個字元' : '••••••••'}
                required
                minLength={6}
                className="w-full px-4 py-3 rounded-lg bg-card border border-white/10 text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/50"
              />
            </div>

            {error && (
              <div className="text-sm text-red-400 bg-red-400/10 px-4 py-2 rounded-lg border border-red-400/20 animate-shake">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={isSubmitting}
              className={cn(
                "w-full py-3 rounded-lg font-medium transition-colors",
                "bg-primary text-primary-foreground hover:bg-primary/90",
                "disabled:opacity-50 disabled:cursor-not-allowed"
              )}
            >
              {isSubmitting 
                ? '處理中...' 
                : mode === 'login' 
                  ? '登入' 
                  : '註冊'}
            </button>
          </form>

          {/* Toggle Mode */}
          <div className="text-center text-sm">
            <span className="text-muted-foreground">
              {mode === 'login' ? '還沒有帳號？' : '已經有帳號？'}
            </span>
            <button
              type="button"
              onClick={toggleMode}
              className="ml-1 text-primary hover:underline"
            >
              {mode === 'login' ? '立即註冊' : '登入'}
            </button>
          </div>


        </div>
      </main>

      {/* Footer */}
      <footer className="flex-none py-4 text-center text-muted-foreground/40 text-[10px] z-10">
        -超智能-
      </footer>
    </div>
  );

  if (isMobile) {
    return (
      <>
        <PWAStandaloneLock />
        {content}
      </>
    );
  }

  return (
    <DeviceFrame>
      <StatusBar />
      {content}
    </DeviceFrame>
  );
}
