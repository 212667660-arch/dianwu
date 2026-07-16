const { contextBridge, ipcRenderer, webUtils } = require('electron')

contextBridge.exposeInMainWorld('a3Desktop', Object.freeze({
  request: (input) => ipcRenderer.invoke('a3:api-request', input),
  modelConfigTest: (input) => ipcRenderer.invoke('a3:model-config-test', input),
  modelConfigSave: (input) => ipcRenderer.invoke('a3:model-config-save', input),
  modelProfilesList: () => ipcRenderer.invoke('a3:model-profiles-list'),
  modelProfileTest: (input) => ipcRenderer.invoke('a3:model-profile-test', input),
  modelProfileUpsert: (input) => ipcRenderer.invoke('a3:model-profile-upsert', input),
  modelProfileDelete: (id) => ipcRenderer.invoke('a3:model-profile-delete', id),
  modelProfilePolicySave: (input) => ipcRenderer.invoke('a3:model-profile-policy-save', input),
  modelRuntimeStatus: () => ipcRenderer.invoke('a3:model-runtime-status'),
  knowledgeChooseFiles: (collectionId) => ipcRenderer.invoke('a3:knowledge-choose-files', collectionId),
  knowledgeImportDroppedFiles: (files, collectionId) => {
    const paths = Array.from(files || [], file => webUtils.getPathForFile(file))
    return ipcRenderer.invoke('a3:knowledge-import-dropped-files', { collectionId, paths })
  },
  knowledgeRevealSource: (documentId) => ipcRenderer.invoke('a3:knowledge-reveal-source', documentId),
  knowledgeOpenSource: (documentId, locator) => ipcRenderer.invoke('a3:knowledge-open-source', { documentId, locator }),
  knowledgeOnImportProgress: (listener) => {
    const callback = (_event, payload) => listener(payload)
    ipcRenderer.on('a3:knowledge-import-progress', callback)
    return () => ipcRenderer.removeListener('a3:knowledge-import-progress', callback)
  },
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
