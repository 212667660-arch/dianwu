import { describe, expect, it, vi } from 'vitest'

import { createPetTaskStateCoordinator } from './task-state'

describe('pet task state coordinator', () => {
  it('keeps the newest nested task visible and restores the remaining task', async () => {
    const states: string[] = []
    const coordinator = createPetTaskStateCoordinator(async state => { states.push(state) })

    const refresh = coordinator.begin('running')
    const generation = coordinator.begin('running')
    generation.update('review')
    generation.complete('waiting')
    refresh.complete('idle')
    await Promise.resolve()

    expect(states).toEqual(['running', 'review', 'running', 'idle'])
  })

  it('shows failed temporarily then restores the current stable state', async () => {
    const states: string[] = []
    let restore: (() => void) | undefined
    const coordinator = createPetTaskStateCoordinator(async state => { states.push(state) }, {
      setTimer: callback => { restore = callback; return 1 },
      clearTimer: vi.fn(),
    })

    coordinator.set('waiting')
    const task = coordinator.begin('running')
    task.fail()
    await Promise.resolve()
    expect(states).toEqual(['waiting', 'running', 'failed'])

    restore?.()
    await Promise.resolve()
    expect(states.at(-1)).toBe('waiting')
  })

  it('deduplicates repeated states and ignores updates after completion', async () => {
    const send = vi.fn().mockResolvedValue(undefined)
    const coordinator = createPetTaskStateCoordinator(send)
    const task = coordinator.begin('running')
    task.update('running')
    task.complete('waiting')
    task.update('review')
    await Promise.resolve()

    expect(send.mock.calls.map(call => call[0])).toEqual(['running', 'waiting'])
  })
})
