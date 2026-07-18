import path from 'node:path'

import {
  PET_TASK_STATES,
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
const PET_MIN_SCALE = 1
const PET_MAX_SCALE = 3
export const PET_RESIZE_CORNERS = Object.freeze(['nw', 'ne', 'sw', 'se'])

export function resizePetBounds({ origin, corner, start, current, cell }) {
  if (!isStoredBounds(origin) || !PET_RESIZE_CORNERS.includes(corner)) {
    throw new TypeError('Pet resize bounds or corner is invalid.')
  }
  ensurePoint(start)
  ensurePoint(current)
  if (!cell || !Number.isFinite(cell.width) || cell.width <= 0 || !Number.isFinite(cell.height) || cell.height <= 0) {
    throw new TypeError('Pet resize cell is invalid.')
  }
  const horizontalDelta = corner.endsWith('e')
    ? current.screenX - start.screenX
    : start.screenX - current.screenX
  const verticalDelta = corner.startsWith('s')
    ? current.screenY - start.screenY
    : start.screenY - current.screenY
  const widthScale = (origin.width + horizontalDelta) / cell.width
  const heightScale = (origin.height + verticalDelta) / cell.height
  const originScale = origin.width / cell.width
  const scale = clampNumber(
    Math.abs(widthScale - originScale) >= Math.abs(heightScale - originScale) ? widthScale : heightScale,
    PET_MIN_SCALE,
    PET_MAX_SCALE,
  )
  const width = Math.round(cell.width * scale)
  const height = Math.round(cell.height * scale)
  return {
    x: corner.endsWith('w') ? origin.x + origin.width - width : origin.x,
    y: corner.startsWith('n') ? origin.y + origin.height - height : origin.y,
    width,
    height,
  }
}

export function constrainPetBounds(bounds, cell, displays) {
  if (!isStoredBounds(bounds) || !cell || !Number.isFinite(cell.width) || cell.width <= 0 || !Number.isFinite(cell.height) || cell.height <= 0 || !Array.isArray(displays) || displays.length === 0) {
    throw new TypeError('Pet bounds, cell, or displays are invalid.')
  }
  const centerX = bounds.x + bounds.width / 2
  const centerY = bounds.y + bounds.height / 2
  const display = [...displays].sort((left, right) => (
    distanceToArea(centerX, centerY, left?.workArea) - distanceToArea(centerX, centerY, right?.workArea)
  ))[0]
  if (!display || !isStoredBounds(display.workArea)) throw new TypeError('Display work area is invalid.')
  const area = display.workArea
  const availableScale = Math.min(area.width / cell.width, area.height / cell.height)
  const maximumScale = Math.max(PET_MIN_SCALE, Math.min(PET_MAX_SCALE, availableScale))
  const scale = clampNumber(bounds.width / cell.width, PET_MIN_SCALE, maximumScale)
  const width = Math.round(cell.width * scale)
  const height = Math.round(cell.height * scale)
  return {
    x: width > area.width ? area.x : Math.round(clampNumber(bounds.x, area.x, area.x + area.width - width)),
    y: height > area.height ? area.y : Math.round(clampNumber(bounds.y, area.y, area.y + area.height - height)),
    width,
    height,
    displayId: display.id,
  }
}

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
  let savedBoundsVersion = 0
  let taskState = 'idle'
  let drag = null
  let resize = null
  let persistQueue = Promise.resolve()

  const settingsPath = path.join(userDataDir, SETTINGS_FILE)

  async function prepare() {
    await fs.mkdir(userDataDir, { recursive: true })
    const stored = await readJson(settingsPath)
    if (stored) {
      const { position, bounds_version: boundsVersion, ...patch } = stored
      try {
        const migrated = Number.isFinite(patch.scale) && patch.scale < PET_MIN_SCALE
          ? { ...patch, scale: PET_MIN_SCALE }
          : patch
        settings = { ...DEFAULT_SETTINGS, ...validatePetSettingsPatch(migrated) }
      } catch {
        settings = { ...DEFAULT_SETTINGS }
      }
      if (isStoredBounds(position)) {
        savedBounds = { ...position }
        savedBoundsVersion = boundsVersion === 1 ? 1 : 0
      }
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
        const resized = constrainPetBounds({
          x: current.x,
          y: current.y,
          width: Math.round(pet.manifest.cell.width * settings.scale),
          height: Math.round(pet.manifest.cell.height * settings.scale),
        }, pet.manifest.cell, screen.getAllDisplays())
        petWindow.setBounds(stripDisplayId(resized))
        savedBounds = stripDisplayId(resized)
        savedBoundsVersion = 1
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

  async function toggleVisibility() {
    if (!petWindow || petWindow.isDestroyed()) return false
    settings = { ...settings, visible: !petWindow.isVisible() }
    if (settings.visible) {
      petWindow.showInactive()
      if (typeof petWindow.moveTop === 'function') petWindow.moveTop()
    } else {
      petWindow.hide()
    }
    await persist()
    sendPet('a3:pet-settings', { settings: { ...settings } })
    return true
  }

  function beginDrag(point) {
    ensurePoint(point)
    if (!petWindow || petWindow.isDestroyed() || drag || resize) return false
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
    const next = constrainPetBounds({
      x: drag.bounds.x + deltaX,
      y: drag.bounds.y + deltaY,
      width: drag.bounds.width,
      height: drag.bounds.height,
    }, pet.manifest.cell, screen.getAllDisplays())
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

  function beginResize(input) {
    if (!input || !PET_RESIZE_CORNERS.includes(input.corner)) throw new TypeError('Pet resize corner is invalid.')
    ensurePoint(input)
    if (!petWindow || petWindow.isDestroyed() || drag || resize) return false
    resize = {
      corner: input.corner,
      start: { screenX: input.screenX, screenY: input.screenY },
      bounds: savedBounds ? { ...savedBounds } : petWindow.getBounds(),
    }
    return true
  }

  function moveResize(point) {
    ensurePoint(point)
    if (!resize || !petWindow || petWindow.isDestroyed()) return false
    const next = constrainPetBounds(resizePetBounds({
      origin: resize.bounds,
      corner: resize.corner,
      start: resize.start,
      current: point,
      cell: pet.manifest.cell,
    }), pet.manifest.cell, screen.getAllDisplays())
    petWindow.setBounds(stripDisplayId(next))
    savedBounds = stripDisplayId(next)
    savedBoundsVersion = 1
    return true
  }

  async function endResize() {
    if (!resize) return false
    resize = null
    await persist()
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
    const next = constrainPetBounds(savedBounds || petWindow.getBounds(), pet.manifest.cell, screen.getAllDisplays())
    petWindow.setBounds(stripDisplayId(next))
    savedBounds = stripDisplayId(next)
    savedBoundsVersion = 1
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
    resize = null
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
      const restored = savedBoundsVersion === 1
        ? normalizePetBounds(savedBounds, pet.manifest.cell)
        : { x: savedBounds.x, y: savedBounds.y, width, height }
      const clamped = constrainPetBounds(restored, pet.manifest.cell, screen.getAllDisplays())
      savedBounds = stripDisplayId(clamped)
      return savedBounds
    }
    const value = constrainPetBounds(
      defaultPetBounds(screen.getPrimaryDisplay(), width, height),
      pet.manifest.cell,
      screen.getAllDisplays(),
    )
    savedBounds = stripDisplayId(value)
    return savedBounds
  }

  function persist() {
    const payload = {
      ...settings,
      bounds_version: 1,
      position: savedBounds ? { x: savedBounds.x, y: savedBounds.y, width: savedBounds.width, height: savedBounds.height } : null,
    }
    const write = async () => {
      await fs.mkdir(userDataDir, { recursive: true })
      const temporary = `${settingsPath}.tmp`
      await fs.writeFile(temporary, `${JSON.stringify(payload, null, 2)}\n`, 'utf8')
      await fs.rename(temporary, settingsPath)
    }
    const pending = persistQueue.then(write, write)
    persistQueue = pending.catch(() => {})
    return pending
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
    toggleVisibility,
    beginDrag,
    moveDrag,
    endDrag,
    beginResize,
    moveResize,
    endResize,
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

function normalizePetBounds(bounds, cell) {
  const scale = clampNumber(bounds.width / cell.width, PET_MIN_SCALE, PET_MAX_SCALE)
  return {
    x: bounds.x,
    y: bounds.y,
    width: Math.round(cell.width * scale),
    height: Math.round(cell.height * scale),
  }
}

function clampNumber(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), maximum)
}

function distanceToArea(x, y, area) {
  if (!isStoredBounds(area)) return Number.POSITIVE_INFINITY
  const dx = x < area.x ? area.x - x : x > area.x + area.width ? x - (area.x + area.width) : 0
  const dy = y < area.y ? area.y - y : y > area.y + area.height ? y - (area.y + area.height) : 0
  return Math.hypot(dx, dy)
}
