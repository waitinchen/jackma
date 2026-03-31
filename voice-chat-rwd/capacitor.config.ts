import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.jackma.voice',
  appName: '馬雲',
  webDir: 'dist',
  android: {
    // 允許 HTTP（開發用，正式環境應使用 HTTPS）
    allowMixedContent: true,
  },
  server: {
    // 允許 cleartext（HTTP）請求
    cleartext: true,
  }
};

export default config;
