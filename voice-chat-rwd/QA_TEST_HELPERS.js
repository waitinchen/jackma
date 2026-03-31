/**
 * 通話音質改善 QA 測試輔助腳本
 * 
 * 使用方式：在瀏覽器 Console 中貼上此腳本
 * 測試網址：https://jackma.tonetown.ai/#/call
 */

// ============================================
// 1. 麥克風配置驗證
// ============================================

/**
 * 檢查當前麥克風配置
 * 用於驗證 echoCancellation, noiseSuppression, autoGainControl 是否啟用
 */
async function checkMicConfig() {
  console.log('📊 正在檢查麥克風配置...');
  
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      }
    });
    
    const track = stream.getAudioTracks()[0];
    const settings = track.getSettings();
    const capabilities = track.getCapabilities();
    
    console.log('✅ 麥克風配置:');
    console.table({
      '回聲消除 (echoCancellation)': settings.echoCancellation ?? '未知',
      '降噪 (noiseSuppression)': settings.noiseSuppression ?? '未知',
      '自動增益 (autoGainControl)': settings.autoGainControl ?? '未知',
      '採樣率 (sampleRate)': settings.sampleRate ?? '未知',
      '聲道數 (channelCount)': settings.channelCount ?? '未知',
    });
    
    console.log('📋 設備能力:', capabilities);
    
    // 停止測試流
    stream.getTracks().forEach(t => t.stop());
    
    return {
      echoCancellation: settings.echoCancellation,
      noiseSuppression: settings.noiseSuppression,
      autoGainControl: settings.autoGainControl,
    };
  } catch (err) {
    console.error('❌ 無法獲取麥克風:', err.message);
    return null;
  }
}

// ============================================
// 2. 網路延遲測試
// ============================================

/**
 * 測量到 ElevenLabs API 的延遲
 */
async function measureLatency(times = 5) {
  console.log(`📡 正在測量網路延遲 (${times} 次)...`);
  
  const results = [];
  
  for (let i = 0; i < times; i++) {
    const start = performance.now();
    try {
      await fetch('https://api.elevenlabs.io/', { method: 'HEAD', mode: 'no-cors' });
      const latency = Math.round(performance.now() - start);
      results.push(latency);
      console.log(`  第 ${i + 1} 次: ${latency}ms`);
    } catch {
      console.log(`  第 ${i + 1} 次: 失敗`);
      results.push(null);
    }
  }
  
  const validResults = results.filter(r => r !== null);
  const avg = validResults.length > 0 
    ? Math.round(validResults.reduce((a, b) => a + b, 0) / validResults.length)
    : null;
  const min = validResults.length > 0 ? Math.min(...validResults) : null;
  const max = validResults.length > 0 ? Math.max(...validResults) : null;
  
  console.log('\n📊 延遲統計:');
  console.table({
    '平均延遲': `${avg}ms`,
    '最小延遲': `${min}ms`,
    '最大延遲': `${max}ms`,
    '建議': avg > 300 ? '⚠️ 建議使用 PTT 模式' : '✅ 延遲正常',
  });
  
  return { avg, min, max, results };
}

// ============================================
// 3. WebSocket 連線狀態檢查
// ============================================

/**
 * 檢查當前 WebSocket 連線狀態
 */
function checkWebSocketStatus() {
  // 嘗試從 React 狀態中獲取連線資訊
  const root = document.getElementById('root');
  if (!root || !root._reactRootContainer) {
    console.log('⚠️ 無法直接存取 React 狀態，請查看頁面上的連線狀態指示器');
    return;
  }
  
  console.log('📡 請查看頁面上的以下指示器:');
  console.log('  - 延遲顯示: 綠色 (<150ms) / 黃色 (150-300ms) / 橙色 (>300ms)');
  console.log('  - 音質等級: 高 / 中 / 低');
  console.log('  - 重連狀態: x/3');
}

// ============================================
// 4. PTT 模式測試輔助
// ============================================

/**
 * 模擬 PTT 按鈕事件（僅用於測試腳本驗證）
 */
function findPTTButton() {
  const buttons = document.querySelectorAll('button');
  for (const btn of buttons) {
    if (btn.textContent.includes('自動偵測') || btn.textContent.includes('對講機模式')) {
      console.log('✅ 找到 PTT 切換按鈕');
      return btn;
    }
  }
  console.log('❌ 未找到 PTT 切換按鈕，請確認已進入通話頁面');
  return null;
}

// ============================================
// 5. 記憶體監控（壓力測試用）
// ============================================

/**
 * 開始記憶體監控
 * @param {number} intervalMs - 監控間隔（毫秒）
 */
function startMemoryMonitor(intervalMs = 5000) {
  if (!window.performance || !window.performance.memory) {
    console.log('⚠️ 此瀏覽器不支援記憶體監控 (需要 Chrome 並開啟 --enable-precise-memory-info)');
    return null;
  }
  
  console.log(`📊 開始記憶體監控 (每 ${intervalMs/1000} 秒)...`);
  console.log('   執行 stopMemoryMonitor() 停止監控');
  
  const startMemory = performance.memory.usedJSHeapSize;
  let samples = [];
  
  window._memoryMonitorId = setInterval(() => {
    const mem = performance.memory;
    const usedMB = (mem.usedJSHeapSize / 1024 / 1024).toFixed(2);
    const totalMB = (mem.totalJSHeapSize / 1024 / 1024).toFixed(2);
    const diffMB = ((mem.usedJSHeapSize - startMemory) / 1024 / 1024).toFixed(2);
    
    samples.push(mem.usedJSHeapSize);
    
    console.log(`📈 記憶體: ${usedMB}MB / ${totalMB}MB (變化: ${diffMB > 0 ? '+' : ''}${diffMB}MB)`);
    
    // 如果記憶體持續增長超過 50MB，發出警告
    if (samples.length >= 6) {
      const trend = samples.slice(-6);
      const isLeaking = trend.every((v, i) => i === 0 || v > trend[i-1]);
      if (isLeaking) {
        console.warn('⚠️ 警告: 記憶體持續增長，可能存在洩漏!');
      }
    }
  }, intervalMs);
  
  return window._memoryMonitorId;
}

/**
 * 停止記憶體監控
 */
function stopMemoryMonitor() {
  if (window._memoryMonitorId) {
    clearInterval(window._memoryMonitorId);
    window._memoryMonitorId = null;
    console.log('📊 記憶體監控已停止');
  }
}

// ============================================
// 6. 快速測試指南
// ============================================

function showTestGuide() {
  console.log(`
╔══════════════════════════════════════════════════════════════╗
║           通話音質改善 QA 測試輔助腳本                        ║
╠══════════════════════════════════════════════════════════════╣
║ 可用函數:                                                     ║
║                                                               ║
║ 1. checkMicConfig()      - 檢查麥克風配置是否正確啟用         ║
║ 2. measureLatency(5)     - 測量網路延遲 (預設 5 次)           ║
║ 3. checkWebSocketStatus()- 檢查 WebSocket 連線狀態            ║
║ 4. findPTTButton()       - 找到 PTT 切換按鈕                  ║
║ 5. startMemoryMonitor()  - 開始記憶體監控（壓力測試用）       ║
║ 6. stopMemoryMonitor()   - 停止記憶體監控                     ║
║                                                               ║
║ 測試流程:                                                     ║
║ 1. 開啟 https://jackma.tonetown.ai/#/call                  ║
║ 2. 撥打電話後執行 checkMicConfig() 驗證麥克風配置             ║
║ 3. 執行 measureLatency() 檢查網路延遲                         ║
║ 4. 長時間測試時執行 startMemoryMonitor() 監控記憶體           ║
╚══════════════════════════════════════════════════════════════╝
  `);
}

// 自動顯示指南
showTestGuide();
