const { app, BrowserWindow, globalShortcut, ipcMain, Tray, Menu, screen } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

const PROJECT = path.join(__dirname, '..');
const PY = path.join(PROJECT, '.venv', 'Scripts', 'python.exe');
const SERVER_URL = 'http://localhost:8340';

let win = null;
let tray = null;
let serverProc = null;

function ping(url) {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => { res.resume(); resolve(true); });
    req.on('error', () => resolve(false));
    req.setTimeout(1500, () => { req.destroy(); resolve(false); });
  });
}

async function ensureServer() {
  if (await ping(SERVER_URL)) return; // already running
  serverProc = spawn(PY, ['server.py'], {
    cwd: PROJECT,
    env: Object.assign({}, process.env, {
      OLLAMA_MODELS: 'A:\\AI\\ollama\\models',
      PLAYWRIGHT_BROWSERS_PATH: 'A:\\AI\\ms-playwright',
    }),
    windowsHide: true,
  });
  serverProc.stdout.on('data', (d) => process.stdout.write('[server] ' + d));
  serverProc.stderr.on('data', (d) => process.stdout.write('[server] ' + d));
  for (let i = 0; i < 90; i++) {
    if (await ping(SERVER_URL)) return;
    await new Promise((r) => setTimeout(r, 1000));
  }
}

function createWindow() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;
  const W = 380, H = 560;
  win = new BrowserWindow({
    width: W,
    height: H,
    x: width - W - 24,
    y: height - H - 24,
    frame: false,
    transparent: true,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: false,
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      autoplayPolicy: 'no-user-gesture-required',
    },
  });
  // Allow microphone (local personal app).
  win.webContents.session.setPermissionRequestHandler((wc, permission, callback) => {
    callback(true);
  });
  win.setAlwaysOnTop(true, 'screen-saver');
  win.loadURL(SERVER_URL + '/?hud=1');
}

const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) app.quit();
app.on('second-instance', () => {
  if (win) { if (win.isMinimized()) win.restore(); win.show(); win.focus(); }
});

app.whenReady().then(async () => {
  if (!gotTheLock) return;
  await ensureServer();
  createWindow();

  globalShortcut.register('Control+Space', () => {
    if (win) win.webContents.send('toggle-listen');
  });

  try {
    tray = new Tray(path.join(__dirname, 'icon.png'));
    const menu = Menu.buildFromTemplate([
      { label: 'Dinle Aç/Kapat (Ctrl+Space)', click: () => win && win.webContents.send('toggle-listen') },
      { label: 'Göster / Gizle', click: () => { if (!win) return; win.isVisible() ? win.hide() : win.show(); } },
      { type: 'separator' },
      { label: 'Çıkış', click: () => app.quit() },
    ]);
    tray.setToolTip('E.V.');
    tray.setContextMenu(menu);
    tray.on('click', () => { if (win) { win.isVisible() ? win.hide() : win.show(); } });
  } catch (e) {
    console.log('Tray kurulamadı:', e.message);
  }
});

const COMPACT = { w: 380, h: 560 };
ipcMain.on('set-mode', (e, mode) => {
  if (!win) return;
  if (mode === 'dashboard') {
    win.setAlwaysOnTop(false);
    win.setResizable(true);
    win.maximize();
  } else {
    win.unmaximize();
    win.setResizable(false);
    const { width, height } = screen.getPrimaryDisplay().workAreaSize;
    win.setBounds({ x: width - COMPACT.w - 24, y: height - COMPACT.h - 24, width: COMPACT.w, height: COMPACT.h });
    win.setAlwaysOnTop(true, 'screen-saver');
  }
});

ipcMain.on('quit', () => app.quit());
ipcMain.on('hide', () => { if (win) win.hide(); });
// Show without stealing focus from the app the user is in.
ipcMain.on('show', () => { if (win) win.showInactive(); });

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
  if (serverProc && !serverProc.killed) {
    try { serverProc.kill(); } catch (e) {}
  }
});

app.on('window-all-closed', () => app.quit());
