import { createBrowserPetAudioRuntime } from './pet-audio.js'

const DIRECTIONAL_STATES = new Set(['running-left', 'running-right'])
const CLICK_DELAY_MS = 220
const IDLE_THROTTLE_MS = 60_000

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
  let interactionTimer = null
  let pointer = null

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
    interactionState = state
    audio.playInteraction(state)
    setState()
    if (interactionTimer !== null) clearTimeout(interactionTimer)
    const total = payload.pet.animations[state].durations.reduce((sum, value) => sum + value, 0) / settings.speed
    interactionTimer = setTimeout(() => {
      interactionState = null
      interactionTimer = null
      setState()
    }, total)
  }

  function drawFrame() {
    const dpr = Math.min(Math.max(window.devicePixelRatio || 1, 1), 3)
    const width = payload.pet.cell.width
    const height = payload.pet.cell.height
    const targetWidth = Math.round(width * dpr)
    const targetHeight = Math.round(height * dpr)
    if (canvas.width !== targetWidth || canvas.height !== targetHeight) {
      canvas.width = targetWidth
      canvas.height = targetHeight
    }
    context.setTransform(dpr, 0, 0, dpr, 0, 0)
    context.clearRect(0, 0, width, height)
    context.imageSmoothingEnabled = true
    context.drawImage(
      atlas,
      frame * width,
      animation().row * height,
      width,
      height,
      0,
      0,
      width,
      height,
    )
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
    pointer = { id: event.pointerId, startX: event.screenX, startY: event.screenY, moved: false }
    root.setPointerCapture(event.pointerId)
    document.body.classList.add('is-dragging')
    bridge.beginDrag({ screenX: event.screenX, screenY: event.screenY })
  })
  root.addEventListener('pointermove', event => {
    if (!pointer || pointer.id !== event.pointerId) return
    const direction = dragDirection(pointer.startX, event.screenX)
    if (direction) {
      pointer.moved = true
      dragState = direction
      setState()
    }
    bridge.moveDrag({ screenX: event.screenX, screenY: event.screenY })
  })
  root.addEventListener('pointerup', event => {
    if (!pointer || pointer.id !== event.pointerId) return
    const moved = pointer.moved
    pointer = null
    dragState = null
    setState()
    document.body.classList.remove('is-dragging')
    bridge.endDrag()
    if (!moved) clickResolver.click()
  })
  root.addEventListener('pointercancel', () => {
    pointer = null
    dragState = null
    setState()
    document.body.classList.remove('is-dragging')
    bridge.endDrag()
  })
  root.addEventListener('dblclick', event => {
    event.preventDefault()
    lastInteractionAt = Date.now()
    clickResolver.doubleClick()
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
