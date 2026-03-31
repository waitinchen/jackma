import { useState, useEffect } from "react";
import { Battery, Wifi, Signal } from "lucide-react";
import { cn } from "@/lib/utils";
import { useIsMobile } from "@/hooks/use-mobile";
import { useStandalone } from "@/hooks/useStandalone";

interface DeviceFrameProps {
  children: React.ReactNode;
}

export function DeviceFrame({ children }: DeviceFrameProps) {
  const standalone = useStandalone();

  return (
    <div
      className={cn(
        "w-full flex items-center justify-center bg-zinc-900",
        "p-4 lg:p-8 max-sm:p-0",
        standalone ? "h-dvh min-h-0 overflow-hidden" : "min-h-screen"
      )}
    >
      <div
        className={cn(
          "relative w-full max-w-[375px] h-[812px] bg-black rounded-[40px] shadow-2xl border-[8px] border-zinc-800 overflow-hidden ring-4 ring-zinc-950/50",
          "lg:h-[850px] lg:max-w-[400px]",
          "max-sm:h-[100dvh] max-sm:max-w-none max-sm:rounded-none max-sm:border-none max-sm:ring-0"
        )}
      >
        <div className="absolute top-0 left-1/2 -translate-x-1/2 h-[30px] w-[120px] bg-black rounded-b-2xl z-50 pointer-events-none max-sm:hidden" />
        <div className="w-full h-full bg-background relative flex flex-col overflow-hidden">
          {children}
        </div>
        <div className="absolute bottom-2 left-1/2 -translate-x-1/2 w-[120px] h-[4px] bg-white/20 rounded-full z-50 pointer-events-none max-sm:mb-2" />
      </div>
    </div>
  );
}

export function StatusBar() {
  const [time, setTime] = useState("");
  const isMobile = useIsMobile();

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setTime(now.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit', hour12: false }));
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  if (isMobile) {
    return null;
  }

  return (
    <div className="w-full h-8 px-4 flex justify-between items-center text-xs text-white/80 font-medium select-none z-40 bg-transparent absolute top-0 left-0">
      {/* Time */}
      <div className="tracking-wide text-sm">{time}</div>
      
      {/* Icons */}
      <div className="flex items-center gap-1.5">
        <Signal size={14} className="fill-current" />
        <Wifi size={14} />
        <div className="relative">
             <Battery size={16} className="rotate-0" />
             <div className="absolute top-[3px] left-[2px] w-[10px] h-[6px] bg-current rounded-[1px]"></div>
        </div>
      </div>
    </div>
  );
}
