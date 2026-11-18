// LOG SENTINEL // Real-Time WebSocket Streaming & Telemetry Spike Analyzer
(function() {
  const streamStatus = document.getElementById('streamStatus');
  const totalLogsCounter = document.getElementById('totalLogsCounter');
  const histogramCanvas = document.getElementById('histogramCanvas');
  const hCtx = histogramCanvas.getContext('2d');

  const logSearchInput = document.getElementById('logSearchInput');
  const filterBtns = document.querySelectorAll('.filter-btn');
  const sourceFilter = document.getElementById('sourceFilter');
  const btnToggleScroll = document.getElementById('btnToggleScroll');
  const btnClearTerminal = document.getElementById('btnClearTerminal');
  const btnAlertRulesModal = document.getElementById('btnAlertRulesModal');
  const logStream = document.getElementById('logStream');
  const consoleContainer = document.getElementById('consoleContainer');

  const alertBanner = document.getElementById('alertBanner');
  const alertBannerText = document.getElementById('alertBannerText');
  const btnDismissAlert = document.getElementById('btnDismissAlert');

  const rulesModal = document.getElementById('rulesModal');
  const btnCloseModal = document.getElementById('btnCloseModal');
  const btnSaveRule = document.getElementById('btnSaveRule');
  const ruleNameInput = document.getElementById('ruleNameInput');
  const ruleLevelSelect = document.getElementById('ruleLevelSelect');
  const ruleThresholdInput = document.getElementById('ruleThresholdInput');
  const ruleWindowInput = document.getElementById('ruleWindowInput');
  const alertHistoryList = document.getElementById('alertHistoryList');

  let activeLevel = "ALL";
  let autoScroll = true;
  let totalIngested = 0;
  let logsMemoryBuffer = [];
  let ws = null;

  // WebAudio Beep for Alerts
  function playAlertBeep() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      osc.frequency.setValueAtTime(440, ctx.currentTime + 0.15);
      gain.gain.setValueAtTime(0.2, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.35);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.35);
    } catch (e) {}
  }

  // WebSocket Connection
  function initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws/logs`);

    ws.onopen = () => {
      streamStatus.textContent = "CONNECTED (LIVE)";
      streamStatus.style.color = "#84CC16";
    };

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === 'LOG') {
          handleIncomingLog(data);
        } else if (data.type === 'ALERT') {
          handleIncomingAlert(data);
        }
      } catch (err) {}
    };

    ws.onclose = () => {
      streamStatus.textContent = "DISCONNECTED (RETRYING)";
      streamStatus.style.color = "#EF4444";
      setTimeout(initWebSocket, 2000);
    };
  }

  function handleIncomingLog(log) {
    totalIngested++;
    totalLogsCounter.textContent = totalIngested.toLocaleString();
    logsMemoryBuffer.push(log);
    if (logsMemoryBuffer.length > 300) logsMemoryBuffer.shift();

    if (matchesFilter(log)) {
      appendLogLine(log);
    }
  }

  function handleIncomingAlert(alert) {
    alertBanner.classList.remove('hidden');
    alertBannerText.textContent = `ALERT TRIGGERED: ${alert.rule} — ${alert.details} (${alert.timestamp})`;
    playAlertBeep();
  }

  btnDismissAlert.addEventListener('click', () => {
    alertBanner.classList.add('hidden');
  });

  function matchesFilter(log) {
    if (activeLevel !== "ALL" && log.level !== activeLevel) return false;
    if (sourceFilter.value !== "ALL" && log.source !== sourceFilter.value) return false;

    const query = logSearchInput.value.trim().toLowerCase();
    if (query) {
      const lineStr = `${log.source} ${log.message} ${log.ip} ${log.level}`.toLowerCase();
      if (!lineStr.includes(query)) return false;
    }
    return true;
  }

  function appendLogLine(log) {
    const line = document.createElement('div');
    line.className = 'log-line';
    const badgeClass = log.level === 'ERROR' ? 'b-error' : log.level === 'WARN' ? 'b-warn' : 'b-info';

    line.innerHTML = `
      <span class="l-time">${log.timestamp.split(' ')[1]}</span>
      <span class="l-badge ${badgeClass}">${log.level}</span>
      <span class="l-source">[${log.source}]</span>
      <span class="l-ip">${log.ip}</span>
      <span class="l-lat">${log.latency}ms</span>
      <span class="l-msg">${escapeHtml(log.message)}</span>
    `;

    logStream.appendChild(line);

    // Limit DOM elements for 60 FPS
    if (logStream.children.length > 250) {
      logStream.removeChild(logStream.children[0]);
    }

    if (autoScroll) {
      consoleContainer.scrollTop = consoleContainer.scrollHeight;
    }
  }

  // Filter Event Listeners
  filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      filterBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeLevel = btn.dataset.level;
      reapplyFilters();
    });
  });

  sourceFilter.addEventListener('change', reapplyFilters);
  logSearchInput.addEventListener('input', reapplyFilters);

  function reapplyFilters() {
    logStream.innerHTML = '';
    logsMemoryBuffer.forEach(log => {
      if (matchesFilter(log)) appendLogLine(log);
    });
  }

  btnToggleScroll.addEventListener('click', () => {
    autoScroll = !autoScroll;
    btnToggleScroll.textContent = `SCROLL: ${autoScroll ? 'ON' : 'OFF'}`;
  });

  btnClearTerminal.addEventListener('click', () => {
    logStream.innerHTML = '';
  });

  // Canvas Histogram (Error/Warn Spikes)
  async function fetchHistogramData() {
    try {
      const res = await fetch('/api/metrics/spikes');
      const data = await res.json();
      renderHistogram(data.buckets);
    } catch (e) {}
  }

  function renderHistogram(buckets) {
    const w = histogramCanvas.width;
    const h = histogramCanvas.height;
    hCtx.clearRect(0, 0, w, h);

    if (!buckets || buckets.length === 0) return;

    const barW = Math.max(12, Math.floor(w / buckets.length) - 8);
    const maxVal = Math.max(8, ...buckets.map(b => b.errors + b.warnings + b.infos));

    buckets.forEach((b, idx) => {
      const x = idx * (barW + 8) + 10;
      let curY = h - 14;

      // Infos (Lime)
      const hInfo = Math.floor((b.infos / maxVal) * (h - 22));
      hCtx.fillStyle = '#84CC16';
      hCtx.fillRect(x, curY - hInfo, barW, hInfo);
      curY -= hInfo;

      // Warnings (Amber)
      const hWarn = Math.floor((b.warnings / maxVal) * (h - 22));
      hCtx.fillStyle = '#F59E0B';
      hCtx.fillRect(x, curY - hWarn, barW, hWarn);
      curY -= hWarn;

      // Errors (Red)
      const hErr = Math.floor((b.errors / maxVal) * (h - 22));
      hCtx.fillStyle = '#EF4444';
      hCtx.fillRect(x, curY - hErr, barW, hErr);

      // Time label
      hCtx.fillStyle = '#565660';
      hCtx.font = "9px 'JetBrains Mono', monospace";
      hCtx.fillText(b.minute, x, h - 2);
    });
  }

  // Alert Rules Modal
  btnAlertRulesModal.addEventListener('click', async () => {
    rulesModal.classList.remove('hidden');
    fetchAlertHistory();
  });

  btnCloseModal.addEventListener('click', () => rulesModal.classList.add('hidden'));

  async function fetchAlertHistory() {
    try {
      const res = await fetch('/api/alerts');
      const data = await res.json();
      alertHistoryList.innerHTML = '';
      data.alerts.forEach(a => {
        const row = document.createElement('div');
        row.style.borderBottom = '1px solid #1E1E26';
        row.style.padding = '4px 0';
        row.innerHTML = `
          <div style="font-weight:700;color:#EF4444;">${escapeHtml(a.rule_name)} (${a.timestamp})</div>
          <div style="color:#A1A1AA;font-size:10px;">${escapeHtml(a.details)}</div>
        `;
        alertHistoryList.appendChild(row);
      });
    } catch (e) {}
  }

  btnSaveRule.addEventListener('click', async () => {
    const payload = {
      name: ruleNameInput.value.trim() || 'Watchdog Rule',
      level: ruleLevelSelect.value,
      threshold_count: parseInt(ruleThresholdInput.value) || 3,
      window_seconds: parseInt(ruleWindowInput.value) || 30
    };

    const res = await fetch('/api/alerts/rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      alert("Alert rule successfully activated in Sentinel Engine.");
      fetchAlertHistory();
    }
  });

  function escapeHtml(str) {
    return String(str).replace(/[&<>'"]/g, tag => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[tag] || tag));
  }

  // Initial Boot
  initWebSocket();
  fetchHistogramData();
  setInterval(fetchHistogramData, 4000);

})();
