import { useState, useEffect } from "react";
import { Download, X, Share2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

function isIOS(): boolean {
  if (typeof navigator === "undefined") return false;
  return /(iPhone|iPad|iPod)/i.test(navigator.userAgent);
}

function checkInstalled(): boolean {
  if (typeof window === "undefined") return false;
  if (window.matchMedia("(display-mode: standalone)").matches) return true;
  const nav = navigator as Navigator & { standalone?: boolean };
  return !!nav.standalone;
}

export function PWAInstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] =
    useState<BeforeInstallPromptEvent | null>(null);
  const [showPrompt, setShowPrompt] = useState(false);
  const [showIOSPrompt, setShowIOSPrompt] = useState(false);
  const [isInstalled, setIsInstalled] = useState(false);

  useEffect(() => {
    if (checkInstalled()) {
      setIsInstalled(true);
      return;
    }

    const dismissed = localStorage.getItem("pwa-install-dismissed");
    if (dismissed) {
      const dismissedTime = parseInt(dismissed, 10);
      const hoursSinceDismissed =
        (Date.now() - dismissedTime) / (1000 * 60 * 60);
      if (hoursSinceDismissed < 24) return;
    }

    const delay = 3000;
    const isIOSUser = isIOS();

    const handleBeforeInstallPrompt = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
      setTimeout(() => setShowPrompt(true), delay);
    };

    const handleAppInstalled = () => {
      setIsInstalled(true);
      setShowPrompt(false);
      setShowIOSPrompt(false);
      setDeferredPrompt(null);
    };

    window.addEventListener("beforeinstallprompt", handleBeforeInstallPrompt);
    window.addEventListener("appinstalled", handleAppInstalled);

    if (isIOSUser) {
      const t = setTimeout(() => setShowIOSPrompt(true), delay);
      return () => {
        clearTimeout(t);
        window.removeEventListener(
          "beforeinstallprompt",
          handleBeforeInstallPrompt
        );
        window.removeEventListener("appinstalled", handleAppInstalled);
      };
    }

    return () => {
      window.removeEventListener(
        "beforeinstallprompt",
        handleBeforeInstallPrompt
      );
      window.removeEventListener("appinstalled", handleAppInstalled);
    };
  }, []);

  const handleInstallClick = async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === "accepted") {
      setShowPrompt(false);
      setDeferredPrompt(null);
    }
  };

  const handleDismiss = () => {
    setShowPrompt(false);
    setShowIOSPrompt(false);
    localStorage.setItem("pwa-install-dismissed", Date.now().toString());
  };

  if (isInstalled) return null;

  const iosBanner = isIOS() && showIOSPrompt;
  const androidBanner = showPrompt && !!deferredPrompt;
  if (!iosBanner && !androidBanner) return null;

  const shared = cn(
    "fixed bottom-4 left-1/2 -translate-x-1/2 z-50",
    "bg-black/90 backdrop-blur-sm border border-white/20 rounded-2xl",
    "px-4 py-3 shadow-2xl",
    "animate-in slide-in-from-bottom-4 fade-in duration-300",
    "max-w-[calc(100vw-2rem)] sm:max-w-md"
  );

  if (iosBanner) {
    return (
      <div className={shared}>
        <div className="flex items-center gap-3">
          <div className="flex-shrink-0">
            <Share2 className="w-5 h-5 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-white">
              加入主畫面使用「馬雲」
            </p>
            <p className="text-xs text-white/70 mt-0.5">
              Safari → 分享 → 加入主畫面
            </p>
          </div>
          <button
            onClick={handleDismiss}
            className={cn(
              "p-1.5 rounded-lg",
              "text-white/70 hover:text-white hover:bg-white/10",
              "transition-colors"
            )}
            aria-label="關閉"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={shared}>
      <div className="flex items-center gap-3">
        <div className="flex-shrink-0">
          <Download className="w-5 h-5 text-white" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white">
            安裝「馬雲」到主畫面
          </p>
          <p className="text-xs text-white/70 mt-0.5">
            獲得更好的使用體驗
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleInstallClick}
            className={cn(
              "px-3 py-1.5 text-xs font-medium rounded-lg",
              "bg-white text-black hover:bg-white/90",
              "transition-colors"
            )}
          >
            安裝
          </button>
          <button
            onClick={handleDismiss}
            className={cn(
              "p-1.5 rounded-lg",
              "text-white/70 hover:text-white hover:bg-white/10",
              "transition-colors"
            )}
            aria-label="關閉"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
