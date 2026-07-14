import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('a3Desktop', Object.freeze({
  request: (input) => ipcRenderer.invoke('a3:api-request', input),
  modelConfigTest: (input) => ipcRenderer.invoke('a3:model-config-test', input),
  modelConfigSave: (input) => ipcRenderer.invoke('a3:model-config-save', input),
  startStream: (streamId, input) => ipcRenderer.send('a3:stream-start', streamId, input),
  cancelStream: (streamId) => ipcRenderer.send('a3:stream-cancel', streamId),
  onStreamEvent: (listener) => {
    const callback = (_event, message) => listener(message)
    ipcRenderer.on('a3:stream-event', callback)
    return () => ipcRenderer.removeListener('a3:stream-event', callback)
  },
  onBackendExit: (listener) => {
    const callback = (_event, payload) => listener(payload)
    ipcRenderer.on('a3:backend-exited', callback)
    return () => ipcRenderer.removeListener('a3:backend-exited', callback)
  },
}))
