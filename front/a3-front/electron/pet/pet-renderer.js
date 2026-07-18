import { createBrowserPetAudioRuntime } from './pet-audio.js'

const DIRECTIONAL_STATES = new Set(['running-left', 'running-right'])
const CLICK_DELAY_MS = 220
const IDLE_THROTTLE_MS = 60_000
const RESIZE_MARGIN_PX = 14

export function resizeCornerAt({ x, y, width, height, margin = RESIZE_MARGIN_PX }) {
  if (![x, y, width, height, margin].every(Number.isFinite) || width <= 0 || height <= 0 || margin <= 0) {
    throw new TypeError('Pet resize hit area is invalid.')
  }
  const west = x >= 0 && x <= margin
  const east = x >= width - margin && x <= width
  const north = y >= 0 && y <= margin
  const south = y >= height - margin && y <= height
  if (north && west) return 'nw'
  if (north && east) return 'ne'
  if (south && west) return 'sw'
  if (south && east) return 'se'
  return null
}

export function frameDuration(duration, speed) {
  if (!Number.isFinite(duration) || duration <= 0 || !Number.isFinite(speed) || speed <= 0) {
    throw new TypeError('Animation timing is invalid.')
  }
  return duration / speed
}

export function advanceAnimation(durations, frame, elapsed, speed) {
  if (!Array.isArray(durations) || durations.length === 0 || !Number.isInteger(frame) || frame < 0 || frame >= durations.length) {
    throw new TypeError('Animation frame input is invalid.')
  }
  let nextFrame = frame
  let remaining = elapsed
  let guard = 0
  while (remaining >= frameDuration(durations[nextFrame], speed) && guard < durations.length * 100) {
    remaining -= frameDuration(durations[nextFrame], speed)
    nextFrame = (nextFrame + 1) % durations.length
    guard += 1
  }
  return { frame: nextFrame, elapsed: remaining }
}

export function resolveDisplayState({ taskState, interactionState, dragState }) {
  return dragState || interactionState || taskState || 'idle'
}

export function dragDirection(startX, currentX, threshold = 3) {
  const delta = currentX - startX
  if (Math.abs(delta) <= threshold) return null
  return delta < 0 ? 'running-left' : 'running-right'
}

export function pointerMoved(startX, startY, currentX, currentY, threshold = 3) {
  if (![startX, startY, currentX, currentY, threshold].every(Number.isFinite) || threshold < 0) {
    throw new TypeError('Pet pointer movement is invalid.')
  }
  return Math.hypot(currentX - startX, currentY - startY) > threshold
}

export function resourceMode({ hidden, state, now, lastInteractionAt }) {
  if (hidden) return 'paused'
  if (state === 'idle' && now - lastInteractionAt >= IDLE_THROTTLE_MS) return 'low'
  return 'normal'
}

export function createClickResolver({
  onSingle,
  onDouble,
  setTimer = (callback, delay) => setTimeout(callback, delay),
  clearTimer = timer => clearTimeout(timer),
  delay = CLICK_DELAY_MS,
}) {
  let pending = null
  return {
    click() {
      if (pending !== null) return
      pending = setTimer(() => {
        pending = null
        onSingle()
      }, delay)
    },
    doubleClick() {
      if (pending !== null) clearTimer(pending)
      pending = null
      onDouble()
    },
    cancel() {
      if (pending !== null) clearTimer(pending)
      pending = null
    },
  }
}

export function canvasBackingSize(cell, value) {
  if (!cell || !Number.isFinite(cell.width) || cell.width <= 0 || !Number.isFinite(cell.height) || cell.height <= 0) {
    throw new TypeError('Canvas cell dimensions are invalid.')
  }
  const dpr = Math.min(Math.max(Number(value) || 1, 1), 3)
  return {
    width: Math.round(cell.width * dpr),
    height: Math.round(cell.height * dpr),
    dpr,
  }
}

export function renderPetFrame({ canvas, context, atlas, cell, animation, frame, dpr }) {
  const target = canvasBackingSize(cell, dpr)
  if (canvas.width !== target.width || canvas.height !== target.height) {
    canvas.width = target.width
    canvas.height = target.height
  }
  if (typeof context.resetTransform === 'function') context.resetTransform()
  else context.setTransform(1, 0, 0, 1, 0, 0)
  context.clearRect(0, 0, canvas.width, canvas.height)
  context.setTransform(target.dpr, 0, 0, target.dpr, 0, 0)
  context.imageSmoothingEnabled = true
  context.drawImage(
    atlas,
    frame * cell.width,
    animation.row * cell.height,
    cell.width,
    cell.height,
    0,
    0,
    cell.width,
    cell.height,
  )
}

export function createInteractionController({
  onState,
  durationFor,
  setTimer = (callback, delay) => setTimeout(callback, delay),
  clearTimer = timer => clearTimeout(timer),
}) {
  let timer = null
  return {
    play(state) {
      if (timer !== null) return false
      onState(state)
      timer = setTimer(() => {
        timer = null
        onState(null)
      }, durationFor(state))
      return true
    },
    cancel() {
      if (timer !== null) clearTimer(timer)
      timer = null
      onState(null)
    },
    isActive() {
      return timer !== null
    },
  }
}

export function queueSingleClick(interactionController, clickResolver) {
  if (interactionController.isActive()) return false
  clickResolver.click()
  return true
}

export function queueDoubleClick(interactionController, clickResolver) {
  if (interactionController.isActive()) return false
  clickResolver.doubleClick()
  return true
}

if (typeof window !== 'undefined' && typeof document !== 'undefined') {
  void startPetRenderer()
}

async function startPetRenderer() {
  const bridge = window.a3Pet
  const root = document.querySelector('#pet')
  const canvas = document.querySelector('#pet-canvas')
  if (!bridge || !(canvas instanceof HTMLCanvasElement) || !root) return

  const payload = await bridge.ready()
  if (!payload?.pet?.spritesheetUrl || !payload.pet.animations) return
  const atlas = await loadImage(payload.pet.spritesheetUrl)
  const context = canvas.getContext('2d', { alpha: true })
  if (!context) return

  let settings = { ...payload.settings }
  const audio = createBrowserPetAudioRuntime(window)
  audio.updateSettings(settings)
  audio.setHidden(document.hidden)
  let taskState = payload.state || 'idle'
  let interactionState = null
  let dragState = null
  let currentState = resolveDisplayState({ taskState, interactionState, dragState })
  let frame = 0
  let elapsed = 0
  let lastTick = performance.now()
  let lastInteractionAt = Date.now()
  let animationHandle = null
  let lowPowerHandle = null
  let pointer = null

  const interactionController = createInteractionController({
    onState: state => {
      interactionState = state
      setState()
    },
    durationFor: state => (
      payload.pet.animations[state].durations.reduce((sum, value) => sum + value, 0) / settings.speed
    ),
  })

  const clickResolver = createClickResolver({
    onSingle: () => playInteraction('waving'),
    onDouble: () => playInteraction('jumping'),
  })

  function animation() {
    return payload.pet.animations[currentState] || payload.pet.animations.idle
  }

  function setState() {
    const next = resolveDisplayState({ taskState, interactionState, dragState })
    if (next === currentState) return
    currentState = next
    frame = 0
    elapsed = 0
    lastTick = performance.now()
  }

  function playInteraction(state) {
    lastInteractionAt = Date.now()
    if (interactionController.play(state)) audio.playInteraction(state)
  }

  function cornerFor(event) {
    return resizeCornerAt({
      x: event.clientX,
      y: event.clientY,
      width: root.clientWidth,
      height: root.clientHeight,
    })
  }

  function setResizeCursor(corner) {
    if (corner) root.dataset.resizeCorner = corner
    else delete root.dataset.resizeCorner
  }

  function drawFrame() {
    renderPetFrame({
      canvas,
      context,
      atlas,
      cell: payload.pet.cell,
      animation: animation(),
      frame,
      dpr: window.devicePixelRatio,
    })
  }

  function cancelScheduledFrame() {
    if (animationHandle !== null) cancelAnimationFrame(animationHandle)
    if (lowPowerHandle !== null) clearTimeout(lowPowerHandle)
    animationHandle = null
    lowPowerHandle = null
  }

  function schedule() {
    cancelScheduledFrame()
    const mode = resourceMode({
      hidden: document.hidden,
      state: currentState,
      now: Date.now(),
      lastInteractionAt,
    })
    if (mode === 'paused') return
    if (mode === 'low') {
      lowPowerHandle = setTimeout(() => { animationHandle = requestAnimationFrame(tick) }, 500)
    } else {
      animationHandle = requestAnimationFrame(tick)
    }
  }

  function tick(timestamp) {
    animationHandle = null
    const delta = Math.min(Math.max(timestamp - lastTick, 0), 1000)
    lastTick = timestamp
    const next = advanceAnimation(animation().durations, frame, elapsed + delta, settings.speed)
    frame = next.frame
    elapsed = next.elapsed
    drawFrame()
    schedule()
  }

  root.addEventListener('pointerdown', event => {
    if (event.button !== 0) return
    lastInteractionAt = Date.now()
    clickResolver.cancel()
    const corner = cornerFor(event)
    pointer = { id: event.pointerId, startX: event.screenX, startY: event.screenY, moved: false, corner }
    root.setPointerCapture(event.pointerId)
    if (corner) {
      document.body.classList.add('is-resizing')
      setResizeCursor(corner)
      bridge.beginResize({ corner, screenX: event.screenX, screenY: event.screenY })
    } else {
      document.body.classList.add('is-dragging')
      bridge.beginDrag({ screenX: event.screenX, screenY: event.screenY })
    }
  })
  root.addEventListener('pointermove', event => {
    if (!pointer) {
      setResizeCursor(cornerFor(event))
      return
    }
    if (pointer.id !== event.pointerId) return
    if (pointer.corner) {
      pointer.moved = pointer.moved || pointerMoved(pointer.startX, pointer.startY, event.screenX, event.screenY)
      bridge.moveResize({ screenX: event.screenX, screenY: event.screenY })
      return
    }
    if (pointerMoved(pointer.startX, pointer.startY, event.screenX, event.screenY)) pointer.moved = true
    const direction = dragDirection(pointer.startX, event.screenX)
    if (direction) {
      dragState = direction
      setState()
    }
    bridge.moveDrag({ screenX: event.screenX, screenY: event.screenY })
  })
  root.addEventListener('pointerup', event => {
    if (!pointer || pointer.id !== event.pointerId) return
    const moved = pointer.moved
    const corner = pointer.corner
    pointer = null
    if (corner) {
      document.body.classList.remove('is-resizing')
      bridge.endResize()
      setResizeCursor(cornerFor(event))
      return
    }
    dragState = null
    setState()
    document.body.classList.remove('is-dragging')
    bridge.endDrag()
    if (!moved) queueSingleClick(interactionController, clickResolver)
  })
  root.addEventListener('pointercancel', () => {
    const corner = pointer?.corner
    pointer = null
    dragState = null
    setState()
    document.body.classList.remove('is-dragging')
    document.body.classList.remove('is-resizing')
    if (corner) bridge.endResize()
    else bridge.endDrag()
    setResizeCursor(null)
  })
  root.addEventListener('dblclick', event => {
    event.preventDefault()
    lastInteractionAt = Date.now()
    queueDoubleClick(interactionController, clickResolver)
  })
  document.addEventListener('visibilitychange', () => {
    lastTick = performance.now()
    audio.setHidden(document.hidden)
    schedule()
  })
  bridge.onState(({ state }) => {
    audio.handleState(state)
    if (DIRECTIONAL_STATES.has(state) && pointer) dragState = state
    else {
      taskState = state
      dragState = null
    }
    setState()
  })
  bridge.onSettings(({ settings: next }) => {
    settings = { ...settings, ...next }
    audio.updateSettings(settings)
    lastInteractionAt = Date.now()
    schedule()
  })

  drawFrame()
  schedule()
}

function loadImage(source) {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.decoding = 'async'
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('Desktop pet spritesheet failed to load.'))
    image.src = source
  })
}
