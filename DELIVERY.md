# NetAudit Windows 下载与交付检查点

2026-10-03：迁移至私人仓库 `klwb360/NetAudit` 已完成。原仓库保留，原 PR #1 已由仓库所有者合并。现有实现与许可证已复用，仓库使用、排错、开发、架构与贡献资料已补齐。

[下载已验收的 Windows x64 构建产物](https://github.com/klwb360/NetAudit/actions/runs/37116561468/artifacts/11272270396)（需登录有权访问本私人仓库的 GitHub 账号）。产物保留至 2027-01-01；过期后请在 [Windows 构建列表](https://github.com/klwb360/NetAudit/actions/workflows/netaudit-windows.yml) 获取后续成功构建，或点击 Run workflow 重新构建。

使用：下载 → 解压 GitHub 外层 ZIP → 解压其中的 `portable.zip` → 双击 `Start-NetAudit.bat` 或 `NetAudit.exe` → 导入配置并选择厂商 → 查看与导出。Ctrl+C 关闭程序；迁移时复制整个便携文件夹，包括 `_internal`。

实际生成文件：

| 文件 | SHA-256 |
|---|---|
| `NetAudit-0.1.0-windows-x64-f2002b79bd6d-portable.zip` | `66f0400a0522395c3cf3cf19aa1294aed0f8243de7c10a6e04c658edff44090d` |
| `NetAudit-0.1.0-windows-x64-f2002b79bd6d-onefile.zip` | `645cc8b90956c82e870d671c0c09698336e288de10eb3672da4722385ad97aa3` |
| `NetAudit-0.1.0-windows-x64-f2002b79bd6d-onefile.exe` | `a1b7f309a5f98e8139cfd99dde446ff0466f1ad846196c977abc5c3756571010` |
| `NetAudit-0.1.0-source-f2002b79bd6d.zip` | `0bac018b90e1709f5e7f826558b66df004c448f6e6a18e275ad6643342157f15` |

GitHub 下载的外层 ZIP SHA-256：`f84bfff005504715e83edadd9f78560a57e0d8efe8436f0ac9140d0ea305ee26`。解压后的 `SHA256SUMS.txt`、`manifest.json` 和三个验收报告提供完整校验值、环境与范围。PowerShell 校验示例：`Get-FileHash .\文件名.zip -Algorithm SHA256`。

构建对应源码提交：[`f2002b79bd6da91e2a29f741c8483951e20bba86`](https://github.com/klwb360/NetAudit/commit/f2002b79bd6da91e2a29f741c8483951e20bba86)。本交付说明随后作为文档提交保存，不改变该次 EXE 对应的源码提交。两个分发 ZIP 都包含同一对应源码归档、原 LICENSE/NOTICE、第三方许可证、示例和使用说明。

[Windows 构建与验收日志](https://github.com/klwb360/NetAudit/actions/runs/37116561468)：Windows Server 2022 10.0.20348 AMD64、Python 3.12.10 x64、PyInstaller 6.22.3、runner image 20260927.320.1。独立构建环境与依赖版本固定。88 项单元测试、25 项实际进程验收（源码 9、onedir 8、onefile 8）通过。

验收覆盖：三厂商和三种导出、中文及空格路径、CLI 返回码和无暂停、端口占用回退、完整网页资源、无参数启动与浏览器调用、只读应用目录、退出无残留服务、onefile 临时目录清理。[Linux Python 3.10 / 3.12 / 3.13 检查](https://github.com/klwb360/NetAudit/actions/runs/37116561322)也全部通过。

实际下载后另行核对外层 SHA、所有产物 SHA、两个分发 ZIP CRC、包内全部文件 SHA、Windows x64 PE、对应源码、LICENSE/NOTICE 与必需的 `base_library.zip`，单 EXE 与其 ZIP 内 EXE 字节一致。

尚未实测：普通非管理员 Windows 账户、物理上未安装 Python 的独立电脑、Explorer 真实双击、系统默认浏览器可视交互与文件选择/筛选/下载对话框、Windows 10/11、ARM64。冻结版验收去除 Python 相关环境并限制 PATH；构建 runner 本身仍安装 Python，不能视为无 Python 电脑的实测。

源码位于 `network-config-auditor/`，Windows workflow 从 `main` 的项目代码改动自动构建，也支持手动运行。此前实现、历史与迁移出处见 [MIGRATION.md](MIGRATION.md)，普通用户说明见 [WINDOWS.md](network-config-auditor/docs/WINDOWS.md)。继续工作时先核对当前状态与本检查点，复用已完成的实现及验收。

本轮补充 10 项验收工具回归测试，改进 Windows 原进程对象追踪、浏览器标记完整写入等待及失败诊断上传。中间 [构建 37114758953](https://github.com/klwb360/NetAudit/actions/runs/37114758953) 在退出验收失败，未发布 EXE；修复后上述新构建全部通过。失败运行没有被记作成功，应用解析、规则、报告与 BAT 保持原样。

首次独立仓库交付对应 `16fb4254150f0cfd48014b3b628efc805dec0095`，通过 78 项测试及 25 项进程验收：[首次构建](https://github.com/klwb360/NetAudit/actions/runs/37101723226)。历史文档与 Git 记录继续保留；当前下载与校验以本文件上表和对应构建清单为准。
