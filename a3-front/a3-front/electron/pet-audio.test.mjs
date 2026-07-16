import assert from 'node:assert/strict'
import test from 'node:test'

import { audioCueForState, createBrowserPetAudioRuntime, createPetAudioRuntime } from './pet/pet-audio.js'

const settings = {
  soundEnabled: true, soundVolume: 0.5, voiceEnabled: true, voiceVolume: 0.75,
}

test('audio cues map only low-frequency pet states and interactions', () => {
  assert.equal(audioCueForState('review'), 'review')
  assert.equal(audioCueForState('waiting'), 'complete')
  assert.equal(audioCueForState('failed'), 'failed')
  assert.equal(audioCueForState('running'), null)
  assert.equal(audioCueForState('idle'), null)
})

test('audio runtime keeps sound and voice volumes independent', () => {
  const cues = []
  const speeches = []
  const runtime = createPetAudioRuntime({
    now: () => 40_000,
    playCue: (name, volume) => cues.push({ name, volume }),
    speak: (text, volume) => speeches.push({ text, volume }),
  })
  runtime.updateSettings(settings)
  runtime.playInteraction('waving')
  runtime.handleState('waiting')

  assert.deepEqual(cues, [{ name: 'wave', volume: 0.5 }, { name: 'complete', volume: 0.5 }])
  assert.equal(speeches.length, 1)
  assert.equal(speeches[0].volume, 0.75)
  assert.match(speeches[0].text, /完成|很好|休息/)
})

test('voice cooldown, repeated states, visibility and disabled channels suppress playback', () => {
  let time = 40_000
  const cues = []
  const speeches = []
  let stoppedCue = 0
  let stoppedSpeech = 0
  const runtime = createPetAudioRuntime({
    now: () => time,
    playCue: (...args) => cues.push(args),
    speak: (...args) => speeches.push(args),
    stopCue: () => { stoppedCue += 1 },
    stopSpeech: () => { stoppedSpeech += 1 },
  })
  runtime.updateSettings(settings)
  runtime.handleState('waiting')
  runtime.handleState('waiting')
  runtime.handleState('review')
  runtime.handleState('waiting')
  assert.equal(speeches.length, 1)

  time += 30_000
  runtime.handleState('running')
  runtime.handleState('waiting')
  assert.equal(speeches.length, 2)

  runtime.setHidden(true)
  runtime.handleState('failed')
  runtime.playInteraction('jumping')
  assert.equal(stoppedCue, 1)
  assert.equal(stoppedSpeech, 1)
  assert.equal(speeches.length, 2)

  runtime.setHidden(false)
  runtime.updateSettings({ ...settings, soundEnabled: false, voiceEnabled: false })
  runtime.handleState('running')
  runtime.handleState('failed')
  assert.equal(cues.length, 4)
  assert.equal(speeches.length, 2)
})

test('failed encouragement interrupts ordinary speech and bypasses cooldown', () => {
  const speeches = []
  let stops = 0
  const runtime = createPetAudioRuntime({
    now: () => 50_000,
    playCue: () => {},
    speak: (...args) => speeches.push(args),
    stopSpeech: () => { stops += 1 },
  })
  runtime.updateSettings(settings)
  runtime.handleState('waiting')
  runtime.handleState('failed')

  assert.equal(stops, 1)
  assert.equal(speeches.length, 2)
  assert.match(speeches[1][0], /没关系|慢慢来|再试/)
})

test('pending browser audio is cancelled when the pet becomes hidden', async () => {
  let resolveResume
  let oscillatorsCreated = 0
  class FakeAudioContext {
    state = 'suspended'
    currentTime = 0
    destination = {}
    resume() {
      return new Promise(resolve => {
        resolveResume = () => { this.state = 'running'; resolve() }
      })
    }
    suspend() { this.state = 'suspended'; return Promise.resolve() }
    createGain() {
      return { gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() { return this } }
    }
    createOscillator() {
      oscillatorsCreated += 1
      return { frequency: { setValueAtTime() {} }, connect() { return this }, start() {}, stop() {} }
    }
  }
  const runtime = createBrowserPetAudioRuntime({ AudioContext: FakeAudioContext })
  runtime.updateSettings({ soundEnabled: true, soundVolume: 1 })
  runtime.playInteraction('waving')
  runtime.setHidden(true)
  resolveResume()
  await Promise.resolve()
  await Promise.resolve()

  assert.equal(oscillatorsCreated, 0)
})

test('browser audio suspends its context after the final note ends', async () => {
  const oscillators = []
  let suspendCalls = 0
  class FakeAudioContext {
    state = 'suspended'
    currentTime = 0
    destination = {}
    resume() { this.state = 'running'; return Promise.resolve() }
    suspend() { suspendCalls += 1; this.state = 'suspended'; return Promise.resolve() }
    createGain() {
      return { gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} }, connect() { return this } }
    }
    createOscillator() {
      const oscillator = { frequency: { setValueAtTime() {} }, connect() { return this }, start() {}, stop() {}, onended: null }
      oscillators.push(oscillator)
      return oscillator
    }
  }
  const runtime = createBrowserPetAudioRuntime({ AudioContext: FakeAudioContext })
  runtime.updateSettings({ soundEnabled: true, soundVolume: 1 })
  runtime.playInteraction('waving')
  await Promise.resolve()
  await Promise.resolve()
  oscillators.at(-1)?.onended?.()
  await Promise.resolve()

  assert.equal(suspendCalls, 1)
})
