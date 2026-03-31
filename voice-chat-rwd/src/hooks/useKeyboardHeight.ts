import { useState, useEffect } from "react";

/**
 * 監聽 iOS PWA 鍵盤高度變化
 * 使用 visualViewport API 計算鍵盤佔用的高度
 */
export function useKeyboardHeight(): number {
  const [height, setHeight] = useState(0);

  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;

    const update = () => {
      // visualViewport.height 是可見區域高度（不含鍵盤）
      // window.innerHeight 是整個視口高度
      const diff = window.innerHeight - vv.height;
      // 設定閾值 50px，避免小幅度變化誤判為鍵盤
      setHeight(diff > 50 ? diff : 0);
    };

    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    
    // 初始化
    update();

    return () => {
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
    };
  }, []);

  return height;
}
