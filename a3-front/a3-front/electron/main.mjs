import { app, BrowserWindow, ipcMain, safeStorage, shell } from 'electron'
import { spawn } from 'node:child_process'
import crypto from 'node:crypto'
import fs from 'node:fs/promises'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { awaitBackendStartup, shouldNotifyBackendExit, stopBackendProcess } from './backend-lifecycle.mjs'
import { createBackendProxy } from './backend-proxy.mjs'
import { desktopError, isTrustedDesktopSender } from './ipc-contract.mjs'
import { createModelConfigStore, modelEnvironment } from './model-config.mjs'
import { createBackendModelTester, createModelConfigController } from './model-config-controller.mjs'
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
let activeModelConfig = null
let isQuitting = false

const modelConfigStore = createModelConfigStore({
  safeStorage,
  filePath: path.join(app.getPath('userData'), 'model-settings.enc'),
})
const testModelCandidate = createBackendModelTester({ getRuntime: () => backendRuntime })
const modelConfigController = createModelConfigController({
  validateSender: event => Boolean(
    backendRuntime
    && isTrustedDesktopSender(event, mainWindow?.webContents, backendRuntime.indexUrl)
  ),
  configStore: modelConfigStore,
  testCandidate: testModelCandidate,
  restart: restartBackendWithConfig,
  getCurrentSettings: readCurrentModelSettings,
  log,
})

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

async function waitForBackendReady(baseUrl, token) {
  const timeoutAt = Date.now() + 20_000
  let lastError = '模型配置尚未就绪。'
  while (Date.now() < timeoutAt) {
    try {
      const response = await fetch(`${baseUrl}/health/ready`, {
        headers: { 'X-A3-Desktop-Token': token },
      })
      if (response.ok) return
      lastError = `模型配置未就绪（${response.status}）。`
    } catch (error) {
      lastError = error instanceof Error ? error.message : '模型配置检查失败。'
    }
    await new Promise(resolve => setTimeout(resolve, 300))
  }
  throw Object.assign(new Error(lastError), { code: 'MODEL_RESTART_FAILED' })
}

async function startBackend(modelConfig = activeModelConfig) {
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
      ...process.env,
      A3_HOST: '127.0.0.1',
      A3_PORT: String(port),
      A3_DATA_DIR: command.dataDir,
      DESKTOP_TOKEN: token,
      APP_ENV: app.isPackaged ? 'production' : 'development',
      CORS_ORIGINS: 'null,http://127.0.0.1:5173',
      ...(modelConfig ? modelEnvironment(modelConfig) : {}),
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

async function restartBackendWithConfig(modelConfig) {
  await stopBackend()
  activeModelConfig = modelConfig
  await startBackend(modelConfig)
  await waitForBackendReady(backendRuntime.baseUrl, backendRuntime.token)
}

async function readCurrentModelSettings() {
  if (!backendRuntime) throw new Error('Backend runtime is unavailable.')
  const response = await fetch(`${backendRuntime.baseUrl}/api/settings/model`, {
    headers: { 'X-A3-Desktop-Token': backendRuntime.token },
  })
  if (!response.ok) throw new Error('Model settings could not be read.')
  const value = await response.json()
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Model settings response is invalid.')
  }
  return value
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

ipcMain.handle('a3:api-request', (event, input) => backendProxy?.request(event, input) ?? ({
  ok: false,
  status: 503,
  error: desktopError('DESKTOP_BACKEND_UNAVAILABLE', '本地学习服务暂时不可用，请稍后重试。', true),
}))
ipcMain.handle('a3:model-config-test', (event, input) => modelConfigController.test(event, input))
ipcMain.handle('a3:model-config-save', (event, input) => modelConfigController.save(event, input))
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
    activeModelConfig = await modelConfigStore.load()
    await startBackend(activeModelConfig)
    createWindow()
  } catch (error) {
    await log(`startup failed: ${error instanceof Error ? error.message : String(error)}`)
    showStartupError(error)
  }
})
app.on('before-quit', () => { isQuitting = true; stopBackend() })
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
