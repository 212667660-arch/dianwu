# Azure Trusted Signing 发布配置

本仓库不会自动创建 Azure 或 GitHub Environment 资源。Windows 正式发布负责人必须按以下顺序完成配置，并保持资源专用于 A3 Windows 发布：

1. 确认所选 Azure 地区提供 Azure Trusted Signing，并确认组织具备完成身份验证的资格。
2. 创建专用的 Trusted Signing account，并在其中创建 `public-trust` certificate profile。
3. 创建专用于 GitHub 签名发布的 Microsoft Entra application/service principal。
4. 仅在目标 Trusted Signing account/profile scope 为该服务主体授予 `Trusted Signing Certificate Profile Signer`。不要授予订阅级、资源组级或其他 profile 的额外权限。
5. 创建 GitHub Environment `windows-signing`，配置 required reviewers、deployment branch/tag restrictions，并在仓库策略允许时禁止管理员绕过保护规则。
6. 在该 Environment 中添加下列 6 个非秘密变量和 1 个 secret。名称必须与工作流完全一致。

非秘密变量：

- `AZURE_TENANT_ID`
- `AZURE_CLIENT_ID`
- `AZURE_TRUSTED_SIGNING_ENDPOINT`
- `AZURE_CODE_SIGNING_ACCOUNT_NAME`
- `AZURE_CERTIFICATE_PROFILE_NAME`
- `A3_EXPECTED_PUBLISHER`

Secret：

- `AZURE_CLIENT_SECRET`

本文不提供 tenant、client、secret、证书、密码、PFX/P12 或私钥示例。真实凭据禁止粘贴到 issues、chat、logs、commits 或 artifacts，也不得进入缓存、诊断包和发布清单。

## 权限与凭据暴露范围

`.github/workflows/windows-signed-release.yml` 使用受保护的 `windows-signing` Environment。Environment 保护审批通过后，长期凭据 `AZURE_CLIENT_SECRET` 仍只注入 `Build signed Windows installer` 签名构建步骤；源码校验、依赖安装、测试、前后端构建、后端打包和 secret 扫描步骤均不可见该 secret。不要把凭据提升到 workflow、job 或其他 step 的环境范围。

正式工作流是唯一的真实 Azure 连接测试。它必须通过人工审批和分支/标签限制后运行；资源、权限或凭据缺失时，发布应被阻断。

## 本地形状校验

在仓库根目录运行：

```powershell
cd front/a3-front
$env:A3_SIGNED_RELEASE = '1'
node scripts/release/validate-signing-env.mjs
```

该命令只检查配置项的存在性和形状，不验证真实 Azure 连接。未在当前进程提供所需配置时，它会列出稳定的缺失/无效配置错误；不要为了让本地校验通过而复制生产 secret。真实 Azure 身份、权限、endpoint 和 certificate profile 由受保护工作流验证。

## 构建入口与失败策略

```text
npm run desktop:pack          # 本地未签名开发包
npm run desktop:dist          # 本地未签名开发安装程序
npm run desktop:dist:signed   # 正式路径；缺少受保护配置时在打包前失败
```

`desktop:pack` 和 `desktop:dist` 只用于本地开发与验收，不得作为正式发布产物。`desktop:dist:signed` 启用 `forceCodeSigning` 并 fail closed：缺少保护配置、Azure 权限、有效 profile 或签名结果时，不得生成或发布未签名替代品。

如果 Azure account/profile 被暂停或撤销，正式发布必须立即阻断。不得通过关闭 `forceCodeSigning`、改走未签名命令或放宽验证来绕过。

## 客户端凭据轮换

严格按以下顺序轮换服务主体凭据：

1. 为同一专用 Entra application 创建第二个客户端凭据，保留旧凭据暂时有效。
2. 仅替换 GitHub Environment `windows-signing` 中的 `AZURE_CLIENT_SECRET` secret；不要修改变量、权限 scope 或工作流暴露范围。
3. 审批并运行一次手动 signed build，确认完整签名、时间戳、发布者和安装验证均通过。
4. 撤销旧客户端凭据。

若第 3 步失败，保留旧凭据并修复新凭据或权限配置；不得撤销可用凭据后再用未签名发布兜底。
