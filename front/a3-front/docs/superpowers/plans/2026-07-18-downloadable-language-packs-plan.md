# Downloadable Language Packs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `zh-CN` the complete offline built-in language, add verified downloadable `en-US` and `zh-TW` packs with offline `.a3lang` import and atomic rollback, and make new AI-generated learning content follow the active UI locale without changing internal protocols.

**Architecture:** The renderer owns Vue message rendering but receives downloadable data only through fixed Electron IPC. The Electron main process owns the active locale, signed catalog, download allowlist, archive verification, versioned installation, last-known-good recovery, native messages, and the controlled `X-A3-Content-Locale` backend header. The backend validates that header and appends a locale instruction to every model-facing prompt while preserving Chinese protocol labels, canonical enums, parsers, database values, and stable error codes.

**Tech Stack:** Vue 3, Pinia, vue-i18n 11, Electron 32, Node.js `crypto` Ed25519, RFC 8785 canonical JSON, `yauzl`/`yazl`, SemVer, Vitest, Node built-in tests, FastAPI, pytest, GitHub Releases, GitHub Actions.

---

### Task 1: Establish the Built-In Catalog Contract

**Files:**
- Create: `front/a3-front/src/i18n/catalog.ts`
- Create: `front/a3-front/src/i18n/catalog.test.ts`
- Create: `front/a3-front/src/i18n/locales/zh-CN/messages/common.json`
- Create: `front/a3-front/src/i18n/locales/zh-CN/messages/navigation.json`
- Create: `front/a3-front/src/i18n/locales/zh-CN/messages/views/dashboard.json`
- Create: `front/a3-front/src/i18n/locales/zh-CN/messages/views/profile.json`
- Create: `front/a3-front/src/i18n/locales/zh-CN/messages/views/agents.json`
- Create: `front/a3-front/src/i18n/locales/zh-CN/messages/views/learning-path.json`
- Create: `front/a3-front/src/i18n/locales/zh-CN/messages/views/tutor.json`
- Create: `front/a3-front/src/i18n/locales/zh-CN/messages/views/assessment.json`
- Create: `front/a3-front/src/i18n/locales/zh-CN/messages/views/knowledge.json`
- Create: `front/a3-front/src/i18n/locales/zh-CN/messages/views/model-settings.json`
- Create: `front/a3-front/src/i18n/locales/zh-CN/messages/views/desktop-settings.json`
- Create: `front/a3-front/src/i18n/locales/zh-CN/messages/views/onboarding.json`
- Create: `front/a3-front/src/i18n/locales/zh-CN/messages/components.json`
- Create: `front/a3-front/src/i18n/locales/zh-CN/messages/statuses.json`
- Create: `front/a3-front/src/i18n/locales/zh-CN/messages/errors.json`
- Create: `front/a3-front/src/i18n/locales/zh-CN/messages/desktop.json`
- Create: `front/a3-front/src/i18n/locales/zh-CN/messages/pet.json`
- Create: `front/a3-front/src/i18n/locales/zh-CN/content/offline-demo.json`
- Modify: `front/a3-front/package.json`
- Modify: `front/a3-front/package-lock.json`

- [ ] **Step 1: Add the catalog tests before the runtime dependency**

The tests import `BUILT_IN_MESSAGES`, `CATALOG_VERSION`, `BASE_CATALOG_HASH`, `flattenMessages`, and `placeholdersFor`. Assert:

```ts
expect(CATALOG_VERSION).toBe(1)
expect(Object.keys(flattenMessages(BUILT_IN_MESSAGES))).toContain('navigation.dashboard')
expect(Object.keys(flattenMessages(BUILT_IN_MESSAGES))).toContain('views.desktopSettings.language.title')
expect(Object.keys(flattenMessages(BUILT_IN_MESSAGES))).toContain('errors.BACKEND_UNAVAILABLE')
expect(Object.keys(flattenMessages(BUILT_IN_MESSAGES))).toContain('desktop.tray.quit')
expect(placeholdersFor('已导出 {fileName}')).toEqual(['fileName'])
expect(BASE_CATALOG_HASH).toMatch(/^[A-F0-9]{64}$/)
```

Also walk every value and reject non-string leaves, empty strings, HTML tags, control characters other than `\n`/`\t`, and object keys `__proto__`, `prototype`, or `constructor`.

- [ ] **Step 2: Run the focused test and confirm RED**

```powershell
cd front/a3-front
npx vitest run src/i18n/catalog.test.ts
```

Expected: FAIL because `src/i18n/catalog.ts` does not exist.

- [ ] **Step 3: Add dependencies and a deterministic catalog implementation**

Install exact compatible packages through npm so lockfile integrity is updated:

```powershell
npm install vue-i18n@^11.1.12 canonicalize@^2.1.0 semver@^7.7.2 yauzl@^3.2.0 @noble/hashes@^1.8.0
npm install --save-dev yazl@^3.3.1 @types/yauzl@^2.10.3
```

`catalog.ts` imports every JSON namespace, builds this root object, and exposes pure helpers:

```ts
export const CATALOG_VERSION = 1
export const BUILT_IN_LOCALE = 'zh-CN' as const
export const DOWNLOADABLE_LOCALES = ['en-US', 'zh-TW'] as const

export const BUILT_IN_MESSAGES = Object.freeze({
  common, navigation,
  views: { dashboard, profile, agents, learningPath, tutor, assessment, knowledge, modelSettings, desktopSettings, onboarding },
  components, statuses, errors, desktop, pet,
})

export function flattenMessages(input: unknown, prefix = '', output: Record<string, string> = {}) {
  if (typeof input === 'string') { output[prefix] = input; return output }
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new TypeError(`Invalid catalog node: ${prefix || '<root>'}`)
  for (const [key, value] of Object.entries(input)) {
    if (['__proto__', 'prototype', 'constructor'].includes(key)) throw new TypeError(`Forbidden catalog key: ${key}`)
    flattenMessages(value, prefix ? `${prefix}.${key}` : key, output)
  }
  return output
}

export function placeholdersFor(value: string) {
  return [...value.matchAll(/\{([A-Za-z][A-Za-z0-9_]*)\}/g)].map(match => match[1]).sort()
}
```

Compute `BASE_CATALOG_HASH` from canonical JSON containing `catalog_version` plus sorted flattened key/placeholder pairs, then SHA-256 it synchronously with `@noble/hashes/sha256` and uppercase hex encoding. Keep the same canonical payload shape in Electron verification and companion-repository tooling and assert all three implementations produce the identical digest fixture.

- [ ] **Step 4: Populate the complete Chinese catalog**

Use these exact namespace responsibilities:

```text
common: buttons, form labels, punctuation-safe templates, generic empty/loading/error text
navigation: brand, route titles, session/desk labels, service state
views.*: text owned by the corresponding Vue view
components: knowledge, learning, model, workspace and pet component text grouped by component name
statuses: canonical API enum display maps without changing the enum values
errors: stable backend/Electron code to Chinese user message
desktop: tray, native dialogs, diagnostics, import filters, startup and updater text
pet: speech lines and native pet labels
content/offline-demo: deterministic demo titles, messages, steps and resource prose
```

Every currently visible Simplified Chinese string from the 43-file inventory must have one key. Internal protocol tokens in `src/utils/protocol.ts`, canonical API enum literals in `src/api/types.ts`, and backend-compatible Chinese fallback `message` values are not translated or used as catalog keys.

- [ ] **Step 5: Run catalog GREEN and commit**

```powershell
npx vitest run src/i18n/catalog.test.ts
git add package.json package-lock.json src/i18n
git commit -m "feat: add built-in Chinese message catalog"
```

### Task 2: Bootstrap vue-i18n, Formatting, and Localized Errors

**Files:**
- Create: `front/a3-front/src/i18n/index.ts`
- Create: `front/a3-front/src/i18n/formatters.ts`
- Create: `front/a3-front/src/i18n/errors.ts`
- Create: `front/a3-front/src/i18n/runtime.test.ts`
- Modify: `front/a3-front/src/main.ts`
- Modify: `front/a3-front/src/tests/setup.ts`
- Modify: `front/a3-front/src/api/client.ts`
- Modify: `front/a3-front/src/api/transport.ts`
- Modify: `front/a3-front/src/api/web-transport.ts`

- [ ] **Step 1: Write runtime and error tests**

Assert the runtime starts in `zh-CN`, cannot remove the built-in messages, formats `12345.6` and a fixed UTC date through `Intl`, localizes a known `BackendApiError` by `errors.<CODE>`, and formats an unknown code as a generic message containing both `code` and `requestId` but not the backend-provided Chinese message.

```ts
const known = new BackendApiError(503, 'BACKEND_UNAVAILABLE', '后端原始消息', true, 'req-1')
expect(localizedErrorMessage(known)).toBe(BUILT_IN_MESSAGES.errors.BACKEND_UNAVAILABLE)
const unknown = new BackendApiError(500, 'NEW_CODE', '内部细节', false, 'req-2')
expect(localizedErrorMessage(unknown)).toContain('NEW_CODE')
expect(localizedErrorMessage(unknown)).toContain('req-2')
expect(localizedErrorMessage(unknown)).not.toContain('内部细节')
```

- [ ] **Step 2: Run RED**

```powershell
npx vitest run src/i18n/runtime.test.ts
```

- [ ] **Step 3: Implement the singleton runtime**

Create `i18n/index.ts`:

```ts
import { createI18n } from 'vue-i18n'
import { BUILT_IN_LOCALE, BUILT_IN_MESSAGES } from './catalog'

export const i18n = createI18n({
  legacy: false,
  locale: BUILT_IN_LOCALE,
  fallbackLocale: BUILT_IN_LOCALE,
  missingWarn: false,
  fallbackWarn: false,
  messages: { [BUILT_IN_LOCALE]: BUILT_IN_MESSAGES },
})

export function installLocaleMessages(locale: string, messages: Record<string, unknown>) {
  i18n.global.setLocaleMessage(locale, messages)
}

export function activateLocale(locale: string) {
  i18n.global.locale.value = i18n.global.availableLocales.includes(locale) ? locale : BUILT_IN_LOCALE
  document.documentElement.lang = i18n.global.locale.value
}
```

`formatters.ts` exposes `formatDate`, `formatDateTime`, `formatNumber`, `formatPercent`, and `formatRelativeTime`, each accepting an explicit locale defaulting to `i18n.global.locale.value` and never using hardcoded `zh-CN`.

`errors.ts` checks `errors.${error.code}` with `i18n.global.te`, otherwise returns `errors.unknownWithReference` using `code` and `requestId || common.notAvailable`.

- [ ] **Step 4: Install the plugin and test helper globally**

In `main.ts`, call `app.use(i18n)` before router. In `src/tests/setup.ts`, append `i18n` to `@vue/test-utils` global plugins so existing component tests continue to mount without per-test boilerplate.

Change `src/api/client.ts` to export `localizedErrorMessage` as `errorMessage`. Keep error envelopes code-first in `transport.ts` and `web-transport.ts`; their Chinese `message` remains only the compatibility fallback stored on the error object.

- [ ] **Step 5: Run focused and API tests, then commit**

```powershell
npx vitest run src/i18n/runtime.test.ts src/api/backend.test.ts src/api/web-transport.test.ts src/api/desktop-transport.test.ts
git add src/main.ts src/tests/setup.ts src/i18n src/api/client.ts src/api/transport.ts src/api/web-transport.ts
git commit -m "feat: bootstrap renderer localization runtime"
```

### Task 3: Convert Router, Shell, and Shared Display Mappings

**Files:**
- Modify: `front/a3-front/src/router/index.ts`
- Modify: `front/a3-front/src/layouts/AppLayout.vue`
- Modify: `front/a3-front/src/layouts/AppLayout.test.ts`
- Modify: `front/a3-front/src/utils/protocol.ts`
- Create: `front/a3-front/src/i18n/display-maps.ts`
- Create: `front/a3-front/src/i18n/coverage.test.ts`

- [ ] **Step 1: Write route-title and coverage tests**

Assert every route meta has `titleKey`, no route meta has `title`, and `titleKey` resolves in the built-in catalog. Assert `AppLayout` renders localized brand/navigation state. Add a source scan that rejects Han characters in production Vue/TypeScript files except:

```text
src/api/types.ts
src/utils/protocol.ts
src/i18n/locales/zh-CN/**
```

The two allowlisted code files may contain only canonical protocol/enum literals; add explicit regex assertions for their allowed values so the allowlist cannot become a general bypass.

- [ ] **Step 2: Run RED**

```powershell
npx vitest run src/i18n/coverage.test.ts src/layouts/AppLayout.test.ts
```

- [ ] **Step 3: Replace route titles and shell text**

Use `meta: { titleKey: 'navigation.onboarding' }` and equivalent keys for all routes. In `AppLayout.vue`, use `useI18n`, translate aria labels/tooltips/drawer titles, map backend state through `statuses.sessionState.<canonical-value>`, and localize backend-exit errors by stable code.

Create `display-maps.ts` with pure mappings that retain API values:

```ts
export const difficultyKey = (value: '基础' | '提高' | '挑战') => ({
  基础: 'statuses.difficulty.basic',
  提高: 'statuses.difficulty.advanced',
  挑战: 'statuses.difficulty.challenge',
}[value])

export const stageKey = (value: '初中' | '高中') => ({
  初中: 'statuses.stage.middleSchool',
  高中: 'statuses.stage.highSchool',
}[value])
```

Add mappings for subject, mastery label, resource type, bundle/artifact status, evidence status, model provider, reasoning effort, import status, access mode, privacy mode, and next action. Never change request/response enum values.

- [ ] **Step 4: Keep protocol parsing internal**

`utils/protocol.ts` continues parsing fixed Chinese protocol labels. Only its user-facing fallback titles/status labels move to translation keys; parser regexes and serialized field names remain unchanged.

- [ ] **Step 5: Run GREEN and commit**

```powershell
npx vitest run src/i18n/coverage.test.ts src/layouts/AppLayout.test.ts src/router/history.test.ts
git add src/router/index.ts src/layouts/AppLayout.vue src/layouts/AppLayout.test.ts src/utils/protocol.ts src/i18n/display-maps.ts src/i18n/coverage.test.ts
git commit -m "feat: localize application shell and display mappings"
```

### Task 4: Localize Knowledge, Learning, Model, Workspace, and Pet Components

**Files:**
- Modify: `front/a3-front/src/components/knowledge/CollectionRail.vue`
- Modify: `front/a3-front/src/components/knowledge/DocumentGrid.vue`
- Modify: `front/a3-front/src/components/knowledge/DocumentInspector.vue`
- Modify: `front/a3-front/src/components/knowledge/KnowledgeSourceList.vue`
- Modify: `front/a3-front/src/components/knowledge/TextbookCatalog.vue`
- Modify: `front/a3-front/src/components/learning/ResourceBundle.vue`
- Modify: `front/a3-front/src/components/learning/ResourceCard.vue`
- Modify: `front/a3-front/src/components/learning/ResourceMenu.vue`
- Modify: `front/a3-front/src/components/learning/SafeMermaid.vue`
- Modify: `front/a3-front/src/components/model/ModelProfileEditor.vue`
- Modify: `front/a3-front/src/components/model/ModelProfileList.vue`
- Modify: `front/a3-front/src/components/model/ModelSelectionPopover.vue`
- Modify: `front/a3-front/src/components/pet/PetSettingsCard.vue`
- Modify: `front/a3-front/src/components/workspace/ConversationRail.vue`
- Modify: `front/a3-front/src/components/workspace/DeskPanel.vue`
- Modify: matching `*.test.ts` files for every component above

- [ ] **Step 1: Update tests to assert catalog output rather than literals in source**

For each existing component test, keep behavior assertions and replace direct source-text assumptions with rendered built-in Chinese output. Add at least one `en-US` injected-message test per component group to prove labels are not hardcoded.

- [ ] **Step 2: Convert every visible literal**

Each component calls `useI18n()`. Use this exact key ownership:

```text
components.collectionRail.*
components.documentGrid.*
components.documentInspector.*
components.knowledgeSources.*
components.textbookCatalog.*
components.resourceBundle.*
components.resourceCard.*
components.resourceMenu.*
components.safeMermaid.*
components.modelProfileEditor.*
components.modelProfileList.*
components.modelSelection.*
components.petSettings.*
components.conversationRail.*
components.deskPanel.*
```

Use `display-maps.ts` for canonical values, `formatters.ts` for date/number/percent output, and `errorMessage()` for failures. User names, file names, textbook titles, model labels, citations, prompts, answers, and notes remain unmodified.

- [ ] **Step 3: Add long-text layout guards**

For label/value grids and buttons, add `min-width: 0`, `overflow-wrap: anywhere` only where a long localized label can overflow, and avoid fixed widths that truncate English. Preserve current responsive breakpoints and keyboard focus styles.

- [ ] **Step 4: Run all component tests and coverage**

```powershell
npx vitest run src/components src/tests/components src/i18n/coverage.test.ts
```

Expected: all pass and the Han-character scan reports no new non-allowlisted production literals.

- [ ] **Step 5: Commit the component migration**

```powershell
git add src/components src/i18n/locales/zh-CN/messages/components.json src/i18n/locales/zh-CN/messages/statuses.json
git commit -m "feat: localize shared learning components"
```

### Task 5: Localize All Views and Add the Language Settings Card Shell

**Files:**
- Modify: `front/a3-front/src/views/AgentWorkspace.vue`
- Modify: `front/a3-front/src/views/Assessment.vue`
- Modify: `front/a3-front/src/views/Dashboard.vue`
- Modify: `front/a3-front/src/views/DesktopSettings.vue`
- Modify: `front/a3-front/src/views/KnowledgeLibrary.vue`
- Modify: `front/a3-front/src/views/LearningPath.vue`
- Modify: `front/a3-front/src/views/ModelSettings.vue`
- Modify: `front/a3-front/src/views/Onboarding.vue`
- Modify: `front/a3-front/src/views/ProfileBuilder.vue`
- Modify: `front/a3-front/src/views/SmartTutor.vue`
- Modify: matching view tests
- Create: `front/a3-front/src/components/language/LanguageSettingsCard.vue`
- Create: `front/a3-front/src/components/language/LanguageSettingsCard.test.ts`

- [ ] **Step 1: Add failing view and card tests**

Preserve existing interaction tests. Add assertions that the language card always shows built-in `简体中文`, shows download/import controls only when `window.a3Desktop` exposes language methods, and displays the exact notice key `views.desktopSettings.language.contentFollowsUi`.

- [ ] **Step 2: Convert view literals to their namespaces**

Each view uses only its assigned `views.<name>.*` namespace plus `common`, `statuses`, and `errors`. Use localized formatters instead of `toLocaleDateString('zh-CN')`, manual `%`, or Chinese suffix concatenation. Preserve all API payloads and route paths.

- [ ] **Step 3: Add the nonfunctional language-card shell**

Create a presentational component with props:

```ts
interface Props {
  activeLocale: string
  languages: LanguagePackSummary[]
  busyLocale: string | null
  progress: LanguageProgress | null
  desktopAvailable: boolean
}
```

Emit `refresh`, `download(locale)`, `activate(locale)`, `remove(locale)`, and `import`. At this task the parent supplies built-in zh-CN only; Electron behavior is added after the pack controller exists.

- [ ] **Step 4: Run view tests and the coverage scan**

```powershell
npx vitest run src/views src/components/language src/i18n/coverage.test.ts
```

- [ ] **Step 5: Commit the view migration**

```powershell
git add src/views src/components/language src/i18n/locales/zh-CN/messages/views
git commit -m "feat: localize views and add language settings UI"
```

### Task 6: Define Signed Catalog and Manifest Schemas

**Files:**
- Create: `front/a3-front/electron/language-pack/constants.mjs`
- Create: `front/a3-front/electron/language-pack/schema.mjs`
- Create: `front/a3-front/electron/language-pack/verifier.mjs`
- Create: `front/a3-front/electron/language-pack/keyring.mjs`
- Create: `front/a3-front/electron/language-pack/schema.test.mjs`
- Create: `front/a3-front/electron/language-pack/verifier.test.mjs`
- Modify: `front/a3-front/package.json`

- [ ] **Step 1: Write schema and Ed25519 tests with an injected test key**

Generate an Ed25519 key pair in test memory with `generateKeyPairSync('ed25519')`. Sign RFC 8785 canonical manifest/catalog payloads and assert valid signatures pass. Mutate locale, file hash, catalog version, app range, placeholder set, key id, signature byte, and base catalog hash one at a time and assert stable errors.

Use exact stable codes:

```text
LANGUAGE_SCHEMA_INVALID
LANGUAGE_LOCALE_INVALID
LANGUAGE_VERSION_INCOMPATIBLE
LANGUAGE_CATALOG_DOWNGRADE
LANGUAGE_BASE_CATALOG_MISMATCH
LANGUAGE_KEY_UNKNOWN
LANGUAGE_KEY_REVOKED
LANGUAGE_SIGNATURE_INVALID
LANGUAGE_FILE_HASH_MISMATCH
LANGUAGE_KEYS_INCOMPLETE
LANGUAGE_PLACEHOLDERS_MISMATCH
LANGUAGE_CONTENT_UNSAFE
```

- [ ] **Step 2: Run RED**

```powershell
node --test electron/language-pack/schema.test.mjs electron/language-pack/verifier.test.mjs
```

- [ ] **Step 3: Implement constants and strict schemas**

`constants.mjs` exports:

```js
export const LANGUAGE_PACK_FORMAT = 'a3-language-pack/v1'
export const LANGUAGE_CATALOG_FORMAT = 'a3-language-catalog/v1'
export const BUILT_IN_LOCALE = 'zh-CN'
export const FIRST_DOWNLOADABLE_LOCALES = Object.freeze(['en-US', 'zh-TW'])
export const MAX_PACK_BYTES = 10 * 1024 * 1024
export const MAX_UNCOMPRESSED_BYTES = 20 * 1024 * 1024
export const MAX_FILE_COUNT = 64
export const MAX_COMPRESSION_RATIO = 100
export const MAX_JSON_DEPTH = 32
export const MAX_STRING_LENGTH = 20_000
export const CATALOG_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000
```

Accept canonical BCP 47 casing for `zh-CN`, `zh-TW`, `en-US`, and future language-region tags. Reject underscores, whitespace, extensions, private-use tags, and locale values longer than 35 characters. Manifest `pack_version` and app versions use `semver`; range is inclusive minimum/exclusive maximum.

- [ ] **Step 4: Implement canonical signature and message validation**

Use `canonicalize` and Node `crypto.verify(null, bytes, publicKey, signature)`. The manifest signature covers the manifest without `signature`. Catalog signature covers all of `catalog.json`. Flatten message keys and compare exact key sets and placeholder sets against the built-in baseline passed into the verifier. Reject HTML-like tags, forbidden object keys, disallowed control characters, excess depth/string length, and non-string leaves.

`keyring.mjs` exports an immutable production key map and revoked-key set; tests inject their own key ring. The production map is populated with `a3-language-2026-01` during Task 15, and production code must reject an empty key ring before catalog refresh or import.

- [ ] **Step 5: Add tests to the Node test list and commit**

```powershell
node --test electron/language-pack/schema.test.mjs electron/language-pack/verifier.test.mjs
git add electron/language-pack package.json
git commit -m "feat: verify signed language metadata"
```

### Task 7: Implement Fixed-Origin Catalog Downloading

**Files:**
- Create: `front/a3-front/electron/language-pack/catalog.mjs`
- Create: `front/a3-front/electron/language-pack/downloader.mjs`
- Create: `front/a3-front/electron/language-pack/catalog.test.mjs`
- Create: `front/a3-front/electron/language-pack/downloader.test.mjs`

- [ ] **Step 1: Write redirect, expiry, and interruption tests**

Inject a fake `fetch` and assert only these hosts are accepted:

```text
api.github.com
github.com
objects.githubusercontent.com
release-assets.githubusercontent.com
```

Require HTTPS on every hop, at most five redirects, fixed repository path `212667660-arch/dianwu-language-packs`, response/body size limits, timeout, content-length agreement, `.part` cleanup, SHA-256 match, ETag/Last-Modified caching, catalog expiry, and highest accepted `catalog_version` downgrade rejection.

- [ ] **Step 2: Run RED**

```powershell
node --test electron/language-pack/catalog.test.mjs electron/language-pack/downloader.test.mjs
```

- [ ] **Step 3: Implement manual redirect control**

`downloader.mjs` exports `fetchAllowed`, `downloadToPartFile`, and `assertAllowedLanguageUrl`. Every request uses `redirect: 'manual'`; each `Location` is resolved against the previous URL and revalidated before the next request. Renderer input is never accepted by these functions.

Production catalog URLs are constants:

```js
export const CATALOG_URL = 'https://github.com/212667660-arch/dianwu-language-packs/releases/latest/download/catalog.json'
export const CATALOG_SIGNATURE_URL = 'https://github.com/212667660-arch/dianwu-language-packs/releases/latest/download/catalog.sig'
```

- [ ] **Step 4: Implement signed caching behavior**

`catalog.mjs` verifies both files before updating cache metadata. A 304 response may reuse only a previously signature-verified, unexpired cache. An expired cache can populate installed-language display but cannot authorize new downloads. Catalog entry asset URLs must name the fixed repository release path and one of the two first locales.

- [ ] **Step 5: Run GREEN and commit**

```powershell
node --test electron/language-pack/catalog.test.mjs electron/language-pack/downloader.test.mjs
git add electron/language-pack/catalog.mjs electron/language-pack/downloader.mjs electron/language-pack/catalog.test.mjs electron/language-pack/downloader.test.mjs
git commit -m "feat: download language catalogs from fixed GitHub origin"
```

### Task 8: Safely Extract and Atomically Install `.a3lang` Archives

**Files:**
- Create: `front/a3-front/electron/language-pack/archive.mjs`
- Create: `front/a3-front/electron/language-pack/state.mjs`
- Create: `front/a3-front/electron/language-pack/installer.mjs`
- Create: `front/a3-front/electron/language-pack/archive.test.mjs`
- Create: `front/a3-front/electron/language-pack/state.test.mjs`
- Create: `front/a3-front/electron/language-pack/installer.test.mjs`

- [ ] **Step 1: Build malicious archive fixtures in tests**

Use `yazl` to create valid and invalid `.a3lang` archives. Cover absolute paths, `..`, backslashes, duplicate normalized paths, case-insensitive collisions, symlinks/external attributes, undeclared files, missing files, too many files, excess total bytes, high compression ratio, malformed JSON, file hash mismatch, interrupted state write, rename failure, downgrade, and revoked-key activation.

- [ ] **Step 2: Run RED**

```powershell
node --test electron/language-pack/archive.test.mjs electron/language-pack/state.test.mjs electron/language-pack/installer.test.mjs
```

- [ ] **Step 3: Implement safe archive extraction**

`archive.mjs` opens with `yauzl` using `lazyEntries: true`, rejects encrypted entries and ZIP64 values beyond limits, normalizes only forward-slash relative paths, checks the exact manifest allowlist, writes each file with exclusive creation under a unique staging directory, hashes while streaming, and validates the fully extracted tree before returning it.

- [ ] **Step 4: Implement state and recovery**

Use this state schema:

```json
{
  "version": 1,
  "active_locale": "zh-CN",
  "installed": {},
  "last_known_good": {},
  "accepted_catalog_version": 0,
  "diagnostic_code": null
}
```

`state.mjs` validates on read, quarantines malformed state by renaming it with a timestamp suffix under the same language-packs directory, writes through a sibling temporary file, and retains a single `.bak` copy. Recovery order is valid current state, valid backup, then clean built-in zh-CN state.

- [ ] **Step 5: Implement version-directory installation**

Install only to `<root>/<locale>/<pack_version>/`. Never overwrite an existing target; revalidate and reuse an identical target or reject it. Update `installed` first, load/test the messages, then update `active_locale` and `last_known_good`. On activation failure, preserve the prior directory/state and record a stable diagnostic code. Deleting a language is allowed only when it is not active and is not the only last-known-good recovery version.

- [ ] **Step 6: Run GREEN and commit**

```powershell
node --test electron/language-pack/archive.test.mjs electron/language-pack/state.test.mjs electron/language-pack/installer.test.mjs
git add electron/language-pack/archive.mjs electron/language-pack/state.mjs electron/language-pack/installer.mjs electron/language-pack/*.test.mjs
git commit -m "feat: install language packs atomically"
```

### Task 9: Add the Main-Process Language Controller and Native Messages

**Files:**
- Create: `front/a3-front/electron/language-pack/controller.mjs`
- Create: `front/a3-front/electron/language-pack/native-messages.mjs`
- Create: `front/a3-front/electron/language-pack/controller.test.mjs`
- Create: `front/a3-front/electron/language-pack/native-messages.test.mjs`
- Modify: `front/a3-front/package.json`

- [ ] **Step 1: Write serialization, import, and fallback tests**

Assert one operation runs at a time per locale, concurrent duplicates share or queue deterministically, cancellation removes `.part`, offline import uses a main-process-selected path, activation returns renderer messages, native messages fall back per key to built-in zh-CN, startup restores last-known-good, and a revoked active key falls back safely.

- [ ] **Step 2: Run RED**

```powershell
node --test electron/language-pack/controller.test.mjs electron/language-pack/native-messages.test.mjs
```

- [ ] **Step 3: Implement controller API**

Expose methods:

```js
prepare()
snapshot()
refreshCatalog()
download(locale)
importFromFile(filePath)
activate(locale)
remove(locale)
cancel(locale)
onProgress(listener)
activeLocale()
activeMessages()
```

`snapshot()` returns built-in/installed/available entries, active locale, browser capability flags, catalog status, and active downloaded messages only. It never returns local paths, URLs, hashes, manifests, public keys, or cache directories.

- [ ] **Step 4: Implement native translation**

`native-messages.mjs` loads built-in `desktop.json`/`pet.json` from packaged `src/i18n/locales/zh-CN`, overlays only verified active pack data, resolves dot keys, verifies placeholder names, and formats `{name}` values without evaluating HTML or code. Missing or invalid values fall back to built-in zh-CN.

- [ ] **Step 5: Include built-in JSON in Electron packaging**

Append this package file pattern without adding downloaded packs:

```json
"src/i18n/locales/zh-CN/**"
```

The built application must contain zh-CN JSON in `app.asar`; `en-US` and `zh-TW` must not be in `dist/assets` or `app.asar`.

- [ ] **Step 6: Run GREEN and commit**

```powershell
node --test electron/language-pack/controller.test.mjs electron/language-pack/native-messages.test.mjs
git add electron/language-pack package.json
git commit -m "feat: manage active language and native messages"
```

### Task 10: Expose Fixed Language IPC and Inject the Content Locale Header

**Files:**
- Modify: `front/a3-front/electron/ipc-contract.mjs`
- Modify: `front/a3-front/electron/ipc-contract.test.mjs`
- Modify: `front/a3-front/electron/preload.cjs`
- Modify: `front/a3-front/electron/main.mjs`
- Modify: `front/a3-front/electron/runtime.test.mjs`
- Modify: `front/a3-front/electron/backend-proxy.mjs`
- Modify: `front/a3-front/electron/backend-proxy.test.mjs`
- Modify: `front/a3-front/src/api/transport.ts`
- Modify: `front/a3-front/src/api/types.ts`
- Modify: `front/a3-front/src/api/backend.ts`

- [ ] **Step 1: Write IPC denial and header tests**

Assert locale validation accepts exactly canonical locale strings and rejects URL/path/hash/key-shaped objects. Assert preload functions have these arities:

```text
languageList()
languageRefreshCatalog()
languageDownload(locale)
languageImport()
languageActivate(locale)
languageRemove(locale)
languageCancel(locale)
languageOnProgress(listener)
```

Assert both normal and SSE backend proxy requests include `X-A3-Content-Locale: en-US` from an injected getter, while renderer `TransportRequest` still has no header field and cannot override it.

- [ ] **Step 2: Run RED**

```powershell
node --test electron/ipc-contract.test.mjs electron/backend-proxy.test.mjs electron/runtime.test.mjs
```

- [ ] **Step 3: Wire controller startup and fixed IPC**

Create the language controller before diagnostics and other native controllers. In startup order:

```text
desktopStateStore.load()
languageController.prepare()
knowledgeImporter.prepare()
petController.prepare()
startBackend()
modelProfileController.bootstrap()
createWindow/createTray/createPet
```

`languageImport()` opens one native file dialog restricted to `.a3lang` and passes its selected path directly to the controller; the path never crosses preload. Every handler validates `trustedKnowledgeSender(event)` before invoking the controller.

- [ ] **Step 4: Inject locale into backend requests**

Extend `createBackendProxy` with `getContentLocale = () => 'zh-CN'`. `buildHeaders` and `buildStreamHeaders` accept a validated locale and add the fixed header. If the getter throws or returns an invalid value, use `zh-CN`; never use renderer input.

- [ ] **Step 5: Add typed renderer API methods**

Define `LanguagePackSummary`, `LanguageSnapshot`, and `LanguageProgress` in `api/types.ts`; extend `DesktopBridge`; add `backendApi.language*` wrappers returning built-in-only snapshots in browser mode. Browser import/download/remove calls throw a localized `LANGUAGE_DESKTOP_ONLY` error.

- [ ] **Step 6: Run GREEN and commit**

```powershell
node --test electron/ipc-contract.test.mjs electron/backend-proxy.test.mjs electron/runtime.test.mjs
npx vitest run src/api
git add electron src/api
git commit -m "feat: expose safe language IPC and content locale"
```

### Task 11: Connect the Locale Store and Language Settings Experience

**Files:**
- Create: `front/a3-front/src/stores/locale.ts`
- Create: `front/a3-front/src/stores/locale.test.ts`
- Modify: `front/a3-front/src/main.ts`
- Modify: `front/a3-front/src/components/language/LanguageSettingsCard.vue`
- Modify: `front/a3-front/src/components/language/LanguageSettingsCard.test.ts`
- Modify: `front/a3-front/src/views/DesktopSettings.vue`
- Modify: `front/a3-front/src/views/DesktopSettings.test.ts`

- [ ] **Step 1: Write store tests for activation and rollback**

Mock backend API and assert initialize installs verified active messages before activation, download progress is reflected, activation updates `i18n`, activation failure preserves the previous locale, remove is disabled for active/built-in versions, and browser mode stays zh-CN with no network/import calls.

- [ ] **Step 2: Run RED**

```powershell
npx vitest run src/stores/locale.test.ts src/components/language/LanguageSettingsCard.test.ts
```

- [ ] **Step 3: Implement the Pinia store**

Store state:

```ts
activeLocale: 'zh-CN'
languages: LanguagePackSummary[]
busyLocale: string | null
progress: LanguageProgress | null
catalogStatus: 'idle' | 'ready' | 'offline' | 'error'
errorCode: string | null
initialized: boolean
```

Actions call only `backendApi.language*`, register/remove the progress listener, install downloaded messages through `installLocaleMessages`, call `activateLocale` only after validation, and localize errors by stable code.

- [ ] **Step 4: Initialize before the first render**

Refactor `main.ts` into an async `bootstrap()` that creates Pinia, installs i18n/router, awaits `localeStore.initialize()`, then mounts. A language-pack failure must log no path and still mount with built-in zh-CN.

- [ ] **Step 5: Complete the settings card interactions**

Display native name, version, built-in/installed/available/error status, progress bar, retry, import, activate, and remove controls. Confirm the explanatory text states UI and new AI content switch together, while existing history/user files are not translated.

- [ ] **Step 6: Run GREEN and commit**

```powershell
npx vitest run src/stores/locale.test.ts src/components/language/LanguageSettingsCard.test.ts src/views/DesktopSettings.test.ts
git add src/stores/locale.ts src/stores/locale.test.ts src/main.ts src/components/language src/views/DesktopSettings.vue src/views/DesktopSettings.test.ts
git commit -m "feat: add downloadable language settings flow"
```

### Task 12: Localize Tray, Native Dialogs, Startup, Diagnostics, and Pet Speech

**Files:**
- Modify: `front/a3-front/electron/tray-lifecycle.mjs`
- Modify: `front/a3-front/electron/tray-lifecycle.test.mjs`
- Modify: `front/a3-front/electron/main.mjs`
- Modify: `front/a3-front/electron/desktop-diagnostics.mjs`
- Modify: `front/a3-front/electron/knowledge-controller.mjs`
- Modify: `front/a3-front/electron/knowledge-import.mjs`
- Modify: `front/a3-front/electron/model-config.mjs`
- Modify: `front/a3-front/electron/model-config-controller.mjs`
- Modify: `front/a3-front/electron/model-profile-controller.mjs`
- Modify: `front/a3-front/electron/model-profile-vault.mjs`
- Modify: `front/a3-front/electron/pet/pet-audio.js`
- Modify: `front/a3-front/electron/pet-audio.test.mjs`
- Modify: relevant Electron tests

- [ ] **Step 1: Write native switching tests**

Inject a `t(key, params)` function into tray/diagnostics/controllers. Assert tray labels/tooltips rebuild after activation, file dialogs use active-language titles/filter names, startup and diagnostics messages use active locale, and pet speech uses locale-specific lines plus speech-synthesis language `zh-CN`, `en-US`, or `zh-TW`.

- [ ] **Step 2: Refactor controllers to dependency-injected messages**

Use `t` only for user-visible strings. Stable error codes, log event ids, validation behavior, filenames, protocol values, and safe fallback `message` fields stay unchanged. `createTrayController` receives `t`, calls it inside `rebuild`, and exposes `setTranslator(next)` or reads a current resolver callback so activation does not recreate the Tray object.

- [ ] **Step 3: Update pet audio locale**

`createPetAudioRuntime` gains `locale` and `speechLines` settings. `createBrowserPetAudioRuntime` selects voices by exact locale, then base language, preferring local service. Active-language messages are sent to the pet window through a fixed `a3:pet-locale` event; pet preload exposes only an `onLocale` listener.

- [ ] **Step 4: Rebuild all native surfaces on activation**

After successful controller activation: rebuild tray menu/tool tip, update application/window title, notify pet, and use the new resolver for subsequent dialogs. Existing open native dialogs are not mutated.

- [ ] **Step 5: Run all Electron tests and commit**

```powershell
npm test
git add electron
git commit -m "feat: localize Electron and pet native surfaces"
```

### Task 13: Validate and Propagate `X-A3-Content-Locale` in FastAPI

**Files:**
- Create: `backend/content_locale.py`
- Create: `backend/tests/test_content_locale.py`
- Modify: `backend/routers/chat.py`
- Modify: `backend/routers/profile.py`
- Modify: `backend/routers/resource.py`
- Modify: `backend/services/profile_agent.py`
- Modify: `backend/services/resource_agent.py`
- Modify: `backend/services/orchestrator.py`
- Modify: `backend/services/resource_bundle/planner.py`
- Modify: `backend/services/resource_bundle/pipeline.py`
- Modify: `backend/services/resource_bundle/service.py`
- Modify: `backend/services/resource_bundle/specialists/base.py`
- Modify: `backend/services/resource_bundle/specialists/course_explanation.py`
- Modify: `backend/services/resource_bundle/specialists/mind_map.py`
- Modify: `backend/services/resource_bundle/specialists/question_bank.py`
- Modify: `backend/services/resource_bundle/specialists/extended_reading.py`
- Modify: `backend/services/resource_bundle/specialists/adaptive_practice.py`
- Modify: `backend/services/resource_bundle/answer_reviewer.py`
- Modify: affected backend tests

- [ ] **Step 1: Write header and prompt-contract tests**

Assert absent header returns `zh-CN`; canonical `en-US`/`zh-TW` pass; malformed/oversized/private-use values return HTTP 400 with stable `CONTENT_LOCALE_INVALID`; future canonical tags normalize and pass. For every prompt builder, assert `en-US` adds an English natural-language instruction while fixed Chinese protocol headings remain present and parsers still accept output.

- [ ] **Step 2: Run RED**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q backend/tests/test_content_locale.py
```

- [ ] **Step 3: Implement the locale dependency and instruction helper**

`backend/content_locale.py` exposes:

```python
import re

BUILT_IN_CONTENT_LOCALE = "zh-CN"
SUPPORTED_CONTENT_LOCALES = {"zh-CN", "en-US", "zh-TW"}
_CONTENT_LOCALE_PATTERN = re.compile(r"^[a-z]{2,3}(?:-[A-Z][a-z]{3})?(?:-(?:[A-Z]{2}|[0-9]{3}))?$")

class ContentLocaleError(ValueError):
    code = "CONTENT_LOCALE_INVALID"

def normalize_content_locale(value: str | None) -> str:
    if value is None:
        return BUILT_IN_CONTENT_LOCALE
    if value != value.strip() or len(value) > 35 or not _CONTENT_LOCALE_PATTERN.fullmatch(value):
        raise ContentLocaleError("content locale is invalid")
    return value

def content_language_instruction(locale: str) -> str:
    language = {"zh-CN": "简体中文", "en-US": "English (United States)", "zh-TW": "繁體中文（台灣）"}.get(locale, locale)
    return (
        f"自然语言正文、问题、解释、反馈和面向学习者的标题必须使用 {language}。"
        "固定协议标题、字段名、枚举值、资料编号、代码、公式和解析器契约必须保持原样，不得翻译。"
    )
```

Add a FastAPI dependency reading `Header(alias='X-A3-Content-Locale')`; convert validation errors to the existing safe error envelope.

- [ ] **Step 4: Thread the explicit locale through generation paths**

Add `content_locale: str = 'zh-CN'` to diagnosis/profile/resource/planner/specialist/answer-review prompt functions and service methods. Append `content_language_instruction(content_locale)` to system messages. `chat` and stream routes pass the dependency into orchestrator; standalone profile/resource and bundle/retry routes do the same. Do not use a process-global or context variable.

- [ ] **Step 5: Localize deterministic learner-facing orchestration text**

Create small locale dictionaries for diagnosis acknowledgements, cancellation/failure display titles, evidence warnings, and answer-review warning prose. Protocol text stored in learner profiles/resources remains parseable because field labels and enums remain canonical Chinese; only natural-language field values and resource bodies switch.

- [ ] **Step 6: Run focused and protocol regressions, then commit**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q backend/tests/test_content_locale.py backend/tests/test_prompt_boundaries.py backend/tests/test_protocols.py backend/tests/test_orchestrator.py backend/tests/test_resource_bundle_pipeline.py backend/tests/test_answer_reviewer.py
git add backend
git commit -m "feat: propagate controlled AI content locale"
```

### Task 14: Add Locale-Specific Deterministic Offline Demo Data

**Files:**
- Modify: `backend/demo/fixtures.py`
- Modify: `backend/demo/service.py`
- Modify: `backend/routers/demo.py`
- Modify: `backend/tests/test_demo_api.py`
- Modify: `backend/tests/test_content_locale.py`

- [ ] **Step 1: Write per-locale demo tests**

For `zh-CN`, `en-US`, and `zh-TW`, seed/status/reset through the locale header and assert a stable locale-specific session id, localized dataset title/degradation text/agent details/resource body, unchanged protocol values, 5 completed Agent steps, and mastery 0.25 to 0.4536. Assert unknown valid locale uses English deterministic content and reports `content_locale_fallback: 'en-US'`.

- [ ] **Step 2: Implement immutable fixture maps**

Use locale ids:

```text
demo_offline_v1_zh_CN
demo_offline_v1_en_US
demo_offline_v1_zh_TW
```

Keep the original CC0 mathematical facts, numeric answers, citations, resource protocol and mastery values identical. Translate only learner-facing prose. `demo_snapshot/seed_demo/reset_demo` accept explicit `content_locale` and never rewrite an existing session from another locale.

- [ ] **Step 3: Run demo tests and commit**

```powershell
& .\.test-venv\Scripts\python.exe -m pytest -q backend/tests/test_demo_api.py backend/tests/test_content_locale.py
git add backend/demo backend/routers/demo.py backend/tests/test_demo_api.py backend/tests/test_content_locale.py
git commit -m "feat: localize deterministic offline demo"
```

### Task 15: Create the Public Language-Pack Repository and Production Trust Root

**Files in main repository:**
- Modify: `front/a3-front/electron/language-pack/keyring.mjs`
- Create: `docs/release/language-packs.md`

**Files in new public repository `212667660-arch/dianwu-language-packs`:**
- Create: `.github/workflows/release-language-packs.yml`
- Create: `.gitignore`
- Create: `LICENSE`
- Create: `README.md`
- Create: `package.json`
- Create: `package-lock.json`
- Create: `scripts/catalog-shape.mjs`
- Create: `catalog-shape.json`
- Create: `scripts/build-pack.mjs`
- Create: `scripts/release.mjs`
- Create: `scripts/verify-release.mjs`
- Create: `test/release.test.mjs`
- Create: `locales/en-US/**`
- Create: `locales/zh-TW/**`

- [ ] **Step 1: Verify GitHub identity without printing tokens**

```powershell
gh auth status
gh repo view 212667660-arch/dianwu-language-packs --json nameWithOwner,isPrivate
```

If the repository does not exist, create it public without initializing secrets in files:

```powershell
gh repo create 212667660-arch/dianwu-language-packs --public --description "Signed downloadable language packs for A3 智学协作台"
```

- [ ] **Step 2: Generate one release key without writing the private key to disk or output**

Run a Node process that generates Ed25519 in memory, invokes `gh secret set A3_LANGUAGE_PACK_SIGNING_KEY --env language-pack-release --repo 212667660-arch/dianwu-language-packs` with the private PEM on child stdin, and prints only the public SPKI PEM plus SHA-256 fingerprint. Capture only that public output and add it under key id `a3-language-2026-01` in `keyring.mjs` with `apply_patch`.

Create the GitHub Environment through `gh api --method PUT repos/212667660-arch/dianwu-language-packs/environments/language-pack-release` before setting the secret. Never echo, log, store, stage, cache, or paste the private PEM.

- [ ] **Step 3: Scaffold deterministic pack tooling**

The companion repository uses `canonicalize`, `semver`, and `yazl`. `build-pack.mjs` loads the main catalog baseline exported as a checked-in `catalog-shape.json`, validates exact keys/placeholders, signs the manifest with `A3_LANGUAGE_PACK_SIGNING_KEY`, and emits `.a3lang`. `release.mjs` builds both packs, hashes them, creates a seven-day catalog, signs it, and emits `catalog.json`, `catalog.sig`, and the two pack files. `verify-release.mjs` verifies all four outputs with the public key.

- [ ] **Step 4: Protect the release workflow**

The workflow runs on `v*` tags and manual dispatch, uses Environment `language-pack-release`, `permissions: contents: write`, `npm ci`, tests, builds, independently verifies, then uploads exactly four assets. It must fail if the private-key secret is absent and never print environment values.

- [ ] **Step 5: Document trust separation and commit both repositories**

`docs/release/language-packs.md` explains public-key fingerprints, key rotation, revoked keys, catalog expiry, pack compatibility, offline import trust limits, and that Azure code-signing credentials are unrelated. Commit/push the companion scaffold, then commit the main-repository public key and documentation. Verify neither repository contains a private key or secret assignment.

### Task 16: Produce Complete `en-US` and `zh-TW` Packs and Publish the First Release

**Files in companion repository:**
- Modify: `locales/en-US/messages/**/*.json`
- Modify: `locales/en-US/content/offline-demo.json`
- Modify: `locales/zh-TW/messages/**/*.json`
- Modify: `locales/zh-TW/content/offline-demo.json`
- Modify: `catalog-shape.json`

- [ ] **Step 1: Export the approved baseline shape**

Generate `catalog-shape.json` from the main repository containing catalog version, base catalog hash, sorted keys, and placeholder arrays only; it must not copy Chinese message values into the public pack repository.

- [ ] **Step 2: Write complete human-readable translations**

Translate every key for US English and Taiwan Traditional Chinese. Preserve placeholders exactly, keep product name `智学协作台` where branded, keep model/protocol/API identifiers unchanged, and do not translate user data, citations, textbook titles, file names, or canonical enum payloads. Use native names `English (United States)` and `繁體中文（台灣）`.

- [ ] **Step 3: Run parity, content, and archive tests**

```powershell
npm ci
npm test
npm run release -- --version 1.0.0 --catalog-version 1 --min-app-version 1.0.0 --max-app-version 2.0.0
npm run verify-release
```

Expected: exact key/placeholder parity, no unsafe HTML/control/prototype content, valid Ed25519 signatures, valid hashes, and four release files.

- [ ] **Step 4: Publish through the protected Environment**

Push an approved `v1.0.0` tag. Confirm GitHub Release assets are public and downloadable without a token. Download them fresh and run `verify-release.mjs` again against the release URLs.

- [ ] **Step 5: Test from the desktop app**

Refresh catalog, download/activate each locale, import a freshly downloaded `.a3lang` offline, restart, disconnect network, and verify last-known-good behavior. Tamper with one pack byte and one JSON file in separate copies and confirm both are rejected without changing the active language.

### Task 17: Full Regression, Packaging, Visual QA, and Queue Completion

**Files:**
- Modify: `front/a3-front/README.md`
- Modify: `README.md`
- Modify: `codex/AI模型任务队列.md`

- [ ] **Step 1: Run full automated verification**

```powershell
& .\.test-venv\Scripts\python.exe -m compileall -q backend
& .\.test-venv\Scripts\python.exe -m pytest -q backend
cd front/a3-front
npm test
npm run build
npm run build:desktop
cd ../..
git diff --check
```

Record actual counts. The final source coverage scan must report no user-visible Han literals outside the built-in catalog and explicit protocol/enum allowlist.

- [ ] **Step 2: Prove bundle separation**

Build `desktop:pack`, inspect `app.asar`, and assert complete zh-CN files exist while no `en-US`/`zh-TW` message corpus or language private key exists. Start with an empty userData directory and no network; application must mount fully in zh-CN.

- [ ] **Step 3: Run desktop language acceptance**

On 100%, 125%, and 150% DPI plus a narrow supported window:

```text
fresh install starts zh-CN
download and instant switch en-US
download and instant switch zh-TW
route titles, shell, every view/component, tray, dialogs, pet speech and errors switch
new AI chat/resource/demo content uses active locale
existing history, filenames, textbook titles and citations remain unchanged
restart and offline use preserve active verified pack
corrupt/revoked/incompatible pack falls back to last-known-good or zh-CN
keyboard focus, screen reader labels and long English layout remain usable
application exit leaves zero backend/Electron processes
```

- [ ] **Step 4: Verify the signed installer integration when S-042 resources are ready**

Run the protected signed-release workflow with the language implementation commit and repeat en-US/zh-TW download/import/switch inside the installed signed application. If Azure resources are still absent, record this cross-feature acceptance as the sole remaining S-042 external blocker; it does not block deterministic S-043 code/test completion.

- [ ] **Step 5: Update documentation and queue**

Document user language operations and pack publishing. Mark S-043 complete only after public pack release and desktop acceptance pass. Record main and companion repository commit/tag URLs, public-key id/fingerprint, catalog/pack SHA-256 values, test counts, package checks, and rollback evidence; never record private keys, GitHub tokens, Azure values, or absolute user paths.

- [ ] **Step 6: Commit and push both repositories**

```powershell
git add README.md front/a3-front/README.md codex/AI模型任务队列.md
git commit -m "docs: record downloadable language pack completion"
git push
```

Verify local HEAD, upstream HEAD, and `git ls-remote` match in both repositories.
