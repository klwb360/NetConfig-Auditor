# Windows 便携化与验收记录

## v0.2.0 发布与验收（2026-10-03）

v0.2.0 在原有便携入口上扩展六域架构、离线 CVE / KEV 和可选本机 AI，源码、onedir、onefile 三种运行形式使用相同审计流程。网页、情报快照和来源资料均需随包保留；资源路径不依赖当前目录，默认不联网、不向安装目录写运行数据。显式情报更新保存到用户指定路径或用户缓存/临时目录，Ollama 是可选外部本机服务，不影响无需 Python 的便携配置审计。

[v0.2.0 Release](https://github.com/klwb360/NetConfig-Auditor/releases/tag/v0.2.0) 已提供 9 个附件，实际 EXE 对应源码 `8a9840601d6c51dbdaff1fbbf62aeaf84cc0b490`。Windows Server 2022 x64 / Python 3.12.10 / PyInstaller 6.22.3 的 [构建 37120272682](https://github.com/klwb360/NetAudit/actions/runs/37120272682) 通过 **192 项单元测试和 28 项真实进程验收**（源码 10、onedir 9、onefile 9）。[Linux 构建 37120272642](https://github.com/klwb360/NetAudit/actions/runs/37120272642) 的 Python 3.10 / 3.12 / 3.13 检查通过，另有 Linux Chromium 24 项网页自动检查通过。[发布运行 37120600936](https://github.com/klwb360/NetAudit/actions/runs/37120600936) 通过 14 项发布保护测试，9 个附件上传后逐个下载回验。

真实 Ollama 模型推理与真实 NVD 产品适用记录尚未实测；AI 使用本机协议替身、NVD 使用合成格式用例验证。普通非管理员账户、物理无 Python 电脑、Windows 10/11、ARM64 和 Windows 真人桌面交互仍待验证，不能从自动进程测试推定通过。

本页下方的旧提交、78 / 88 项测试和 25 项进程记录是 v0.1.0 历史验收。新版文件、环境、校验值与未测项以 [当前交付记录](https://github.com/klwb360/NetConfig-Auditor/blob/main/DELIVERY.md) 和该构建报告为准；v0.1.0 保留下载，不覆盖已发布字节。

## 开始时的状态

2026-10-03 检查目标分支 `codex/network-config-auditor`，基线提交 `7499dfd18c218d998694242a5b50686ace347465`。本次执行环境最初只有初始提交的 `work` 分支，没有未提交修改，也没有 BAT 或打包入口。通过 GitHub 连接器取回目标分支文件，逐一校验 blob 与完整 Git tree，并恢复原始提交。仓库与项目及其父目录未发现适用的 AGENTS.md。

已完成的原功能：三厂商解析、27 条规则、中文网页、CLI、JSON/Markdown/HTML 导出；原 LICENSE、NOTICE、规则目录和固定上游审计记录全部保留。此基线提交的 GitHub Actions Python 3.10/3.12/3.13 测试已成功。本次便携化不重写解析、规则或报告逻辑。

检查时待补齐、现已完成的工作：双击启动、Python 检测、EXE 优先、浏览器启动和禁止浏览器选项、占用端口回退、Windows 构建与真实 EXE 验收、分发所需源码/许可证/构建记录，以及普通用户说明。

## 实现与构建依据

无参数默认启动本地网页，保留 `audit` 与 `serve --no-browser`。保留控制台以显示实际地址、错误和 Ctrl+C 关闭提示。BAT 切换到自身目录并传递 CLI 参数；参数调用不会暂停。网页与 EXE 无运行时第三方包依赖，不要求目标电脑安装 Python。

打包方法实际核对 PyInstaller 官方 **v6.22.3** 标签文档及 release（2026-09-12 的稳定版本），通过官方 GitHub 源码文档读取：

- [工作方式](https://github.com/pyinstaller/pyinstaller/blob/v6.22.3/doc/operating-mode.rst)：Windows EXE 在 Windows 上构建；先验收 onedir，再提供 onefile。
- [运行时资源](https://github.com/pyinstaller/pyinstaller/blob/v6.22.3/doc/runtime-information.rst)：按 `__file__` 定位资源，并保持打包相对目录。
- [用法与临时目录](https://github.com/pyinstaller/pyinstaller/blob/v6.22.3/doc/usage.rst)：onefile 默认使用系统临时目录；不设置程序目录为解压目录。
- [依赖声明](https://github.com/pyinstaller/pyinstaller/blob/v6.22.3/pyproject.toml)与[许可例外](https://github.com/pyinstaller/pyinstaller/blob/v6.22.3/COPYING.txt)。

Windows workflow 使用独立 venv 与固定构建依赖。分发 ZIP 包含 EXE、运行库（onedir）、BAT、普通用户说明、示例、原许可证与归属、第三方许可证和完整对应源码 ZIP。源码 ZIP 含项目和 `.github/workflows`，便于重建。构建清单记录 commit、实际 Windows/Python/架构、依赖、验收 JSON 与 SHA-256；GitHub runner 镜像可能更新，因此固定依赖不等于承诺二进制逐字节可重现。

程序从只读位置启动时不向安装目录写运行数据。浏览器下载报告到用户选择的位置；CLI 显式输出路径必须可写。onefile 使用用户临时目录，正常退出会清理；强制终止进程或系统崩溃后的临时残留由系统/用户清理。

开发者在 Windows x64 安装 Python **3.12.10** 和 Git，检出构建清单中的完整源提交，确保没有未提交或未跟踪的修改，然后运行：

```bat
cd network-config-auditor
python tools/build_windows.py
```

脚本自动创建独立临时 venv，安装锁定依赖并执行验收；输出位于 `dist/windows`。普通用户不需要执行构建命令。分发的源码 ZIP 是完整源码归档，不含 `.git`；复现原提交请使用仓库的对应 checkout。仅用源码归档重建时，应在归档根目录初始化 Git 并提交，构建清单将记录这个新的本地提交。

## 验收方式

`tools/smoke_portable.py` 在独立临时目录和子进程中验收，报告记录实际环境与未测项目。Windows 构建只有在源码、onedir 与 onefile 验收完成后才上传产物。覆盖完整网页资源、三厂商审计和三种报告、中文/空格路径、端口回退、参数退出码和退出后的服务清理。冻结版子进程移除 Python 相关环境变量并将 PATH 限定为 Windows 系统目录，验证使用随包运行库；runner 本身仍安装 Python，不能视为物理无 Python 电脑的实测。只读目录验证使用临时副本并恢复权限，不更改用户目录权限。

Linux 源码单元测试、静态检查或打包入口检查不能代替 Windows EXE 验收。自动测试默认浏览器调用与打开完整网页资源；真实 Windows 桌面的双击、浏览器可视交互、下载保存对话框仍需人工验证。具体结果以本次构建的验收 JSON 和 Actions 日志为准。

## v0.1.0 已交付版本的实际验收（2026-10-03）

- 原仓库源码提交 `741bb5a70e675e28735da1182ab0cc9f1de33773` 在 [Windows 构建 37100067081](https://github.com/klwb360/Codex-code/actions/runs/37100067081) 通过 78 项单元测试与 25 项实际进程验收。
- 独立仓库迁移后源码提交 `16fb4254150f0cfd48014b3b628efc805dec0095` 在 [Windows 构建 37101723226](https://github.com/klwb360/NetAudit/actions/runs/37101723226) 再次通过 78 项单元测试与 25 项实际进程验收（源码 9、onedir 8、onefile 8）。环境为 Windows Server 2022 10.0.20348 AMD64、Python 3.12.10 x64、PyInstaller 6.22.3，runner image 20260927.320.1。
- 独立仓库的 [Linux 构建 37101723192](https://github.com/klwb360/NetAudit/actions/runs/37101723192) 在 Python 3.10 / 3.12 / 3.13 上全部通过。
- EXE、两个分发 ZIP 和对应源码已实际生成并下载校验，文件名、SHA-256、下载入口见 [交付记录](https://github.com/klwb360/NetConfig-Auditor/blob/main/DELIVERY.md)。这份记录对应上述构建提交，后续文档更新不改变既有 EXE。

尚未实测普通非管理员 Windows 账户、物理无 Python 的独立电脑、Windows 10/11、ARM64、资源管理器真实双击、系统默认浏览器可视交互与文件选择/下载对话框。源码与自动化进程检查通过，不代表这些人工或设备环境已验收。

## 初期本地检查（历史记录）

- 初期执行器：Linux x86_64，Python 3.12.14，Node.js 24.19.0。
- 初次原基线检查：58 项非网页测试通过；网页测试因沙箱禁止创建 socket（`PermissionError: Operation not permitted`）未能运行。3 项上游隔离复现通过；Python 编译与 JavaScript 语法检查通过。
- 便携化源码初期检查：原有 58 项与新增 9 项无需 socket 的测试合计 67 项通过；当时沙箱未运行 HTTP 测试。这是初期部分测试记录，后续 Windows 完整测试集为 78 项。
- 最终 Windows 环境、结果、产物名称和 SHA-256 已记录在对应产物的验收 JSON、`manifest.json`、`SHA256SUMS.txt` 与上列 Actions 日志中。

普通用户操作见 [Windows 使用说明](WINDOWS.md)。下载私人仓库产物需要相应 GitHub 权限。旧 PR #1 已由仓库所有者合并；独立仓库迁移记录见 [MIGRATION.md](https://github.com/klwb360/NetConfig-Auditor/blob/main/MIGRATION.md)。
