# 验证记录

## v1.0.1 Windows 构建与正式发布验收（2026-10-09）

实际构建源码与标签为 `fb5a64016f4502666b1394ef57238f1518d8799b`，[v1.0.1](https://github.com/klwb360/NetAudit/releases/tag/v1.0.1) 已正式发布。分别核验源码、浏览器、Windows 冻结 EXE 与发布器，不能以源码通过推定 EXE 验收。

| 环境与检查 | 结果与证据 |
|---|---|
| `Windows-2022Server-10.0.20348-SP0` / AMD64；Python 3.12.10 x64、PyInstaller 6.22.3；runner image 20261004.326.1 | [构建 37980042815](https://github.com/klwb360/NetAudit/actions/runs/37980042815)：396 项应用测试、27 组分类测试、28 项真实进程验收通过（源码 10、onedir 9、onefile 9） |
| Linux CI；Python 3.10 / 3.12 / 3.13 | [运行 37980042931](https://github.com/klwb360/NetAudit/actions/runs/37980042931)：三个版本全部通过 |
| 本地 Linux x86_64 / Python 3.12.14 / Chromium 151 / Playwright 1.62 | 396 项应用测试、27 组分类测试、66 项发布工具测试、5 项源码进程验收及 185 项网页检查通过 |
| GitHub Actions 发布器 | [正式发布运行 37980621937](https://github.com/klwb360/NetAudit/actions/runs/37980621937)：66 项保护测试、永久归档及三个运行附件上传后的下载回验通过 |

Windows 源码、onedir、onefile 均验证六个完整网页资源，包含新增厂商分类与高亮脚本；继续验证四厂商导入识别、中文目标、模拟命令事务与失败回滚、原文 / CRLF / 未知行保留、实际 `plan` / `simulate` CLI 与 JSON 输出、三种审计报告、中文及空格路径、BAT / CLI 无暂停、端口回退、默认启动及可观察浏览器调用、只读位置与用户临时目录。全部 18 份停服记录无剩余进程、无强制清理且端口关闭；onefile 临时目录清理通过。冻结版限制 PATH 并移除 Python 环境变量后运行，runner 本身仍装有构建 Python。

Linux Chromium 完成 185 项实际网页检查：四色与共享语法上下文、未知行 / 注释 / Banner 中性显示、图例与光标行解释、拖入与示例、草案 / 预览标签、模拟应用 / 撤销 / 重置、原生编辑 / 选择 / 复制 / 撤销、CRLF 与合成凭据原文导出及三种完整报告。明亮、暗黑、跟随系统、文字对比度、宽窄屏与横纵滚动通过；30,000 行末尾无累计错位，背景仅绘制可见行，2 MiB 单行及超限后恢复通过。中文输入组合只测试合成事件，未验证 Windows 真实输入法。无 JavaScript 异常或外部请求，测试服务正常退出且端口关闭。测试、截图和构建样例仅使用合成配置，真实备份与私有报告未纳入。

独立核验外层 GitHub artifact SHA、九个原始产物、八个顶层校验值、全部 ZIP CRC，以及 onedir 133 / onefile 67 个包内校验值。149 个源码文件对应固定提交，其中 50 个逐字节一致、99 个 UTF-8 文本仅发生 Windows CRLF 检出转换；二进制、官方情报和已有档案保持原字节。核对两个运行 ZIP 中的对应源码、独立 EXE 一致性、AMD64 PE、运行库、许可证与归属，并直接提取 onefile CArchive 六个网页资源、情报与 `base_library.zip`。三种运行形式的资源与浏览器验收源码一致。Linux 独立文件核验不执行 Windows EXE，EXE 运行证据来自真实 Windows runner。

底色属于保守的阅读提示，无法覆盖所有型号、固件或厂商语法；共享语法不能单独证明配置来自某一家厂商。底色不判断安全或可执行性，具体结论仍看模拟预览及按需审计。这是离线配置状态模拟，不模拟数据包转发、物理链路、协议收敛或真实登录；完整范围见 [模拟练习说明](SIMULATOR.md)。

Windows 10/11、ARM64、普通非管理员账户、物理上未安装 Python 的独立电脑，以及 Windows Explorer 人工双击、系统默认浏览器可视交互、实际拖入和真实中文输入法仍未实测。建议命令未在真实设备执行；真实 Ollama 模型和实际产品 NVD 适用性仍待验证。

以下逐字保留发布前本地验收与旧版记录；最终 Windows 交付以上节为准。

## v1.0.1 厂商底色高亮：本地验收（2026-10-09）

在已发布 v1.0.0 基础上增加四厂商语法底色、共享语法说明和光标行提示；不改变模拟器、审计解析或报告语义。本节为发布前源码与浏览器实测，Windows 构建和 EXE 验收将单独追加。

Linux x86_64 / Python 3.12.14 上 396 项应用回归、66 项发布工具保护测试、27 组 Node 分类测试通过。分类覆盖四厂商、兼容上下文与共享语法、未知行、注释、Cisco Banner、华为及 H3C Header 正文与文件引用、原文和大小边界。源码版 5 项真实进程验收通过，三条服务路径均核对完整六个网页资源；测试服务正常退出、端口关闭且无剩余服务进程。标准 wheel 的六个网页资源与最终源码逐字一致。

Chromium 151 / Playwright 1.62 在 Linux 完成 185 项实际网页检查，含本次高亮和原有配置练习回归。覆盖四厂商颜色、共享候选与上下文、原生编辑/复制/撤销、拖入与示例、草案/预览标签、应用/撤销/重置刷新、CRLF 和未知行/合成凭据的原文导出、三种审计报告、明暗主题与系统切换、文字对比度、宽窄屏、横纵滚动及大小边界。30,000 行滚动至末尾无累计错位，背景只绘制可见行；2 MiB 单行与超限后的降级恢复通过。中文输入组合事件只做合成事件检查，不代表 Windows 实际中文输入法验收。

浏览器无 JavaScript 异常或外部请求，测试服务正常退出且端口关闭；六网页资源及服务端/模拟引擎/目标规划共九个源码文件的 SHA-256 绑定到最终测试版本。仅使用合成配置，未上传用户备份或私有报告。源码和 Linux 浏览器测试不能代替 Windows 冻结 EXE、Explorer 双击或真实设备验证。

## v1.0.0 Windows 构建与正式发布验收（2026-10-09）

实际构建源码与 Release 标签为 `e2b4efecdc2682db8cef49d369c6fb0c9114b8b0`，[v1.0.0](https://github.com/klwb360/NetAudit/releases/tag/v1.0.0) 已正式发布。源码、本地浏览器、Windows 冻结 EXE 与发布器分别核验，结果如下。

| 环境与检查 | 结果与证据 |
|---|---|
| Windows Server 2022 10.0.20348 AMD64；Python 3.12.10 x64、PyInstaller 6.22.3；runner image 20261004.326.1 | [构建 37895686338](https://github.com/klwb360/NetAudit/actions/runs/37895686338)：396 项应用测试、28 项真实进程验收通过（源码 10、onedir 9、onefile 9） |
| Linux CI；Python 3.10 / 3.12 / 3.13 | [运行 37895686403](https://github.com/klwb360/NetAudit/actions/runs/37895686403)：三个版本全部通过 |
| 本地 Linux x86_64 / Python 3.12.14 / Chromium / Playwright | 396 项应用测试、5 项源码进程验收、128 项网页检查、62 项发布工具测试通过 |
| GitHub Actions 发布器 | [正式发布运行 37896235786](https://github.com/klwb360/NetAudit/actions/runs/37896235786)：62 项保护测试、永久工程归档与三个运行附件下载回验通过 |

Windows 源码、onedir 和 onefile 三种运行形式实际验证四厂商导入识别、中文目标生成与重放、命令预览 / 配置事务与整批回滚、CRLF 与未知配置 / 凭据保留、真正 `plan` / `simulate` CLI 的成功与失败 JSON 输出及退出码；模拟默认不调用审计或 AI。继续验证四厂商三种审计报告、原有 RGOS VLAN 范围与风险聚合、完整审计流程、中文 / 空格路径、BAT / CLI 不暂停、端口回退、四个完整网页资源、默认启动及可观察的浏览器调用、只读位置与用户临时目录。全部 18 份停服记录无剩余进程、无强制清理且端口关闭；onefile 临时目录清理通过。冻结版移除 Python 环境变量并限制 PATH 后运行，构建主机本身仍装有 Python。

Linux Chromium / Playwright 完成 128 项实际网页检查：四厂商拖入、中文目标就绪 / 缺参 / 不支持、预览后明确应用、失败批次不应用、模式续练、撤销与重置、原文配置导出再导入、按需审当前已应用副本与三种完整报告、过期异步结果隔离、忙碌 / 错误恢复、主题切换、重复风险折叠、键盘及桌面 / 窄屏布局。无 JavaScript 错误或外部请求，测试服务正常退出且端口关闭。全部测试、截图和构建样例仅使用合成配置，真实备份和私有报告未纳入仓库、日志或分发包。

独立核验外层 GitHub artifact SHA、九个原始产物、八个顶层校验值、全部 ZIP CRC，以及 onedir 131 / onefile 67 个包内校验值。139 个完整源码文件对应固定构建提交，其中 43 个逐字节一致、96 个 UTF-8 文本仅发生 Windows CRLF 检出转换；二进制、官方情报和已有发布档案均保持原字节。两个运行 ZIP 中的对应源码包和独立 EXE 字节一致；核对 AMD64 PE、运行库、许可证与归属，直接提取 onefile CArchive 的四个网页资源、情报及 `base_library.zip`。网页与 Windows 三种服务形式和 Linux 浏览器使用的规范化源码一致。Linux 独立文件核验不执行 Windows EXE，运行证据来自真实 Windows runner。

首次 [Windows 构建 37895371014](https://github.com/klwb360/NetAudit/actions/runs/37895371014) 已通过 396 项应用测试，但 `source-BAT` 的模拟失败批次验收发现启动器错误提示混入标准输出，使原本用于自动化的 JSON 不可直接解析。启动器诊断统一改到标准错误，保留应用退出码和无暂停行为；修复后重新构建并完成上方全部验收。首次失败记录不作为最终 EXE 交付依据。

这是离线配置状态模拟，覆盖范围以 [模拟练习说明](SIMULATOR.md) 为准；不模拟数据包转发、物理链路、STP 收敛、OSPF 邻居或真实登录。“可修改”不保证实机型号 / 固件兼容或业务连通；“尚不支持”不能据此判断真实设备禁止执行。中文草案是有限的离线单目标模板，复杂需求须拆分并补齐参数。

Windows 10/11、ARM64、普通非管理员账户、物理上未安装 Python 的独立电脑，以及 Windows Explorer 人工双击、系统默认浏览器可视交互与实际拖入仍未实测。冻结版通过限制 PATH、移除 Python 环境验证随包运行库，构建 runner 本身仍安装 Python。建议命令没有在真实设备执行；真实 Ollama 模型和实际产品 NVD 适用性仍待验证。

以下保留本地集成与旧版验收的完整记录；正式 Windows 交付以上节为准。

## v1.0.0 配置模拟器：本地集成验收（2026-10-09）

本节记录发布前的实际本地检查；Windows 构建与正式发布结果将在完成后追加，不能由源码测试推断 EXE 已验收。

Linux x86_64 / Python 3.12.14 上 **396 项应用测试通过**：原有 272 项继续通过，新增 83 项四厂商模拟引擎、29 项中文目标规划、12 项 HTTP/CLI 入口测试。覆盖无损编辑、CRLF 与未知行/凭据保留、整批回滚及上下文、VLAN 依赖、接口模式/IP、ACL/路由边界、错误厂商/参数、输入与输出限制、单目标完整理解、明确预览及可选审计。

源码版 **5 项真实进程验收通过**，包含四个网页资源、四厂商规划/模拟/失败回滚、中文与空格路径、真实 CLI 的 `plan` / `simulate` 和配置输出、三种审计导出、0/1/2 退出码与无暂停、端口占用回退、无参数启动及可观察浏览器调用、只读程序位置与用户临时目录。模拟默认不调用审计或 AI。测试服务全部正常退出，无剩余进程、无强制清理且端口关闭。

Linux Chromium / Playwright 的 **128 项实际网页检查通过**，覆盖四厂商导入、中文目标与命令预览、明确应用、撤销/重置/导出再导入、按需审当前副本及三报告、过期请求隔离、出错恢复、明暗主题、重复风险折叠及宽窄屏。无 JavaScript 错误或外部请求，测试服务退出码 0 且端口关闭。此结果不是 Windows 人工桌面验收。

标准 wheel 包含 `simulator.py`、`simulation_goals.py` 与四个网页资源；网页字节与当前源码一致。Python 编译、两份 JavaScript 语法和原有三项上游隔离复现检查通过。全部测试仅使用合成配置；真实备份和私有报告未加入代码、日志或截图。

**62 项发布工具保护测试通过**；v1.0.0 起发布器要求每种运行方式均提供模拟 API、真实 CLI、四网页资源与正常停服证据，旧 0.x 版本发布说明保持原样。

这是离线配置状态学习工具；不模拟数据包、物理链路、STP 收敛、OSPF 邻居或真实登录。通过离线检查不保证实机型号/固件支持或业务连通，未知命令也不能据此判定实机禁止执行。

## v0.2.3 主题与风险折叠发布验收（2026-10-08）

实际构建源码与 Release 标签为 `7900be2b84104fe2f9e75ab186bb21d1d034c7e6`。[Windows 构建 37749761790](https://github.com/klwb360/NetAudit/actions/runs/37749761790) 在 Windows Server 2022 10.0.20348 AMD64 / Python 3.12.10 x64 / PyInstaller 6.22.3 / runner image 20260927.320.1 通过 **272 项应用测试、28 项真实进程验收**（源码 10、onedir 9、onefile 9）。[Linux CI 37749762017](https://github.com/klwb360/NetAudit/actions/runs/37749762017) 的 Python 3.10 / 3.12 / 3.13 全部通过。

Windows 三种运行形式验证四厂商和三种报告、识别接口、RGOS VLAN 范围和原有风险聚合、完整命令与流程、中文 / 空格路径、BAT / CLI 返回码及无暂停、端口回退、静态资源、默认启动与可观察浏览器调用、只读目录和临时目录清理。18 份停服记录均无剩余进程、无强制清理且端口关闭。

Linux / Python 3.12.14 的 272 项应用测试与 57 项发布工具测试通过。真实 Chromium / Playwright 最终完成 **112 项检查**（构建源码文档曾记录首批 106 项；追加检查未改变网页资源），覆盖明亮、暗黑、跟随系统及系统配色变化、主题记忆、浏览器禁止存储的回退、键盘操作、六个结果页签、1440×1000 与 390×844 布局，以及稳定配色后的文字对比度。切换主题不清空输入或报告，仅保存主题偏好。

同类风险在网页按规则、严重度、分类、确认程度与标题折叠，显示组数、发现项数和涉及处数。检查验证默认折叠、展开 / 收起全部、筛选后状态、不同 VLAN 的独立对象 / 证据 / 命令、已有后端合并结果、恶意文本安全显示、四厂商文件拖入及 JSON / Markdown / HTML 完整导出。原始发现、审计统计和报告数据保持完整；仅使用合成配置，无 JavaScript 错误或外部请求，测试服务正常退出且端口关闭。

[正式发布运行](https://github.com/klwb360/NetAudit/actions/runs/37773236976) 通过 57 项保护测试、永久工程归档及三个运行附件上传后的下载回验，[v0.2.3](https://github.com/klwb360/NetAudit/releases/tag/v0.2.3) 已发布。独立核验九个原始产物、全部 ZIP CRC/SHA、onedir 129 / onefile 66 个包内校验、AMD64 PE、运行库、许可证、官方情报及 onefile CArchive 嵌入资源。124 个源码文件对应构建提交，其中 35 个逐字节一致、89 个文本仅发生 Windows CRLF 转换。三个网页资源与 Windows 实际服务及 Linux 浏览器检查使用的规范化文件一致。

浏览器自动化和独立文件核验在 Linux 执行；EXE 运行检查来自真实 Windows runner。Windows 10/11、ARM64、普通非管理员账户、物理上未安装 Python 的独立电脑，以及 Windows Explorer 人工双击、系统默认浏览器可视交互与实际拖入仍未实测。冻结版通过限制 PATH、移除 Python 环境验证随包运行库，构建 runner 本身仍安装 Python。建议命令没有在真实设备执行；真实 Ollama 模型和实际产品 NVD 适用性仍待验证。 文件、SHA 与详细边界见[交付记录](https://github.com/klwb360/NetAudit/blob/main/DELIVERY.md)。

## v0.2.2 Windows 构建与发布验收（2026-10-08）

实际构建源码与 Release 标签为 `8015ed5ed3d2abbd6e70e7f10775724c7aafe265`。[Windows 构建 37712559596](https://github.com/klwb360/NetAudit/actions/runs/37712559596) 在 Windows Server 2022 10.0.20348 AMD64 / Python 3.12.10 x64 / PyInstaller 6.22.3 / runner image 20261004.326.1 通过 **272 项应用测试、28 项真实进程验收**（源码 10、onedir 9、onefile 9）。[Linux CI 37712559568](https://github.com/klwb360/NetAudit/actions/runs/37712559568) 的 Python 3.10 / 3.12 / 3.13 全部通过。

三种运行形式验证四厂商和三格式报告、按内容识别与模糊时 `needs-manual`、RGOS VLAN 范围和同类聚合、完整命令脚本与独立模板、中文/空格路径、BAT/CLI 退出码及无暂停、端口冲突回退、静态资源、默认启动/浏览器调用、只读目录、完整流程及本机 AI 协议替身。18 份停服记录均无剩余进程、无强制清理且端口关闭；onefile 临时目录清理通过。

[发布运行 37712979040](https://github.com/klwb360/NetAudit/actions/runs/37712979040) 通过 55 项保护测试、永久工程归档与三个运行附件上传后的下载回验；[v0.2.2](https://github.com/klwb360/NetAudit/releases/tag/v0.2.2) 正式发布。随后独立核验九个原始产物、全部 ZIP CRC/SHA、包内完整对应源码、运行库、AMD64 PE、许可与情报原字节，并直接提取 onefile CArchive 网页/情报/base_library。117 个源码文件与提交一致，其中 89 个文本仅发生 Windows CRLF 转换；冻结资源与实际 HTTP 服务字节按相同转换核对。

Linux Chromium 的 85 项拖入追加检查使用与本次 EXE 相同的规范化网页和服务端源文件；此前 RGOS / 聚合为 184 项网页检查。浏览器自动化在 Linux 执行，独立产物核验不运行 Windows EXE。真正的 Windows EXE 进程验证由上方 runner 完成。建议命令仅经[官方参考核对](REMEDIATION.md)和离线回归，没有在真实设备执行。Windows 10/11、ARM64、普通账户、物理无 Python 电脑、Explorer 人工双击和实际 Windows 浏览器拖入仍未实测；真实 Ollama 模型与实际 NVD 产品适用性也待验证。详细文件、SHA 和边界见[交付记录](https://github.com/klwb360/NetAudit/blob/main/DELIVERY.md)。

以下两节保留发布前在 Linux 的分阶段检查记录，当前 Windows 验收以上节为准。

## v0.2.2 文件拖入与导入识别追加验收（2026-10-08）

在下述 RGOS 修复基础上加入文件拖入和导入时识别。Linux x86_64 / Python 3.12.14 的完整应用测试增至 **272 项，全部通过**；新增 13 项本地识别 API 测试，覆盖四厂商、模糊/混合、大小与行数边界、无配置泄露、会话/来源防护，确认识别不运行审计或 AI。发布说明 27 项针对性回归通过，旧发布策略保持。

Chromium 151.0.7922.173 / Playwright 在 1440×1000、390×844 完成 **85 项追加检查**：拖入与选择文件按内容识别，中文空格及无扩展名文件、多个文件/目录/空文件/非 UTF-8/控制字符/超限提示、恰 30000 行尾部换行、读取与检测超时、手动调整、示例取消、连续导入与旧响应隔离、旧读取不提前解锁新识别、三种实际报告下载和窄屏布局。仅用合成配置，无 JavaScript 错误或外部请求；测试服务退出 0，端口关闭。

扩展后的 **5 项源码进程检查通过**，四厂商识别接口及不明确时 `needs-manual` 已纳入 Windows 共用验收脚本；路径、默认启动、端口回退、静态资源、四厂商报告和正常清理继续通过。`node --check` 和 `git diff --check` 通过。当时尚未执行 Windows EXE；这组 Linux 结果本身不等于 EXE 验收，后续真实 Windows 结果见本页首节。

## v0.2.2 发布前源码修复验收（2026-10-08）

实际环境为 Linux x86_64 / Python 3.12.14。**259 项应用测试通过**，包含原有规则与流程回归，以及 RGOS 识别和 VLAN 范围、同类聚合、完整脚本、参数模板、脱敏和报告兼容性。JavaScript 语法与 `git diff --check` 通过。

**55 项发布工具保护测试通过**，新版发布说明显示四厂商与命令前提，旧三个版本的说明输出逐字节保持。测试使用本地协议替身，不代表本次已向 GitHub 发布。

源码版完成 **5 项真实进程验收**：四厂商样例和 JSON / Markdown / HTML 导出、退出码 0/1/2、中文及空格路径与外部工作目录、端口冲突回退、完整静态资源、无参数启动与可观察的浏览器调用、只读程序目录与用户临时目录、完整流程及显式本机 AI 协议替身。新增 RGOS 自动识别、批量 VLAN、VTY 聚合与独立模板的进程断言。全部服务正常退出，端口关闭，无强制清理或剩余进程。Linux 验收不包含 Windows BAT 或冻结 EXE。

真实 Chromium headless 在 1440×1000 和 390×844 完成 **184 项网页检查**：第四厂商选项、文件导入、同 VLAN 聚合与不同 VLAN 分开、所有对象和原始证据、三类命令及前提、三种实际下载、严重度筛选不截断导出、HTML 转义与窄屏布局。无 JavaScript pageerror；唯一资源错误为既有 `/favicon.ico` 404，三个网页资源均加载正常。测试服务和诊断线程已退出。截图仅使用合成配置；真实配置与私有报告未加入仓库、构建样例或测试夹具。

建议命令经过离线回归和[官方参考核对](REMEDIATION.md)，未在真实设备上执行。此阶段未执行 Windows onedir / onefile；之后的实际 runner 验收见本页首节。物理无 Python 目标机、普通 Windows 账户或实际 RGOS 转发行为仍未验证；旧版 v0.2.1 EXE 不包含本次修复。

## v0.2.1 已发布界面版本验收（2026-10-03）

界面独立参考 `copy-only` 的抽象工作区结构：顶部概览与入门提示、左侧配置、右侧六页签、集中操作与状态、窄屏堆叠。解析器、35 条规则、漏洞适用性、AI 和报告逻辑保留。

Linux Python 3.12.14 上 **192 项应用测试**与 **14 项发布保护测试**通过。JavaScript 语法、Markdown 链接/锚点、问题反馈表单及原许可证/归属核对通过。

Linux Chromium headless 的 **65 项实际网页检查**通过：六页签和 ARIA/键盘焦点、配置与可选文件切换保留、中文 UTF-8 导入/字节信息、六域和完整流程、严重度筛选、精确版本与候选区分、三种真实下载、AI 设置及本机 HTTP 协议、恶意模型文本与导出 HTML 转义，以及 1440×1000、390×844、320×844 布局。修改配置、厂商或情报/模型设置后，旧结果不可导出；审计中途修改输入，以及文件异步读取期间先发起旧文本审计，均不会保留旧快照。测试无 JavaScript 错误，两项测试服务端口均关闭。

浏览器报告记录最终三个网页文件 SHA-256，运行前后与源码完全一致。首页截图使用清理可选设置后的 Cisco 合成示例，不包含真实配置。该结果是 Linux 浏览器自动化，不能等同于 Windows 人工桌面验收。真实 Ollama 模型未运行，NVD/KEV 匹配用例为标注的合成数据；随包官方 KEV 校验仍独立保留。

实际源码及 Release 标签对应 `befb38bbecbbaa9d0d97c48c922e50e18c42f462`。[Windows 构建 37136065995](https://github.com/klwb360/NetAudit/actions/runs/37136065995) 在 Windows Server 2022 10.0.20348 AMD64 / Python 3.12.10 x64 / PyInstaller 6.22.3 / runner image 20260927.320.1 通过 **192 项应用测试、28 项真实进程验收**（源码 10、onedir 9、onefile 9）。[Linux CI 37136065998](https://github.com/klwb360/NetAudit/actions/runs/37136065998) 的 Python 3.10 / 3.12 / 3.13 全部通过。

[发布运行 37136432263](https://github.com/klwb360/NetAudit/actions/runs/37136432263) 的 14 项保护测试与全部 9 个附件下载回验通过，[v0.2.1](https://github.com/klwb360/NetAudit/releases/tag/v0.2.1) 已正式发布。实际下载后另行核对全部 ZIP CRC/SHA、78 个完整对应源码文件和 PNG、原许可证与官方情报字节、运行库、AMD64 PE；直接提取 onefile 内嵌的三个网页资源并确认与源码、onedir 和实际服务内容一致。Windows 继续检查路径、BAT/CLI、端口回退、只读目录、报告与流程、默认启动、退出和临时目录；全部停服无剩余进程/无强制清理/端口关闭。

新版本不覆盖 v0.2.0 或 v0.1.0。后续发布元数据及文档提交不改变对应 EXE；最终文件、SHA-256 与未测边界见 [交付记录](https://github.com/klwb360/NetAudit/blob/main/DELIVERY.md)。

## v0.2.0 已发布版本验收（2026-10-03）

实际 EXE 源码与 Release 标签对应 `8a9840601d6c51dbdaff1fbbf62aeaf84cc0b490`；[v0.2.0 Release](https://github.com/klwb360/NetAudit/releases/tag/v0.2.0) 提供源码、onedir 与 onefile，共 9 个原始附件。后续发布元数据和文档提交不改变这次构建。

| 环境与检查 | 实际结果与证据 |
|---|---|
| Windows Server 2022 10.0.20348 AMD64；Python 3.12.10 x64、PyInstaller 6.22.3；runner image 20260927.320.1 | [构建 37120272682](https://github.com/klwb360/NetAudit/actions/runs/37120272682)：192 项应用测试、28 项真实进程验收通过（源码 10、onedir 9、onefile 9） |
| Linux CI；Python 3.10 / 3.12 / 3.13 | [运行 37120272642](https://github.com/klwb360/NetAudit/actions/runs/37120272642)：三个版本全部通过 |
| GitHub Actions 发布器 | [运行 37120600936](https://github.com/klwb360/NetAudit/actions/runs/37120600936)：14 项保护测试通过，9 个附件上传后全部下载回验 |

Windows 三种运行形式实际检查六阶段/六域、新情报资源、三格式报告、中文与空格路径、BAT/CLI 返回码和无暂停、端口回退、完整网页资源、无参数启动/浏览器调用、只读目录、进程/端口及 onefile 临时目录清理。停服记录均无剩余进程、无强制清理且端口关闭。下载后独立核对 ZIP CRC、全部产物与包内 SHA、对应源码、x64 PE、运行库、原许可证、官方情报/许可来源，以及 onefile 中直接提取的嵌入资源。

当前源码已完成六阶段审计流程。Linux Python 3.12.14 上 192 项应用测试通过，原解析/规则与启动测试继续保留；另有 14 项 Release 发布保护测试通过。源码真实进程 5 项检查通过，覆盖新情报资源、精确 CPE/NVD 条件、三种导出、AI 协议、中文与空格路径、只读目录、端口回退和退出清理。

Linux Chromium headless 的 24 项实际网页检查通过：文件导入、示例、六域与流程、精确匹配和候选区分、严重度筛选、三种真实下载、AI 设置、模型文字转义及桌面/移动布局。HTML/CSS/JavaScript 完整加载，未见脚本错误，测试服务均关闭。该检查不是 Windows 人工桌面验收。

真实 CISA KEV 快照为 2026.10.02 / 1733 条，原始文件 SHA、来源和 CC0 许可证已核对。NVD 官方 API 在本次环境被网络代理返回 403；NVD 测试采用明确标注的合成适用条件，不能作为真实设备漏洞适用证明。AI 使用真实 loopback HTTP 协议测试服务，尚未运行实际 Ollama 模型；模型解释质量与真实设备整改均需另行验证。

标准 0.2.0 wheel 构建与资源核对、Python 编译、JavaScript 语法和 3 项上游复现检查通过。上述本地检查与实际 Windows EXE 验收分别记录；最终文件、SHA-256 与未测项见 [交付记录](https://github.com/klwb360/NetAudit/blob/main/DELIVERY.md)。

首次 [Windows 检查 37119894388](https://github.com/klwb360/NetAudit/actions/runs/37119894388) 因 Git 检出转换 KEV 换行而触发官方文件 SHA 校验失败，未生成分发 EXE。项目 `.gitattributes` 保持情报数据及许可证的原始字节，并用 Windows `core.autocrlf=true` 检出模拟回归。数据校验继续要求完整原始 SHA；最终 EXE 验收以修复后的成功构建为准。

## v0.1.0 首次独立仓库交付历史（2026-10-03）

独立仓库的已验收构建对应源码提交 `16fb4254150f0cfd48014b3b628efc805dec0095`；后续文档提交不改变该次 EXE 对应的源码。

| 环境与检查 | 结果 | 证据 |
|---|---|---|
| Windows Server 2022 10.0.20348 AMD64；Python 3.12.10 x64、PyInstaller 6.22.3；runner image 20260927.320.1 | 78 项单元测试、25 项实际进程验收通过（源码 9、onedir 8、onefile 8） | [Windows 构建 37101723226](https://github.com/klwb360/NetAudit/actions/runs/37101723226) |
| Linux；Python 3.10 / 3.12 / 3.13 | 三个版本的 CI 检查全部通过 | [Linux 构建 37101723192](https://github.com/klwb360/NetAudit/actions/runs/37101723192) |

Windows 验收覆盖三厂商、三种报告、中文与空格路径、BAT/CLI 退出码及无暂停、端口冲突回退、完整网页资源、无参数启动和浏览器调用、只读应用目录、退出后无遗留服务，以及 onefile 临时目录清理。下载后还核对了外层 ZIP 和所有产物 SHA-256、ZIP CRC、包内文件哈希、Windows x64 PE、对应源码与许可证。文件名、下载入口和校验值见 [交付记录](https://github.com/klwb360/NetAudit/blob/main/DELIVERY.md)。

冻结版进程通过移除 Python 相关环境变量并限制 PATH，验证使用随包运行库；构建 runner 本身仍安装 Python。这不能等同于物理无 Python 电脑的实测。普通非管理员 Windows 账户、Windows 10/11、ARM64、资源管理器真实双击、系统默认浏览器可视交互及文件选择/下载对话框尚未实测。真实设备型号、软件版本和转发行为也未验收。

## 原版基线（2026-10-02）

以下为便携化前的历史记录：执行环境 Python 3.12、Linux，67 项测试通过；该交付版本的完整测试集结果见上表；后续提交的测试数量和结果以对应 CI 运行记录为准。

| 检查 | 结果 | 覆盖内容 |
|---|---|---|
| `python -m unittest discover -s tests -v` | 67 项通过 | 三厂商解析、VLAN、路由、ACL、NAT、VTY、证据行号、缺失默认值处理、误报边界、脱敏、HTML/Markdown 转义、CLI、本地 HTTP API |
| `python tools/reproduce_upstream.py` | 3 项通过 | HTTP 关闭命令误判、SSH 字符串比较 TypeError、跨 VTY 段的 Telnet 漏报，均使用固定方法摘录与解析替身 |
| `python -m compileall -q netaudit` | 通过 | Python 语法 |
| `node --check netaudit/web/app.js` | 通过 | 网页脚本语法 |
| 标准 setuptools wheel 构建与隔离导入 | 通过 | 纯 Python wheel、本地静态资源入包、命令行模块可加载 |
| 三厂商样例 CLI 导出 | 通过 | JSON/Markdown/HTML 报告、清单和密码隐藏 |

测试中的 HTTP 服务仅监听测试机回环地址，检查非法 Host、跨域 Origin、缺失令牌、异常 JSON、路径穿越及正常审计导出。无需第三方服务、真实配置或设备账号。

基线执行环境没有可用浏览器二进制，网页验证采用脚本语法、静态资源响应与 HTTP API 集成测试。该记录只代表当时的本地 Python 3.12 检查；后续 Python 3.10/3.12/3.13 的 CI 成功记录见上表。

CI 使用只读仓库权限，checkout 和 setup-python 固定为检索时核实的提交 SHA。运行测试、上游隔离复现和 wheel 构建，不导出真实网络配置到构建日志。
