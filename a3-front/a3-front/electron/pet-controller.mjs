import path from 'node:path'

import {
  PET_TASK_STATES,
  clampPetBounds,
  defaultPetBounds,
  parsePetManifestText,
  validatePetSettingsPatch,
} from './pet-config.mjs'

const DEFAULT_SETTINGS = Object.freeze({
  visible: true,
  alwaysOnTop: true,
  scale: 1,
  speed: 1,
  soundEnabled: true,
  soundVolume: 0.5,
  voiceEnabled: false,
  voiceVolume: 0.75,
})
const SETTINGS_FILE = 'pet-settings.json'
const CUSTOM_PET_PATH = Object.freeze(['pets', 'current'])

export function createPetController({
  BrowserWindow,
  screen,
  fs,
  userDataDir,
  packagedPetDir,
  petIndex,
  petPreload,
  pathToFileURL,
}) {
  let petWindow = null
  let mainWebContents = null
  let pet = null
  let settings = { ...DEFAULT_SETTINGS }
  let savedBounds = null
  let taskState = 'idle'
  let drag = null

  const settingsPath = path.join(userDataDir, SETTINGS_FILE)

  async function prepare() {
    await fs.mkdir(userDataDir, { recursive: true })
    const stored = await readJson(settingsPath)
    if (stored) {
      const { position, ...patch } = stored
      try {
        settings = { ...DEFAULT_SETTINGS, ...validatePetSettingsPatch(patch) }
      } catch {
        settings = { ...DEFAULT_SETTINGS }
      }
      if (isStoredBounds(position)) savedBounds = { ...position }
    }
    pet = await loadAvailablePet()
    return snapshot()
  }

  function createWindow({ forceHidden = false } = {}) {
    ensurePrepared()
    if (petWindow && !petWindow.isDestroyed()) return petWindow

    const bounds = initialBounds()
    petWindow = new BrowserWindow({
      x: bounds.x,
      y: bounds.y,
      width: bounds.width,
      height: bounds.height,
      transparent: true,
      frame: false,
      alwaysOnTop: settings.alwaysOnTop,
      skipTaskbar: true,
      resizable: false,
      movable: false,
      maximizable: false,
      minimizable: false,
      fullscreenable: false,
      hasShadow: false,
      backgroundColor: '#00000000',
      show: false,
      webPreferences: {
        preload: petPreload,
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
      },
    })
    petWindow.loadFile(petIndex)
    const createdWindow = petWindow
    petWindow.on('closed', () => { if (petWindow === createdWindow) petWindow = null })
    if (settings.visible && !forceHidden) petWindow.showInactive()
    return petWindow
  }

  function snapshot() {
    return {
      pet: pet ? { ...pet.manifest, spritesheetUrl: pet.spritesheetUrl } : null,
      settings: { ...settings },
      bounds: savedBounds ? { ...savedBounds } : null,
      state: taskState,
    }
  }

  function readyPayload() {
    ensurePrepared()
    return snapshot()
  }

  async function updateSettings(input) {
    const patch = validatePetSettingsPatch(input)
    settings = { ...settings, ...patch }

    if (petWindow && !petWindow.isDestroyed()) {
      if (Object.hasOwn(patch, 'scale')) {
        const current = savedBounds || petWindow.getBounds()
        const resized = clampPetBounds({
          x: current.x,
          y: current.y,
          width: Math.round(pet.manifest.cell.width * settings.scale),
          height: Math.round(pet.manifest.cell.height * settings.scale),
        }, screen.getAllDisplays())
        petWindow.setBounds(stripDisplayId(resized))
        savedBounds = stripDisplayId(resized)
      }
      if (Object.hasOwn(patch, 'visible')) {
        if (settings.visible) petWindow.showInactive()
        else petWindow.hide()
      }
      if (Object.hasOwn(patch, 'alwaysOnTop')) petWindow.setAlwaysOnTop(settings.alwaysOnTop)
    }

    await persist()
    sendPet('a3:pet-settings', { settings: { ...settings } })
    return snapshot()
  }

  function beginDrag(point) {
    ensurePoint(point)
    if (!petWindow || petWindow.isDestroyed()) return false
    drag = {
      screenX: point.screenX,
      screenY: point.screenY,
      bounds: savedBounds ? { ...savedBounds } : petWindow.getBounds(),
      directionState: null,
    }
    return true
  }

  async function moveDrag(point) {
    ensurePoint(point)
    if (!drag || !petWindow || petWindow.isDestroyed()) return false
    const deltaX = point.screenX - drag.screenX
    const deltaY = point.screenY - drag.screenY
    const next = clampPetBounds({
      x: drag.bounds.x + deltaX,
      y: drag.bounds.y + deltaY,
      width: drag.bounds.width,
      height: drag.bounds.height,
    }, screen.getAllDisplays())
    petWindow.setPosition(next.x, next.y)
    savedBounds = stripDisplayId(next)

    const directionState = deltaX < 0 ? 'running-left' : deltaX > 0 ? 'running-right' : drag.directionState
    if (directionState && directionState !== drag.directionState) {
      drag.directionState = directionState
      sendPet('a3:pet-state', { state: directionState })
    }
    return true
  }

  async function endDrag() {
    if (!drag) return false
    drag = null
    await persist()
    sendPet('a3:pet-state', { state: taskState })
    return true
  }

  function setTaskState(state) {
    if (!PET_TASK_STATES.includes(state)) throw new TypeError('Pet task state is invalid.')
    taskState = state
    if (!drag) sendPet('a3:pet-state', { state })
    return taskState
  }

  async function reclamp() {
    if (!petWindow || petWindow.isDestroyed()) return null
    const next = clampPetBounds(savedBounds || petWindow.getBounds(), screen.getAllDisplays())
    petWindow.setBounds(stripDisplayId(next))
    savedBounds = stripDisplayId(next)
    await persist()
    return { ...savedBounds }
  }

  function setMainWebContents(webContents) {
    mainWebContents = webContents
  }

  function isMainSender(event) {
    return Boolean(mainWebContents) && event?.sender === mainWebContents && !mainWebContents.isDestroyed()
  }

  function isPetSender(event) {
    return Boolean(petWindow) && !petWindow.isDestroyed() && event?.sender === petWindow.webContents
  }

  function destroy() {
    if (petWindow && !petWindow.isDestroyed()) petWindow.destroy()
    petWindow = null
    mainWebContents = null
    drag = null
  }

  async function reloadPet({ forceHidden = false } = {}) {
    pet = await loadAvailablePet()
    const previous = petWindow
    petWindow = null
    if (previous && !previous.isDestroyed()) previous.destroy()
    return createWindow({ forceHidden })
  }

  async function loadAvailablePet() {
    const customDir = path.join(userDataDir, ...CUSTOM_PET_PATH)
    const custom = await tryLoadPet(customDir)
    if (custom) return custom
    const packaged = await tryLoadPet(packagedPetDir)
    if (!packaged) throw new Error('The packaged desktop pet is missing or invalid.')
    return packaged
  }

  async function tryLoadPet(directory) {
    try {
      const manifest = parsePetManifestText(await fs.readFile(path.join(directory, 'pet.json'), 'utf8'))
      const spritesheet = path.join(directory, manifest.spritesheetPath)
      await fs.access(spritesheet)
      return { manifest, spritesheetUrl: pathToFileURL(spritesheet).href }
    } catch {
      return null
    }
  }

  function initialBounds() {
    const width = Math.round(pet.manifest.cell.width * settings.scale)
    const height = Math.round(pet.manifest.cell.height * settings.scale)
    if (savedBounds) {
      const clamped = clampPetBounds({ x: savedBounds.x, y: savedBounds.y, width, height }, screen.getAllDisplays())
      savedBounds = stripDisplayId(clamped)
      return savedBounds
    }
    const value = defaultPetBounds(screen.getPrimaryDisplay(), width, height)
    savedBounds = stripDisplayId(value)
    return savedBounds
  }

  async function persist() {
    await fs.mkdir(userDataDir, { recursive: true })
    const payload = { ...settings, position: savedBounds ? { x: savedBounds.x, y: savedBounds.y, width: savedBounds.width, height: savedBounds.height } : null }
    const temporary = `${settingsPath}.tmp`
    await fs.writeFile(temporary, `${JSON.stringify(payload, null, 2)}\n`, 'utf8')
    await fs.rename(temporary, settingsPath)
  }

  async function readJson(file) {
    try {
      return JSON.parse(await fs.readFile(file, 'utf8'))
    } catch {
      return null
    }
  }

  function sendPet(channel, payload) {
    if (petWindow && !petWindow.isDestroyed() && !petWindow.webContents.isDestroyed()) {
      petWindow.webContents.send(channel, payload)
    }
  }

  function ensurePrepared() {
    if (!pet) throw new Error('Desktop pet controller is not prepared.')
  }

  return {
    prepare,
    createWindow,
    snapshot,
    readyPayload,
    updateSettings,
    beginDrag,
    moveDrag,
    endDrag,
    setTaskState,
    reclamp,
    setMainWebContents,
    isMainSender,
    isPetSender,
    destroy,
    reloadPet,
  }
}

function ensurePoint(value) {
  if (!value || !Number.isFinite(value.screenX) || !Number.isFinite(value.screenY)) {
    throw new TypeError('Pet drag point is invalid.')
  }
}

function isStoredBounds(value) {
  return Boolean(value)
    && ['x', 'y', 'width', 'height'].every(key => Number.isFinite(value[key]))
    && value.width > 0
    && value.height > 0
}

function stripDisplayId(bounds) {
  return { x: bounds.x, y: bounds.y, width: bounds.width, height: bounds.height }
}
