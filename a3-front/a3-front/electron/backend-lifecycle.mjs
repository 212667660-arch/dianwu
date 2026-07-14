export function stopBackendProcess(childProcess) {
  if (!childProcess || childProcess.killed) return false
  try {
    return childProcess.kill()
  } catch {
    return false
  }
}

export function shouldNotifyBackendExit(currentProcess, exitedProcess, isQuitting) {
  return currentProcess === exitedProcess && isQuitting !== true
}

export function awaitBackendStartup(childProcess, waitForHealthy) {
  return new Promise((resolve, reject) => {
    let startupFinished = false

    const cleanupStartupListeners = () => {
      childProcess.removeListener('error', handleSpawnError)
      childProcess.removeListener('exit', handleEarlyExit)
    }

    const failStartup = (error, stopProcess = true) => {
      if (startupFinished) return
      startupFinished = true
      cleanupStartupListeners()
      if (stopProcess) stopBackendProcess(childProcess)
      reject(error)
    }

    const handleSpawnError = (error) => failStartup(error)
    const handleEarlyExit = (code, signal) => {
      const reason = signal ? `signal ${signal}` : `code ${code ?? 'unknown'}`
      failStartup(new Error(`Backend exited before becoming ready (${reason})`), false)
    }

    childProcess.once('error', handleSpawnError)
    childProcess.once('exit', handleEarlyExit)
    Promise.resolve()
      .then(waitForHealthy)
      .then(() => {
        if (startupFinished) return
        startupFinished = true
        cleanupStartupListeners()
        resolve()
      }, failStartup)
  })
}
