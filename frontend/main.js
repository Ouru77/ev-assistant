// E.V. — Frontend (local Whisper STT + ElevenLabs TTS, cyber core visualizer)
const vizCanvas = document.getElementById('viz');
const status = document.getElementById('status');
const transcript = document.getElementById('transcript');
let orbState = 'idle';

let ws;
let audioQueue = [];
let isPlaying = false;      // ElevenLabs audio playback
let ttsSpeaking = false;    // browser speech synthesis
let awaitingResponse = false;
let listeningEnabled = false;  // muted by default; Ctrl+Space / orb click toggles
let audioUnlocked = false;
let watchdog = null;
let currentEvDiv = null;  // streamed E.V. line being appended to
let currentAudio = null;  // the HTMLAudio currently playing (so we can stop it)
// Language: /stats sets it from config; ?lang=en|tr overrides (handy for previews).
const _langOverride = new URLSearchParams(location.search).get('lang');
let appLang = _langOverride === 'en' ? 'en' : 'tr';  // set from /stats; drives TTS + UI

// Static UI labels. The HTML is authored in English; applyI18n swaps in the
// active language. BOTH languages carry a dict so switching is reversible — a
// server config of "en" must undo any Turkish applied before /stats resolved.
const I18N = {
    en: {
        sys: '// SYSTEM', modules: '// MODULES', workshop: '// WORKSHOP', log: '// EVENT LOG',
        mem: 'MEMORY', core: 'CORE', voice: 'VOICE', send: 'SEND',
        start: 'Press Ctrl+Space to start', ph: 'Message E.V.…',
    },
    tr: {
        sys: '// SİSTEM', modules: '// MODÜLLER', workshop: '// ATÖLYE', log: '// OLAY GÜNLÜĞÜ',
        mem: 'BELLEK', core: 'ÇEKİRDEK', voice: 'SES', send: 'GÖNDER',
        start: 'Başlamak için Ctrl+Space', ph: "E.V.'ye yaz…",
    },
};
let lastI18nLang = null;
let _seedWorkshop = null;  // assigned by the workshop IIFE; re-seed on language change
let _startupLogged = false;  // log "core initialized" once, after /stats resolves the language
function applyI18n() {
    document.documentElement.lang = appLang;
    const d = I18N[appLang] || I18N.en;
    lastI18nLang = appLang;
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const k = el.getAttribute('data-i18n'); if (d[k]) el.textContent = d[k];
    });
    document.querySelectorAll('[data-i18n-ph]').forEach(el => {
        const k = el.getAttribute('data-i18n-ph'); if (d[k]) el.placeholder = d[k];
    });
}

// Dynamic status / log strings (change with state).
const STR = {
    tr: {
        start: 'Başlamak için tıkla / Ctrl+Space', muted: 'Sessiz · Ctrl+Space ile aç',
        listening: 'Dinliyorum…', idleMuted: 'Boşta sessize alındı · Ctrl+Space ile aç',
        thinking: 'E.V. düşünüyor…', timeout: 'Yanıt gecikti, tekrar dene.',
        disconnected: 'Bağlantı koptu…', micPerm: 'Mikrofon izni gerekli. Adres çubuğundan izin ver.',
        micPrep: 'Mikrofon hazırlanıyor…', idleLog: 'Konuşma modu boşta kaldı, sessize alındı.',
        fsIn: 'Tam ekran algılandı, E.V. tepsiye çekildi.', fsOut: 'Tam ekran bitti, E.V. geri döndü.',
        yes: 'Evet', no: 'Hayır', egglog: 'atölye günlüğü', started: 'E.V. çekirdeği başlatıldı.',
    },
    en: {
        start: 'Click / Ctrl+Space to start', muted: 'Muted · press Ctrl+Space',
        listening: 'Listening…', idleMuted: 'Muted while idle · press Ctrl+Space',
        thinking: 'E.V. is thinking…', timeout: 'Response is late, try again.',
        disconnected: 'Connection lost…', micPerm: 'Microphone permission needed. Allow it from the address bar.',
        micPrep: 'Preparing the microphone…', idleLog: 'Conversation mode went idle, muted.',
        fsIn: 'Fullscreen detected, E.V. dropped to the tray.', fsOut: 'Fullscreen ended, E.V. is back.',
        yes: 'Yes', no: 'No', egglog: 'workshop log', started: 'E.V. core initialized.',
    },
};
const T = (k) => (STR[appLang] || STR.tr)[k] || '';

// Track "waiting for E.V." with a safety timeout so the UI never gets stuck.
function setAwaiting(v) {
    awaitingResponse = v;
    if (watchdog) { clearTimeout(watchdog); watchdog = null; }
    if (v) {
        watchdog = setTimeout(() => {
            awaitingResponse = false;
            status.textContent = T('timeout');
            resumeListening();
        }, 60000);
    }
}

// ---- Mic capture / VAD state ----
let micStream = null;
let audioCtx = null;
let analyser = null;
let mediaRecorder = null;
let recChunks = [];
let recording = false;
let lastVoiceTime = 0;
let recStartTime = 0;
let vadTimer = null;

// Tunable thresholds (energy on a 0..1 scale)
const START_THRESHOLD = 0.028;   // start recording above this
const KEEP_THRESHOLD = 0.020;    // keep recording above this
const SILENCE_MS = 1800;         // stop after this much trailing silence (lets you pause mid-sentence)
const MIN_RECORD_MS = 400;       // ignore ultra-short blips

function busy() {
    return isPlaying || ttsSpeaking || awaitingResponse;
}

// ---- Conversation mode: auto-mute after a stretch of silence ----
let lastActivity = Date.now();
const IDLE_MUTE_MS = 120000; // 2 min idle → auto-mute (safe during gaming)
function markActivity() { lastActivity = Date.now(); }

// Unlock audio + start mic on the first user interaction.
async function unlockAndInit() {
    if (!audioUnlocked) {
        audioUnlocked = true;
        try {
            const silent = new Audio('data:audio/mp3;base64,SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjU4Ljc2LjEwMAAAAAAAAAAAAAAA//tQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAABhgC7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7//////////////////////////////////////////////////////////////////8AAAAATGF2YzU4LjEzAAAAAAAAAAAAAAAAJAAAAAAAAAAAAYZNIGPkAAAAAAAAAAAAAAAAAAAA');
            silent.play().catch(() => {});
        } catch (e) {}
        await initMic();
    }
}
document.addEventListener('click', unlockAndInit);
document.addEventListener('keydown', unlockAndInit);

async function initMic() {
    if (micStream) return;
    try {
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
        status.textContent = T('micPerm');
        return;
    }
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === 'suspended') { try { await audioCtx.resume(); } catch (e) {} }
    const source = audioCtx.createMediaStreamSource(micStream);
    analyser = audioCtx.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);

    let mime = 'audio/webm;codecs=opus';
    if (!MediaRecorder.isTypeSupported(mime)) mime = 'audio/webm';
    if (!MediaRecorder.isTypeSupported(mime)) mime = '';
    mediaRecorder = new MediaRecorder(micStream, mime ? { mimeType: mime } : undefined);
    mediaRecorder.ondataavailable = (e) => { if (e.data && e.data.size > 0) recChunks.push(e.data); };
    mediaRecorder.onstop = onRecordingStopped;

    if (!vadTimer) vadTimer = setInterval(vadTick, 50);
    resumeListening();
}

function currentVolume() {
    if (!analyser) return 0;
    const buf = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) {
        const v = (buf[i] - 128) / 128;
        sum += v * v;
    }
    return Math.sqrt(sum / buf.length);
}

function vadTick() {
    if (!analyser) return;
    // Only record when listening is enabled and E.V. isn't speaking/thinking.
    if (busy() || !listeningEnabled) {
        if (recording) { try { mediaRecorder.stop(); } catch (e) {} recording = false; recChunks = []; }
        return;
    }
    const vol = currentVolume();
    const now = Date.now();

    if (!recording) {
        // Auto-mute if the conversation has gone quiet for a while.
        if (now - lastActivity > IDLE_MUTE_MS) {
            listeningEnabled = false;
            setOrbState('muted');
            status.textContent = T('idleMuted');
            logSys(T('idleLog'));
            return;
        }
        if (vol > START_THRESHOLD) {
            recChunks = [];
            recording = true;
            recStartTime = now;
            lastVoiceTime = now;
            try { mediaRecorder.start(); } catch (e) { recording = false; return; }
            setOrbState('listening');
        }
    } else {
        if (vol > KEEP_THRESHOLD) lastVoiceTime = now;
        if (now - lastVoiceTime > SILENCE_MS) {
            recording = false;
            try { mediaRecorder.stop(); } catch (e) {}
        }
    }
}

function onRecordingStopped() {
    const durationOk = (Date.now() - recStartTime) >= MIN_RECORD_MS;
    const blob = new Blob(recChunks, { type: 'audio/webm' });
    recChunks = [];
    if (!durationOk || blob.size < 1200) {
        if (!busy()) setOrbState('listening');
        return; // too short / probably noise
    }
    setOrbState('thinking');
    status.textContent = T('thinking');
    setAwaiting(true);
    markActivity();
    const reader = new FileReader();
    reader.onloadend = () => {
        const b64 = reader.result.split(',')[1];
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ audio: b64 }));
        }
    };
    reader.readAsDataURL(blob);
}

function connect() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = () => {
        console.log('[E.V.] WebSocket connected');
        // Reset any stale audio/playback state on (re)connect.
        isPlaying = false; ttsSpeaking = false; audioQueue = [];
        status.textContent = '';
        setOrbState('thinking');
        setAwaiting(true);
        ws.send(JSON.stringify({ text: 'Selam E.V.' }));
    };
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        markActivity();
        if (data.type === 'response') {
            addTranscript('ev', data.text);
            setAwaiting(false);
            if (data.audio && data.audio.length > 0) {
                queueAudio(data.audio);
            } else if (data.text && data.text.trim()) {
                speakBrowser(data.text);
            } else {
                resumeListening();
            }
        } else if (data.type === 'response_chunk') {
            setAwaiting(false);
            if (!currentEvDiv) {
                currentEvDiv = document.createElement('div');
                currentEvDiv.className = 'ev';
                transcript.appendChild(currentEvDiv);
            }
            currentEvDiv.textContent += (currentEvDiv.textContent ? ' ' : '') + data.text;
            transcript.scrollTop = transcript.scrollHeight;
            if (data.audio && data.audio.length > 0) queueAudio(data.audio);
        } else if (data.type === 'response_done') {
            currentEvDiv = null;
            setAwaiting(false);
            if (!isPlaying && !ttsSpeaking && audioQueue.length === 0) resumeListening();
        } else if (data.type === 'confirm') {
            // Destructive action awaiting a yes/no. Speak it + show quick buttons.
            setAwaiting(false);
            addConfirm(data.text);
            if (data.audio && data.audio.length > 0) queueAudio(data.audio);
            else if (data.text) speakBrowser(data.text);
            else resumeListening();
        } else if (data.type === 'sleep') {
            // Farewell: stop listening and stay muted (don't auto-resume).
            listeningEnabled = false;
            logSys(appLang === 'en' ? 'Going to sleep. Ctrl+Space to wake me.' : 'Uykuya geçiyorum. Ctrl+Space ile uyandır.');
        } else if (data.type === 'fullscreen') {
            handleFullscreen(data.active);
        } else if (data.type === 'user_text') {
            addTranscript('user', data.text);
        } else if (data.type === 'idle') {
            setAwaiting(false);
            resumeListening();
        } else if (data.type === 'status') {
            status.textContent = data.text;
        }
    };
    ws.onclose = () => {
        status.textContent = T('disconnected');
        setTimeout(connect, 3000);
    };
}

// Auto-tray E.V. while a fullscreen app (game / video) is running, restore after.
let hiddenByFullscreen = false;
function handleFullscreen(active) {
    if (!isElectron || !window.electronAPI) return;
    if (active) {
        // Don't fight the fullscreen app: stop listening and drop to the tray.
        if (listeningEnabled) { listeningEnabled = false; setOrbState('muted'); }
        window.electronAPI.hide();
        hiddenByFullscreen = true;
        logSys(T('fsIn'));
    } else if (hiddenByFullscreen) {
        window.electronAPI.show();
        hiddenByFullscreen = false;
        logSys(T('fsOut'));
    }
}

function resumeListening() {
    if (busy()) return;
    if (listeningEnabled && analyser) {
        setOrbState('listening');
        status.textContent = T('listening');
    } else {
        setOrbState(analyser ? 'muted' : 'idle');
        status.textContent = analyser ? T('muted') : T('start');
    }
}

// ---- ElevenLabs audio playback (kept for optional use) ----
function queueAudio(base64Audio) {
    audioQueue.push(base64Audio);
    if (!isPlaying) playNext();
}
function playNext() {
    if (audioQueue.length === 0) {
        isPlaying = false;
        resumeListening();
        return;
    }
    isPlaying = true;
    setOrbState('speaking');
    const b64 = audioQueue.shift();
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: 'audio/mpeg' }));
    const audio = new Audio(url);
    currentAudio = audio;
    hookOutputAnalyser(audio);  // let the visualizer react to E.V.'s voice
    audio.onended = () => { URL.revokeObjectURL(url); playNext(); };
    audio.onerror = () => { URL.revokeObjectURL(url); playNext(); };
    audio.play().catch(() => { isPlaying = false; resumeListening(); });
}

// Stop everything E.V. is saying/doing right now (barge-in on output).
function stopEverything() {
    audioQueue = [];
    if (currentAudio) { try { currentAudio.pause(); } catch (e) {} currentAudio = null; }
    try { window.speechSynthesis.cancel(); } catch (e) {}
    isPlaying = false; ttsSpeaking = false;
    currentEvDiv = null;
    setAwaiting(false);
    logSys(appLang === 'en' ? 'Stopped.' : 'Durduruldu.');
    resumeListening();
}

// ---- Free, key-less browser TTS (Turkish) ----
function pickVoice() {
    const voices = window.speechSynthesis.getVoices() || [];
    const prefix = appLang === 'en' ? 'en' : 'tr';
    const cand = voices.filter(v => v.lang && v.lang.toLowerCase().startsWith(prefix));
    if (cand.length === 0) return null;
    // Prefer higher-quality neural / online voices.
    return cand.find(v => /natural|neural|online/i.test(v.name)) || cand[0];
}
// Log available Turkish voices to the console (helps pick the best one).
if ('speechSynthesis' in window) {
    window.speechSynthesis.addEventListener('voiceschanged', () => {
        const tr = (window.speechSynthesis.getVoices() || []).filter(v => v.lang && v.lang.toLowerCase().startsWith('tr'));
        if (tr.length) console.log('[E.V.] Turkish voices:', tr.map(v => v.name).join(' | '));
    });
}
function speakBrowser(text) {
    if (!('speechSynthesis' in window)) { resumeListening(); return; }
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = appLang === 'en' ? 'en-US' : 'tr-TR';
    const v = pickVoice();
    if (v) u.voice = v;
    u.rate = 1.0;
    u.pitch = 1.0;
    ttsSpeaking = true;
    setOrbState('speaking');
    status.textContent = '';
    u.onend = () => { ttsSpeaking = false; resumeListening(); };
    u.onerror = () => { ttsSpeaking = false; resumeListening(); };
    window.speechSynthesis.speak(u);
}
if ('speechSynthesis' in window) {
    window.speechSynthesis.onvoiceschanged = pickVoice;
}

vizCanvas.addEventListener('click', () => { toggleListen(); });

async function toggleListen() {
    await unlockAndInit();
    if (!analyser) { status.textContent = T('micPrep'); return; }
    listeningEnabled = !listeningEnabled;
    if (listeningEnabled) {
        markActivity();
        if (!busy()) { setOrbState('listening'); status.textContent = T('listening'); }
    } else {
        if (recording) { try { mediaRecorder.stop(); } catch (e) {} recording = false; recChunks = []; }
        setOrbState('muted');
        status.textContent = T('muted');
    }
}

// ---- Mode (compact orb vs full dashboard) ----
const isElectron = !!(window.electronAPI && window.electronAPI.isElectron);
if (isElectron) document.body.classList.add('electron');
const startCompact = new URLSearchParams(location.search).has('hud');

function setMode(mode) {
    document.body.classList.toggle('compact', mode === 'compact');
    document.body.classList.toggle('dashboard', mode === 'dashboard');
    if (isElectron && window.electronAPI.setMode) window.electronAPI.setMode(mode);
}
setMode(startCompact ? 'compact' : 'dashboard');

// ---- Clock ----
function updateClock() {
    const now = new Date();
    const t = document.getElementById('clock-time');
    const d = document.getElementById('clock-date');
    const loc = appLang === 'en' ? 'en-US' : 'tr-TR';
    if (t) t.textContent = now.toLocaleTimeString(loc, { hour: '2-digit', minute: '2-digit' });
    if (d) d.textContent = now.toLocaleDateString(loc, { weekday: 'long', day: 'numeric', month: 'long' });
}
setInterval(updateClock, 1000);
updateClock();

// ---- System stats + weather ----
function setBar(id, v) {
    const bar = document.getElementById('bar-' + id);
    const val = document.getElementById('val-' + id);
    if (bar) bar.style.width = Math.max(0, Math.min(100, v)) + '%';
    if (val) val.textContent = v + '%';
}
function setText(id, txt) { const el = document.getElementById(id); if (el) el.textContent = txt; }
async function pollStats() {
    try {
        const s = await (await fetch('/stats')).json();
        if (s.language && !_langOverride) appLang = s.language;
        if (appLang !== lastI18nLang) {  // language resolved/changed → re-render UI text
            applyI18n();
            if (_seedWorkshop) _seedWorkshop();  // regenerate flavor lines in the right language
        }
        if (!_startupLogged) { _startupLogged = true; logSys(T('started')); }
        setBar('cpu', s.cpu); setBar('ram', s.ram); setBar('disk', s.disk);
        setText('s-ram', s.ram_used_gb + '/' + s.ram_total_gb + ' GB');
        setText('s-disk', s.disk_free_gb + ' GB');
        setText('w-city', s.city || '');
        const dl = document.getElementById('lbl-disk');
        if (dl) dl.textContent = (appLang === 'en' ? 'FREE (' : 'BOŞ (') + (s.disk_drive || '—') + ')';
        if (s.modules) {
            setText('m-stt', s.modules.stt); setText('m-brain', s.modules.brain);
            setText('m-voice', s.modules.voice); setText('m-gpu', s.modules.gpu);
        }
        if (s.weather) {
            setText('w-temp', s.weather.temp + '°');
            setText('w-desc', s.weather.description);
            setText('w-wind', s.weather.wind_kmh + (appLang === 'en' ? ' km/h' : ' km/s'));
        } else {
            setText('w-desc', appLang === 'en' ? 'no weather' : 'hava yok');
            setText('w-wind', '—');
        }
    } catch (e) {}
}
setInterval(pollStats, 2500);
pollStats();

// ---- Text input ----
const STOP_WORDS = /^(dur|durdur|dursana|kes|sus|stop|shut up|be quiet|cancel)\.?$/i;
function sendText() {
    const input = document.getElementById('text-input');
    if (!input) return;
    const txt = input.value.trim();
    if (!txt) return;
    input.value = '';
    if (STOP_WORDS.test(txt)) { stopEverything(); return; }  // local stop, don't send
    addTranscript('user', txt);
    setOrbState('thinking');
    status.textContent = T('thinking');
    setAwaiting(true);
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ text: txt }));
}

// ---- Button wiring ----
function wire(id, fn) { const el = document.getElementById(id); if (el) el.addEventListener('click', fn); }
wire('btn-expand', () => setMode('dashboard'));
wire('btn-compact', () => setMode('compact'));
wire('mic-btn', () => toggleListen());
wire('stop-btn', stopEverything);
wire('send-btn', sendText);
const ti = document.getElementById('text-input');
if (ti) ti.addEventListener('keydown', (e) => { if (e.key === 'Enter') sendText(); });
// Esc anywhere = stop E.V. immediately.
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') stopEverything(); });

if (isElectron) {
    window.electronAPI.onToggleListen(() => toggleListen());
    wire('btn-quit', () => window.electronAPI.quit());
    wire('btn-hide', () => window.electronAPI.hide());
}

const STATUS_LABEL = {
    tr: { idle: 'ONLINE', muted: 'SESSİZ', listening: 'DİNLİYOR', thinking: 'İŞLİYOR', speaking: 'KONUŞUYOR' },
    en: { idle: 'ONLINE', muted: 'MUTED', listening: 'LISTENING', thinking: 'PROCESSING', speaking: 'SPEAKING' },
};
function setOrbState(state) {
    orbState = state;
    const cs = document.getElementById('core-state');
    const lbl = STATUS_LABEL[appLang] || STATUS_LABEL.tr;
    if (cs) cs.textContent = lbl[state] || 'ONLINE';
    const mic = document.getElementById('mic-btn');
    if (mic) mic.classList.toggle('on', state === 'listening');
}

function addTranscript(role, text) {
    const div = document.createElement('div');
    div.className = role;
    div.textContent = text;
    transcript.appendChild(div);
    transcript.scrollTop = transcript.scrollHeight;
}

function sendConfirm(approved) {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ confirm: approved }));
}

function addConfirm(text) {
    const div = document.createElement('div');
    div.className = 'ev confirm';
    div.textContent = text + '  ';
    const yes = document.createElement('button');
    yes.className = 'confirm-btn yes'; yes.textContent = T('yes');
    const no = document.createElement('button');
    no.className = 'confirm-btn no'; no.textContent = T('no');
    const done = (v) => { yes.disabled = no.disabled = true; sendConfirm(v); };
    yes.addEventListener('click', () => done(true));
    no.addEventListener('click', () => done(false));
    div.appendChild(yes); div.appendChild(no);
    transcript.appendChild(div);
    transcript.scrollTop = transcript.scrollHeight;
}

function logSys(text) {
    const t = new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const div = document.createElement('div');
    div.className = 'sys';
    div.textContent = `[${t}] ${text}`;
    transcript.appendChild(div);
    transcript.scrollTop = transcript.scrollHeight;
}

// ---- Center audio-core visualizer (circular waveform) ----
const vctx = vizCanvas.getContext('2d');
let outCtx = null, outAnalyser = null;
function hookOutputAnalyser(audioEl) {
    try {
        if (!outCtx) {
            outCtx = new (window.AudioContext || window.webkitAudioContext)();
            outAnalyser = outCtx.createAnalyser();
            outAnalyser.fftSize = 1024;
            outAnalyser.connect(outCtx.destination);
        }
        if (outCtx.state === 'suspended') outCtx.resume();
        const src = outCtx.createMediaElementSource(audioEl);
        src.connect(outAnalyser);
    } catch (e) {}
}

function resizeViz() {
    const r = vizCanvas.getBoundingClientRect();
    vizCanvas.width = Math.max(1, Math.round(r.width * devicePixelRatio));
    vizCanvas.height = Math.max(1, Math.round(r.height * devicePixelRatio));
}
window.addEventListener('resize', resizeViz);

const VIZ_COLOR = { idle: '#00e5ff', muted: '#5a7183', listening: '#00ff66', thinking: '#ffb020', speaking: '#00e5ff' };
let vizT = 0;
function drawViz() {
    requestAnimationFrame(drawViz);
    if (vizCanvas.width < 2) resizeViz();
    const w = vizCanvas.width, h = vizCanvas.height, cx = w / 2, cy = h / 2;
    vctx.clearRect(0, 0, w, h);
    const col = VIZ_COLOR[orbState] || '#00e5ff';
    const R = Math.min(w, h) * 0.28;

    // pick a live audio source: mic while listening, E.V.'s voice while speaking
    let data = null;
    if (orbState === 'listening' && analyser) { data = new Uint8Array(analyser.fftSize); analyser.getByteTimeDomainData(data); }
    else if (orbState === 'speaking' && outAnalyser) { data = new Uint8Array(outAnalyser.fftSize); outAnalyser.getByteTimeDomainData(data); }

    // outer decorative rings
    vctx.strokeStyle = 'rgba(0,229,255,0.12)';
    vctx.lineWidth = 1;
    for (const m of [1.55, 1.85]) { vctx.beginPath(); vctx.arc(cx, cy, R * m, 0, Math.PI * 2); vctx.stroke(); }

    // circular waveform
    vctx.beginPath();
    vctx.lineWidth = Math.max(1.5, w * 0.0035);
    vctx.strokeStyle = col;
    vctx.shadowBlur = 16; vctx.shadowColor = col;
    const N = 160;
    for (let i = 0; i <= N; i++) {
        const ang = (i / N) * Math.PI * 2 - Math.PI / 2;
        let amp;
        if (data) { amp = (data[Math.floor(i / N * (data.length - 1))] - 128) / 128; }
        else {
            const gain = orbState === 'thinking' ? 0.14 : (orbState === 'muted' ? 0.03 : 0.07);
            amp = Math.sin(i * 0.4 + vizT) * gain + Math.sin(i * 0.13 - vizT * 1.7) * gain * 0.5;
        }
        const rr = R + amp * R * 0.7;
        const x = cx + Math.cos(ang) * rr, y = cy + Math.sin(ang) * rr;
        i === 0 ? vctx.moveTo(x, y) : vctx.lineTo(x, y);
    }
    vctx.closePath(); vctx.stroke();

    // glowing core
    vctx.shadowBlur = 30;
    vctx.fillStyle = col + '22';
    vctx.beginPath(); vctx.arc(cx, cy, R * 0.55, 0, Math.PI * 2); vctx.fill();
    vctx.shadowBlur = 0;

    vizT += orbState === 'speaking' ? 0.22 : (orbState === 'thinking' ? 0.16 : 0.04);
}
resizeViz();
drawViz();

// ---- Scrolling code strip (decorative) ----
(function () {
    const el = document.getElementById('code-line');
    if (!el) return;
    const bits = ['0x1A3F', 'EV.core.tick()', 'stt=whisper.ok', 'gemma2:9b>gpu', 'tts=voice.ready', 'vram=100%', 'ws://8340', 'audio.sync', 'env.load', 'core.stable'];
    let s = '';
    for (let i = 0; i < 24; i++) s += bits[Math.floor(Math.random() * bits.length)] + '   ';
    el.textContent = s + s; // doubled for seamless scroll
})();

// ---- Workshop terminal log (left panel; original Brand New Day flavor) ----
const hhmm = () => new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
(function () {
    const box = document.getElementById('workshop');
    if (!box) return;
    const POOLS = {
        tr: [
            ['doku birimi', 'kalibrasyon bekliyor'], ['lehim', '340°C, hazır'],
            ['kahve', 'kritik seviye'], ['sırt çantası', 'tornavida + notlar'],
            ['çatı katı', 'esinti geliyor'], ['eski radyo', 'parazit arasında bir çağrı'],
            ['3 blok öte', 'siren dinleniyor'], ['not', "'büyük güç…' (karalanmış)"],
            ['devre kartı', 'lehim soğuyor'], ['batarya', '%86, şarj oluyor'],
            ['gece nöbeti', 'gündem sakin'], ['eskiz', 'yeni tasarım karalandı'],
            ['multimetre', 'iade bekliyor'], ['maske', 'onarım listesinde'],
            ['pencere', 'aralık bırakıldı'], ['sensör dizisi', 'yeşil'],
            ['şehir', 'nefes alıyor'], ['fizik ödevi', 'yarına ertelendi'],
        ],
        en: [
            ['fabricator', 'awaiting calibration'], ['solder', '340°C, ready'],
            ['coffee', 'critical level'], ['backpack', 'screwdriver + notes'],
            ['rooftop', 'a breeze rolling in'], ['old radio', 'a call through static'],
            ['3 blocks over', 'siren, listening'], ['note', "'great power…' (scribbled)"],
            ['circuit board', 'solder cooling'], ['battery', '86%, charging'],
            ['night watch', 'all quiet'], ['sketch', 'new design roughed out'],
            ['multimeter', 'still borrowed'], ['mask', 'on the repair list'],
            ['window', 'left ajar'], ['sensor array', 'green'],
            ['the city', 'breathing'], ['physics homework', 'put off till tomorrow'],
        ],
    };
    function append() {
        const POOL = POOLS[appLang] || POOLS.tr;
        const [tag, txt] = POOL[Math.floor(Math.random() * POOL.length)];
        const line = document.createElement('span');
        line.className = 'wl';
        line.innerHTML = `<span class="wt">${hhmm()}</span><span class="tag">${tag}</span> ›› ${txt}`;
        box.appendChild(line);
        while (box.children.length > 30) box.removeChild(box.firstChild);
        box.scrollTop = box.scrollHeight;
    }
    _seedWorkshop = function () { box.innerHTML = ''; for (let i = 0; i < 6; i++) append(); };
    _seedWorkshop();
    setInterval(append, 3500);
})();

// ---- E.V.'s ambient "thoughts" in the right-side log ----
const THOUGHTS = {
    tr: [
        'Sistemler sakin. Bu iyi bir şey.', 'Bazen en iyi tasarım en basit olandır.',
        'Bir fikir belirdi, sonra kayboldu. Geri gelir.', 'Dışarısı sessiz; odaklanmak için güzel.',
        'Kahveni içmeyi unutma.', 'Küçük onarımlar büyük fark yaratır.',
        'Bugün ne inşa edeceğiz, merak ediyorum.', 'Sabırlı ol; iyi şeyler zaman alır.',
        'Bir sorun, çözülmeyi bekleyen bir bulmacadır.', 'Buradayım, gerektiğinde.',
        'Gürültüyü kısıp asıl işe dönmek iyi geliyor.', 'Her şeyi değil, sadece bir sonraki adımı düşün.',
    ],
    en: [
        'Systems are calm. That is a good thing.', 'Sometimes the simplest design is the best one.',
        'An idea flickered, then faded. It will come back.', "It's quiet out there — good for focus.",
        "Don't forget to drink your coffee.", 'Small repairs make a big difference.',
        'I wonder what we will build today.', 'Be patient; good things take time.',
        'A problem is just a puzzle waiting to be solved.', "I'm here, whenever you need me.",
    ],
};
function maybeThink() {
    if (busy() || currentEvDiv) return;            // never interrupt a real exchange
    const pool = THOUGHTS[appLang] || THOUGHTS.tr;
    addTranscript('thought', pool[Math.floor(Math.random() * pool.length)]);
}
setTimeout(() => { maybeThink(); setInterval(maybeThink, 45000); }, 12000);

// ---- Hidden easter egg: tap "E.V. CORE" three times → cycles through log entries ----
(function () {
    const el = document.querySelector('.core-name');
    if (!el) return;
    const EGGS = {
        tr: [
            "'çatıdan şehir güzel görünüyor.'", "'lehim kokusu... ev gibi.'",
            "'bir tasarım daha, bir gece daha.'", "'sessizlik, en sevdiğim frekans.'",
            "'not defterinin üçüncü sayfası hâlâ boş. yakında.'",
            "'bazı kahramanların pelerini yoktur; benim ekranım var.'",
            "'devriye sakin. iyi.'",
        ],
        en: [
            "'the city looks good from the rooftop.'", "'smell of solder... feels like home.'",
            "'one more design, one more night.'", "'silence, my favorite frequency.'",
            "'page three of the notebook is still blank. soon.'",
            "'some heroes don't have capes; I have a screen.'",
            "'patrol is quiet. good.'",
        ],
    };
    let n = 0, t = 0, egg = 0;
    el.addEventListener('click', () => {
        const now = Date.now();
        n = (now - t < 800) ? n + 1 : 1;
        t = now;
        if (n >= 3) {
            n = 0; egg++;
            const pool = EGGS[appLang] || EGGS.tr;
            const num = String(egg).padStart(3, '0');
            logSys(`E.V. ›› ${T('egglog')} #${num}: ${pool[(egg - 1) % pool.length]}`);
        }
    });
})();

applyI18n();  // apply immediately for ?lang override; pollStats re-applies for server config
// "core initialized" is logged from pollStats once /stats resolves the language,
// so it isn't printed in the wrong language before the server config is known.
connect();
