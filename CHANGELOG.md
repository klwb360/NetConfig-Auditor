# 更新记录

应用版本以 `network-config-auditor/pyproject.toml` 为准。构建文件名同时包含源码提交前 12 位；同一应用版本的不同提交具有各自 SHA-256。

## 0.2.0 — 2026-10-03

- 将配置解析、六域架构检查、安全规则、CVE / KEV、本机可选 AI 和报告输出组织为同一审计流程，网页、CLI 与三种报告展示一致的阶段状态。
- 新增显式 STP 与 IPv4 OSPF 配置解析和审计，保留未知状态及单设备离线检查边界；原有 27 条配置规则保留，共 35 个规则 ID。
- 增加 VLAN、STP、OSPF、ACL、NAT、Management Plane 六域覆盖、证据与确认程度展示。
- 随包提供 CISA 官方 2026-10-02 KEV 快照，增加本地设备 CPE / 候选 CVE 和 NVD CVE 2.0 JSON 导入；只有足够的产品版本证据才确认匹配。
- 增加显式 `intel-update` 官方 KEV 下载，默认审计保持离线，更新输出使用用户目录。
- 增加显式启用的本机 Ollama 解释；未启用、模型不可用或解释失败时保留规则和情报结果，模型输出作为待人工审阅建议。
- JSON 报告升级为 schema 1.1，保留原有字段并增加架构、情报、AI 和流程信息；Markdown / HTML 保留相同结论与来源。
- 发布 [v0.2.0](https://github.com/klwb360/NetAudit/releases/tag/v0.2.0)，提供源码版、Windows onedir 便携 ZIP 和 onefile EXE，共 9 个附件；v0.1.0 保留。
- Windows Server 2022 x64 通过 192 项单元测试与 28 项真实进程验收（源码 10、onedir 9、onefile 9）；Linux Python 3.10 / 3.12 / 3.13 与 Chromium 24 项网页检查通过。
- 发布保护 14 项测试通过，全部 9 个附件上传后下载回验；Release 标签指向实际 EXE 源码提交 `8a9840601d6c51dbdaff1fbbf62aeaf84cc0b490`。
- AI 使用本机协议替身、NVD 使用合成格式用例；真实模型推理与真实 NVD 产品适用性，以及未列为实测的 Windows 人工/物理环境仍待验证。

## Release 下载 — 2026-10-03

- 发布 [v0.1.0](https://github.com/klwb360/NetAudit/releases/tag/v0.1.0)，提供便携 ZIP、单 EXE 包、单 EXE、对应源码、构建清单、三份验收报告与 SHA-256。
- 首页提供 Release 和推荐便携 ZIP 入口，下载后只需解压一次。
- 新增发布工作流与维护指南，复用已验收的原始构建文件；标签指向 EXE 对应源码。
- 12 项发布保护测试通过；正式发布前逐个下载附件回验，不覆盖已有版本的不同标签或文件。

已交付程序和校验值保持不变，Windows 验收仍对应 `f2002b79bd6da91e2a29f741c8483951e20bba86`。

## 仓库维护 — 2026-10-03

- 完善仓库首页、使用与开发导航、常见问题、故障排查和架构说明。
- 补齐贡献指南、问题反馈/功能建议表单、PR 模板，以及根许可证入口。
- 统一当前验收摘要与历史基线，保留物理无 Python 电脑和真实桌面交互等未测边界。
- 改进 Windows 验收脚本的进程身份追踪；验收失败时上传 JSON 诊断报告，成功构建继续单独上传便携包。
- 新增 10 项验收工具回归测试，Windows 与 Linux 完整 88 项测试通过；Windows 25 项真实进程验收通过。

上述为仓库资料与构建验收改进，应用版本保持 `0.1.0`，已交付 EXE 的行为未变。

## 0.1.0 — 2026-10-03（首次便携验收）

- 提供 Cisco、华为、H3C 解析，27 条审计规则，中文本地网页与 CLI。
- 支持文件导入、厂商选择、示例、严重度筛选及 JSON/Markdown/HTML 导出。
- 完成 Windows BAT、无参数网页与浏览器启动、端口回退及 CLI 参数/退出码传递。
- 提供 PyInstaller onedir 便携 ZIP 与 onefile EXE，附对应源码、许可、环境记录和 SHA-256。
- Windows 78 项单元测试、25 项进程验收及 Linux 三版本检查通过。
- 迁移至私人仓库 `klwb360/NetAudit`，保留旧仓库及来源记录。

文件、下载地址、对应源码和真实验收范围见 [DELIVERY.md](DELIVERY.md)，原仓库与提交历史见 [MIGRATION.md](MIGRATION.md)。
