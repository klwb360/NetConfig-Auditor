# NetAudit

本地网络配置审计工具，支持 Cisco、华为、H3C，提供中文网页、命令行和 JSON / Markdown / HTML 报告。配置处理在本机完成，普通使用不需要管理员权限。

Windows 用户：[直接下载已验收版本及校验值](DELIVERY.md)。

使用步骤：

1. 登录有权访问本私人仓库的 GitHub 账号，打开 [Windows 构建列表](https://github.com/klwb360/NetAudit/actions/workflows/netaudit-windows.yml)，选择成功的构建，在页面底部 Artifacts 下载产物。
2. 解压下载的 ZIP，再解压其中名称带 `portable` 的 ZIP。
3. 双击 `Start-NetAudit.bat` 或 `NetAudit.exe`，浏览器会自动打开。
4. 导入设备配置、选择厂商，点击“开始审计”，查看问题并导出报告。

关闭程序：回到启动窗口按 Ctrl+C。迁移到另一台电脑：复制整个便携文件夹，包括 `_internal`；目标电脑不需要安装 Python。

优先使用便携文件夹版本。产物也包含经过验证的单 EXE、对应源码、许可证、构建环境说明和 SHA-256 校验文件。

- [Windows 使用说明](network-config-auditor/docs/WINDOWS.md)
- [源码、CLI 与项目说明](network-config-auditor/README.md)
- [审计规则](network-config-auditor/docs/RULES.md)
- [便携化与验收范围](network-config-auditor/docs/PORTABILITY.md)
- [迁移记录](MIGRATION.md)

源码保留在 `network-config-auditor/`，自动构建从 `main` 分支运行。项目使用 [GPL-3.0-only](network-config-auditor/LICENSE)，原有 [归属说明](network-config-auditor/NOTICE) 和 [上游分析](network-config-auditor/docs/UPSTREAM_AUDIT.md) 保留。
