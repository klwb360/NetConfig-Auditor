# 更新记录

应用版本以 `network-config-auditor/pyproject.toml` 为准。构建文件名同时包含源码提交前 12 位；同一应用版本的不同提交具有各自 SHA-256。

## 未发布

- 完善仓库首页、使用与开发导航、常见问题、故障排查和架构说明。
- 补齐贡献指南、问题反馈/功能建议表单、PR 模板，以及根许可证入口。
- 统一当前验收摘要与历史基线，保留物理无 Python 电脑和真实桌面交互等未测边界。

上述为仓库资料改进，应用版本保持 `0.1.0`，已交付 EXE 的行为未变。

## 0.1.0 — 2026-10-03（已验收构建）

- 提供 Cisco、华为、H3C 解析，27 条审计规则，中文本地网页与 CLI。
- 支持文件导入、厂商选择、示例、严重度筛选及 JSON/Markdown/HTML 导出。
- 完成 Windows BAT、无参数网页与浏览器启动、端口回退及 CLI 参数/退出码传递。
- 提供 PyInstaller onedir 便携 ZIP 与 onefile EXE，附对应源码、许可、环境记录和 SHA-256。
- Windows 78 项单元测试、25 项进程验收及 Linux 三版本检查通过。
- 迁移至私人仓库 `klwb360/NetAudit`，保留旧仓库及来源记录。

文件、下载地址、对应源码和真实验收范围见 [DELIVERY.md](DELIVERY.md)，原仓库与提交历史见 [MIGRATION.md](MIGRATION.md)。
