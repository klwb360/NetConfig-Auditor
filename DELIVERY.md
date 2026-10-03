# NetAudit Windows 下载与交付检查点

2026-10-03：迁移至私人仓库 `klwb360/NetAudit` 已完成。原仓库保留，原 PR #1 已由仓库所有者合并。现有实现与许可证已复用，不需要重新实施便携化。

[下载已验收的 Windows x64 构建产物](https://github.com/klwb360/NetAudit/actions/runs/37101723226/artifacts/11266582040)（需登录有权访问本私人仓库的 GitHub 账号）。产物保留至 2027-01-01；过期后请在 [Windows 构建列表](https://github.com/klwb360/NetAudit/actions/workflows/netaudit-windows.yml) 获取后续成功构建，或点击 Run workflow 重新构建。

使用：下载 → 解压 GitHub 外层 ZIP → 解压其中的 `portable.zip` → 双击 `Start-NetAudit.bat` 或 `NetAudit.exe` → 导入配置并选择厂商 → 查看与导出。Ctrl+C 关闭程序；迁移时复制整个便携文件夹，包括 `_internal`。

实际生成文件：

| 文件 | SHA-256 |
|---|---|
| `NetAudit-0.1.0-windows-x64-16fb4254150f-portable.zip` | `90d0dcd80c938b1c7a9722811d7a77e278681bed8478ec1ec83464a156516e6f` |
| `NetAudit-0.1.0-windows-x64-16fb4254150f-onefile.zip` | `f21ef40302252932715cf82e1b6611af7dc97f7c77a460cb5fbf47b68530365d` |
| `NetAudit-0.1.0-windows-x64-16fb4254150f-onefile.exe` | `373b3398068e34f1469412980d38c346542f45174cd14e4446dfe7b23676f229` |
| `NetAudit-0.1.0-source-16fb4254150f.zip` | `098fd664fddc04b5819b34be745dae3c2a00d952fbcb5d4ebc9f29f2175ee346` |

GitHub 下载的外层 ZIP SHA-256：`8c039ef314c0586f55467685ba8d8a2610ce543e1f95e3d460fba62ac3df1ceb`。解压后的 `SHA256SUMS.txt`、`manifest.json` 和三个验收报告提供完整校验值、环境与范围。PowerShell 校验示例：`Get-FileHash .\文件名.zip -Algorithm SHA256`。

构建对应源码提交：[`16fb4254150f0cfd48014b3b628efc805dec0095`](https://github.com/klwb360/NetAudit/commit/16fb4254150f0cfd48014b3b628efc805dec0095)。本交付说明随后作为文档提交保存，不改变该次 EXE 对应的源码提交。两个分发 ZIP 都包含同一对应源码归档、原 LICENSE/NOTICE、第三方许可证、示例和使用说明。

[Windows 构建与验收日志](https://github.com/klwb360/NetAudit/actions/runs/37101723226)：Windows Server 2022 10.0.20348 AMD64、Python 3.12.10 x64、PyInstaller 6.22.3、runner image 20260927.320.1。独立构建环境与依赖版本固定。78 项单元测试、25 项实际进程验收（源码 9、onedir 8、onefile 8）通过。

验收覆盖：三厂商和三种导出、中文及空格路径、CLI 返回码和无暂停、端口占用回退、完整网页资源、无参数启动与浏览器调用、只读应用目录、退出无残留服务、onefile 临时目录清理。[Linux Python 3.10 / 3.12 / 3.13 检查](https://github.com/klwb360/NetAudit/actions/runs/37101723192)也全部通过。

实际下载后另行核对外层 SHA、所有产物 SHA、两个分发 ZIP CRC、包内全部文件 SHA、Windows x64 PE、对应源码、LICENSE/NOTICE 与必需的 `base_library.zip`，单 EXE 与其 ZIP 内 EXE 字节一致。

尚未实测：普通非管理员 Windows 账户、物理上未安装 Python 的独立电脑、Explorer 真实双击、系统默认浏览器可视交互与文件选择/筛选/下载对话框、Windows 10/11、ARM64。冻结版验收去除 Python 相关环境并限制 PATH；构建 runner 本身仍安装 Python，不能视为无 Python 电脑的实测。

源码位于 `network-config-auditor/`，Windows workflow 从 `main` 的项目代码改动自动构建，也支持手动运行。此前实现、历史与迁移出处见 [MIGRATION.md](MIGRATION.md)，普通用户说明见 [WINDOWS.md](network-config-auditor/docs/WINDOWS.md)。继续工作时先核对当前状态与本检查点，复用已完成的实现及验收。
