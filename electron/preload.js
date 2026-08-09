const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,
  quit: () => ipcRenderer.send('quit'),
  hide: () => ipcRenderer.send('hide'),
  show: () => ipcRenderer.send('show'),
  setMode: (mode) => ipcRenderer.send('set-mode', mode),
  onToggleListen: (cb) => ipcRenderer.on('toggle-listen', () => cb()),
});
