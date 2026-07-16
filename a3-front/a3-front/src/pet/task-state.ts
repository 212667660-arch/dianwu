import { backendApi, type PetTaskState } from '@/api'

export interface PetTaskTicket {
  update(state: PetTaskState): void
  complete(state?: PetTaskState): void
  fail(): void
}

interface TimerOptions {
  setTimer?: (callback: () => void, delay: number) => unknown
  clearTimer?: (timer: unknown) => void
  failedDuration?: number
}

export function createPetTaskStateCoordinator(
  send: (state: PetTaskState) => Promise<unknown>,
  options: TimerOptions = {},
) {
  const tasks: Array<{ id: symbol; state: PetTaskState }> = []
  const setTimer = options.setTimer || setTimeout
  const clearTimer = options.clearTimer || (timer => clearTimeout(timer as ReturnType<typeof setTimeout>))
  const failedDuration = options.failedDuration ?? 4200
  let baseState: PetTaskState = 'idle'
  let lastPublished: PetTaskState | null = null
  let failedTimer: unknown | null = null

  function visibleState() { return tasks.at(-1)?.state || baseState }
  function publish(state = visibleState(), force = false) {
    if (!force && state === lastPublished) return
    lastPublished = state
    void Promise.resolve(send(state)).catch(() => undefined)
  }
  function set(state: PetTaskState) {
    baseState = state
    if (!tasks.length) publish()
  }
  function begin(state: PetTaskState = 'running'): PetTaskTicket {
    const task = { id: Symbol('pet-task'), state }
    tasks.push(task)
    publish()
    let closed = false
    return {
      update(next) {
        if (closed) return
        task.state = next
        publish()
      },
      complete(next = 'waiting') {
        if (closed) return
        closed = true
        baseState = next
        removeTask(task.id)
        publish()
      },
      fail() {
        if (closed) return
        closed = true
        removeTask(task.id)
        if (failedTimer !== null) clearTimer(failedTimer)
        publish('failed', true)
        failedTimer = setTimer(() => {
          failedTimer = null
          publish(visibleState(), true)
        }, failedDuration)
      },
    }
  }
  function removeTask(id: symbol) {
    const index = tasks.findIndex(task => task.id === id)
    if (index >= 0) tasks.splice(index, 1)
  }
  return { set, begin }
}

export const petTaskState = createPetTaskStateCoordinator(state => backendApi.setPetTaskState(state))
