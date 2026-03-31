import { useEffect } from "react";
import { useStandalone } from "@/hooks/useStandalone";

const CLASS = "pwa-standalone";

/**
 * When running as PWA (add-to-homescreen), add `pwa-standalone` to <html>.
 * CSS uses this to lock body/root scroll and allow only the conversation history to scroll.
 */
export function PWAStandaloneLock() {
  const standalone = useStandalone();

  useEffect(() => {
    const el = document.documentElement;
    if (standalone) el.classList.add(CLASS);
    else el.classList.remove(CLASS);
    return () => el.classList.remove(CLASS);
  }, [standalone]);

  return null;
}
