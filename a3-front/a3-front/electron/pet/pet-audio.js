const VOICE_COOLDOWN_MS = 30_000
const SPEECH_LINES = Object.freeze({
  waiting: Object.freeze([
    '这一小步完成得很好，可以轻轻休息一下。',
    '做得很好，我会在这里等你继续。',
    '今天的努力已经留下痕迹了。',
  ]),
  failed: Object.freeze([
    '没关系，我们慢慢来，再试一次就好。',
    '这次没有完成也没关系，我会陪你重新整理。',
    '先停一下呼吸，再试一次也来得及。',
  ]),
})

const CUE_NOTES = Object.freeze({
  wave: [[660, 0.07], [820, 0.09]],
  jump: [[520, 0.06], [700, 0.06], [900, 0.1]],
  review: [[540, 0.08], [620, 0.08]],
  complete: [[620, 0.08], [780, 0.08], [980, 0.12]],
  failed: [[420, 0.1], [350, 0.16]],
})

export function audioCueForState(state) {
  return { review: 'review', waiting: 'complete', failed: 'failed' }[state] || null
}

export function createPetAudioRuntime({
  now = () => Date.now(),
  playCue = () => {},
  speak = () => {},
  stopCue = () => {},
  stopSpeech = () => {},
} = {}) {
  let settings = { soundEnabled: false, soundVolume: 0, voiceEnabled: false, voiceVolume: 0 }
  let hidden = false
  let lastState = null
  let lastSpeechAt = Number.NEGATIVE_INFINITY
  let speechIndex = 0

  function updateSettings(next) {
    settings = { ...settings, ...next }
    if (!settings.soundEnabled || settings.soundVolume === 0) stopCue()
    if (!settings.voiceEnabled || settings.voiceVolume === 0) stopSpeech()
  }

  function setHidden(value) {
    hidden = Boolean(value)
    if (hidden) {
      stopCue()
      stopSpeech()
    }
  }

  function playInteraction(state) {
    if (hidden || !settings.soundEnabled || settings.soundVolume === 0) return
    const cue = state === 'waving' ? 'wave' : state === 'jumping' ? 'jump' : null
    if (cue) playCue(cue, settings.soundVolume)
  }

  function handleState(state) {
    if (state === lastState) return
    lastState = state
    if (hidden) return
    const cue = audioCueForState(state)
    if (cue && settings.soundEnabled && settings.soundVolume > 0) playCue(cue, settings.soundVolume)
    if (!SPEECH_LINES[state] || !settings.voiceEnabled || settings.voiceVolume === 0) return
    const timestamp = now()
    if (state !== 'failed' && timestamp - lastSpeechAt < VOICE_COOLDOWN_MS) return
    if (state === 'failed') stopSpeech()
    const lines = SPEECH_LINES[state]
    const text = lines[speechIndex % lines.length]
    speechIndex += 1
    lastSpeechAt = timestamp
    speak(text, settings.voiceVolume)
  }

  function stop() {
    stopCue()
    stopSpeech()
  }

  return { updateSettings, setHidden, playInteraction, handleState, stop }
}

export function createBrowserPetAudioRuntime(scope) {
  const AudioContextClass = scope.AudioContext || scope.webkitAudioContext
  const synthesizer = scope.speechSynthesis
  let audioContext = null
  let activeNodes = []
  let cueVersion = 0

  function stopCue() {
    cueVersion += 1
    for (const node of activeNodes) {
      try { node.stop() } catch {}
    }
    activeNodes = []
    if (audioContext?.state === 'running') void audioContext.suspend().catch(() => undefined)
  }

  function playCue(name, volume) {
    if (!AudioContextClass || !CUE_NOTES[name]) return
    try {
      cueVersion += 1
      const currentVersion = cueVersion
      for (const node of activeNodes) {
        try { node.stop() } catch {}
      }
      activeNodes = []
      audioContext ||= new AudioContextClass()
      void audioContext.resume().then(() => {
        if (currentVersion !== cueVersion) return
        let startsAt = audioContext.currentTime
        activeNodes = CUE_NOTES[name].map(([frequency, duration]) => {
          const oscillator = audioContext.createOscillator()
          const gain = audioContext.createGain()
          oscillator.type = 'sine'
          oscillator.frequency.setValueAtTime(frequency, startsAt)
          gain.gain.setValueAtTime(0.0001, startsAt)
          gain.gain.exponentialRampToValueAtTime(Math.max(0.0001, volume * 0.08), startsAt + 0.012)
          gain.gain.exponentialRampToValueAtTime(0.0001, startsAt + duration)
          oscillator.connect(gain).connect(audioContext.destination)
          oscillator.start(startsAt)
          oscillator.stop(startsAt + duration + 0.01)
          startsAt += duration
          return oscillator
        })
        const finalNode = activeNodes.at(-1)
        if (finalNode) finalNode.onended = () => {
          if (currentVersion !== cueVersion) return
          activeNodes = []
          if (audioContext?.state === 'running') void audioContext.suspend().catch(() => undefined)
        }
      }).catch(() => undefined)
    } catch {}
  }

  function stopSpeech() {
    try { synthesizer?.cancel() } catch {}
  }

  function speak(text, volume) {
    if (!synthesizer || !scope.SpeechSynthesisUtterance) return
    try {
      const utterance = new scope.SpeechSynthesisUtterance(text)
      utterance.lang = 'zh-CN'
      utterance.volume = volume
      utterance.rate = 0.96
      utterance.pitch = 1.05
      const voices = synthesizer.getVoices?.() || []
      utterance.voice = voices.find(voice => voice.lang?.toLowerCase().startsWith('zh') && voice.localService)
        || voices.find(voice => voice.lang?.toLowerCase().startsWith('zh'))
        || null
      synthesizer.cancel()
      synthesizer.speak(utterance)
    } catch {}
  }

  return createPetAudioRuntime({ playCue, speak, stopCue, stopSpeech })
}
