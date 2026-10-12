# NetAudit → 公开NetConfig-Auditor迁移（2026-10-12）

- 来源私有仓库 `klwb360/NetAudit`，ID1402731653，main `535653cd580dc497429fb83200e93a8349bc707d`。
- 目标公开仓库 [klwb360/NetConfig-Auditor](https://github.com/klwb360/NetConfig-Auditor)，ID1415268968；保留来源全部36提交和七个原标签。
- 七个历史Release、21运行附件共206493668字节已复制，并对旧附件、本地备份、新附件及新下载逐一核对SHA256。[固定迁移收据](docs/migration/legacy-release-receipt.json)可追溯旧/新asset ID。
- 本地完整Git bundle、21附件和issues(0)/pulls(0)/branches(1)/Actions runs(34)元数据已备份在用户工作区outputs。Git bundle无外部前置依赖且已验证。
- GPL许可证、NOTICE、上游归属、历史源码与验收档案保留。公开仓库只包含合成配置和审计测试，真实设备备份仍被忽略。
- 用户最新选择自行删除旧NetAudit，因此工具不再执行删除；备份已保留。Codex-code不属于删除范围。
- PR [#1](https://github.com/klwb360/NetConfig-Auditor/pull/1)标注本次新增和修复；新验收见[固定证据](docs/acceptance/v1.1.0/README.md)。

以下保留2026-10-03迁移历史。旧提交、校验值和运行地址只说明当时状态，最新公开迁移与交付以上方及PROJECT_STATUS为准。

# NetAudit 独立仓库迁移记录

迁移日期：2026-10-03（UTC）。目标仓库：私人仓库 [klwb360/NetAudit](https://github.com/klwb360/NetAudit)。

来源为 [klwb360/Codex-code](https://github.com/klwb360/Codex-code) 的 `network-config-auditor` 项目，以及两个 GitHub Actions workflow。原 [PR #1](https://github.com/klwb360/Codex-code/pull/1) 已由仓库所有者合并。

- 已验收的源码提交：`741bb5a70e675e28735da1182ab0cc9f1de33773`。
- 原仓库 `main` 合并提交：`dbc4a8040693263cca918e0d14c3e9cc8ccca847`。
- 迁移使用前一提交的文件快照；已核对其文件树与上述合并结果一致。
- 保留原目录结构、配置解析、27 条审计规则、网页、报告、测试、构建脚本、依赖锁定、示例、完整 LICENSE、NOTICE 和上游来源说明。
- 迁移修改仅涉及新仓库下载链接、Windows workflow 的 `main` 分支触发、根 README 与迁移说明。旧仓库内容保留。

新仓库已从独立初始提交导入源码快照，旧 Git 历史、PR 讨论、Actions 运行与构建产物仍在原仓库；本文件保留对应出处。新仓库已重新构建并生成与新提交对应的 EXE、便携 ZIP 和 SHA-256，旧产物校验值不能作为新构建的校验值。

独立仓库首次构建对应源码提交：[`16fb4254150f0cfd48014b3b628efc805dec0095`](https://github.com/klwb360/NetAudit/commit/16fb4254150f0cfd48014b3b628efc805dec0095)。[Windows 构建 37101723226](https://github.com/klwb360/NetAudit/actions/runs/37101723226) 在 Windows Server 2022 10.0.20348 AMD64、Python 3.12.10 x64、PyInstaller 6.22.3 环境通过 78 项单元测试和 25 项实际进程验收（源码 9、onedir 8、onefile 8）。[Linux 构建 37101723192](https://github.com/klwb360/NetAudit/actions/runs/37101723192) 的 Python 3.10 / 3.12 / 3.13 检查也全部通过。已实际下载核对产物与包内文件；下载入口、文件名和 SHA-256 见 [DELIVERY.md](DELIVERY.md)。后续文档提交不改变该次 EXE 对应的源码。

原已验收运行（供追溯）：[Windows 构建 37100067081](https://github.com/klwb360/Codex-code/actions/runs/37100067081)，[原构建产物](https://github.com/klwb360/Codex-code/actions/runs/37100067081/artifacts/11265925710)。原 Windows Server 2022 x64 / Python 3.12.10 环境通过 78 项单元测试和 25 项实际进程验收（源码 9、onedir 8、onefile 8）。

验收范围：含中文及空格路径、CLI 返回码与无暂停、端口冲突回退、完整网页资源、三厂商及三种报告、无参数打开浏览器的自动化调用、只读位置、退出无遗留服务。冻结版进程通过去除 Python 相关环境变量并限制 PATH 验证其使用随包运行库。尚未在物理无 Python 的电脑、普通非管理员账户、Windows 10/11 或 ARM64 上实测；默认浏览器真实窗口与资源管理器双击未作人工实测。

使用方式见 [Windows 使用说明](network-config-auditor/docs/WINDOWS.md)。许可证与归属说明继续见 [LICENSE](network-config-auditor/LICENSE) 和 [NOTICE](network-config-auditor/NOTICE)。

后续仓库资料与构建验收工具维护已经完成；最新已验收构建及对应源码、校验值见 [DELIVERY.md](DELIVERY.md)，旧迁移与首次验收记录继续保留。
