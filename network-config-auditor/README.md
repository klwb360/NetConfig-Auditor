# NetAudit · 网络配置审计工具

输入一台 Cisco、华为、H3C 或锐捷 RGOS 交换机/路由器的完整配置，依次进行 **配置解析 → 六域架构检查 → 安全规则 → CVE / KEV 情报 → 可选本机 AI 解释 → 报告输出**。保留带原始行号的配置问题、风险、建议和结构化清单，提供中文本地网页与命令行；程序运行时仅使用 Python 标准库。

**[v0.2.3 已发布](https://github.com/klwb360/NetAudit/releases/tag/v0.2.3)**。可 [直接下载单 EXE](https://github.com/klwb360/NetAudit/releases/download/v0.2.3/NetAudit-0.2.3-windows-x64-7900be2b8410-onefile.exe) 双击运行，或使用 [便携 ZIP](https://github.com/klwb360/NetAudit/releases/download/v0.2.3/NetAudit-0.2.3-windows-x64-7900be2b8410-portable.zip)；新版提供主题切换和重复风险折叠，保留文件拖入、四厂商识别、风险合并与分步骤命令。真实测试范围与校验值见 [仓库交付记录](https://github.com/klwb360/NetAudit/blob/main/DELIVERY.md)。旧 v0.2.1 Windows 包仍为三厂商版本。

本项目审计了 [pynipper-ng](https://github.com/syn-4ck/pynipper-ng)，保留并改写其插件基类，重建了三厂商解析、审计规则和报告模块。来源、固定提交和改动见 [NOTICE](NOTICE)；审计详情见 [代码审计报告](docs/UPSTREAM_AUDIT.md)。项目采用 GPL-3.0-only。

## 最快开始

Windows 普通用户建议使用便携包：**下载 → 解压 → 双击 `Start-NetAudit.bat` → 导入配置 → 查看与导出**。便携 EXE 包自带 Python 运行库，无需安装 Python、配置开发环境或使用管理员权限。下载方法、关闭与迁移说明见 [Windows 使用说明](docs/WINDOWS.md)。构建方法与实际验收边界见 [便携化记录](docs/PORTABILITY.md)。

v0.2.2 可将一份 UTF-8 配置文件拖入左侧文本区域，或使用“导入配置文件”；两种方式都按内容自动识别四厂商，支持没有扩展名的配置文件。信息不足或混合厂商标记时提示手动选择，识别后仍可调整；点击“开始审计”才运行审计。文件最大 2 MiB、30000 行，文件夹与一次多个文件会给出提示。旧版 v0.2.1 EXE 不包含此功能。

**v0.2.3** 在顶部提供“明亮风格”“暗黑风格”和“跟随系统”主题选项，默认跟随系统，浏览器记住主题偏好。审计后，同类风险集中展示项数与涉及处数；重复项目默认折叠，单项单处直接显示。点击项目查看完整对象、证据与整改建议，也可“展开全部”或“收起全部”。不同 VLAN 等独立发现保留各自命令；折叠只调整展示，统计和三种报告保留完整发现。本页上方 v0.2.3 Windows 包已包含这两项功能；旧 v0.2.2 EXE 不包含。

源码版 Windows 也可双击 `Start-NetAudit.bat`，需要 Python **3.10 或更新版本**。BAT 会优先运行同目录的 `NetAudit.exe`，否则检测 Python。

需要 Python **3.10 或更新版本**。在仓库根目录进入本项目：

```bash
cd network-config-auditor
python -m netaudit serve
```

无参数运行 `python -m netaudit` 或双击 EXE，会启动网页并自动打开默认浏览器。`serve` 同样默认打开浏览器；使用 `python -m netaudit serve --no-browser` 可关闭此行为。默认访问 **http://127.0.0.1:8765**，端口占用时自动选择空闲端口，以启动窗口显示的实际地址为准。

选择厂商，粘贴配置或导入 UTF-8 文本，点击“开始审计”。可先点击“载入示例”。v0.2.0 界面支持严重度筛选、六域覆盖、查看完整解析清单、本地情报输入、可选本机 AI 和 JSON / Markdown / HTML 导出。关闭程序请回到启动窗口按 **Ctrl+C**；关闭网页标签页不会停止服务。迁移时复制整个解压文件夹。

Windows 通常可将 `python` 替换为 `py -3`；Linux/macOS 通常可替换为 `python3`。不安装依赖也可以直接运行。

```bash
# Cisco 样例 → HTML 报告
python -m netaudit audit examples/cisco.cfg --format html --out reports/cisco.html

# 华为配置 → 完整结构化 JSON
python -m netaudit audit examples/huawei.cfg --vendor huawei --format json --out reports/huawei.json

# H3C 配置 → Markdown 报告
python -m netaudit audit examples/h3c.cfg --vendor h3c --format md --out reports/h3c.md

# 锐捷 RGOS 配置 → Markdown 报告
python -m netaudit audit examples/ruijie.cfg --vendor ruijie --format md --out reports/ruijie.md

# 达到 high 及以上风险时以退出码 1 返回，方便 CI 使用
python -m netaudit audit examples/cisco.cfg --fail-on high --format json --out reports/result.json

# 存在未支持的配置行时以退出码 2 返回，仍输出报告
python -m netaudit audit examples/cisco.cfg --strict
```

也可安装命令行入口：

```bash
python -m pip install .
netaudit serve
netaudit audit device.cfg --vendor cisco --format json --out reports/device.json
```

`audit -` 从标准输入读取配置。输入与输出不能是同一个文件；报告使用原子写入，在支持 POSIX 权限的系统上默认权限为 `0600`。

## 情报与可选 AI

默认审计使用随包 CISA KEV 离线快照，不进行外部联网。CVE 适用性需要用户提供精确设备 CPE、明确版本以及本地 NVD CVE 2.0 数据；不能仅凭品牌或配置片段确认漏洞。KEV 也不能证明当前设备已被入侵。文件格式、官方来源、版本比较限制与快照许可见 [INTELLIGENCE.md](docs/INTELLIGENCE.md)。

```bash
# 本地产品版本核对；asset.json / nvd-subset.json 格式见情报说明
python -m netaudit audit device.cfg --asset-info asset.json --nvd-file nvd-subset.json --format html --out reports/device.html

# 显式联网下载官方 KEV；不会上传配置，默认保存到用户缓存或临时目录
python -m netaudit intel-update --out reports/kev.json
python -m netaudit audit device.cfg --kev-file reports/kev.json --format md --out reports/device.md

# 可选本机 Ollama；替换为已安装模型名称
python -m netaudit audit device.cfg --ai-model YOUR_INSTALLED_MODEL --ai-endpoint http://127.0.0.1:11434 --ai-timeout 45 --format md --out reports/device-ai.md
```

AI 默认关闭，当前只支持本机 Ollama 回环地址。仅在用户明确启用并选定已有模型后调用；模型失败仍生成规则与情报报告。便携配置审计无需 Python，Ollama 仅为可选 AI 功能的额外软件。规则内建建议与模型生成解释分别标注，真实模型输出需人审；发送内容与设置见 [AI.md](docs/AI.md)。

## 配置如何取得

从设备导出完整运行配置：Cisco / 锐捷 RGOS 使用 `show running-config`，华为/H3C 使用 `display current-configuration`。导出时关闭分页、去掉命令提示符/分页符/终端颜色转义，保存为 UTF-8 文本。一次输入一台设备，不要拼接多台配置。

厂商有独有语法时可自动识别。RGOS 使用明确的 `version ...RGOS` 标记识别；其余配置常与 IOS 共享语法，缺少版本标记时请手动选择“锐捷 RGOS”或 CLI `--vendor ruijie`。华为/H3C 有很多共享命令，只有 `sysname` 等共享语法时请明确选择厂商。混合厂商标记会拒绝自动猜测。

## 支持范围

| 类别 | Cisco IOS / IOS XE | Huawei VRP | H3C Comware |
|---|---|---|---|
| 接口 | 地址、secondary、VRF、shutdown、描述、switchport、ACL 绑定、NAT 角色 | 地址/sub、VPN 实例、shutdown、描述、link-type、ACL 绑定 | 地址/sub、VPN 实例、shutdown、描述、link-type、ACL 绑定 |
| VLAN | VLAN 定义，access/native，trunk 列表与 add/remove/except | vlan batch、default/PVID、allow-pass 与 undo | VLAN 定义、access/PVID、permit 与 undo |
| 静态路由 | ip route，VRF、下一跳、出接口、管理距离 | ip route-static、VPN 实例、下一跳、preference | ip route-static、VPN 实例、下一跳、preference |
| STP | 显式模式、全局/接口/VLAN 启停、PortFast、BPDU 过滤/保护 | 显式启停、模式、edged-port、BPDU 过滤/保护 | 显式启停、模式、edged-port、BPDU 过滤/保护 |
| OSPF（IPv4） | 进程、VRF、Router ID、区域、network、被动接口、认证模式与接口绑定 | 进程、VPN 实例、Router ID、区域、network、silent-interface、认证模式与接口绑定 | 进程、VPN 实例、Router ID、区域、network、silent-interface、认证模式与接口绑定 |
| 其他动态路由 | BGP/RIP 进程与配置原文 | BGP 进程与配置原文 | BGP 进程与配置原文 |
| IPv4 ACL | 数字/命名 standard/extended，any/host/wildcard，协议、基本端口条件、log | basic/advanced，rule 序号，source/destination、基本端口条件 | basic/advanced，rule 序号，source/destination、基本端口条件 |
| NAT | inside/outside、source list、pool、static 与 TCP/UDP 端口映射 | nat outbound、address-group、nat server | nat outbound、address-group、nat server |
| 管理面 | HTTP、SSH 参数、VTY、密码类型、community | HTTP、Telnet、VTY、密码类型、community | HTTP、Telnet、VTY、密码类型、community |

锐捷 RGOS 支持已建模的 IOS 风格接口、IPv4 ACL、静态路由、管理面及 STP / OSPF 语法，并处理 `vlan range 100-102,200`、显式 `no spanning-tree` 和 `switchport protected`。合成示例见 [examples/ruijie.cfg](examples/ruijie.cfg)。这不代表所有 RGOS 型号、版本或 Cisco 扩展命令都兼容；未建模命令保留警告。`switchport protected` 是端口隔离配置，不能作为 STP 已启用或没有环路风险的证据。

当前以常见 IPv4 配置为目标。Cisco ASA/NX-OS、IPv6、接口 range、ACL object-group、复杂 time-range/established、route-map/PBR、完整动态路由语义、USG 安全策略、现代 NAT 的全部变体尚未建模。未支持的动态路由子命令保留在清单并提示人工审查。STP 检查不确认根桥或实时环路，OSPF 检查不确认邻居、收敛或密钥有效性；缺失命令和继承关系不能直接等同于关闭或未认证。

未建模行会出现在 `inventory.warnings`，最多展示 200 行，并保留实际总数。解析器识别行数表示识别的结构/命令范围，并非所有字段语义覆盖率。未知条件的 ACL 规则不参与覆盖推断，也不会直接判作 unrestricted permit；`match-order auto` 不进行遮蔽推断。审计不足不能当成“已安全”。

## 报告如何判断

- `confirmed-config`：有明确配置证据。实际影响仍依赖网络可达性与运行状态。
- `needs-review`：需结合版本、拓扑或业务目的核对，例如静态 NAT 映射、Trunk VLAN 范围、缺少来源 ACL。
- 情报的 `cpe-version-match` 表示本地 NVD 条件与输入产品版本匹配；未知条件保留 `needs-review` 候选，不能冒充已确认受影响或已遭入侵。
- 六域状态 `checked / needs-review / not-observed` 表示检查覆盖或复核需要，不能当作合规分数。
- 严重度：`critical / high / medium / low / info`。详情见 [规则目录](docs/RULES.md)。
- NAT 选流 ACL 会单独标注，宽泛选流不会当成防火墙已放通。
- 各 VTY 段独立审查；安全段不会掩盖另一段 Telnet 或不认证配置。
- 同一前缀的多条静态路由可能是 ECMP/浮动路由，工具不会直接认定冲突。
- 同一未见定义的 VLAN 按 VLAN ID 合并为一项发现，列出全部关联端口；同端口的 access / native 双重引用只算一个端口。不同 VLAN 保持分开。
- 只有整改条件相同的白名单规则合并。严重度统计与 `summary.total` 按合并后的发现计数，`summary.occurrences_total` 保留涉及处数；`affected_objects`、`occurrences` 和证据展示具体范围。
- 先执行只读 `verification_commands` 核查；`commands` 为参数已知的候选整改脚本，`command_templates` 需要补齐 `<参数名>`，`command_notes` 说明前提与验证。工具不会连接设备、执行命令或自动保存配置，先核对 NOS 版本、业务和管理回退路径。使用方法和官方参考见 [建议命令说明](docs/REMEDIATION.md)。

JSON 使用 `schema_version: "1.1"`，保留 `device`、`summary`、`findings`、`inventory`、`limitations`，增加 `architecture`（六域覆盖）、`intelligence`（来源、候选与产品版本匹配）、`ai`（启用状态与解释）和 `pipeline`（六个阶段状态）。CLI 与网页使用完整流程；直接调用底层 `rules.audit(config)` 仅得到架构与规则结果，不会调用情报或模型。每项发现包含 `rule_id`、`severity`、`problem`、`risk`、`recommendation`、`confidence`、`evidence` 和可选建议命令。证据行号从 1 开始，按照原始输入计数。

接口的 `allowed_vlan_ranges` 使用闭区间列表，例如 `[[10, 12], [20, 20]]` 表示 10、11、12、20；`[[1, 4094]]` 表示 all，`[]` 表示 none，`null` 表示没有已识别的显式允许列表。这样全 VLAN Trunk 不会使报告膨胀。

## 本地运行与配置保护

网页服务只监听 `127.0.0.1`；校验 Host、Origin 和每次启动生成的会话令牌，不启用跨域读取。页面、样式、脚本均在本地，无第三方 CDN。默认不请求外部情报和模型；显式 `intel-update` 才连接官方 CISA 数据源，显式 AI 才连接本机 Ollama。网页不会持久保存上传配置，也不记录配置请求；用户导出报告时会主动写入下载目录。

凭据在保留证据和清单前隐藏，HTML 输出使用转义，网页使用 `textContent`。自动脱敏覆盖常见 password/secret、SNMP community、key/key-string 和认证密钥语法；不保证识别所有自定义敏感字段。报告仍含地址、设备名和网络结构，应按内部配置资料保护。真实配置放在被忽略的 `configs/`，报告放在 `reports/`；仓库示例全部为合成数据。

资源限制：每份输入 2 MiB / 30000 行、512 个接口、每 ACL 256 条规则、总计 2048 条 ACL 规则。超限拒绝输出部分结果。Web 同时最多执行 4 个审计请求。

## 验证

```bash
python -m unittest discover -s tests -v
python tools/reproduce_upstream.py
```

测试覆盖四厂商解析、VLAN 范围与同类发现合并、命令前提和参数模板、ACL 覆盖顺序、NAT 选流语义、多个 VTY 范围、原始行号、脱敏、HTML 转义、CLI 退出码、文件权限及本地服务的来源/Host/令牌限制。上游复现脚本使用固定源码方法与只实现正则查询的解析替身，隔离复现三个已确认缺陷；不代表安装旧依赖后跑过完整上游程序。

新增规则可在 `netaudit/rules.py` 继承 `GenericPlugin`，并加入显式 `PLUGINS` 注册表。新增解析需补充能覆盖误报/漏报边界的 fixture 与测试。
