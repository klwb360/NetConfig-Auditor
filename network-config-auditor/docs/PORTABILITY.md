# Windows 便携化与验收记录

## 开始时的状态

2026-10-03 检查目标分支 `codex/network-config-auditor`，基线提交 `7499dfd18c218d998694242a5b50686ace347465`。本次执行环境最初只有初始提交的 `work` 分支，没有未提交修改，也没有 BAT 或打包入口。通过 GitHub 连接器取回目标分支文件，逐一校验 blob 与完整 Git tree，并恢复原始提交。仓库与项目及其父目录未发现适用的 AGENTS.md。

已完成的原功能：三厂商解析、27 条规则、中文网页、CLI、JSON/Markdown/HTML 导出；原 LICENSE、NOTICE、规则目录和固定上游审计记录全部保留。此基线提交的 GitHub Actions Python 3.10/3.12/3.13 测试已成功。本次便携化不重写解析、规则或报告逻辑。

需要补齐的工作：双击启动、Python 检测、EXE 优先、浏览器启动和禁止浏览器选项、占用端口回退、Windows 构建与真实 EXE 验收、分发所需源码/许可证/构建记录，以及普通用户说明。

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

`tools/smoke_portable.py` 在独立临时目录和子进程中验收，报告记录实际环境与未测项目。Windows 构建只有在源码、onedir 与 onefile 验收完成后才上传产物。覆盖完整网页资源、三厂商审计和三种报告、中文/空格路径、端口回退、参数退出码、无 Python 环境和退出后的服务清理。只读目录验证使用临时副本并恢复权限，不更改用户目录权限。

Linux 源码单元测试、静态检查或打包入口检查不能代替 Windows EXE 验收。自动测试默认浏览器调用与打开完整网页资源；真实 Windows 桌面的双击、浏览器可视交互、下载保存对话框仍需人工验证。具体结果以本次构建的验收 JSON 和 Actions 日志为准。

## 本次实际环境

- 当前执行器：Linux x86_64，Python 3.12.14，Node.js 24.19.0。
- 初次原基线检查：58 项非网页测试通过；网页测试因沙箱禁止创建 socket（`PermissionError: Operation not permitted`）未能运行。3 项上游隔离复现通过；Python 编译与 JavaScript 语法检查通过。
- 便携化源码检查：原有 58 项与新增 9 项无需 socket 的测试合计 67 项通过；当前沙箱未运行 HTTP 测试。
- Windows 构建的实际环境、结果、产物名称和 SHA-256 由对应产物的验收 JSON、`manifest.json`、`SHA256SUMS.txt` 与 Actions 日志记录；未生成的产物不预填名称或哈希。

普通用户操作见 [Windows 使用说明](WINDOWS.md)。下载私人仓库产物需要相应 GitHub 权限。旧 PR #1 已由仓库所有者合并；独立仓库迁移记录见 [MIGRATION.md](https://github.com/klwb360/NetAudit/blob/main/MIGRATION.md)。
