# 1.1.0 批量审计与解析完整性更新

本项目已迁入公开 NetConfig-Auditor。新增 audit-batch、严格多编码导入、文件路径/哈希/行号追溯、独立50配置金标准；修复路由/NAT条件丢失、NAT伪映射和H3C撤销语法。包名与 NetAudit 启动器保持兼容。使用与验证见 [公开仓库说明](../README.md)、[验收方法](../docs/ACCEPTANCE.md)和[检查点](../docs/checkpoints/)。

# NetAudit · 网络配置学习与审计

导入一台 Cisco、华为、H3C 或锐捷 RGOS 交换机/路由器的备份，在独立副本中练习配置：**中文目标或设备命令 → 预览结果、理由与差异 → 明确应用 → 撤销 / 重置 / 导出配置 → 按需审计**。原有六域架构检查、35 个规则 ID、CVE / KEV 核对、可选本机 AI 与 JSON / Markdown / HTML 报告继续提供；运行时仅使用 Python 标准库。

**本页对应 v1.0.1 源码**。Windows 运行文件见 [最新 Release](https://github.com/klwb360/NetConfig-Auditor/releases/latest) 的 **Assets**：选择 `*-onefile.exe` 双击运行，或下载 `*-portable.zip` 解压后启动；模拟功能需要 **1.0.0 或更新**，厂商底色高亮需要 **1.0.1 或更新**，旧 v0.2.3 只有审计功能。实际发布状态、文件名、校验值与验收范围见在线 [仓库交付记录](https://github.com/klwb360/NetAudit/blob/main/DELIVERY.md)。

本项目审计了 [pynipper-ng](https://github.com/syn-4ck/pynipper-ng)，保留并改写其插件基类，重建了三厂商解析、审计规则和报告模块。来源、固定提交和改动见 [NOTICE](NOTICE)；审计详情见 [代码审计报告](docs/UPSTREAM_AUDIT.md)。项目采用 GPL-3.0-only。

## 最快开始

Windows 普通用户使用便携包：**下载 → 解压 → 双击 `Start-NetAudit.bat` → 导入备份 → 模拟练习 → 按需审计与导出**。单 EXE 下载后无需解压。便携 EXE 自带 Python 运行库，普通使用设计为无需管理员权限。下载方法、关闭与迁移说明见 [Windows 使用说明](docs/WINDOWS.md)。构建方法与实际验收边界见 [便携化记录](docs/PORTABILITY.md)。

将一份 UTF-8 配置文件拖入左侧文本区域，或使用“导入配置文件”；按内容自动识别四厂商，支持中文、空格及无扩展名文件。信息不足或混合厂商标记时提示手动选择。文件最大 2 MiB / 30000 行，每次一个文件，不支持文件夹；也可粘贴文本或“载入示例”。

顶部提供“明亮风格”“暗黑风格”和“跟随系统”，默认跟随系统，浏览器仅保存主题偏好。审计后同类风险默认折叠，保留各自对象、证据与建议；可以“展开全部”或“收起全部”。折叠和严重度筛选不影响完整报告。

原始备份和模拟命令区按已识别的语法显示底色与文字标签：**Cisco 蓝、华为橙、H3C 紫、锐捷绿**。多厂商共享的语法在“自动识别”选项下保持中性；指定兼容厂商后可按该厂商着色，并注明“共享语法”。未知行、普通注释和 banner 正文不据此猜测厂商。底色仅帮助读懂语法，不能证明命令安全或真实设备可执行；输入、复制及配置和报告导出不会加入颜色标记。长命令保持一行，左右滚动查看。详见 [高亮说明](docs/SIMULATOR.md#厂商底色高亮v101)。

源码版 Windows 也可双击 `Start-NetAudit.bat`，需要 Python **3.10 或更新版本**。BAT 会优先运行同目录的 `NetAudit.exe`，否则检测 Python。

需要 Python **3.10 或更新版本**。在仓库根目录进入本项目：

```bash
cd network-config-auditor
python -m netaudit serve
```

无参数运行 `python -m netaudit` 或双击 EXE，会启动网页并自动打开默认浏览器。`serve` 同样默认打开浏览器；使用 `python -m netaudit serve --no-browser` 可关闭此行为。默认访问 **http://127.0.0.1:8765**，端口占用时自动选择空闲端口，以启动窗口显示的实际地址为准。

默认进入“配置练习”。点击“载入模拟”，建立独立副本；中文目标点击“生成命令草案”后可“将草案放入命令区”，也可直接输入命令。点击“预览运行”，阅读理由与差异，再“应用本次预览”。审计是可选操作：点击“审查当前模拟配置”；未载入模拟时，“开始审计”直接检查左侧备份。关闭程序请回到启动窗口按 **Ctrl+C**；关闭网页标签页不会停止服务。迁移时复制整个解压文件夹。

Windows 通常可将 `python` 替换为 `py -3`；Linux/macOS 通常可替换为 `python3`。不安装依赖也可以直接运行。

```bash
# 生成单个中文目标的命令草案，不应用修改
python -m netaudit plan examples/cisco.cfg --vendor cisco --goal "创建 VLAN 20"

# 逐条指定命令，成功后另存配置；也可以使用 --commands commands.txt
python -m netaudit simulate examples/cisco.cfg --vendor cisco --command "configure terminal" --command "vlan 20" --command "end" --out reports/practice.cfg

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

## 配置模拟与中文目标

这是**离线配置状态模拟器**：它核对语法、命令视图及当前配置依赖，不连接设备，不模拟 ping、数据包转发、链路通断、STP 收敛或 OSPF 邻居。“可修改”不保证真实设备型号、固件、登录或业务支持；“尚不支持”只表示本工具没有实现该语法，不能判断实机不能运行。

练习范围包括 VLAN 创建/删除、已有接口的描述和管理启停、access/trunk VLAN、主 IPv4 地址、基础 ACL、默认 VRF IPv4 静态路由和部分 VTY / HTTP / SSH / STP 配置。练习范围小于下方解析范围，例如解析到 OSPF 或 NAT 并不代表能练习所有相关命令；当前视图的提示和 [模拟练习说明](docs/SIMULATOR.md) 给出具体边界。

中文草案由离线规则生成，不调用 AI；只接受一个明确目标，并用同一模拟器验证整份草案。可尝试 `创建 VLAN 20`、`把接口 GigabitEthernet0/1 加入 VLAN 20`、`关闭 HTTP`。接口必须使用备份中的完整名称，地址、掩码和下一跳需明确给出；缺少参数、含有条件或多个动作时会提示补充。本版不生成账号、密码或密钥修改草案。

一批命令中任何一条被阻止、参数错误或尚未支持，整批配置和视图变更都回滚。网页只有点击“应用本次预览”才改变副本；未应用的候选不参与导出和审计。原始备份不被覆盖，未知行和未改动原文保留。可撤销最多 20 步，历史总量不超过 16 MiB；重置恢复原始备份及执行视图。刷新、关闭页面或变更左侧原始输入会结束练习，请及时导出需要保留的配置。

CLI `simulate` 和 `plan` 都向本机标准输出写 JSON。`simulate` 可省略命令以查看初始状态；每批最多 200 行 / 64 KiB。`--commands` 命令文件与可重复的 `--command` 互斥。需要续练时，用上次已接受的 `config` 作为新输入，将上次 `context` 对象单独保存为 JSON 文件，再传入 `--context context.json`。`--out candidate.cfg` 仅在整批成功时原子写入配置，保留原有行尾，不允许覆盖输入资料；失败返回 2 且不写输出文件。`plan` 只有 `ready` 返回 0，其余待补充或不支持状态返回 2。

模拟 JSON 的 `config` 字段及导出 `.cfg` **保留原始凭据**，用于继续练习或保存完整备份；请勿放入公开日志或反馈中。显示与差异会遮蔽常见凭据，不能保证所有自定义字段均已脱敏。需要报告时，再对已导出的配置运行 `audit`；配置导出与 JSON / Markdown / HTML 审计报告是不同用途。

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

以下为解析与审计范围，模拟命令支持范围见上节与 [SIMULATOR.md](docs/SIMULATOR.md)。

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

网页服务只监听 `127.0.0.1`；校验 Host、Origin 和每次启动生成的会话令牌，不启用跨域读取。页面、样式、脚本均在本地，无第三方 CDN。默认练习和审计不请求外部情报和模型；显式 `intel-update` 才连接官方 CISA 数据源，显式 AI 才连接本机 Ollama。网页不会持久保存上传配置或练习历史，也不记录配置请求；用户导出配置或报告时会写入下载目录。

凭据在保留证据和清单前隐藏，HTML 输出使用转义，网页使用 `textContent`。自动脱敏覆盖常见 password/secret、SNMP community、key/key-string 和认证密钥语法；不保证识别所有自定义敏感字段。报告仍含地址、设备名和网络结构，应按内部配置资料保护。真实配置放在被忽略的 `configs/`，报告放在 `reports/`；仓库示例全部为合成数据。

资源限制：每份输入 2 MiB / 30000 行、512 个接口、每 ACL 256 条规则、总计 2048 条 ACL 规则。超限拒绝输出部分结果。模拟每批最多 200 行 / 64 KiB，中文目标最多 2000 字符；Web 处理请求使用最多 4 个并发名额。

## 验证

```bash
python -m unittest discover -s tests -v
node tests/vendor_syntax_cases.js
python tools/reproduce_upstream.py
```

测试覆盖四厂商解析、VLAN 范围与同类发现合并、命令前提和参数模板、ACL 覆盖顺序、NAT 选流语义、多个 VTY 范围、原始行号、脱敏、HTML 转义、CLI 退出码、文件权限及本地服务的来源/Host/令牌限制。v1.0.0 增加模拟视图、依赖阻止、整批回滚、原文保留、中文草案、API 和 CLI 验证；v1.0.1 增加前端语法归属分类用例，开发验证需 Node.js，普通运行无需安装。实际通过结果、环境与未实测范围以 [验证记录](docs/TESTING.md) 为准。上游复现脚本使用固定源码方法与只实现正则查询的解析替身，隔离复现三个已确认缺陷；不代表安装旧依赖后跑过完整上游程序。

新增规则可在 `netaudit/rules.py` 继承 `GenericPlugin`，并加入显式 `PLUGINS` 注册表。新增解析需补充能覆盖误报/漏报边界的 fixture 与测试。
