import { useState } from "react";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Router, Route, Switch } from "wouter";
import { useHashLocation } from "wouter/use-hash-location";
import { motion } from "framer-motion";
import ErrorBoundary from "@/components/ErrorBoundary";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { AuthProvider } from "@/contexts/AuthContext";
import { PWAStandaloneLock } from "@/components/PWAStandaloneLock";
import { useRegisterSW } from "virtual:pwa-register/react";
import Home from "@/pages/Home";
import Call from "@/pages/Call";
import Login from "@/pages/Login";
import Changelog from "@/pages/Changelog";

// 頁面切換動畫設定 - 只有淡入，沒有淡出
const pageVariants = {
  initial: { opacity: 0 },
  animate: { opacity: 1 }
};

// 動畫包裝組件
function AnimatedPage({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      className="h-full w-full"
      variants={pageVariants}
      initial="initial"
      animate="animate"
      transition={{ duration: 0.25, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}

// Use hash-based routing (/#/) to support opening index.html directly via file:// protocol
function AppRouter() {
  const [location] = useHashLocation();
  
  return (
    <Router hook={useHashLocation}>
      <Switch key={location}>
        <Route path="/">
          <AnimatedPage><Home /></AnimatedPage>
        </Route>
        <Route path="/call">
          <AnimatedPage><Call /></AnimatedPage>
        </Route>
        <Route path="/realtime">
          <AnimatedPage><Call /></AnimatedPage>
        </Route>
        <Route path="/login">
          <AnimatedPage><Login /></AnimatedPage>
        </Route>
        <Route path="/changelog">
          <AnimatedPage><Changelog /></AnimatedPage>
        </Route>
      </Switch>
    </Router>
  );
}

// Note on theming:
// - Choose defaultTheme based on your design (light or dark background)
// - Update the color palette in index.css to match
// - If you want switchable themes, add `switchable` prop and use `useTheme` hook

function UpdateBanner() {
  const [dismissed, setDismissed] = useState(false);
  const {
    needRefresh: [needRefresh],
    updateServiceWorker,
  } = useRegisterSW();

  if (!needRefresh || dismissed) return null;

  return (
    <div className="fixed top-0 left-0 right-0 z-[9999] flex items-center justify-center gap-3 bg-amber-600/90 backdrop-blur-sm px-4 py-2 text-sm text-white">
      <span
        className="cursor-pointer hover:underline"
        onClick={() => updateServiceWorker(true)}
      >
        馬雲已更新，點此重新載入
      </span>
      <button
        onClick={() => setDismissed(true)}
        className="ml-2 text-white/70 hover:text-white text-lg leading-none"
        aria-label="關閉"
      >
        &times;
      </button>
    </div>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider defaultTheme="dark">
        <AuthProvider>
          <PWAStandaloneLock />
          <UpdateBanner />
          <TooltipProvider>
            <Toaster />
            <AppRouter />
          </TooltipProvider>
        </AuthProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;

