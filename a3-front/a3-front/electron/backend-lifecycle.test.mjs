import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import test from 'node:test'

async function loadLifecycle() {
  return import('./backend-lifecycle.mjs')
}

function createChildProcess() {
  const child = new EventEmitter()
  child.killed = false
  child.killCalls = 0
  child.kill = () => {
    child.killCalls += 1
    child.killed = true
    return true
  }
  return child
}

test('spawn error is handled and terminates the child before startup rejects', async () => {
  const { awaitBackendStartup } = await loadLifecycle()
  const child = createChildProcess()
  const startup = awaitBackendStartup(child, () => new Promise(() => {}))
  const spawnError = new Error('spawn failed')

  child.emit('error', spawnError)

  await assert.rejects(startup, spawnError)
  assert.equal(child.killCalls, 1)
  assert.equal(child.killed, true)
})

test('health-check startup failure terminates the still-running child before rejecting', async () => {
  const { awaitBackendStartup } = await loadLifecycle()
  const child = createChildProcess()
  const healthError = new Error('health check failed')

  await assert.rejects(
    awaitBackendStartup(child, async () => { throw healthError }),
    healthError,
  )
  assert.equal(child.killCalls, 1)
  assert.equal(child.killed, true)
})

test('successful health check removes temporary startup error and exit listeners', async () => {
  const { awaitBackendStartup } = await loadLifecycle()
  const child = createChildProcess()

  await awaitBackendStartup(child, async () => {})

  assert.equal(child.listenerCount('error'), 0)
  assert.equal(child.listenerCount('exit'), 0)
})

test('child exit before health readiness rejects promptly without waiting for health polling', async () => {
  const { awaitBackendStartup } = await loadLifecycle()
  const child = createChildProcess()
  const startup = awaitBackendStartup(child, () => new Promise(() => {}))

  child.emit('exit', 7, null)

  await assert.rejects(
    Promise.race([
      startup,
      new Promise((_, reject) => setTimeout(() => reject(new Error('startup remained pending after child exit')), 50)),
    ]),
    /exited before becoming ready/,
  )
})

test('an intentionally replaced backend cannot mark the current backend offline', async () => {
  const { shouldNotifyBackendExit } = await loadLifecycle()
  const oldBackend = createChildProcess()
  const currentBackend = createChildProcess()

  assert.equal(shouldNotifyBackendExit(currentBackend, oldBackend, false), false)
  assert.equal(shouldNotifyBackendExit(currentBackend, currentBackend, false), true)
  assert.equal(shouldNotifyBackendExit(currentBackend, currentBackend, true), false)
})
