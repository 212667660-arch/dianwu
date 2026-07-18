# Windows Trusted Signing Design

**任务：** S-041 / S-042
**日期：** 2026-07-18
**状态：** 已批准
**目标：** 使用 Azure Trusted Signing 和受保护 GitHub Actions 发布环境，为 Windows 桌面发布链中的自有可执行文件提供可验证、可审计、缺凭据即失败的可信签名。

## 1. 已确认决策

- 正式签名服务采用 Azure Trusted Signing。
- 正式签名只在 GitHub Actions 的 `windows-signing` 受保护 Environment 中执行。
- 触发方式限于手动 `workflow_dispatch` 和受保护的 `v*` 发布标签；pull request、fork 和普通分支测试不得获得签名权限。
- Azure Trusted Signing 资源按“尚未创建”处理。仓库提供创建与配置说明；资源未就绪时，正式发布任务必须明确阻塞，而不是退化为未签名发布。
- 本地开发允许继续构建 unsigned unpacked/installer 用于测试，但不得标记为正式发布。
- Windows 正式发布缺少签名、时间戳或发布者不匹配时必须硬失败。
- 只签项目自有可执行文件，不批量重签 Microsoft、Python 或其他第三方 DLL/PYD。

## 2. 当前状态与根因

`front/a3-front/package.json` 仅设置 `win.signAndEditExecutable: true`。该选项允许 electron-builder 修改 PE 资源并在有证书时签名，但没有证书时会跳过 Authenticode，因此不等价于“已启用可信签名”。当前项目没有：

- `forceCodeSigning` 发布门；
- Azure Trusted Signing 配置；
- 签名专用 GitHub Actions workflow；
- 对安装器、主程序、后端子进程和卸载器的签名验证；
- 签名后制品清单。

PyInstaller 构建的 `api.exe` 会作为 `extraResources/backend/api.exe` 被 Electron 启动。只签外层安装器不能解决未签名子进程被 Defender、EDR 或应用控制策略阻止的问题。

## 3. 发布架构

### 3.1 配置边界

新增独立的正式发布配置 `front/a3-front/electron-builder.signed.cjs`：

- 复用现有 appId、productName、图标、NSIS 和 extraResources 设置；
- 设置 `forceCodeSigning: true`；
- 只使用 SHA-256；
- 从环境变量读取 Azure endpoint、code signing account 和 certificate profile；
- 不在配置、命令行参数或日志中打印认证秘密；
- 未发现全部必需配置时，在开始打包前返回稳定错误。

本地 `desktop:pack` 与 `desktop:dist` 保留为开发/验收入口。新增 `desktop:dist:signed`，它只允许在显式 `A3_SIGNED_RELEASE=1` 且 Azure 配置完整时运行。

### 3.2 GitHub Environment

`windows-signing` Environment 保存：

GitHub Environment variables（非秘密）：

- `AZURE_TENANT_ID`
- `AZURE_CLIENT_ID`
- `AZURE_TRUSTED_SIGNING_ENDPOINT`
- `AZURE_CODE_SIGNING_ACCOUNT_NAME`
- `AZURE_CERTIFICATE_PROFILE_NAME`
- `A3_EXPECTED_PUBLISHER`

GitHub Environment secret：

- `AZURE_CLIENT_SECRET`

`AZURE_CLIENT_SECRET` 只在受保护 job 生命周期内注入，并纳入日志脱敏；不得写入仓库、artifact、缓存、诊断包、命令回显或制品清单。服务主体只授予目标 Trusted Signing account/profile 所需的最小权限。Environment 必须启用人工审批或等效保护规则。

### 3.3 Workflow

新增 `.github/workflows/windows-signed-release.yml`：

1. 检出请求提交并确认工作树提交与发布标签一致。
2. 安装锁定版本 Node/Python 依赖。
3. 运行后端 `compileall`、完整 pytest、Electron/Node、Vitest 和 `build:desktop`。
4. 使用现有 PyInstaller 脚本构建并验证完整 onedir 后端。
5. 复制最终后端到 `front/a3-front/desktop-backend`。
6. 用 `desktop:dist:signed` 调用 electron-builder 和 Azure Trusted Signing。
7. 验证所有要求签名的制品。
8. 签名验证通过后生成 SHA-256、大小、发布者、时间戳和源提交清单。
9. 仅在 `v*` 标签触发时创建/更新对应 GitHub Release；手动非标签运行只上传受限 Actions artifact。

Workflow 不使用来自 PR 的脚本搭配签名秘密。GitHub Environment 审批时显示待签名提交、版本和触发者。

## 4. 签名范围与顺序

顺序必须保证签名后文件不再被修改：

1. PyInstaller 生成完整 `dist/api`。
2. 完成 worker、健康检查、OCR、恶意内容扫描和文件一致性检查。
3. 将最终后端复制到 `desktop-backend`。
4. electron-builder 完成主程序资源编辑，并在打包过程中签署：
   - `win-unpacked/智学协作台.exe`
   - `win-unpacked/resources/backend/api.exe`
   - electron-builder 自有的 `elevate.exe`
5. 生成并签署 NSIS 卸载器。
6. 生成并签署最终 `智学协作台 Setup <version>.exe`。
7. 对安装前和真实安装后的主程序、后端、elevate、卸载器和安装器执行验证。
8. 最后计算发布 SHA-256 并写入 JSON 制品清单；清单至少记录 schema 版本、源提交、应用版本、相对路径、字节数、SHA-256、签名 Subject、时间戳状态和验证时间。

如果未来独立发布 `dist/api/api.exe`，它必须作为单独产品签名和验收；当前范围只保证桌面安装包内的后端子进程。

## 5. 验证与失败处理

新增 `scripts/release/verify-windows-signatures.ps1`，使用 `Get-AuthenticodeSignature` 和可用时的 `signtool verify /pa /all /v` 检查：

- `Status` 为 `Valid`；
- Subject/发布者与 `A3_EXPECTED_PUBLISHER` 精确匹配；
- 文件摘要为 SHA-256；
- 存在可信时间戳，且签名时间落在证书有效期内；
- 安装前后对应二进制哈希和签名身份符合清单；
- 任一制品缺失、未签名、签名无效、发布者错误或无时间戳时退出非零。

安装后验证使用隔离临时目录和受控静默安装参数，并从安装根目录定位主程序、`resources/backend/api.exe`、`resources/elevate.exe` 与卸载器；路径缺失或出现同名歧义时不得猜测，直接失败。临时安装验证完成后必须卸载并确认无残留 A3 进程。

测试模式使用构造的签名结果对象验证脚本分支，不需要真实生产凭据。真实签名验收只在受保护发布环境执行。

## 6. 自动化门槛

- 静态测试证明 signed config 启用 `forceCodeSigning`、SHA-256 和 Azure 配置校验。
- 静态扫描证明仓库不包含 PFX/P12、私钥、证书密码、Azure client secret 或 Base64 证书。
- 无 Azure 配置时 `desktop:dist:signed` 必须在打包前失败；普通开发构建仍可运行。
- 构造的 Valid/NotSigned/HashMismatch/PublisherMismatch/NotTimeStamped 结果都有定向测试。
- 对签名后的临时副本修改一个字节，验收脚本必须拒绝。
- 干净 Windows VM 完成安装、启动、托盘退出、卸载和零残留进程验收。
- 保留现有 560 项后端、180 项 Electron/Node、151 项 Vitest 与桌面生命周期回归门槛，并以实施后的实际计数为准更新队列。

## 7. Azure 资源准备

仓库文档 `docs/release/azure-trusted-signing.md` 必须给出：

- Trusted Signing account 与 certificate profile 创建步骤；
- 身份验证要求与支持区域检查；
- 服务主体最小权限；
- GitHub Environment variables/secrets 的准确名称；
- 如何在不输出秘密的情况下验证 Azure 连接；
- 凭据轮换和吊销流程；
- 资源未就绪时任务保持阻塞的预期行为。

文档不得要求用户把 secret、证书或密码提交到仓库或聊天。

## 8. 非目标

- 不实现 macOS notarization 或 Linux 包签名。
- 不把自签名证书当作正式可信发布证书。
- 不关闭 Windows、GitHub 或 Azure 的安全保护来通过发布。
- 不为普通 CI、pull request 或开发构建开放签名秘密。
