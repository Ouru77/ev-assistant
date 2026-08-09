const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,
  quit: () => ipcRenderer.send('quit'),
  hide: () => ipcRenderer.send('hide'),
  setMode: (mode) => ipcRenderer.send('set-mode', mode),
  onToggleListen: (cb) => ipcRenderer.on('toggle-listen', () => cb()),
});
