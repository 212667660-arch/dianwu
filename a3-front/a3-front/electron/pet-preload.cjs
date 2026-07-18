const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('a3Pet', Object.freeze({
  ready: () => ipcRenderer.invoke('a3:pet-ready'),
  beginDrag: point => ipcRenderer.send('a3:pet-drag-begin', point),
  moveDrag: point => ipcRenderer.send('a3:pet-drag-move', point),
  endDrag: () => ipcRenderer.send('a3:pet-drag-end'),
  beginResize: input => ipcRenderer.send('a3:pet-resize-begin', input),
  moveResize: point => ipcRenderer.send('a3:pet-resize-move', point),
  endResize: () => ipcRenderer.send('a3:pet-resize-end'),
  onState: listener => {
    const callback = (_event, payload) => listener(payload)
    ipcRenderer.on('a3:pet-state', callback)
    return () => ipcRenderer.removeListener('a3:pet-state', callback)
  },
  onSettings: listener => {
    const callback = (_event, payload) => listener(payload)
    ipcRenderer.on('a3:pet-settings', callback)
    return () => ipcRenderer.removeListener('a3:pet-settings', callback)
  },
}))
