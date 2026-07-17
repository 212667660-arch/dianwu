import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

import { createDesktopStateStore } from './desktop-state.mjs'

async function fixture() {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'a3-desktop-state-'))
  const filePath = path.join(root, 'desktop-state.json')
  return { root, filePath, store: createDesktopStateStore({ fs, filePath }) }
}

test('new and corrupt desktop state recover to safe version one defaults', async t => {
  const { root, filePath, store } = await fixture()
  t.after(() => fs.rm(root, { recursive: true, force: true }))

  assert.deepEqual(await store.load(), {
    version: 1, onboarding_completed: false, ai_paused: false,
  })
  await fs.writeFile(filePath, '{broken', 'utf8')
  assert.deepEqual(await store.load(), {
    version: 1, onboarding_completed: false, ai_paused: false,
  })
})

test('desktop state writes atomically and persists onboarding and AI pause', async t => {
  const { root, filePath, store } = await fixture()
  t.after(() => fs.rm(root, { recursive: true, force: true }))

  await store.load()
  await store.completeOnboarding()
  await store.setAiPaused(true)

  assert.deepEqual(JSON.parse(await fs.readFile(filePath, 'utf8')), {
    version: 1, onboarding_completed: true, ai_paused: true,
  })
  await assert.rejects(fs.access(`${filePath}.tmp`))
})
