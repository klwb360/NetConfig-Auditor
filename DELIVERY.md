# NetAudit Windows 下载与交付检查点

2026-10-03：私人仓库 `klwb360/NetAudit` 已发布 **v0.2.0**。原仓库、已合并的 PR #1、许可证和归属继续保留；旧 v0.1.0 不覆盖。

[打开 v0.2.0 Release](https://github.com/klwb360/NetAudit/releases/tag/v0.2.0) · **[直接下载推荐便携 ZIP](https://github.com/klwb360/NetAudit/releases/download/v0.2.0/NetAudit-0.2.0-windows-x64-8a9840601d6c-portable.zip)**（需登录有权访问本私人仓库的 GitHub 账号）。共 9 个原始附件，包含 Windows 便携 ZIP、单 EXE 包、独立 EXE、对应源码、构建清单、三份验收报告和校验文件。

使用：下载 `*-portable.zip` → 解压一次 → 双击 `Start-NetAudit.bat` 或 `NetAudit.exe` → 导入配置并选择厂商 → 查看与导出。Ctrl+C 关闭程序；迁移时复制整个便携文件夹，包括 `_internal`。配置审计保持本地运行，不需要另装 Python；本机 Ollama 和模型仅用于用户显式启用的 AI 建议。

## v0.2.0 实现与实际文件

统一流程：配置文件 → 三厂商解析器 → VLAN / STP / OSPF / ACL / NAT / Management Plane 架构检查 → 安全规则 → CVE / KEV 情报 → 可选本机 AI 解释与整改建议 → Markdown / HTML / JSON 报告。网页、CLI、源码、onedir 与 onefile 共用流程。原有 27 条规则保留，新增 8 条 STP / OSPF 规则，共 35 个规则 ID；离线配置检查不确认实时拓扑。

默认随包提供 CISA 官方 KEV 2026.10.02 快照（1733 条），附原始来源和 CC0 许可证。导入设备 CPE 与 NVD CVE 2.0 数据后根据足够证据确认适用性，证据不足时列为候选。AI 默认关闭，只接受显式配置的本机模型，不发送原始配置，不改变规则或漏洞结论；失败时保留报告。

| 实际生成文件 | SHA-256 |
|---|---|
| `NetAudit-0.2.0-windows-x64-8a9840601d6c-portable.zip` | `72eb86ba6b99b8bef964c388b84bc9ad251e5e181dadfd537b082b73299bb794` |
| `NetAudit-0.2.0-windows-x64-8a9840601d6c-onefile.zip` | `77f4849a3ca90b5d1ca7b5698ddf92b29d9d1bb7e08d741be94204b482b98e92` |
| `NetAudit-0.2.0-windows-x64-8a9840601d6c-onefile.exe` | `bc0ae2627bd1baca884a4b1cc9950e912beaa9a0f0ff9b012c9a5d46539e70ab` |
| `NetAudit-0.2.0-source-8a9840601d6c.zip` | `6727e00ba46557b7839673cf6cc4c84bed07241f105d69dc4f2755493bb68f52` |

完整校验、环境和范围见 Release 的 `SHA256SUMS.txt`、`manifest.json` 与三份 smoke 报告。PowerShell 校验：`Get-FileHash .\文件名.zip -Algorithm SHA256`。

实际构建源码及 Release 标签：[8a9840601d6c51dbdaff1fbbf62aeaf84cc0b490](https://github.com/klwb360/NetAudit/commit/8a9840601d6c51dbdaff1fbbf62aeaf84cc0b490)。后续发布元数据及本交付说明不改变 EXE 对应源码。两种分发 ZIP 都含同一完整源码归档、原 LICENSE/NOTICE、第三方许可证、示例、网页、情报快照和使用说明。

备用下载：[原 Actions 产物](https://github.com/klwb360/NetAudit/actions/runs/37120272682/artifacts/11272449538)，保留至 2027-01-01。Actions 下载先解压 GitHub 外层 ZIP，再解压便携 ZIP；外层 SHA-256 为 `45dc43a26b1073a3214e86f32eb6e7d59571e7bb4cf8b296ae366af067fdacb1`。Release 附件与外层 ZIP 内文件逐字节一致。

## v0.2.0 实际验收与发布

| 环境与检查 | 实际结果与证据 |
|---|---|
| Windows Server 2022 10.0.20348 AMD64；Python 3.12.10 x64、PyInstaller 6.22.3；runner image 20260927.320.1 | [构建 37120272682](https://github.com/klwb360/NetAudit/actions/runs/37120272682)：192 项应用测试、28 项真实进程验收通过（源码 10、onedir 9、onefile 9） |
| Linux CI；Python 3.10 / 3.12 / 3.13 | [运行 37120272642](https://github.com/klwb360/NetAudit/actions/runs/37120272642)：三个版本全部通过 |
| 本地 Linux；Python 3.12.14、Chromium headless | 192 项应用测试、5 项源码真实进程检查、24 项实际网页检查通过 |
| GitHub Actions 发布器 | [运行 37120600936](https://github.com/klwb360/NetAudit/actions/runs/37120600936)：14 项保护测试通过，9 个附件上传后全部下载回验，于 2026-10-03 11:44:38 UTC 正式发布 |

Windows 三种运行形式覆盖原三厂商与三种导出、六阶段/六域、新情报资源、中文及空格路径、BAT/CLI 返回码与无暂停、端口冲突回退、完整网页资源、无参数启动/浏览器调用、只读目录、退出无遗留服务、onefile 临时目录清理。停服记录均无剩余进程、无强制清理且端口关闭。

Chromium 实际导入文件并检查示例、筛选、六域/流程、精确匹配与候选、三个真实下载、AI 设置/HTTP 协议、恶意模型文本转义、桌面/移动布局；无脚本错误，服务已关闭。该结果属于 Linux 浏览器自动化。

下载后独立核对外层与全部产物 SHA、ZIP CRC、包内哈希、Windows AMD64 PE、运行库、对应完整源码、LICENSE/NOTICE、情报来源和 CC0 许可。onedir 资源、两包可读情报数据，以及直接从 onefile EXE 解出的嵌入数据均与对应源码逐字节一致；独立 EXE 与其 ZIP 内文件一致。

首次 [v0.2.0 Windows 运行 37119894388](https://github.com/klwb360/NetAudit/actions/runs/37119894388) 因 Git 检出转换官方 KEV 换行而触发 SHA 校验失败，未生成分发 EXE。项目 `.gitattributes` 保持官方数据与许可证原始字节，并新增实际 `core.autocrlf=true` 临时 Git 检出回归；上述成功构建包含修复，没有放宽校验。

## v0.2.0 尚未实测

AI 已通过实际本机 HTTP 协议替身的单元、CLI、网页和 Windows 冻结版检查，尚未运行真实 Ollama 模型，不能确认模型解释质量。NVD 官方 API 在本次环境被代理返回 403；适用条件测试采用明确标注的合成数据，实际产品/版本仍须导入真实情报并复核。KEV 收录不等于设备受影响或已被入侵。

普通非管理员 Windows 账户、物理上未安装 Python 的独立电脑、Explorer 人工双击、系统默认浏览器可视交互与文件选择/下载对话框、Windows 10/11、ARM64 尚未实测。冻结版验收去除 Python 环境并限制 PATH；构建 runner 本身仍安装 Python，不能视为独立无 Python 电脑的实测。

以下保留 **v0.1.0 历史交付记录**，其中文件名、下载、提交与测试数仅对应旧版；当前版本以本页上方 v0.2.0 和对应 Release 清单为准。

## v0.1.0 历史交付记录

2026-10-03：迁移至私人仓库 `klwb360/NetAudit` 已完成。原仓库保留，原 PR #1 已由仓库所有者合并。现有实现与许可证已复用，仓库使用、排错、开发、架构与贡献资料已补齐。

[打开 v0.1.0 Release 下载页](https://github.com/klwb360/NetAudit/releases/tag/v0.1.0) · **[直接下载推荐便携 ZIP](https://github.com/klwb360/NetAudit/releases/download/v0.1.0/NetAudit-0.1.0-windows-x64-f2002b79bd6d-portable.zip)**（需登录有权访问本私人仓库的 GitHub 账号）。Release 保存本次验收的原始文件、对应源码、构建清单、三份验收报告与校验文件，共 9 个附件。

使用：下载 Release 的 `*-portable.zip` → 解压一次 → 双击 `Start-NetAudit.bat` 或 `NetAudit.exe` → 导入配置并选择厂商 → 查看与导出。Ctrl+C 关闭程序；迁移时复制整个便携文件夹，包括 `_internal`。

开发或备用下载：[原 Actions 构建产物](https://github.com/klwb360/NetAudit/actions/runs/37116561468/artifacts/11272270396)，保留至 2027-01-01。Actions 下载须先解压 GitHub 外层 ZIP，再解压其中的便携 ZIP。[后续 Windows 构建](https://github.com/klwb360/NetAudit/actions/workflows/netaudit-windows.yml)与 [Release 发布指南](docs/RELEASING.md)用于维护新版本。

实际生成文件：

| 文件 | SHA-256 |
|---|---|
| `NetAudit-0.1.0-windows-x64-f2002b79bd6d-portable.zip` | `66f0400a0522395c3cf3cf19aa1294aed0f8243de7c10a6e04c658edff44090d` |
| `NetAudit-0.1.0-windows-x64-f2002b79bd6d-onefile.zip` | `645cc8b90956c82e870d671c0c09698336e288de10eb3672da4722385ad97aa3` |
| `NetAudit-0.1.0-windows-x64-f2002b79bd6d-onefile.exe` | `a1b7f309a5f98e8139cfd99dde446ff0466f1ad846196c977abc5c3756571010` |
| `NetAudit-0.1.0-source-f2002b79bd6d.zip` | `0bac018b90e1709f5e7f826558b66df004c448f6e6a18e275ad6643342157f15` |

Actions 下载的外层 ZIP SHA-256：`f84bfff005504715e83edadd9f78560a57e0d8efe8436f0ac9140d0ea305ee26`。Release 附件与该 ZIP 内的文件逐字节一致；上表是可直接下载文件的校验值。`SHA256SUMS.txt`、`manifest.json` 和三个验收报告提供完整校验值、环境与范围。PowerShell 校验示例：`Get-FileHash .\文件名.zip -Algorithm SHA256`。

构建对应源码提交：[`f2002b79bd6da91e2a29f741c8483951e20bba86`](https://github.com/klwb360/NetAudit/commit/f2002b79bd6da91e2a29f741c8483951e20bba86)。本交付说明随后作为文档提交保存，不改变该次 EXE 对应的源码提交。两个分发 ZIP 都包含同一对应源码归档、原 LICENSE/NOTICE、第三方许可证、示例和使用说明。

Release 标签 `v0.1.0` 指向上述构建提交。[发布工作流](https://github.com/klwb360/NetAudit/actions/runs/37118017366)先核对成功构建、外层 SHA 与全部文件清单，再创建草稿、上传和下载回验 9 个附件，全部通过后正式发布；发布本身不重建 EXE。12 项发布保护测试通过，已有版本标签或附件冲突时拒绝覆盖。

[Windows 构建与验收日志](https://github.com/klwb360/NetAudit/actions/runs/37116561468)：Windows Server 2022 10.0.20348 AMD64、Python 3.12.10 x64、PyInstaller 6.22.3、runner image 20260927.320.1。独立构建环境与依赖版本固定。88 项单元测试、25 项实际进程验收（源码 9、onedir 8、onefile 8）通过。

验收覆盖：三厂商和三种导出、中文及空格路径、CLI 返回码和无暂停、端口占用回退、完整网页资源、无参数启动与浏览器调用、只读应用目录、退出无残留服务、onefile 临时目录清理。[Linux Python 3.10 / 3.12 / 3.13 检查](https://github.com/klwb360/NetAudit/actions/runs/37116561322)也全部通过。

实际下载后另行核对外层 SHA、所有产物 SHA、两个分发 ZIP CRC、包内全部文件 SHA、Windows x64 PE、对应源码、LICENSE/NOTICE 与必需的 `base_library.zip`，单 EXE 与其 ZIP 内 EXE 字节一致。

尚未实测：普通非管理员 Windows 账户、物理上未安装 Python 的独立电脑、Explorer 真实双击、系统默认浏览器可视交互与文件选择/筛选/下载对话框、Windows 10/11、ARM64。冻结版验收去除 Python 相关环境并限制 PATH；构建 runner 本身仍安装 Python，不能视为无 Python 电脑的实测。

源码位于 `network-config-auditor/`，Windows workflow 从 `main` 的项目代码改动自动构建，也支持手动运行。此前实现、历史与迁移出处见 [MIGRATION.md](MIGRATION.md)，普通用户说明见 [WINDOWS.md](network-config-auditor/docs/WINDOWS.md)。继续工作时先核对当前状态与本检查点，复用已完成的实现及验收。

本轮补充 10 项验收工具回归测试，改进 Windows 原进程对象追踪、浏览器标记完整写入等待及失败诊断上传。中间 [构建 37114758953](https://github.com/klwb360/NetAudit/actions/runs/37114758953) 在退出验收失败，未发布 EXE；修复后上述新构建全部通过。失败运行没有被记作成功，应用解析、规则、报告与 BAT 保持原样。

首次独立仓库交付对应 `16fb4254150f0cfd48014b3b628efc805dec0095`，通过 78 项测试及 25 项进程验收：[首次构建](https://github.com/klwb360/NetAudit/actions/runs/37101723226)。历史文档与 Git 记录继续保留；当前下载与校验以本文件上表和对应构建清单为准。
