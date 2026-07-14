import assert from 'node:assert/strict'
import { execSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'

const projectDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

async function loadRuntime() {
  return import('./runtime.mjs')
}

test('runtime source no longer contains the legacy runtime-info authorization helper', () => {
  const runtimeSource = fs.readFileSync(path.join(projectDir, 'electron', 'runtime.mjs'), 'utf8')

  assert.doesNotMatch(runtimeSource, /canAccessRuntimeInfo/)
})

test('only test mode can override Electron userData for isolated package verification', async () => {
  const { electronUserDataPath } = await loadRuntime()
  const appData = 'C:\\Users\\student\\AppData\\Roaming'
  const isolated = 'E:\\workspace\\isolated-user-data'

  assert.equal(
    electronUserDataPath({ appData, testMode: true, override: isolated }),
    path.resolve(isolated),
  )
  assert.equal(
    electronUserDataPath({ appData, testMode: false, override: isolated }),
    path.join(appData, 'A3LearningAgent'),
  )
  assert.equal(
    electronUserDataPath({ appData, testMode: true, override: '' }),
    path.join(appData, 'A3LearningAgent'),
  )
})

test('backend commands remain within the project in development and packaged resources in production', async () => {
  const { backendCommand } = await loadRuntime()
  const userDataDir = path.join(projectDir, '.test-user-data')
  const development = backendCommand({
    isPackaged: false,
    projectDir,
    resourcesPath: path.join(projectDir, '.unused-resources'),
    userDataDir,
  })
  const productionResources = path.join(projectDir, '.test-resources')
  const production = backendCommand({
    isPackaged: true,
    projectDir,
    resourcesPath: productionResources,
    userDataDir,
  })

  assert.deepEqual(development, {
    command: path.join(projectDir, 'desktop-backend', 'api.exe'),
    args: [],
    cwd: path.join(projectDir, 'desktop-backend'),
    dataDir: path.join(userDataDir, 'backend'),
  })
  assert.deepEqual(production, {
    command: path.join(productionResources, 'backend', 'api.exe'),
    args: [],
    cwd: path.join(productionResources, 'backend'),
    dataDir: path.join(userDataDir, 'backend'),
  })
})

test('navigation permits only the renderer index file and sends web links outside the app', async () => {
  const { navigationAction } = await loadRuntime()
  const indexFile = path.join(projectDir, 'dist', 'index.html')

  assert.equal(navigationAction(pathToFileURL(indexFile).href, indexFile), 'allow')
  assert.equal(navigationAction(pathToFileURL(path.join(projectDir, 'dist', 'other.html')).href, indexFile), 'deny')
  assert.equal(navigationAction('file:///C:/untrusted/index.html', indexFile), 'deny')
  assert.equal(navigationAction('https://example.com/resource', indexFile), 'external')
})

test('packaging embeds the backend only from the project desktop-backend directory', () => {
  const packageJson = JSON.parse(fs.readFileSync(path.join(projectDir, 'package.json'), 'utf8'))

  assert.deepEqual(packageJson.build.extraResources, [
    { from: 'desktop-backend', to: 'backend' },
  ])
})

function runBuild(base) {
  const baseArgument = base ? ` --base=${base}` : ''
  execSync(`npx vite build${baseArgument}`, { cwd: projectDir, encoding: 'utf8' })
}

function builtAssetUrls() {
  const indexFile = path.join(projectDir, 'dist', 'index.html')
  const html = fs.readFileSync(indexFile, 'utf8')
  return [...html.matchAll(/(?:src|href)="([^"]+\.(?:js|css))"/g)].map((match) => match[1])
}

test('web builds keep root asset URLs while Electron builds resolve relative assets from dist', () => {
  runBuild()
  const webAssetUrls = builtAssetUrls()

  assert.ok(webAssetUrls.length > 0, 'the web build must reference JavaScript or CSS assets')
  for (const resourceUrl of webAssetUrls) {
    assert.ok(resourceUrl.startsWith('/assets/'), `web resource must use the root asset path: ${resourceUrl}`)
  }

  runBuild('./')
  const desktopAssetUrls = builtAssetUrls()
  const indexFile = path.join(projectDir, 'dist', 'index.html')
  const indexUrl = pathToFileURL(indexFile)
  const assetsDir = path.join(projectDir, 'dist', 'assets')

  assert.ok(desktopAssetUrls.length > 0, 'the Electron build must reference JavaScript or CSS assets')
  for (const resourceUrl of desktopAssetUrls) {
    assert.ok(!resourceUrl.startsWith('/'), `resource must be relative: ${resourceUrl}`)
    const resourcePath = fileURLToPath(new URL(resourceUrl, indexUrl))
    assert.ok(resourcePath.startsWith(`${assetsDir}${path.sep}`), `resource must resolve inside dist/assets: ${resourceUrl}`)
    assert.ok(fs.existsSync(resourcePath), `resolved resource must exist: ${resourcePath}`)
  }
})

test('preload does not expose the removed external-link IPC capability', () => {
  const preload = fs.readFileSync(path.join(projectDir, 'electron', 'preload.mjs'), 'utf8')
  const client = fs.readFileSync(path.join(projectDir, 'src', 'api', 'client.ts'), 'utf8')

  assert.doesNotMatch(preload, /a3:open-external|openExternal/)
  assert.doesNotMatch(client, /openExternal/)
})

test('preload and renderer client do not contain runtime token or backend address injection', () => {
  const preload = fs.readFileSync(path.join(projectDir, 'electron', 'preload.mjs'), 'utf8')
  const client = fs.readFileSync(path.join(projectDir, 'src', 'api', 'client.ts'), 'utf8')

  assert.doesNotMatch(preload, /desktopToken|apiBaseUrl|a3:runtime-info/)
  assert.doesNotMatch(client, /desktopToken|window\.a3Desktop\?\.apiBaseUrl/)
})

test('preload exposes fixed request, stream, and model config bridge methods only', () => {
  const preload = fs.readFileSync(path.join(projectDir, 'electron', 'preload.mjs'), 'utf8')

  for (const name of [
    'request:',
    'startStream:',
    'cancelStream:',
    'onStreamEvent:',
    'onBackendExit:',
    'modelConfigTest:',
    'modelConfigSave:',
  ]) {
    assert.match(preload, new RegExp(name))
  }
  assert.doesNotMatch(preload, /(?:^|[,{]\s*)ipcRenderer\s*:/m)
  assert.doesNotMatch(preload, /openExternal/)
})

test('main process owns encrypted model config, startup injection, and fixed config IPC', () => {
  const main = fs.readFileSync(path.join(projectDir, 'electron', 'main.mjs'), 'utf8')

  assert.match(main, /safeStorage/)
  assert.match(main, /createModelConfigStore/)
  assert.match(main, /modelEnvironment/)
  assert.match(main, /createModelConfigController/)
  assert.match(main, /a3:model-config-test/)
  assert.match(main, /a3:model-config-save/)
  assert.match(main, /model-settings\.enc/)
  assert.doesNotMatch(main, /console\.(?:log|error)\([^\n]*api_key/i)
})

test('renderer, preload, and desktop bundle do not receive token or backend address injection', () => {
  const rendererFiles = [
    path.join(projectDir, 'electron', 'preload.mjs'),
    path.join(projectDir, 'src', 'api', 'backend.ts'),
    path.join(projectDir, 'src', 'api', 'client.ts'),
    path.join(projectDir, 'src', 'api', 'desktop-transport.ts'),
    path.join(projectDir, 'src', 'views', 'ModelSettings.vue'),
  ]
  for (const file of rendererFiles) {
    const source = fs.readFileSync(file, 'utf8')
    assert.doesNotMatch(source, /desktopToken|apiBaseUrl|X-A3-Desktop-Token|MODEL_API_KEY/)
  }
  const preload = fs.readFileSync(path.join(projectDir, 'electron', 'preload.mjs'), 'utf8')
  assert.doesNotMatch(preload, /safeStorage|model-settings\.enc/)
  const assetsDir = path.join(projectDir, 'dist', 'assets')
  const emitted = fs.readdirSync(assetsDir).filter(name => name.endsWith('.js'))
  assert.ok(emitted.length > 0, 'desktop build must contain renderer JavaScript')
  for (const file of emitted) {
    assert.doesNotMatch(fs.readFileSync(path.join(assetsDir, file), 'utf8'), /desktopToken|X-A3-Desktop-Token|MODEL_API_KEY/)
  }
})

test('test-mode startup forces Electron exit after the backend has stopped', () => {
  const main = fs.readFileSync(path.join(projectDir, 'electron', 'main.mjs'), 'utf8')
  const testModeExit = main.match(/async function exitTestMode\(\) \{[\s\S]*?\n\}/)?.[0]

  assert.match(main, /A3_ELECTRON_TEST_MODE/)
  assert.ok(testModeExit, 'test-mode exit handler must exist')
  assert.match(testModeExit, /await stopBackend\(\)/)
  assert.match(testModeExit, /await log\('test-mode forcing process exit'\)/)
  assert.match(testModeExit, /process\.exit\(0\)/)
  assert.doesNotMatch(testModeExit, /mainWindow\.destroy\(\)|app\.exit\(0\)/)
})

test('window close cleanup does not read webContents from a destroyed BrowserWindow', () => {
  const main = fs.readFileSync(path.join(projectDir, 'electron', 'main.mjs'), 'utf8')

  assert.match(main, /const mainWebContents = mainWindow\.webContents/)
  assert.match(main, /mainWindow\.on\('closed', \(\) => \{[\s\S]*cleanupWebContents\(mainWebContents\)/)
  assert.doesNotMatch(main, /cleanupWebContents\(mainWindow\?\.webContents\)/)
})
