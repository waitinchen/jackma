import { cn } from "@/lib/utils";

interface SplashScreenProps {
  className?: string;
}

export function SplashScreen({ className }: SplashScreenProps) {
  return (
    <div
      className={cn(
        "fixed inset-0 z-50 flex flex-col items-center justify-center bg-background",
        "animate-in fade-in duration-300",
        className
      )}
    >
      {/* 背景光暈 */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="splash-glow absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 rounded-full bg-primary/20 blur-3xl" />
      </div>

      {/* 主要內容 */}
      <div className="relative flex flex-col items-center gap-4">
        {/* 馬雲 - 主標題 */}
        <h1 className="splash-title text-5xl font-bold text-primary tracking-[0.2em] drop-shadow-[0_0_30px_rgba(234,179,8,0.4)]">
          馬雲
        </h1>

        {/* 語氣靈 | 智能體 - 副標題 */}
        <div className="splash-subtitle flex items-center gap-2">
          <span className="text-sm text-muted-foreground tracking-[0.15em] border-r border-muted-foreground/30 pr-2">
            語氣靈
          </span>
          <span className="text-sm text-muted-foreground tracking-[0.15em]">
            智能體
          </span>
        </div>

        {/* 載入指示器 */}
        <div className="splash-loader mt-8 flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-bounce" style={{ animationDelay: "0ms" }} />
          <span className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-bounce" style={{ animationDelay: "150ms" }} />
          <span className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-bounce" style={{ animationDelay: "300ms" }} />
        </div>
      </div>

      {/* 底部標語 */}
      <div className="splash-footer absolute bottom-12 text-[10px] text-muted-foreground/40 tracking-[0.3em]">
        -超智能-
      </div>
    </div>
  );
}
