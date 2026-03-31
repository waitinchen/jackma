/**
 * 簡體中文 → 繁體中文 轉換
 * 使用 opencc-js（Open Chinese Convert）— 支援詞組級轉換
 * 取代手動 765 字映射表，覆蓋 3,500+ 字
 */
import * as OpenCC from 'opencc-js';

const converter = OpenCC.Converter({ from: 'cn', to: 'tw' });

/** 簡體中文 → 繁體中文 */
export function s2t(text: string): string {
  if (!text) return text;
  return converter(text);
}
