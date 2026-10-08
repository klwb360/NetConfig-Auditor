# NetAudit Windows 下载与交付检查点

2026-10-08：私人仓库 `klwb360/NetAudit` 已发布 **v0.2.2**，包含文件拖入自动识别、锐捷 RGOS 解析、同类风险合并和分步骤建议命令。v0.2.1、v0.2.0、v0.1.0 的原始运行文件、标签及验收记录继续保留。

**[直接下载单 EXE](https://github.com/klwb360/NetAudit/releases/download/v0.2.2/NetAudit-0.2.2-windows-x64-8015ed5ed3d2-onefile.exe)** · [推荐便携 ZIP](https://github.com/klwb360/NetAudit/releases/download/v0.2.2/NetAudit-0.2.2-windows-x64-8015ed5ed3d2-portable.zip) · [v0.2.2 Release](https://github.com/klwb360/NetAudit/releases/tag/v0.2.2)（需登录有权限的 GitHub 账号）。Release 恰有三个运行附件；校验、构建清单和三份验收报告永久保存在 [v0.2.2 发布档案](docs/releases/v0.2.2/README.md)。

单 EXE 使用：下载 → 双击 → 等待本地网页打开 → 将一份配置拖入左侧配置文本区域 → 核对厂商 → 开始审计 → 查看与导出。也可点击导入按钮；无法可靠识别时手动选择。只读配置处理在本机完成，程序不会连接设备或执行建议命令。关闭请回到启动窗口按 Ctrl+C。便携 ZIP 解压一次后双击，迁移时复制整个文件夹，包括 `_internal`。

## v0.2.2 实际生成文件

| 文件 | SHA-256 |
|---|---|
| `NetAudit-0.2.2-windows-x64-8015ed5ed3d2-portable.zip` | `59d18d31d81e3bdc5e5875d77c5d0d0aa515dd90d0fef6ab7edf1c6b6625f9c2` |
| `NetAudit-0.2.2-windows-x64-8015ed5ed3d2-onefile.zip` | `f3865ce9012c174c51c99faa7cb0f43d319710f383e4f376fb27d41ff134aa4a` |
| `NetAudit-0.2.2-windows-x64-8015ed5ed3d2-onefile.exe` | `28fed42ae6243e7364dd51d6ef02c017ee7b0417cf304ac7b23206d90461b58c` |
| `NetAudit-0.2.2-source-8015ed5ed3d2.zip`（两个运行 ZIP 内） | `e9ce9f944d7c95be0223ea21ceda44f2f22fde3e6023f7ea47eb846e8238fedf` |

源码与 Release 标签指向 [`8015ed5ed3d2abbd6e70e7f10775724c7aafe265`](https://github.com/klwb360/NetAudit/commit/8015ed5ed3d2abbd6e70e7f10775724c7aafe265)。构建时源工作区干净；后续发布元数据和文档提交不改变 EXE 与附件字节。两个运行 ZIP 都提供完整对应源码、GPL-3.0-only LICENSE/NOTICE、第三方运行库许可、示例、网页和官方情报来源。包内文档保留构建时状态，最终发布与验收以本页及固定发布档案为准。

备用下载：[Windows Actions 原始产物](https://github.com/klwb360/NetAudit/actions/runs/37712559596/artifacts/11522815408)，有保留期限；外层 ZIP SHA-256：`e5eedba268a1e28a9f82467ebf923ecf10862e2abb5d1fda09a3eed54ee9c0dc`。Actions 下载先解压外层，再解压便携 ZIP；Release 直接提供内部运行文件。

## v0.2.2 实际验收与发布

| 环境与检查 | 结果与证据 |
|---|---|
| Windows Server 2022 10.0.20348 AMD64；Python 3.12.10 x64、PyInstaller 6.22.3；runner image 20261004.326.1 | [构建 37712559596](https://github.com/klwb360/NetAudit/actions/runs/37712559596)：272 项应用测试、28 项真实进程验收通过（源码 10、onedir 9、onefile 9） |
| Linux CI；Python 3.10 / 3.12 / 3.13 | [运行 37712559568](https://github.com/klwb360/NetAudit/actions/runs/37712559568)：三个版本全部通过 |
| 本地 Linux Python 3.12.14、Chromium 151.0.7922.173 / Playwright | 272 项应用测试、5 项源码进程检查、85 项拖入追加检查通过；此前 RGOS / 聚合为 184 项网页检查 |
| 发布器 | [运行 37712979040](https://github.com/klwb360/NetAudit/actions/runs/37712979040)：55 项保护测试、永久工程归档和三个运行附件下载回验通过，再正式发布 |

Windows 三种运行形式覆盖四厂商、JSON / Markdown / HTML 导出、识别接口与模糊时 `needs-manual`、RGOS 批量 VLAN 和同类聚合、完整流程、中文/空格路径、BAT/CLI 返回码与无暂停、端口占用回退、完整网页资源、只读程序目录、默认启动与可观察的浏览器调用、进程和 onefile 临时目录清理。全部 18 份停服记录无剩余进程、无强制清理，端口关闭。冻结版限制 PATH、移除 Python 环境验证运行库；没有从构建机卸载 Python。

Chromium 拖入检查仅使用合成配置，覆盖四厂商按内容识别、中文/空格/无扩展名文件、无效文件和多文件/目录提示、大小与行数边界、读取和检测超时、手动更改、连续导入与旧响应隔离、三种实际报告下载和 1440×1000 / 390×844 布局。无 JavaScript 错误或外部请求，测试服务退出 0，端口关闭。此前 184 项 RGOS 检查另验证全部对象、证据、合并与不同 VLAN、三类命令及前提。真实配置与私有报告没有加入源码、样例或构建包。

下载后独立核对外层 GitHub SHA、九个原始产物及八个顶层校验值、全部 ZIP CRC、onedir 129 / onefile 66 个包内校验值、两个包内源码 ZIP 和独立 EXE 字节一致、AMD64 PE、运行库及许可。117 个源码文件与固定提交一致：28 个逐字节匹配，89 个 UTF-8 文本仅发生 Windows 检出 CRLF 转换；二进制、官方情报和原归档记录保持原字节。直接解析 onefile CArchive 核对三个网页资源、四份情报资料和 `base_library.zip`；三个运行方式实际服务的规范化网页字节一致。Linux 独立核验不执行 Windows EXE，EXE 运行验证由真实 Windows runner 完成。

## v0.2.2 未测边界

Windows 10/11、ARM64、普通非管理员账户、物理上未安装 Python 的独立电脑，以及 Windows Explorer 人工双击、系统默认浏览器可视交互与实际拖入仍未实测。冻结版通过限制 PATH、移除 Python 环境验证随包运行库，构建 runner 本身仍安装 Python。建议命令经[官方参考核对](network-config-auditor/docs/REMEDIATION.md)与离线回归，没有在真实设备执行；真实 Ollama 模型和实际产品 NVD 适用性仍待验证。

以下原样保留三个旧版本交付历史，文件、提交、校验与测试数量仅对应各自版本。当前下载以本页上方 v0.2.2 和其 Release 清单为准。

## v0.2.1 历史交付记录

2026-10-03：私人仓库 `klwb360/NetAudit` 已发布 **v0.2.1 界面优化版**。旧 v0.2.0 与 v0.1.0 的运行文件、对应源码与验收记录继续保留。

[打开 v0.2.1 Release](https://github.com/klwb360/NetAudit/releases/tag/v0.2.1) · **[直接下载推荐便携 ZIP](https://github.com/klwb360/NetAudit/releases/download/v0.2.1/NetAudit-0.2.1-windows-x64-befb38bbecbb-portable.zip)**（需登录有权限的 GitHub 账号）。当前共 3 个运行附件：便携 ZIP、单 EXE 配套 ZIP、独立 EXE；源码在两个 ZIP 内提供，校验、构建清单与验收报告见 [v0.2.1 发布档案](docs/releases/v0.2.1/README.md)。

三个版本均按此方式整理：原五份校验与构建/验收资料按原始字节归档到 `docs/releases/<版本>/`，独立源码 ZIP 移除，包内源码及固定版本标签保留。原始 `SHA256SUMS.txt` 仍覆盖完整九文件构建产物；下表的源码 ZIP 哈希用于核对包内源码，并非独立附件下载。GitHub 自动生成的 Source code ZIP/tar.gz 仍会显示。本次仅整理下载入口和发布资料，没有重建 Windows EXE，也不增加其实际验收环境。

使用：下载 → 解压一次 → 双击 BAT 或 EXE → 导入配置 → 开始审计 → 切换结果页签 → 查看与导出。关闭回到启动窗口按 Ctrl+C；迁移时复制整个文件夹，包括 `_internal`。

## v0.2.1 界面优化

独立参考 `copy-only` 的概览、主题分区、内容与操作分离以及窄屏层次，整理为顶部概览和三步入门提示、左侧配置/折叠情报与 AI、右侧摘要与六页签。页签为安全发现、网络架构、漏洞情报、AI 建议、报告与清单、使用帮助；支持键盘方向键、Home/End 和原生按钮操作，切换保留输入。

修改配置、厂商或可选情报/模型设置后，旧结果和导出失效，需重新审计。进行中修改输入及慢文件读取期间启动旧文本审计，都不会把旧快照保留为新输入的结果。字体、证据文本与状态对比度已优化，桌面左右布局、窄屏堆叠。首页附 [真实合成示例截图](docs/images/workspace.png)。

解析器、35 条规则、六阶段流程、CVE/KEV、可选本机 AI 及三种报告逻辑保留。无外部字体、CDN 或新运行时依赖；原许可证和来源说明保留。

## v0.2.1 实际生成文件

| 文件 | SHA-256 |
|---|---|
| `NetAudit-0.2.1-windows-x64-befb38bbecbb-portable.zip` | `67e207dc67a6ce0d3c09fb6f69f0fb7de62ab46ca2273673c6034ca9014d7f9d` |
| `NetAudit-0.2.1-windows-x64-befb38bbecbb-onefile.zip` | `4498444bdbc5f36816fe71b1fa730c3440b92d1937b3e49a21759ab632ad55a4` |
| `NetAudit-0.2.1-windows-x64-befb38bbecbb-onefile.exe` | `a20572e92de8891b6f4f27204a4a7fccef3ebe0facc907a2d7aeb1dba013e3d8` |
| `NetAudit-0.2.1-source-befb38bbecbb.zip`（两个运行 ZIP 内） | `7d9b3c654a727269dbec07d2df40b8f4295d69ec868e4877e4cdc49341cef44e` |

实际 EXE 源码与 Release 标签指向 [`befb38bbecbbaa9d0d97c48c922e50e18c42f462`](https://github.com/klwb360/NetAudit/commit/befb38bbecbbaa9d0d97c48c922e50e18c42f462)。后续发布元数据和文档提交不改变 EXE 或附件字节。两包均提供完整对应源码、原 LICENSE/NOTICE、运行库许可、示例、网页和官方情报来源资料。

备用下载：[Actions 原始产物](https://github.com/klwb360/NetAudit/actions/runs/37136065995/artifacts/11278162885)，保留至 2027-01-01。Actions 外层 ZIP SHA-256：`06ce04dae8a15f345a159dbdcd5bdfcb50ae9b6954887379d65442aaa9ebee40`。Release 附件即其中原始文件；下载 Release 便携 ZIP 只需解压一次。

## v0.2.1 实际验收

| 环境与检查 | 结果与证据 |
|---|---|
| Windows Server 2022 10.0.20348 AMD64；Python 3.12.10 x64、PyInstaller 6.22.3；runner image 20260927.320.1 | [构建 37136065995](https://github.com/klwb360/NetAudit/actions/runs/37136065995)：192 项应用测试、28 项真实进程检查通过（源码 10、onedir 9、onefile 9） |
| Linux CI；Python 3.10 / 3.12 / 3.13 | [运行 37136065998](https://github.com/klwb360/NetAudit/actions/runs/37136065998)：三个版本全部通过 |
| 本地 Linux Python 3.12.14、Chromium headless | 192 项应用测试、65 项实际网页检查通过，0 JavaScript 错误；1440×1000、390×844、320×844 六页无整页横向溢出 |
| 发布器 | [运行 37136432263](https://github.com/klwb360/NetAudit/actions/runs/37136432263)：14 项保护测试与全部 9 个附件下载回验通过，再正式发布 |

网页验证包括六页签及键盘焦点、中文 UTF-8 导入、输入/情报文件保留、导出失效及异步竞态、原架构和情报流程、严重度筛选、三种真实下载、可选 AI 本机 HTTP 协议、恶意模型文本与 HTML 导出转义；最终三个网页文件 SHA 在整个检查期间不变，与本次源码和冻结版实际服务的资源 SHA 一致。截图使用清理可选设置后的 Cisco 合成示例。

Windows 三种运行形式继续覆盖中文/空格路径、BAT/CLI 返回码与无暂停、端口占用回退、资源加载、三厂商/三导出、完整流程、只读目录、默认启动与浏览器调用、退出和临时目录清理。报告全部停服记录无剩余进程、无强制清理且端口关闭。

实际下载后独立核对外层 SHA、全部 ZIP CRC、8 个顶层校验值、onedir 127 / onefile 64 个包内校验值、78 个完整对应源码文件、PNG 原始字节、原 GPL/NOTICE/CC0、官方情报字节、AMD64 PE 与运行库；直接解析 onefile CArchive，提取三个网页文件、四个情报文件和 `base_library.zip`，与 onedir/源码对应内容一致。Linux 独立核对不执行 Windows EXE，真实 EXE 进程验证由上述 Windows runner 完成。

## v0.2.1 未测边界

尚未实测真实 Ollama 模型质量、实际设备 NVD 适用条件、普通非管理员账户、物理独立无 Python 的电脑、Windows 10/11、ARM64，以及 Windows Explorer 人工双击/系统默认浏览器可视交互。AI 使用本机 HTTP 协议替身，NVD 匹配使用明确合成数据；官方 KEV 快照与许可另行核对。Linux Chromium 页面验收不能等同于 Windows 人工桌面验收。冻结版通过限制 PATH/移除 Python 环境验证随包运行库，构建 runner 本身仍安装 Python。

以下保留旧版本交付历史，其中的文件、提交、下载与测试数量仅对应各自版本；当前下载以本页上方 v0.2.1 与其 Release 清单为准。

## v0.2.0 历史交付记录

2026-10-03：私人仓库 `klwb360/NetAudit` 已发布 **v0.2.0**。原仓库、已合并的 PR #1、许可证和归属继续保留；旧 v0.1.0 不覆盖。

[打开 v0.2.0 Release](https://github.com/klwb360/NetAudit/releases/tag/v0.2.0) · **[直接下载推荐便携 ZIP](https://github.com/klwb360/NetAudit/releases/download/v0.2.0/NetAudit-0.2.0-windows-x64-8a9840601d6c-portable.zip)**（需登录有权访问本私人仓库的 GitHub 账号）。首次发布包含 9 个原始附件；整理后保留 3 个运行附件，包内提供源码，工程资料见 [v0.2.0 发布档案](docs/releases/v0.2.0/README.md)。

使用：下载 `*-portable.zip` → 解压一次 → 双击 `Start-NetAudit.bat` 或 `NetAudit.exe` → 导入配置并选择厂商 → 查看与导出。Ctrl+C 关闭程序；迁移时复制整个便携文件夹，包括 `_internal`。配置审计保持本地运行，不需要另装 Python；本机 Ollama 和模型仅用于用户显式启用的 AI 建议。

## v0.2.0 实现与实际文件

统一流程：配置文件 → 三厂商解析器 → VLAN / STP / OSPF / ACL / NAT / Management Plane 架构检查 → 安全规则 → CVE / KEV 情报 → 可选本机 AI 解释与整改建议 → Markdown / HTML / JSON 报告。网页、CLI、源码、onedir 与 onefile 共用流程。原有 27 条规则保留，新增 8 条 STP / OSPF 规则，共 35 个规则 ID；离线配置检查不确认实时拓扑。

默认随包提供 CISA 官方 KEV 2026.10.02 快照（1733 条），附原始来源和 CC0 许可证。导入设备 CPE 与 NVD CVE 2.0 数据后根据足够证据确认适用性，证据不足时列为候选。AI 默认关闭，只接受显式配置的本机模型，不发送原始配置，不改变规则或漏洞结论；失败时保留报告。

| 实际生成文件 | SHA-256 |
|---|---|
| `NetAudit-0.2.0-windows-x64-8a9840601d6c-portable.zip` | `72eb86ba6b99b8bef964c388b84bc9ad251e5e181dadfd537b082b73299bb794` |
| `NetAudit-0.2.0-windows-x64-8a9840601d6c-onefile.zip` | `77f4849a3ca90b5d1ca7b5698ddf92b29d9d1bb7e08d741be94204b482b98e92` |
| `NetAudit-0.2.0-windows-x64-8a9840601d6c-onefile.exe` | `bc0ae2627bd1baca884a4b1cc9950e912beaa9a0f0ff9b012c9a5d46539e70ab` |
| `NetAudit-0.2.0-source-8a9840601d6c.zip`（两个运行 ZIP 内） | `6727e00ba46557b7839673cf6cc4c84bed07241f105d69dc4f2755493bb68f52` |

完整校验、环境和范围见 [v0.2.0 发布档案](docs/releases/v0.2.0/README.md) 的 `SHA256SUMS.txt`、`manifest.json` 与三份 smoke 报告。PowerShell 校验：`Get-FileHash .\文件名.zip -Algorithm SHA256`。

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

以下保留 **v0.1.0 历史交付记录**，其中文件名、下载、提交与测试数仅对应旧版；该历史版本以本节 v0.1.0 和对应 Release 清单为准。

## v0.1.0 历史交付记录

2026-10-03：迁移至私人仓库 `klwb360/NetAudit` 已完成。原仓库保留，原 PR #1 已由仓库所有者合并。现有实现与许可证已复用，仓库使用、排错、开发、架构与贡献资料已补齐。

[打开 v0.1.0 Release 下载页](https://github.com/klwb360/NetAudit/releases/tag/v0.1.0) · **[直接下载推荐便携 ZIP](https://github.com/klwb360/NetAudit/releases/download/v0.1.0/NetAudit-0.1.0-windows-x64-f2002b79bd6d-portable.zip)**（需登录有权访问本私人仓库的 GitHub 账号）。首次发布包含 9 个原始附件；整理后保留 3 个运行附件，包内提供源码，工程资料见 [v0.1.0 发布档案](docs/releases/v0.1.0/README.md)。

使用：下载 Release 的 `*-portable.zip` → 解压一次 → 双击 `Start-NetAudit.bat` 或 `NetAudit.exe` → 导入配置并选择厂商 → 查看与导出。Ctrl+C 关闭程序；迁移时复制整个便携文件夹，包括 `_internal`。

开发或备用下载：[原 Actions 构建产物](https://github.com/klwb360/NetAudit/actions/runs/37116561468/artifacts/11272270396)，保留至 2027-01-01。Actions 下载须先解压 GitHub 外层 ZIP，再解压其中的便携 ZIP。[后续 Windows 构建](https://github.com/klwb360/NetAudit/actions/workflows/netaudit-windows.yml)与 [Release 发布指南](docs/RELEASING.md)用于维护新版本。

实际生成文件：

| 文件 | SHA-256 |
|---|---|
| `NetAudit-0.1.0-windows-x64-f2002b79bd6d-portable.zip` | `66f0400a0522395c3cf3cf19aa1294aed0f8243de7c10a6e04c658edff44090d` |
| `NetAudit-0.1.0-windows-x64-f2002b79bd6d-onefile.zip` | `645cc8b90956c82e870d671c0c09698336e288de10eb3672da4722385ad97aa3` |
| `NetAudit-0.1.0-windows-x64-f2002b79bd6d-onefile.exe` | `a1b7f309a5f98e8139cfd99dde446ff0466f1ad846196c977abc5c3756571010` |
| `NetAudit-0.1.0-source-f2002b79bd6d.zip`（两个运行 ZIP 内） | `0bac018b90e1709f5e7f826558b66df004c448f6e6a18e275ad6643342157f15` |

Actions 下载的外层 ZIP SHA-256：`f84bfff005504715e83edadd9f78560a57e0d8efe8436f0ac9140d0ea305ee26`。保留的 Release 运行附件与该 ZIP 内的文件逐字节一致；上表同时记录运行文件与包内源码的校验值。[v0.1.0 发布档案](docs/releases/v0.1.0/README.md) 的 `SHA256SUMS.txt`、`manifest.json` 和三个验收报告提供完整校验值、环境与范围。PowerShell 校验示例：`Get-FileHash .\文件名.zip -Algorithm SHA256`。

构建对应源码提交：[`f2002b79bd6da91e2a29f741c8483951e20bba86`](https://github.com/klwb360/NetAudit/commit/f2002b79bd6da91e2a29f741c8483951e20bba86)。本交付说明随后作为文档提交保存，不改变该次 EXE 对应的源码提交。两个分发 ZIP 都包含同一对应源码归档、原 LICENSE/NOTICE、第三方许可证、示例和使用说明。

Release 标签 `v0.1.0` 指向上述构建提交。[发布工作流](https://github.com/klwb360/NetAudit/actions/runs/37118017366)先核对成功构建、外层 SHA 与全部文件清单，再创建草稿、上传和下载回验 9 个附件，全部通过后正式发布；发布本身不重建 EXE。12 项发布保护测试通过，已有版本标签或附件冲突时拒绝覆盖。

[Windows 构建与验收日志](https://github.com/klwb360/NetAudit/actions/runs/37116561468)：Windows Server 2022 10.0.20348 AMD64、Python 3.12.10 x64、PyInstaller 6.22.3、runner image 20260927.320.1。独立构建环境与依赖版本固定。88 项单元测试、25 项实际进程验收（源码 9、onedir 8、onefile 8）通过。

验收覆盖：三厂商和三种导出、中文及空格路径、CLI 返回码和无暂停、端口占用回退、完整网页资源、无参数启动与浏览器调用、只读应用目录、退出无残留服务、onefile 临时目录清理。[Linux Python 3.10 / 3.12 / 3.13 检查](https://github.com/klwb360/NetAudit/actions/runs/37116561322)也全部通过。

实际下载后另行核对外层 SHA、所有产物 SHA、两个分发 ZIP CRC、包内全部文件 SHA、Windows x64 PE、对应源码、LICENSE/NOTICE 与必需的 `base_library.zip`，单 EXE 与其 ZIP 内 EXE 字节一致。

尚未实测：普通非管理员 Windows 账户、物理上未安装 Python 的独立电脑、Explorer 真实双击、系统默认浏览器可视交互与文件选择/筛选/下载对话框、Windows 10/11、ARM64。冻结版验收去除 Python 相关环境并限制 PATH；构建 runner 本身仍安装 Python，不能视为无 Python 电脑的实测。

源码位于 `network-config-auditor/`，Windows workflow 从 `main` 的项目代码改动自动构建，也支持手动运行。此前实现、历史与迁移出处见 [MIGRATION.md](MIGRATION.md)，普通用户说明见 [WINDOWS.md](network-config-auditor/docs/WINDOWS.md)。继续工作时先核对当前状态与本检查点，复用已完成的实现及验收。

本轮补充 10 项验收工具回归测试，改进 Windows 原进程对象追踪、浏览器标记完整写入等待及失败诊断上传。中间 [构建 37114758953](https://github.com/klwb360/NetAudit/actions/runs/37114758953) 在退出验收失败，未发布 EXE；修复后上述新构建全部通过。失败运行没有被记作成功，应用解析、规则、报告与 BAT 保持原样。

首次独立仓库交付对应 `16fb4254150f0cfd48014b3b628efc805dec0095`，通过 78 项测试及 25 项进程验收：[首次构建](https://github.com/klwb360/NetAudit/actions/runs/37101723226)。历史文档与 Git 记录继续保留；当前下载与校验以本文件上表和对应构建清单为准。
