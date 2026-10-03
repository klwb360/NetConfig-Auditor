# NetAudit · 网络配置审计工具

导入 Cisco、华为或 H3C 的设备配置，在中文本地网页中查看配置问题、风险、原始行号和修改建议，导出 JSON、Markdown 或 HTML 报告。配置处理在本机完成，工具不会连接设备或下发命令。

**[下载已验收的 Windows 便携包](DELIVERY.md)** · [使用说明](network-config-auditor/docs/WINDOWS.md) · [常见问题](docs/FAQ.md) · [故障排查](docs/TROUBLESHOOTING.md)

## Windows：下载后双击使用

1. 登录有权访问本私人仓库的 GitHub 账号，在 [下载与校验记录](DELIVERY.md) 打开构建产物链接。
2. 解压 GitHub 下载的外层 ZIP，再解压其中名称带 `portable` 的 ZIP；不要在 ZIP 预览窗口中运行。
3. 双击解压文件夹中的 `Start-NetAudit.bat` 或 `NetAudit.exe`，浏览器会自动打开。若未打开，复制启动窗口显示的实际地址到浏览器。
4. 导入 UTF-8 配置、选择厂商，点击“开始审计”；也可先使用“载入示例”。
5. 查看发现、严重度和证据，点击 JSON、Markdown 或 HTML 导出。

**关闭程序**：回到启动窗口按 Ctrl+C。关闭浏览器标签页不会停止服务。**迁移电脑**：复制整个便携文件夹，包括 `_internal`，再双击使用。便携 EXE 自带 Python 运行库，普通使用设计为无需安装 Python 或使用管理员权限。

| 下载内容 | 用途 |
|---|---|
| `*-portable.zip` | 推荐。包含 EXE、运行库、BAT、说明、示例、许可证与对应源码。必须保留整个文件夹。 |
| `*-onefile.zip` | 单 EXE 及配套资料；启动时使用用户临时目录，可能比便携文件夹版稍慢。 |
| `*-onefile.exe` | 可独立运行的单 EXE；再次分发时仍需提供许可证、归属说明与对应源码。 |
| `*-source-*.zip` | 对应完整源码，用于查阅、修改与重建。普通使用无需解压源码。 |

Actions 产物有保留期限。文件名、SHA-256、源码提交、构建环境和有效期见 [交付记录](DELIVERY.md)；后续成功构建见 [Windows 构建列表](https://github.com/klwb360/NetAudit/actions/workflows/netaudit-windows.yml)。不同构建使用各自的校验值。

## 能做什么

- 解析 Cisco IOS/IOS XE、Huawei VRP、H3C Comware 的常见 IPv4 配置。
- 提供 27 条审计规则，覆盖管理面、接口、VLAN、路由、ACL 和 NAT。
- 展示接口、VLAN、路由、ACL、NAT 清单，以及未建模配置行的警告。
- 提供中文网页、严重度筛选、三厂商示例、文件导入及三种报告导出。
- 保留命令行、标准输入、严格模式与严重度退出码，便于本地批量处理。

审计仅覆盖已建模语法。Cisco ASA/NX-OS、IPv6、复杂策略及完整动态路由语义等尚未完整覆盖。没有告警不能视为配置已安全；建议命令需结合设备版本、拓扑和业务人工核对。完整 [支持范围](network-config-auditor/README.md#支持范围) 与 [27 条规则说明](network-config-auditor/docs/RULES.md) 可供查阅。

## 源码与命令行

源码运行需要 Python **3.10 或更新版本**，运行时仅使用标准库。在仓库根目录执行：

```bash
cd network-config-auditor
python -m netaudit
```

无参数默认启动本地网页并打开浏览器。默认端口为 8765；端口占用时会选择空闲端口，以启动窗口显示的 `http://127.0.0.1:端口` 为准。

```bash
# 启动网页，但不打开浏览器
python -m netaudit serve --no-browser

# Cisco 示例导出 HTML 报告
python -m netaudit audit examples/cisco.cfg --vendor cisco --format html --out reports/cisco.html

# 华为示例导出 JSON；Markdown 的格式参数为 md
python -m netaudit audit examples/huawei.cfg --vendor huawei --format json --out reports/huawei.json
```

Windows 可使用 `py -3`，Linux 常用 `python3`。便携版可以用 `NetAudit.exe` 或 `Start-NetAudit.bat` 传递相同参数。退出码：0 调用成功；1 达到 `--fail-on` 指定严重度；2 参数、输入或文件错误，或 `--strict` 检出未建模行。详细用法见 [项目说明](network-config-auditor/README.md)。

## 文档导航

| 想了解 | 文档 |
|---|---|
| 下载、双击、关闭、迁移 | [Windows 使用说明](network-config-auditor/docs/WINDOWS.md)、[常见问题](docs/FAQ.md) |
| 启动、导入或报告问题 | [故障排查](docs/TROUBLESHOOTING.md) |
| 开发、测试与 Windows 构建 | [开发指南](docs/DEVELOPMENT.md)、[验证记录](network-config-auditor/docs/TESTING.md) |
| 模块职责、数据流与扩展点 | [架构说明](docs/ARCHITECTURE.md) |
| 规则与上游来源 | [规则目录](network-config-auditor/docs/RULES.md)、[上游审计](network-config-auditor/docs/UPSTREAM_AUDIT.md) |
| 贡献、反馈与版本变化 | [贡献指南](CONTRIBUTING.md)、[更新记录](CHANGELOG.md) |
| 交付与迁移历史 | [下载与交付检查点](DELIVERY.md)、[迁移记录](MIGRATION.md) |

## 仓库结构

```text
NetAudit/
├── .github/                  自动构建、问题反馈与 PR 模板
├── docs/                     仓库使用、排错、开发与架构资料
├── network-config-auditor/
│   ├── netaudit/             解析、规则、报告、CLI、本地服务与网页
│   ├── examples/             三厂商合成配置
│   ├── tests/                单元和集成测试
│   ├── tools/                上游复现、Windows 构建与进程验收
│   └── docs/                 规则、Windows 使用与验收说明
├── DELIVERY.md               实际产物、源码提交、SHA-256 与验收边界
├── MIGRATION.md              原仓库与历史来源
└── LICENSE / NOTICE          许可证与归属说明
```

## 验证与配置保护

已验收构建在 Windows Server 2022 x64 / Python 3.12.10 上通过 **88 项测试和 25 项进程验收**；Linux Python 3.10/3.12/3.13 检查也通过。普通非管理员账户、物理无 Python 电脑、真实桌面交互、Windows 10/11 和 ARM64 尚未实测，范围以 [交付记录](DELIVERY.md) 为准。

网页仅监听 `127.0.0.1`，资源随程序提供，上传配置不持久保存。报告仍含网络结构，自动脱敏也不能覆盖所有自定义字段。真实配置放在项目 `configs/`，报告放在 `reports/`；问题反馈使用合成或人工脱敏的最小样例。

## 许可证与来源

项目使用 **GPL-3.0-only**；根 [LICENSE](LICENSE) 与 [项目许可证](network-config-auditor/LICENSE) 内容一致。项目复用并改写 pynipper-ng 的部分方法，原 [归属说明](network-config-auditor/NOTICE)、固定上游提交与 [审计记录](network-config-auditor/docs/UPSTREAM_AUDIT.md) 均保留。私人仓库属性不改变已有许可证；分发便携包时请保留许可证、归属说明和对应源码。
