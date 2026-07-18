import assert from 'node:assert/strict'
import test from 'node:test'

import {
  advanceAnimation,
  canvasBackingSize,
  createClickResolver,
  createInteractionController,
  dragDirection,
  frameDuration,
  resolveDisplayState,
  resourceMode,
  renderPetFrame,
} from './pet/pet-renderer.js'

test('repeated interactions retain only one expiry timer', () => {
  const timers = new Map()
  const states = []
  let nextId = 0
  const controller = createInteractionController({
    onState: state => states.push(state),
    durationFor: () => 400,
    setTimer: callback => {
      const id = ++nextId
      timers.set(id, callback)
      return id
    },
    clearTimer: id => timers.delete(id),
  })

  for (let index = 0; index < 100; index += 1) controller.play('waving')

  assert.equal(timers.size, 1)
  assert.equal(states.at(-1), 'waving')
  timers.values().next().value()
  assert.equal(states.at(-1), null)
})

test('repeated identical interactions cannot extend the current animation lifetime', () => {
  const timers = new Map()
  let nextId = 0
  let clearCount = 0
  const controller = createInteractionController({
    onState: () => {},
    durationFor: () => 400,
    setTimer: callback => {
      const id = ++nextId
      timers.set(id, callback)
      return id
    },
    clearTimer: id => {
      clearCount += 1
      timers.delete(id)
    },
  })

  controller.play('jumping')
  for (let index = 0; index < 100; index += 1) controller.play('jumping')

  assert.equal(nextId, 1)
  assert.equal(clearCount, 0)
  assert.equal(timers.size, 1)
})

test('canvas backing size depends only on logical dimensions and clamped dpr', () => {
  assert.deepEqual(canvasBackingSize({ width: 192, height: 208 }, 1), {
    width: 192,
    height: 208,
    dpr: 1,
  })
  assert.deepEqual(canvasBackingSize({ width: 192, height: 208 }, 2.5), {
    width: 480,
    height: 520,
    dpr: 2.5,
  })
  assert.deepEqual(canvasBackingSize({ width: 192, height: 208 }, 9), {
    width: 576,
    height: 624,
    dpr: 3,
  })
})

test('one hundred real frame renders preserve canvas and client dimensions', () => {
  const canvas = { width: 0, height: 0, clientWidth: 192, clientHeight: 208 }
  const calls = []
  const context = {
    resetTransform: () => calls.push('reset'),
    clearRect: (...args) => calls.push(['clear', ...args]),
    setTransform: (...args) => calls.push(['transform', ...args]),
    drawImage: (...args) => calls.push(['draw', ...args]),
    imageSmoothingEnabled: false,
  }
  const cell = { width: 192, height: 208 }
  for (let index = 0; index < 100; index += 1) {
    renderPetFrame({ canvas, context, atlas: {}, cell, animation: { row: 0 }, frame: index % 4, dpr: 2 })
    assert.deepEqual(
      { width: canvas.width, height: canvas.height, clientWidth: canvas.clientWidth, clientHeight: canvas.clientHeight },
      { width: 384, height: 416, clientWidth: 192, clientHeight: 208 },
    )
  }
  assert.equal(calls.filter(call => Array.isArray(call) && call[0] === 'draw').length, 100)
})

test('animation timing applies speed and advances across multiple frames', () => {
  assert.equal(frameDuration(120, 2), 60)
  assert.deepEqual(advanceAnimation([100, 200, 300], 0, 350, 1), {
    frame: 2,
    elapsed: 50,
  })
  assert.deepEqual(advanceAnimation([100, 200], 1, 130, 2), {
    frame: 0,
    elapsed: 30,
  })
})

test('interaction state overrides task state and drag state has highest priority', () => {
  assert.equal(resolveDisplayState({ taskState: 'review', interactionState: null, dragState: null }), 'review')
  assert.equal(resolveDisplayState({ taskState: 'review', interactionState: 'waving', dragState: null }), 'waving')
  assert.equal(resolveDisplayState({ taskState: 'review', interactionState: 'waving', dragState: 'running-left' }), 'running-left')
})

test('single click is delayed and a double click cancels it', () => {
  const events = []
  const timers = new Map()
  let id = 0
  const resolver = createClickResolver({
    onSingle: () => events.push('single'),
    onDouble: () => events.push('double'),
    setTimer: callback => { const timer = ++id; timers.set(timer, callback); return timer },
    clearTimer: timer => timers.delete(timer),
  })

  resolver.click()
  assert.deepEqual(events, [])
  resolver.doubleClick()
  assert.deepEqual(events, ['double'])
  for (const callback of timers.values()) callback()
  assert.deepEqual(events, ['double'])

  resolver.click()
  for (const callback of timers.values()) callback()
  assert.deepEqual(events, ['double', 'single'])
})

test('drag direction uses a movement threshold', () => {
  assert.equal(dragDirection(100, 98), null)
  assert.equal(dragDirection(100, 90), 'running-left')
  assert.equal(dragDirection(100, 112), 'running-right')
})

test('hidden pets pause and idle pets throttle after sixty seconds', () => {
  assert.equal(resourceMode({ hidden: true, state: 'running', now: 70_000, lastInteractionAt: 0 }), 'paused')
  assert.equal(resourceMode({ hidden: false, state: 'idle', now: 59_999, lastInteractionAt: 0 }), 'normal')
  assert.equal(resourceMode({ hidden: false, state: 'idle', now: 60_000, lastInteractionAt: 0 }), 'low')
  assert.equal(resourceMode({ hidden: false, state: 'waiting', now: 90_000, lastInteractionAt: 0 }), 'normal')
})
