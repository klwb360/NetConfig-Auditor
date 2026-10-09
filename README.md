# NetAudit · 网络配置学习与审计

导入 Cisco、华为、H3C 或锐捷 RGOS 的配置备份，用中文描述一个具体目标，或在模拟命令行逐条练习；先查看命令的前提、理由与配置差异，确认后应用到练习副本，需要时再运行原有审计。配置处理在本机完成，工具不会连接设备或下发命令。

**v1.0.0 待发布**：本分支新增“中文目标 + 模拟命令行”学习流程；Windows 构建与验收结果确认后更新下载入口。当前稳定包为 **[v0.2.3](https://github.com/klwb360/NetAudit/releases/tag/v0.2.3)**，提供四厂商审计、主题切换与重复风险折叠，尚不包含模拟练习。

**[直接下载可运行的单 EXE](https://github.com/klwb360/NetAudit/releases/download/v0.2.3/NetAudit-0.2.3-windows-x64-7900be2b8410-onefile.exe)**：下载后双击，等待本地网页打开即可使用，无需安装 Python。需要 BAT、示例和配套资料时选择 **[便携 ZIP](https://github.com/klwb360/NetAudit/releases/download/v0.2.3/NetAudit-0.2.3-windows-x64-7900be2b8410-portable.zip)**，解压一次后双击启动。

[v0.2.3 发布页](https://github.com/klwb360/NetAudit/releases/tag/v0.2.3) · [使用说明与常见问题](docs/FAQ.md) · [故障排查](docs/TROUBLESHOOTING.md) · [文件校验与实测范围](DELIVERY.md)

[下载与双击](#windows下载后双击使用) · [模拟练习步骤](#新版网页怎么用) · [练习范围](network-config-auditor/docs/SIMULATOR.md) · [命令行](#源码与命令行) · [文档索引](#文档导航)

## Windows：下载后双击使用

1. **下载**：登录有权访问本私人仓库的 GitHub 账号，点击上方“直接下载可运行的单 EXE”。也可在 [最新 Release](https://github.com/klwb360/NetAudit/releases/latest) 的 **Assets** 中选择 `-onefile.exe` 或 `-portable.zip`。
2. **准备**：单 EXE 无需解压。下载 ZIP 时，在 Windows 中右键 →“全部提取”，打开解压后的文件夹；不要在 ZIP 预览窗口中运行。
3. **启动**：双击下载的 `*-onefile.exe`，或便携文件夹中的 `Start-NetAudit.bat` / `NetAudit.exe`，默认浏览器会自动打开本地网页。若未打开，复制启动窗口显示的实际 `http://127.0.0.1:端口` 地址到浏览器，并保留启动窗口。
4. **导入备份**：先点击“载入示例”，或拖入一台设备的 UTF-8 配置文件；也可点击“导入配置文件”或粘贴文本。支持中文、空格和无扩展名文件名，最大 2 MiB / 30000 行，一次一个文件。程序按内容识别四厂商，无法可靠识别时请手动选择。
5. **开始练习（v1.0.0）**：点击“载入模拟”，输入一个目标，例如 `创建 VLAN 20`，点击“生成命令草案”，阅读每步理由后点击“将草案放入命令区”。也可直接输入设备命令，每行一条。
6. **预览并应用（v1.0.0）**：点击“预览运行”，查看每条命令能否运行、原因和配置差异；确认后点击“应用本次预览”。这只改变当前练习副本，原始备份保留。需要时撤销、重置或“导出模拟配置 .cfg”。
7. **按需审查与导出**：v1.0.0 点击“审查当前模拟配置”；若只想检查备份，未载入模拟时直接点击“开始审计”。查看安全发现、网络架构、漏洞情报等页签，按严重度筛选，展开重复风险，点击 **JSON、Markdown 或 HTML** 下载完整报告。

当前 v0.2.3 下载包在导入后直接点击“开始审计”；第 5、6 步及“审查当前模拟配置”适用于 v1.0.0 源码与随后发布的新版包。

**切换风格**：在网页顶部选择“明亮风格”“暗黑风格”或“跟随系统”，浏览器记住主题偏好；默认跟随系统。配置内容不会随主题设置保存。

首次使用保持高级设置默认值即可。“设备版本与本地情报”和“本机 AI”均为可选功能，普通配置审计可直接运行；默认随包提供 KEV 快照，AI 默认关闭。按需了解 [情报核对](network-config-auditor/docs/INTELLIGENCE.md) 与 [本机 AI](network-config-auditor/docs/AI.md)。

**用完关闭**：回到启动窗口按 **Ctrl+C**，等待程序退出；仅关闭浏览器标签页不会停止服务。**迁移电脑**：先关闭程序，再复制整个便携文件夹，包括 `_internal`，到另一台 Windows 电脑后重新双击。便携 EXE 自带 Python 运行库，普通使用设计为无需安装 Python 或使用管理员权限。

| 下载内容 | 用途 |
|---|---|
| `*-portable.zip` | 推荐。包含 EXE、运行库、BAT、说明、示例、许可证与对应源码。必须保留整个文件夹。 |
| `*-onefile.zip` | 单 EXE 及配套资料；启动时使用用户临时目录，可能比便携文件夹版稍慢。 |
| `*-onefile.exe` | 可独立运行的单 EXE；再次分发时仍需提供许可证、归属说明与对应源码。 |

Release 只保留以上三种运行附件。仓库保持私人，Release 下载也需要访问权限；源码、校验与验收资料见下方 [源码与命令行](#源码与命令行) 和 [发布档案](docs/releases/README.md)。

## 新版网页怎么用

![NetAudit v1.0.0 配置练习工作台，使用合成配置示例](docs/images/simulator.png)

v1.0.0 默认进入“配置练习”。左侧保存原始备份，右侧维护独立练习副本；窄屏依次堆叠。生成草案、放入命令区、预览和应用是四个独立操作，只有“应用本次预览”才改变练习副本。一批命令中有任何一条失败，整批配置和命令行视图都回滚。

“可修改”表示本工具支持该语法且当前配置前提满足；“当前不能运行”会解释缺少的 VLAN、模式或其他依赖；“尚不支持”表示本工具没有实现，不能据此判断真实设备不允许执行。命令区下方可查看当前视图支持的命令。它不模拟 ping、数据包转发、链路通断、STP 收敛或 OSPF 邻居，也不保证型号、固件或真实登录条件兼容。

中文草案使用离线规则，只支持明确的单一目标，例如 `创建 VLAN 20`、`把接口 GigabitEthernet0/1 加入 VLAN 20`、`关闭 HTTP`。接口名称必须来自备份；缺少参数或包含多个动作时会提示补充，不会猜测部分需求。这项功能不需要 AI 或联网；详细支持范围见 [模拟练习说明](network-config-auditor/docs/SIMULATOR.md)。

撤销最多保留 20 步，并受累计 16 MiB 上限约束；刷新或关闭页面会清除练习。导出的 `.cfg` 是已应用的模拟配置，保留原文与凭据，需按敏感文件保管。重新导入、编辑原始备份或更改厂商会结束当前练习。进入“按需审查”可检查当前副本；未建立模拟副本时检查左侧备份。审计保留以下页签：

| 结果页签 | 查看内容 |
|---|---|
| 安全发现 | 按严重度筛选；同类风险显示项数与涉及处数，可展开核对逐项证据和建议。 |
| 网络架构 | 查看 VLAN、STP、OSPF、ACL、NAT、Management Plane 的覆盖与待复核项。 |
| 漏洞情报 | 查看本地 CVE / KEV 来源、版本匹配及未确认候选。 |
| AI 建议 | 查看显式启用的本机模型解释，以及未启用或失败状态。 |
| 报告与清单 | 下载 JSON、Markdown、HTML，查看结构化清单和未建模行。 |
| 使用帮助 | 查看输入要求、关闭、迁移和检查边界。 |

同类风险按规则、严重度、分类、确认程度与标题集中展示，重复项目默认折叠，单项单处直接显示；可“展开全部”或“收起全部”。不同 VLAN 等独立发现仍保留各自对象、证据与命令。页签、主题、筛选和折叠只调整显示，审计统计与完整导出内容保持。模拟配置、原始输入或审计设置变化后，旧审计结果与导出会失效，需重新审计。默认审计不依赖云端服务，可选 AI 只连接本机 Ollama。

详细操作见 [Windows 使用说明](network-config-auditor/docs/WINDOWS.md#新版网页工作区)，当前下载和真实验证结果见 [交付记录](DELIVERY.md)。

## 能做什么

v1.0.0 在保留原有审计能力的基础上增加离线练习；发布包与实测范围以 [交付记录](DELIVERY.md) 为准。

- 解析 Cisco IOS/IOS XE、Huawei VRP、H3C Comware 和锐捷 RGOS 已建模的常见 IPv4 配置。
- 练习基础 VLAN、已有接口、默认 VRF 静态路由、基础 ACL 与部分管理面 / STP 命令；说明当前模式、依赖和拒绝原因，预览差异后明确应用，支持撤销、重置和导出配置。练习支持范围小于解析范围。
- 按 VLAN、STP、OSPF、ACL、NAT、Management Plane 六个领域展示检查覆盖与待复核问题，保留原有 27 条配置规则并增加 8 条 STP / OSPF 规则，共 35 个规则 ID。
- 展示接口、VLAN、STP、OSPF、路由、ACL、NAT 清单，以及未建模配置行的警告。
- 随包提供 CISA 官方 KEV 离线快照；输入精确产品 CPE 与本地 NVD CVE 2.0 数据后进行版本适用性核对，无法确认的项保持候选状态。
- 显式启用本机 Ollama 后提供 AI 解释与整改建议；未设置模型时不调用 AI，失败仍保留审计报告。
- 提供中文网页、明亮 / 暗黑 / 跟随系统主题、重复风险折叠、严重度筛选、四厂商合成示例、文件拖入 / 导入时按内容识别及三种报告导出。
- 同一未见定义的 VLAN 按 VLAN ID 合并，列出所有关联端口与原始证据；其他具有相同整改条件的同类风险也合并，保留涉及处数。
- 根据厂商提供只读核查命令、已知参数的整改脚本和待填写参数的模板，说明适用前提；未知业务、拓扑、地址或密钥需人工补充。
- 保留命令行、标准输入、严格模式与严重度退出码，便于本地批量处理。

审计仅覆盖已建模语法。Cisco ASA/NX-OS、IPv6、复杂策略及完整动态路由语义等尚未完整覆盖。没有告警不能视为配置已安全；建议命令需结合设备版本、拓扑和业务人工核对。完整 [支持范围](network-config-auditor/README.md#支持范围) 与 [规则说明](network-config-auditor/docs/RULES.md) 可供查阅。KEV 记录表示相关漏洞曾在现实中被利用，不能证明当前设备受影响或已被入侵。

## 审计流程

练习先走“备份 → 中文草案或直接输入命令 → 预览 → 明确应用 → 导出配置”；点击审查后，当前配置再进入下面的原有流程：

```mermaid
flowchart TD
    F[配置文件] --> P[配置解析器]
    P --> A[网络架构检查]
    A --> V[VLAN]
    A --> S[STP]
    A --> O[OSPF]
    A --> C[ACL]
    A --> N[NAT]
    A --> M[Management Plane]
    V --> R[安全规则引擎]
    S --> R
    O --> R
    C --> R
    N --> R
    M --> R
    R --> I[CVE / KEV 情报]
    I --> AI[可选本机 AI 解释与整改建议]
    AI --> OUT[Markdown / HTML / JSON 报告]
```

六个领域的状态描述当前输入的检查覆盖，不能证明真实拓扑或运行状态。默认使用本地快照，不联网；显式 `intel-update` 才下载官方 KEV。AI 需要自行安装和运行 Ollama 并选择本机已有模型，只影响可选解释功能，便携版的配置审计仍无需安装 Python。详见 [情报使用说明](network-config-auditor/docs/INTELLIGENCE.md)与 [AI 使用说明](network-config-auditor/docs/AI.md)。

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

# 根据一个中文目标生成草案；不应用修改
python -m netaudit plan examples/cisco.cfg --vendor cisco --goal "创建 VLAN 20"

# 在副本中模拟命令，成功后另存配置；原备份不改
python -m netaudit simulate examples/cisco.cfg --vendor cisco --command "configure terminal" --command "vlan 20" --command "end" --out reports/practice.cfg

# Cisco 示例导出 HTML 报告
python -m netaudit audit examples/cisco.cfg --vendor cisco --format html --out reports/cisco.html

# 华为示例导出 JSON；Markdown 的格式参数为 md
python -m netaudit audit examples/huawei.cfg --vendor huawei --format json --out reports/huawei.json

# 锐捷 RGOS 合成示例导出 Markdown
python -m netaudit audit examples/ruijie.cfg --vendor ruijie --format md --out reports/ruijie.md

# 使用精确设备 CPE 与本地 NVD 数据核对 CVE；文件格式见情报说明
python -m netaudit audit device.cfg --asset-info asset.json --nvd-file nvd-subset.json --format html --out reports/device.html

# 显式下载官方 KEV 到用户指定位置；审计时用 --kev-file 指定
python -m netaudit intel-update --out reports/kev.json

# 可选：调用本机已安装的 Ollama 模型；模型名需替换成实际名称
python -m netaudit audit device.cfg --ai-model YOUR_INSTALLED_MODEL --format md --out reports/device.md
```

Windows 可使用 `py -3`，Linux 常用 `python3`。v1.0.0 便携版可以用 `NetAudit.exe` 或 `Start-NetAudit.bat` 传递相同参数。`plan` / `simulate` 向本机标准输出写 JSON；`simulate` 的 `config` 包含未脱敏原文，不宜将输出放入公开日志。命令文件用 `--commands commands.txt`，续练视图用 `--context context.json`（保存上次结果中的 `context` 对象）。模拟失败整批回滚、退出码 2，且不写 `--out`；成功导出保留原有行尾。

退出码：0 调用成功；审计 1 表示达到 `--fail-on` 指定严重度；2 表示参数、输入或文件错误、`--strict` 检出未建模行、模拟批次失败或目标草案尚未就绪。详细用法见 [项目说明](network-config-auditor/README.md)。

两个运行 ZIP 都包含对应完整 `*-source-*.zip`，用于查阅、修改与重建；版本标签固定到 EXE 的构建源码。Release 不再重复上传独立源码 ZIP。`SHA256SUMS.txt`、构建清单与三份验收报告按原始字节永久保存在 [发布档案](docs/releases/README.md)，其中校验文件仍记录原始九文件构建产物。普通使用无需解压源码；源码提交、SHA-256 和实测范围见 [交付记录](DELIVERY.md)。GitHub 自动生成的 “Source code” ZIP/tar.gz 无法单独隐藏，普通用户选择上方运行包即可。

开发或备份获取途径：[Windows 构建列表](https://github.com/klwb360/NetAudit/actions/workflows/netaudit-windows.yml) 的 Actions 产物仍可下载，但有保留期限；它包含外层产物 ZIP，需先解压外层，再解压其中的 `portable.zip`。Release 直接提供内部便携 ZIP，只需解压一次。不同构建使用各自的校验值。

## 文档导航

| 想了解 | 文档 |
|---|---|
| 下载、双击、关闭、迁移 | [使用说明与常见问题](docs/FAQ.md)；[详细启动说明](network-config-auditor/docs/WINDOWS.md)保留 Actions 包获取方式 |
| 中文目标、命令练习、撤销与配置导出 | [模拟练习说明](network-config-auditor/docs/SIMULATOR.md) |
| 启动、导入或报告问题 | [故障排查](docs/TROUBLESHOOTING.md) |
| 开发、测试与 Windows 构建 | [开发指南](docs/DEVELOPMENT.md)、[验证记录](network-config-auditor/docs/TESTING.md) |
| 发布新版本与下载资产 | [发布指南](docs/RELEASING.md) |
| 各版本校验、构建环境与验收报告 | [发布档案](docs/releases/README.md) |
| 模块职责、数据流与扩展点 | [架构说明](docs/ARCHITECTURE.md) |
| CVE / KEV 和本机 AI | [情报说明](network-config-auditor/docs/INTELLIGENCE.md)、[AI 说明](network-config-auditor/docs/AI.md) |
| 规则与上游来源 | [规则目录](network-config-auditor/docs/RULES.md)、[上游审计](network-config-auditor/docs/UPSTREAM_AUDIT.md) |
| 贡献、反馈与版本变化 | [贡献指南](CONTRIBUTING.md)、[更新记录](CHANGELOG.md) |
| 交付与迁移历史 | [下载与交付检查点](DELIVERY.md)、[迁移记录](MIGRATION.md) |

## 仓库结构

```text
NetAudit/
├── .github/                  自动构建、问题反馈与 PR 模板
├── docs/                     仓库使用、排错、开发与架构资料
├── tools/                    已验收产物的 Release 发布与校验
├── network-config-auditor/
│   ├── netaudit/             解析、规则、报告、CLI、本地服务与网页
│   ├── examples/             四厂商合成配置
│   ├── tests/                单元和集成测试
│   ├── tools/                上游复现、Windows 构建与进程验收
│   └── docs/                 规则、Windows 使用与验收说明
├── DELIVERY.md               实际产物、源码提交、SHA-256 与验收边界
├── MIGRATION.md              原仓库与历史来源
└── LICENSE / NOTICE          许可证与归属说明
```

## 验证与配置保护

v1.0.0 的实际构建、测试与未实测项目将在 [交付记录](DELIVERY.md) 中单独记录；以下为旧版已完成的验证，不代表新版 EXE 已验收。

v0.2.3 在 Windows Server 2022 x64 / Python 3.12.10 / PyInstaller 6.22.3 上通过 **272 项应用测试和 28 项真实进程验收**（源码 10、onedir 9、onefile 9）；Linux Python 3.10/3.12/3.13 CI 全部通过。Linux Chromium 完成 **112 项主题与风险折叠检查**；浏览器自动化不等于 Windows 人工桌面交互。发布器通过 57 项保护测试，三个运行附件上传后均下载回验，实际源码标签与 Windows 构建提交一致。

历史 v0.2.2 保留 272 项应用测试、28 项 Windows 进程验收、85 项拖入追加检查与此前 184 项 RGOS 检查，原运行文件与标签保持。

历史 v0.2.1 在 Windows Server 2022 x64 上通过 192 项应用测试和 28 项进程验收，Linux Chromium 65 项网页检查、当时的 14 项发布保护测试与 9 附件回验保持原记录。旧版本没有重新构建。

历史 [v0.2.0](https://github.com/klwb360/NetAudit/releases/tag/v0.2.0) 的 192 项测试、28 项进程验收与 24 项网页检查，以及 [v0.1.0](https://github.com/klwb360/NetAudit/releases/tag/v0.1.0) 的 88 项测试与 25 项进程验收保持原记录；旧版本保留下载，文件和 SHA-256 均记录在 [交付记录](DELIVERY.md)。

Windows 10/11、ARM64、普通非管理员账户、物理上未安装 Python 的独立电脑，以及 Windows Explorer 人工双击、系统默认浏览器可视交互与实际拖入仍未实测。冻结版通过限制 PATH、移除 Python 环境验证随包运行库，构建 runner 本身仍安装 Python。建议命令经[官方参考核对](network-config-auditor/docs/REMEDIATION.md)与离线回归，没有在真实设备执行；真实 Ollama 模型和实际产品 NVD 适用性仍待验证。范围以 [交付记录](DELIVERY.md) 为准。

网页仅监听 `127.0.0.1`，资源随程序提供，上传配置和练习历史不持久保存。默认不请求外部情报或模型；本机 AI 仅在用户显式选择模型后调用，发送内容与限制见 [AI 说明](network-config-auditor/docs/AI.md)。报告仍含网络结构，自动脱敏也不能覆盖所有自定义字段；模拟配置导出及 CLI / API 的 `config` 字段保留原始凭据，需按备份文件保护。真实配置放在项目 `configs/`，报告放在 `reports/`；问题反馈使用合成或人工脱敏的最小样例。

## 许可证与来源

项目使用 **GPL-3.0-only**；根 [LICENSE](LICENSE) 与 [项目许可证](network-config-auditor/LICENSE) 内容一致。项目复用并改写 pynipper-ng 的部分方法，原 [归属说明](network-config-auditor/NOTICE)、固定上游提交与 [审计记录](network-config-auditor/docs/UPSTREAM_AUDIT.md) 均保留。私人仓库属性不改变已有许可证；分发便携包时请保留许可证、归属说明和对应源码。随包 CISA KEV 数据按其 CC0 说明保留来源与快照记录，详见 [情报说明](network-config-auditor/docs/INTELLIGENCE.md)。
