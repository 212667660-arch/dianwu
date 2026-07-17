const DEFAULT_STATE = Object.freeze({
  version: 1,
  onboarding_completed: false,
  ai_paused: false,
})

export function createDesktopStateStore({ fs, filePath }) {
  let state = { ...DEFAULT_STATE }
  let loaded = false

  return {
    async load() {
      state = await readState(fs, filePath)
      loaded = true
      return snapshot()
    },
    snapshot,
    async completeOnboarding() {
      ensureLoaded()
      state.onboarding_completed = true
      await persist()
      return snapshot()
    },
    async setAiPaused(value) {
      ensureLoaded()
      if (typeof value !== 'boolean') throw new TypeError('AI pause state must be boolean.')
      state.ai_paused = value
      await persist()
      return snapshot()
    },
  }

  function snapshot() {
    return { ...state }
  }

  function ensureLoaded() {
    if (!loaded) throw new Error('Desktop state is not loaded.')
  }

  async function persist() {
    await fs.mkdir(pathDirectory(filePath), { recursive: true })
    const temporary = `${filePath}.tmp`
    await fs.writeFile(temporary, `${JSON.stringify(state, null, 2)}\n`, 'utf8')
    await fs.rename(temporary, filePath)
  }
}

async function readState(fs, filePath) {
  try {
    const value = JSON.parse(await fs.readFile(filePath, 'utf8'))
    if (
      value?.version === 1
      && typeof value.onboarding_completed === 'boolean'
      && typeof value.ai_paused === 'boolean'
    ) return { version: 1, onboarding_completed: value.onboarding_completed, ai_paused: value.ai_paused }
  } catch {}
  return { ...DEFAULT_STATE }
}

function pathDirectory(filePath) {
  const slash = Math.max(filePath.lastIndexOf('/'), filePath.lastIndexOf('\\'))
  return slash > 0 ? filePath.slice(0, slash) : '.'
}
