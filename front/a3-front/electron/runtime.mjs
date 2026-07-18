import path from 'node:path'
import { pathToFileURL } from 'node:url'

export function electronUserDataPath({ appData, testMode, override }) {
  if (testMode === true && typeof override === 'string' && override.trim()) {
    return path.resolve(override.trim())
  }
  return path.join(appData, 'A3LearningAgent')
}

export function backendCommand({ isPackaged, projectDir, resourcesPath, userDataDir }) {
  const backendDir = isPackaged
    ? path.join(resourcesPath, 'backend')
    : path.join(projectDir, 'desktop-backend')

  return {
    command: path.join(backendDir, 'api.exe'),
    args: [],
    cwd: backendDir,
    dataDir: path.join(userDataDir, 'backend'),
  }
}

export function isTrustedRendererUrl(url, indexFile) {
  return typeof url === 'string' && url === pathToFileURL(indexFile).href
}

export function navigationAction(url, indexFile) {
  if (isTrustedRendererUrl(url, indexFile)) return 'allow'
  try {
    const protocol = new URL(url).protocol
    if (protocol === 'http:' || protocol === 'https:') return 'external'
  } catch {
    // Invalid URLs are not trusted navigation targets.
  }
  return 'deny'
}
