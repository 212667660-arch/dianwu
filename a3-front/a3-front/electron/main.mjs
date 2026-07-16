import { app, BrowserWindow, dialog, ipcMain, nativeImage, safeStorage, screen, shell } from 'electron'
import { spawn } from 'node:child_process'
import crypto from 'node:crypto'
import fs from 'node:fs/promises'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { awaitBackendStartup, shouldNotifyBackendExit, stopBackendProcess } from './backend-lifecycle.mjs'
import { createBackendProxy } from './backend-proxy.mjs'
import {
  desktopError,
  isTrustedDesktopSender,
  validateKnowledgeCollectionId,
  validateKnowledgeDroppedPaths,
  validateKnowledgeLocator,
  validateModelConfigInput,
  validateModelProfileId,
  validateModelProfileInput,
  validateModelProfilePolicyInput,
  validatePetSettingsInput,
  validatePetTaskStateInput,
} from './ipc-contract.mjs'
import { createKnowledgeImporter } from './knowledge-import.mjs'
import { createKnowledgeController } from './knowledge-controller.mjs'
import { createModelConfigStore, sanitizeModelEnvironment } from './model-config.mjs'
import { createModelProfileVault } from './model-profile-vault.mjs'
import { createModelProfileController } from './model-profile-controller.mjs'
import { createPetController } from './pet-controller.mjs'
import { createPetCharacterImporter, validatePetAtlasBitmap } from './pet-character-import.mjs'
import { backendCommand, electronUserDataPath, navigationAction } from './runtime.mjs'

const mainDir = path.dirname(fileURLToPath(import.meta.url))
const projectDir = path.resolve(mainDir, '..')

app.setName('智学协作台')
app.setPath('userData', electronUserDataPath({
  appData: app.getPath('appData'),
  testMode: process.env.A3_ELECTRON_TEST_MODE === '1',
  override: process.env.A3_ELECTRON_USER_DATA_DIR,
}))

let mainWindow = null
let backendProcess = null
let backendRuntime = null
let backendProxy = null
let isQuitting = false

const petController = createPetController({
  BrowserWindow,
  screen,
  fs,
  userDataDir: app.getPath('userData'),
  packagedPetDir: path.join(mainDir, 'pets', 'motuan'),
  petIndex: path.join(mainDir, 'pet', 'index.html'),
  petPreload: path.join(mainDir, 'pet-preload.cjs'),
  pathToFileURL,
})
const petCharacterImporter = createPetCharacterImporter({
  fs,
  userDataDir: app.getPath('userData'),
  inspectAtlas: inspectPetAtlas,
})

const modelConfigStore = createModelConfigStore({
  safeStorage,
  filePath: path.join(app.getPath('userData'), 'model-settings.enc'),
})
const modelProfileVault = createModelProfileVault({
  safeStorage,
  filePath: path.join(app.getPath('userData'), 'model-profiles.enc'),
  legacyStore: modelConfigStore,
})
const knowledgeImporter = createKnowledgeImporter({ userDataDir: app.getPath('userData') })
const knowledgeController = createKnowledgeController({
  chooseFiles: async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title: '选择要放进知识库的资料',
      properties: ['openFile', 'multiSelections'],
      filters: [{
        name: '学习资料',
        extensions: ['pdf', 'docx', 'pptx', 'xlsx', 'txt', 'md', 'markdown', 'csv'],
      }],
    })
    return result.canceled ? [] : result.filePaths
  },
  importer: knowledgeImporter,
  apiRequest: (input, event) => backendProxy?.request(event, input) ?? ({
    ok: false,
    status: 503,
    error: desktopError('DESKTOP_BACKEND_UNAVAILABLE', '本地学习服务暂时不可用，请稍后重试。', true),
  }),
  validateSender: event => trustedKnowledgeSender(event),
  previewRoot: path.join(app.getPath('userData'), 'knowledge-preview'),
  openPath: filePath => shell.openPath(filePath),
  showItemInFolder: filePath => shell.showItemInFolder(filePath),
  onProgress: jobs => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('a3:knowledge-import-progress', jobs)
    }
  },
})
const modelProfileController = createModelProfileController({
  validateSender: event => trustedKnowledgeSender(event),
  vault: modelProfileVault,
  testProfile: profile => internalRuntimeRequest('POST', '/internal/model-runtime/test', profile),
  bootstrapSnapshot: snapshot => internalRuntimeRequest('POST', '/internal/model-runtime/bootstrap', snapshot, true),
  applySnapshot: snapshot => internalRuntimeRequest('PUT', '/internal/model-runtime/snapshot', snapshot, true),
  runtimeStatus: () => internalRuntimeRequest('GET', '/internal/model-runtime/status', undefined, true),
  log: entry => log(`model profile ${entry.event}${entry.code ? `: ${entry.code}` : ''}`),
})

async function internalRuntimeRequest(method, route, body, raw = false) {
  if (!backendRuntime) throw Object.assign(new Error('Backend runtime unavailable.'), { code: 'DESKTOP_BACKEND_UNAVAILABLE' })
  const response = await fetch(new URL(route, `${backendRuntime.baseUrl}/`), {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-A3-Desktop-Token': backendRuntime.token,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const value = await response.json().catch(() => null)
  if (!response.ok) throw Object.assign(new Error('Model runtime request failed.'), { code: value?.code || 'MODEL_RUNTIME_APPLY_FAILED' })
  return raw ? value : { ok: true, status: response.status, data: value }
}

function electronLogPath() {
  return path.join(app.getPath('userData'), 'logs', 'electron.log')
}

async function log(message) {
  await fs.mkdir(path.dirname(electronLogPath()), { recursive: true })
  await fs.appendFile(electronLogPath(), `${new Date().toISOString()} ${message}\n`, 'utf8')
}

async function reservePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.unref()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      const port = typeof address === 'object' && address ? address.port : null
      server.close((error) => error ? reject(error) : resolve(port))
    })
  })
}

async function waitForBackend(baseUrl) {
  const timeoutAt = Date.now() + 20_000
  let lastError = '后端尚未响应。'
  while (Date.now() < timeoutAt) {
    try {
      const response = await fetch(`${baseUrl}/health/live`)
      if (response.ok) return
      lastError = `后端未就绪（${response.status}）。`
    } catch (error) {
      lastError = error instanceof Error ? error.message : '后端连接失败。'
    }
    await new Promise(resolve => setTimeout(resolve, 300))
  }
  throw new Error(lastError)
}

async function startBackend() {
  const port = await reservePort()
  const token = crypto.randomBytes(32).toString('base64url')
  const command = backendCommand({
    isPackaged: app.isPackaged,
    projectDir,
    resourcesPath: process.resourcesPath,
    userDataDir: app.getPath('userData'),
  })
  await fs.mkdir(command.dataDir, { recursive: true })
  if (!await fs.stat(command.command).then(() => true).catch(() => false)) {
    throw new Error(`找不到后端启动文件：${command.command}`)
  }

  const baseUrl = `http://127.0.0.1:${port}`
  const runningProcess = spawn(command.command, command.args, {
    cwd: command.cwd,
    env: {
      ...sanitizeModelEnvironment(process.env),
      A3_HOST: '127.0.0.1',
      A3_PORT: String(port),
      A3_DATA_DIR: command.dataDir,
      A3_KNOWLEDGE_DIR: knowledgeImporter.knowledgeRoot,
      DESKTOP_TOKEN: token,
      APP_ENV: app.isPackaged ? 'production' : 'development',
      CORS_ORIGINS: 'null,http://127.0.0.1:5173',
    },
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  backendProcess = runningProcess
  runningProcess.stdout?.on('data', data => log(`backend stdout: ${String(data).trim().slice(0, 500)}`))
  runningProcess.stderr?.on('data', data => log(`backend stderr: ${String(data).trim().slice(0, 500)}`))
  runningProcess.on('error', error => log(`backend process error: ${error.message}`))
  runningProcess.once('exit', (code) => {
    log(`backend exited with code ${code ?? 'unknown'}`)
    const notifyRenderer = shouldNotifyBackendExit(backendProcess, runningProcess, isQuitting)
    if (backendProcess === runningProcess) {
      backendProxy?.cleanupAll()
      backendRuntime = null
      backendProcess = null
    }
    if (notifyRenderer && mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send('a3:backend-exited', { code })
  })
  try {
    await awaitBackendStartup(runningProcess, () => waitForBackend(baseUrl))
  } catch (error) {
    if (backendProcess === runningProcess) backendProcess = null
    throw error
  }
  backendRuntime = {
    baseUrl,
    token,
    indexUrl: pathToFileURL(path.join(projectDir, 'dist', 'index.html')).href,
  }
  backendProxy = createBackendProxy({
    getRuntime: () => backendRuntime,
    getMainWebContents: () => mainWindow?.webContents,
    log: entry => log(`backend proxy ${entry.event ?? 'event'}${entry.code ? `: ${entry.code}` : ''}`),
  })
  await log(`backend ready on port ${port}`)
}

async function stopBackend() {
  backendProxy?.cleanupAll()
  backendRuntime = null
  if (!backendProcess) return
  const running = backendProcess
  backendProcess = null
  stopBackendProcess(running)
  await log('backend stop requested')
}

async function exitTestMode() {
  isQuitting = true
  try {
    await stopBackend()
  } finally {
    await log('test-mode forcing process exit')
    process.exit(0)
  }
}

function createWindow() {
  const indexFile = path.join(projectDir, 'dist', 'index.html')
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1060,
    minHeight: 720,
    show: false,
    backgroundColor: '#f5efe6',
    titleBarStyle: 'hidden',
    titleBarOverlay: { color: '#f5efe6', symbolColor: '#6f6254', height: 34 },
    webPreferences: {
      preload: path.join(mainDir, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })
  const mainWebContents = mainWindow.webContents
  petController.setMainWebContents(mainWebContents)
  mainWindow.setMenuBarVisibility(false)
  mainWindow.once('ready-to-show', () => {
    if (process.env.A3_ELECTRON_TEST_MODE !== '1') mainWindow?.show()
  })
  if (process.env.A3_ELECTRON_TEST_MODE === '1') {
    mainWindow.webContents.once('did-finish-load', () => setTimeout(() => { void exitTestMode() }, 800))
  }
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (navigationAction(url, indexFile) === 'external') void shell.openExternal(url)
    return { action: 'deny' }
  })
  mainWindow.webContents.on('will-navigate', (event, url) => {
    const action = navigationAction(url, indexFile)
    if (action === 'allow') return
    event.preventDefault()
    backendProxy?.cleanupWebContents(mainWindow.webContents)
    if (action === 'external') void shell.openExternal(url)
  })
  mainWindow.on('closed', () => {
    backendProxy?.cleanupWebContents(mainWebContents)
    mainWindow = null
  })
  mainWindow.loadFile(indexFile)
}

function showStartupError(error) {
  const detail = (error instanceof Error ? error.message : '未知错误').replace(/[<>&]/g, '')
  const window = new BrowserWindow({ width: 620, height: 400, backgroundColor: '#f5efe6' })
  window.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(`<!doctype html><meta charset="utf-8"><style>body{margin:0;padding:42px;background:#f5efe6;color:#40372f;font:16px 'Microsoft YaHei',sans-serif}h1{font-size:24px}.card{padding:28px;background:#fffaf4;border:1px solid #e4d8ca;border-radius:18px}p{line-height:1.7;color:#6f6254}</style><main class="card"><h1>智学协作台未能启动</h1><p>本地学习服务尚未就绪。请检查安装文件或稍后重试。</p><p>${detail}</p></main>` )}`)
}

function trustedKnowledgeSender(event) {
  return Boolean(
    backendRuntime
    && isTrustedDesktopSender(event, mainWindow?.webContents, backendRuntime.indexUrl)
  )
}

ipcMain.handle('a3:api-request', (event, input) => backendProxy?.request(event, input) ?? ({
  ok: false,
  status: 503,
  error: desktopError('DESKTOP_BACKEND_UNAVAILABLE', '本地学习服务暂时不可用，请稍后重试。', true),
}))
ipcMain.handle('a3:model-config-test', (event, input) => withValidatedInput(validateModelConfigInput(input), value => modelProfileController.testLegacy(event, value)))
ipcMain.handle('a3:model-config-save', (event, input) => withValidatedInput(validateModelConfigInput(input), value => modelProfileController.upsertLegacy(event, value)))
ipcMain.handle('a3:model-profiles-list', event => modelProfileController.list(event))
ipcMain.handle('a3:model-profile-test', (event, input) => withValidatedInput(validateModelProfileInput(input), value => modelProfileController.test(event, value)))
ipcMain.handle('a3:model-profile-upsert', (event, input) => withValidatedInput(validateModelProfileInput(input), value => modelProfileController.upsert(event, value)))
ipcMain.handle('a3:model-profile-delete', (event, id) => withValidatedInput(validateModelProfileId(id), value => modelProfileController.delete(event, value)))
ipcMain.handle('a3:model-profile-policy-save', (event, input) => withValidatedInput(validateModelProfilePolicyInput(input), value => modelProfileController.savePolicy(event, value)))
ipcMain.handle('a3:model-runtime-status', event => modelProfileController.status(event))
ipcMain.handle('a3:knowledge-choose-files', (event, collectionId) => {
  const validated = validateKnowledgeCollectionId(collectionId)
  return validated.ok ? knowledgeController.chooseFiles(event, validated.value) : validated
})
ipcMain.handle('a3:knowledge-import-dropped-files', (event, input) => {
  const validated = validateKnowledgeDroppedPaths(input)
  return validated.ok ? knowledgeController.importDroppedFiles(event, validated.value) : validated
})
ipcMain.handle('a3:knowledge-reveal-source', (event, documentId) => knowledgeController.revealSource(event, documentId))
ipcMain.handle('a3:knowledge-open-source', (event, input) => {
  if (!input || !Number.isSafeInteger(input.documentId) || input.documentId < 1) {
    return { ok: false, error: desktopError('DESKTOP_REQUEST_DENIED', '知识库来源请求无效。') }
  }
  const locator = validateKnowledgeLocator(input.locator)
  if (!locator.ok) return locator
  return knowledgeController.openSource(event, input.documentId, locator.value)
})
ipcMain.handle('a3:pet-get', event => {
  if (!trustedPetMainSender(event)) return deniedPetRequest()
  return { ok: true, status: 200, data: publicPetSnapshot() }
})
ipcMain.handle('a3:pet-update-settings', (event, input) => {
  if (!trustedPetMainSender(event)) return deniedPetRequest()
  return withValidatedInput(validatePetSettingsInput(input), async value => {
    await petController.updateSettings(value)
    return { ok: true, status: 200, data: publicPetSnapshot() }
  })
})
ipcMain.handle('a3:pet-set-task-state', (event, input) => {
  if (!trustedPetMainSender(event)) return deniedPetRequest()
  return withValidatedInput(validatePetTaskStateInput(input), value => ({
    ok: true,
    status: 200,
    data: petController.setTaskState(value),
  }))
})
ipcMain.handle('a3:pet-choose-character', async event => {
  if (!trustedPetMainSender(event)) return deniedPetRequest()
  const result = await dialog.showOpenDialog(mainWindow, {
    title: '选择桌宠角色包文件夹',
    properties: ['openDirectory'],
  })
  if (result.canceled || !result.filePaths[0]) return { ok: true, status: 200, data: publicPetSnapshot() }
  try {
    await petCharacterImporter.importFromDirectory(result.filePaths[0])
    await petController.reloadPet({ forceHidden: process.env.A3_ELECTRON_TEST_MODE === '1' })
    return { ok: true, status: 200, data: publicPetSnapshot() }
  } catch (error) {
    void log(`pet character import failed: ${error instanceof Error ? error.message : String(error)}`)
    return petImportError()
  }
})
ipcMain.handle('a3:pet-reset-character', async event => {
  if (!trustedPetMainSender(event)) return deniedPetRequest()
  try {
    await petCharacterImporter.reset()
    await petController.reloadPet({ forceHidden: process.env.A3_ELECTRON_TEST_MODE === '1' })
    return { ok: true, status: 200, data: publicPetSnapshot() }
  } catch (error) {
    void log(`pet character reset failed: ${error instanceof Error ? error.message : String(error)}`)
    return petImportError()
  }
})
ipcMain.handle('a3:pet-ready', event => petController.isPetSender(event)
  ? petController.readyPayload()
  : deniedPetRequest())
ipcMain.on('a3:pet-drag-begin', (event, point) => {
  if (petController.isPetSender(event)) safelyMovePet(() => petController.beginDrag(point))
})
ipcMain.on('a3:pet-drag-move', (event, point) => {
  if (petController.isPetSender(event)) safelyMovePet(() => petController.moveDrag(point))
})
ipcMain.on('a3:pet-drag-end', event => {
  if (petController.isPetSender(event)) safelyMovePet(() => petController.endDrag())
})
ipcMain.on('a3:stream-start', (event, streamId, input) => { void backendProxy?.startStream(event, streamId, input) })
ipcMain.on('a3:stream-cancel', (event, streamId) => { backendProxy?.cancelStream(event, streamId) })

if (!app.requestSingleInstanceLock()) app.quit()
app.on('second-instance', () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.focus()
  }
})
app.whenReady().then(async () => {
  try {
    await knowledgeImporter.prepare()
    await petController.prepare()
    await startBackend()
    await modelProfileController.bootstrap()
    createWindow()
    petController.createWindow({ forceHidden: process.env.A3_ELECTRON_TEST_MODE === '1' })
    screen.on('display-added', reclampPetWindow)
    screen.on('display-removed', reclampPetWindow)
    screen.on('display-metrics-changed', reclampPetWindow)
  } catch (error) {
    await log(`startup failed: ${error instanceof Error ? error.message : String(error)}`)
    showStartupError(error)
  }
})
app.on('before-quit', () => { isQuitting = true; petController.destroy(); void knowledgeController.shutdown(); stopBackend() })
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })

function withValidatedInput(validation, invoke) {
  if (validation.ok) return invoke(validation.value)
  return {
    ok: false,
    status: validation.error.code === 'DESKTOP_REQUEST_DENIED' ? 403 : 400,
    error: validation.error,
  }
}

function trustedPetMainSender(event) {
  return petController.isMainSender(event) && trustedKnowledgeSender(event)
}

function deniedPetRequest() {
  return {
    ok: false,
    status: 403,
    error: desktopError('DESKTOP_REQUEST_DENIED', '桌宠请求来源不受信任。'),
  }
}

function safelyMovePet(action) {
  try {
    void Promise.resolve(action()).catch(error => log(`pet movement failed: ${error instanceof Error ? error.message : String(error)}`))
  } catch (error) {
    void log(`pet movement denied: ${error instanceof Error ? error.message : String(error)}`)
  }
}

function reclampPetWindow() {
  void petController.reclamp().catch(error => log(`pet display clamp failed: ${error instanceof Error ? error.message : String(error)}`))
}

function publicPetSnapshot() {
  const value = petController.snapshot()
  return {
    available: true,
    pet: value.pet ? { id: value.pet.id, displayName: value.pet.displayName, description: value.pet.description } : null,
    settings: value.settings,
    state: value.state,
  }
}

function petImportError() {
  return {
    ok: false,
    status: 400,
    error: desktopError('PET_CHARACTER_IMPORT_FAILED', '角色包无效，请检查 pet.json 和 spritesheet.webp。'),
  }
}

async function inspectPetAtlas(filePath) {
  const image = nativeImage.createFromPath(filePath)
  if (image.isEmpty()) return { width: 0, height: 0, validTransparency: false }
  const { width, height } = image.getSize()
  if (width !== 1536 || height !== 1872) return { width, height, validTransparency: false }
  const bitmap = image.toBitmap({ scaleFactor: 1 })
  return { width, height, validTransparency: validatePetAtlasBitmap(bitmap, width, height) }
}
