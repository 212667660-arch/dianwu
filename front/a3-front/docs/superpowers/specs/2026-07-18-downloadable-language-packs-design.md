# Downloadable Language Packs Design

**任务：** S-041 / S-043
**日期：** 2026-07-18
**状态：** 已批准
**目标：** 让应用始终内置完整简体中文，并从可信公开 GitHub Releases 下载、验证、安装和切换英语与繁体中文语言包，同时让 AI 学习内容跟随界面语言。

## 1. 已确认决策

- `zh-CN` 是唯一内置且永远可用的完整回退语言，不依赖网络或用户数据目录。
- 首批下载语言为 `en-US` 和 `zh-TW`；后续再扩展 `ja-JP`、`ko-KR`。
- 切换 UI 语言时，AI 生成内容自动使用同一语言。
- 内部模型协议字段、数据库枚举和稳定错误码不随 UI 语言翻译。
- 语言包托管在独立公开仓库 `212667660-arch/dianwu-language-packs` 的 GitHub Releases，避免私有主仓库下载需要在桌面端携带 GitHub Token。
- 支持本地选择并导入 `.a3lang`。在线下载与离线导入使用相同的包内签名、逐文件哈希、schema 和兼容性验证；在线下载额外要求 signed catalog 与整包 SHA-256，以验证网络传输来源。
- Renderer 不直接联网、不接收任意 URL、本地路径、签名私钥或信任公钥。
- 语言包只包含 JSON 数据，不允许 JavaScript、CSS、HTML、SVG、字体或可执行内容。

## 2. 当前状态

当前项目没有 i18n 运行时。生产代码中约 44 个 Vue/Electron 文件包含中文，路由标题、日期格式、托盘、原生对话框、桌宠语音和错误提示均存在直接硬编码。

`package.json` 的 `electronLanguages: ["zh-CN", "en-US"]` 只控制 Chromium/Electron 自带资源，不会翻译 Vue 应用。`desktop-state.json` 当前也没有 locale 字段。

后端已经提供稳定错误码，但前端主要直接展示后端中文 message。模型内部协议依赖固定中文标记，因此不能通过语言包翻译协议字段。

## 3. 组件边界

### 3.1 Renderer

新增：

- `src/i18n/index.ts`：初始化 vue-i18n、注册内置中文和已验证下载消息、统一 fallback。
- `src/i18n/catalog.ts`：catalog 版本、必需 key、命名空间和占位符约束。
- `src/i18n/locales/zh-CN/`：完整基准消息。
- `src/stores/locale.ts`：当前语言、安装列表、下载/导入进度和错误状态。
- `src/i18n/formatters.ts`：日期、时间、数字、百分比和相对时间。

消息命名空间：

- `common`
- `navigation`
- `views.dashboard`
- `views.profile`
- `views.agents`
- `views.learningPath`
- `views.tutor`
- `views.assessment`
- `views.knowledge`
- `views.modelSettings`
- `views.desktopSettings`
- `views.onboarding`
- `components`
- `statuses`
- `errors`
- `desktop`
- `pet`

路由使用 `meta.titleKey`，禁止保存最终中文标题。未知 key、缺失 key 或加载失败统一回退内置 `zh-CN`，不得导致空白页面。

### 3.2 Electron 主进程

新增 `electron/language-pack/`：

- `manifest.mjs`：严格解析 manifest 和 BCP 47 locale。
- `verifier.mjs`：验证 Ed25519、整包与逐文件 SHA-256、key/占位符一致性。
- `catalog.mjs`：读取和验证远端 signed catalog。
- `downloader.mjs`：受控 HTTPS 下载、大小限制、进度、超时和重定向白名单。
- `installer.mjs`：安全解压、staging、版本目录原子 rename、状态原子替换和回滚。
- `state.mjs`：installed/active/last-known-good 持久化。
- `controller.mjs`：串行化下载、导入、激活和删除。
- `native-messages.mjs`：托盘、对话框、启动错误和桌宠文案。

主进程拥有 locale 和安装状态。preload 只暴露固定 IPC：

- `languageList()`
- `languageRefreshCatalog()`
- `languageDownload(locale)`
- `languageImport()`
- `languageActivate(locale)`
- `languageRemove(locale)`
- `onLanguageProgress(callback)`

Renderer 只能提交受控 locale，不能提交 URL、文件路径、hash、公钥、manifest 或目标目录。

### 3.3 后端

后端不读取 Electron 语言包，也不按 `Accept-Language` 翻译协议字段。

Electron 后端代理根据主进程 active locale 注入受控 `X-A3-Content-Locale`。Web 模式默认 `zh-CN`。后端只接受规范 BCP 47 值，并把 locale 显式传给诊断、画像、普通聊天、五类资源和答案复核提示构建器。

模型输出规则要求自然语言正文使用选定 locale，但固定协议标题、字段名、枚举值和解析器契约保持不变。离线演示对 `zh-CN`、`en-US`、`zh-TW` 提供确定性内容；未来未知 locale 在无模型时回退 `en-US` 并明确显示离线回退状态。

HTTP/SSE 继续返回稳定 `code`、`retryable`、`request_id` 和中文兼容 `message`。客户端优先使用 `errors.<CODE>`，未知 code 显示本地化通用错误并附 code/request_id。

## 4. 语言包格式

扩展名：`.a3lang`。归档只允许：

- `manifest.json`
- `messages/common.json`
- `messages/navigation.json`
- `messages/views/*.json`
- `messages/components.json`
- `messages/statuses.json`
- `messages/errors.json`
- `messages/desktop.json`
- `messages/pet.json`
- `content/offline-demo.json`

Manifest 字段：

- `format: "a3-language-pack/v1"`
- `locale`
- `native_name`
- `pack_version`
- `catalog_version`
- `base_catalog_hash`
- `min_app_version`
- `max_app_version`
- `fallback_locale: "zh-CN"`
- `files[]: {path, size, sha256}`
- `license_spdx`
- `publisher`
- `key_id`
- `created_at`
- `signature_algorithm: "Ed25519"`
- `signature`

`pack_version`、`min_app_version` 和非空的 `max_app_version` 使用规范 SemVer；应用兼容区间为 `[min_app_version, max_app_version)`，`max_app_version: null` 表示无上界。`catalog_version` 是只增正整数，低于应用已接受版本的 catalog 或 pack 一律视为降级攻击。`base_catalog_hash` 是应用内置 `zh-CN` 必需 key、占位符和 catalog 版本规范化后的 SHA-256，用于拒绝针对错误基准制作的语言包。

签名覆盖删除 `signature` 后按 RFC 8785 规范化的 manifest。公钥 key ring 内置在应用，不能信任包内公钥。语言包签名密钥与 Azure Windows 代码签名凭据完全分离。

## 5. Catalog 与下载信任链

公开语言包仓库发布：

- `catalog.json`
- `catalog.sig`
- `a3-lang-en-US-<pack_version>.a3lang`
- `a3-lang-zh-TW-<pack_version>.a3lang`

Catalog 使用 `a3-language-catalog/v1` schema，包含固定 owner/repository、release、locale、pack_version、catalog_version、文件大小、整包 SHA-256、asset URL、key_id、应用兼容范围、`issued_at` 和 `expires_at`。`catalog.sig` 是对 RFC 8785 规范化 `catalog.json` 的 Ed25519 签名；`expires_at` 不得晚于 `issued_at` 后 7 天。

主进程只允许访问：

- `api.github.com/repos/212667660-arch/dianwu-language-packs/`
- `github.com/212667660-arch/dianwu-language-packs/`
- GitHub Release 官方重定向使用的 `objects.githubusercontent.com` 和 `release-assets.githubusercontent.com`

每次重定向重新验证 HTTPS 和 hostname。禁止 Renderer 提供或覆盖下载地址。

过期 catalog 不能授权新下载，但不影响已验证安装包离线使用。缓存 catalog 保存 ETag/Last-Modified、签名验证时间和已接受的最高 `catalog_version`。离线导入不把本地文件路径或来源声明当作信任依据；其信任根是应用内置 key ring 和 manifest 签名。

## 6. 验证与安全限制

所有安装来源都必须验证：

- manifest Ed25519 签名和 key_id；
- locale、format、catalog_version 和应用版本范围；
- 逐文件大小与 SHA-256；
- 必需 key 完整性；
- 所有语言的占位符集合与 `zh-CN` 一致；
- JSON 深度、单字符串长度、文件数、解压总量和压缩比；
- 禁止 HTML 标签、控制字符、原型污染 key；
- 禁止绝对路径、`..`、符号链接、大小写冲突、重复路径和 ZIP bomb。

在线下载还必须验证 signed catalog 和 catalog 中声明的整包 SHA-256；离线导入不声称验证网络来源，但不得跳过任何包内签名、内容和兼容性检查。

默认拒绝安装低于当前已安装版本的包。受控回滚只能选择本机已验证的 last-known-good 版本，不从网络下载旧包。

## 7. 原子安装与状态

目录：

```text
userData/language-packs/
  language-state.json
  catalog-cache/
  .downloads/
  .staging/
  en-US/<pack_version>/
  zh-TW/<pack_version>/
```

流程：

1. 下载为 `.part`。
2. 在 staging 完成全部验签、哈希、解压和 schema 检查。
3. staging 原子 rename 为新的 `<locale>/<pack_version>/`；目标版本已存在时先验证已存在内容，禁止静默覆盖。
4. 以临时文件加 replace 的方式原子更新 `language-state.json` 中的 `installed`；旧活动版本目录保持不变。
5. 激活成功后再原子更新 `active` 和 `last_known_good`，其中 `last_known_good` 指向切换前仍通过验证的版本。
6. 激活后通知 Renderer、重建托盘/原生菜单并更新桌宠语音 locale。
7. 激活失败或下次启动解析失败时恢复 last-known-good；仍失败则回退内置 `zh-CN`。失败的新版本保持未激活并记录诊断，不得删除或覆盖旧活动版本。

同一 locale 的安装、激活、删除按队列串行化。下载取消、磁盘不足、rename 失败和进程退出均不得破坏现有可用语言。

## 8. 设置与体验

桌面设置新增“语言”卡片：

- 当前语言；
- 内置/已安装/可下载状态；
- 原生名称与版本；
- 下载进度、失败原因和重试；
- 离线导入；
- 删除非活动下载包；
- 切换说明：“界面和 AI 学习内容将同时切换”。

全新安装始终以 `zh-CN` 启动，不自动跟随 Windows 系统语言。下载包切换无需重启；托盘、原生对话框和桌宠语音也必须同步。网页开发模式只提供内置 `zh-CN`，不开放语言包文件或下载能力。

## 9. 翻译与兼容规则

- `zh-CN` 是 key 和占位符的唯一基准。
- `en-US` 与 `zh-TW` 必须覆盖全部必需 key 才能发布，不允许以“部分翻译”冒充完整包。
- 用户数据、文件名、教材名、模型名和引用原文不翻译。
- “初中/高中/数学”“基础/提高/挑战”等 API 枚举保持 canonical 值，由客户端映射为本地化显示。
- UI locale 与 content locale 联动，但会话历史不重写；新生成内容使用当前 locale。
- 搜索与知识检索仍使用用户原始输入，不自动翻译查询。
- 中文模型协议字段继续只在后端内部使用，不进入语言包。

## 10. 自动化与验收

自动化覆盖：

- zh-CN key 完整性、en-US/zh-TW 全量 key 与占位符一致性；
- 缺 key、损坏状态、未知 locale 和浏览器模式回退；
- Router title、日期、数字、百分比和长英文布局；
- HTTP/SSE 错误码映射、未知 code 和 request_id；
- catalog/pack 签名、hash、错误 key、兼容范围、降级攻击和 key rotation；
- traversal、symlink、大小写冲突、重复项、ZIP bomb、HTML 注入和超限；
- 下载中断、并发、磁盘不足、rename 失败和 last-known-good 回滚；
- Renderer 不能提交 URL/路径/公钥，CSP 不放宽；
- content locale 进入模型提示但不改变协议字段；
- 打包后内置 zh-CN 可完全离线启动，en-US/zh-TW 不进入主 JS bundle。

桌面验收覆盖：

- 全新安装默认简体中文；
- 下载并即时切换 en-US/zh-TW；
- 全部路由、托盘、原生对话框、桌宠、错误提示和 AI 新内容同步切换；
- 重启、升级、断网、离线导入和损坏包回滚；
- 100%/125%/150% DPI、窄屏、长英文、CJK 字体、键盘焦点和屏幕阅读器；
- 真实签名安装包中完成语言包下载与切换，退出后无残留进程。

## 11. 密钥轮换

语言包签名使用独立 Ed25519 release key，私钥仅保存在受保护 GitHub Environment。应用内置公钥 key ring。

轮换流程：

1. 先发布同时信任旧 key 和新 key 的应用版本。
2. 再用新 key 发布 catalog 与语言包。
3. 观察升级覆盖后停止旧 key 发布。
4. 通过后续应用更新移除已吊销 key。

被应用内置撤销列表标记的 key 所签署的新下载和已安装包都必须拒绝。启动或激活时发现活动包使用已撤销 key，应先回退到由未撤销 key 签署的 last-known-good；没有可用版本时回退内置 `zh-CN`，并记录不含用户路径的诊断状态。

## 12. 非目标

- 不执行语言包内脚本、样式、HTML 或字体。
- 不让语言包改变模型协议、数据库 schema 或安全策略。
- 不在桌面端保存 GitHub Token。
- 不在本轮建立通用应用自动更新系统。
- 不自动机器翻译用户数据、教材内容或历史消息。
