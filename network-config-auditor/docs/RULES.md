# 审计规则目录

v0.2.0 保留原有 27 个规则 ID，新增 8 个 STP / OSPF 规则 ID，共 35 个配置规则 ID。CVE / KEV 与 AI 使用独立报告字段，不加入这 35 个 ID，也不改变原规则判断。

严重度评估的是配置中可见的问题或待核对风险。离线输入不能证明实时转发、设备可达性或完整合规。命令建议需核对具体 NOS 版本。

| 规则 ID | 默认严重度 | 触发条件 / 适用边界 |
|---|---|---|
| MGMT-CREDENTIAL | high | 显式明文、simple、type 0/7 或未标注保护类型的全局 password/secret |
| MGMT-SNMP-COMMUNITY | medium / high | community 配置；rw/write 权限提高到 high |
| MGMT-HTTP | high | 最后一条受支持命令显式开启 HTTP；关闭命令不会触发 |
| MGMT-TELNET-SERVER | high | 最后一条受支持命令显式开启 Telnet 服务器 |
| MGMT-VTY-TELNET | high | 每个 VTY 段单独检查 telnet/all 入站协议 |
| MGMT-VTY-NOAUTH | critical | no login / authentication-mode none；实际影响要求入站协议可用且可达 |
| MGMT-VTY-TIMEOUT | medium | 显式空闲超时为 0 或超过 900 秒 |
| MGMT-VTY-UNKNOWN | info | 缺少已识别的显式入站协议；不猜测设备默认值 |
| MGMT-VTY-SOURCE | low | VTY 未见受支持来源 ACL；需核对管理 VRF/上游防火墙 |
| MGMT-SSH-RETRIES | medium | 显式 SSH 认证重试次数 > 5 |
| MGMT-SSHV1 | high | 显式 ip ssh version 1 |
| PARSE-NUMBER | info | SSH 重试参数无法转换为整数 |
| ACL-UNDEFINED | high | 接口引用输入中不存在的 ACL；需核对输入完整性 |
| ACL-VTY-UNDEFINED | high | VTY 引用输入中不存在的 ACL |
| ACL-UNBOUND | info | 没有接口/VTY/NAT 引用；可能有未建模的 QoS/route-map 用途 |
| ACL-PERMIT-ANY | high / low | 完整识别的宽泛 IP permit；绑定过滤/管理为 high，NAT 选流/未见引用为 low；被已知前序覆盖时不报放通风险 |
| ACL-SHADOW | medium | 前序完整规则的协议、地址和端口条件完全覆盖后序规则；auto 排序不推断；只判断精确端口条件或不限端口 |
| VLAN-UNDEFINED | medium | access/native 引用未见 VLAN 定义（VLAN 1 例外）；需核对隐式/动态创建 |
| VLAN-TRUNK-ALL | low | 显式完整允许 VLAN 1–4094；需核对透传/堆叠业务 |
| VLAN-NATIVE-1 | low | 显式 native/PVID 为 1；需核对标签行为和业务基线 |
| VLAN-PVID-NOT-ALLOWED | info | 显式 PVID 不在显式允许列表；不同平台行为不同 |
| IF-DUPLICATE-IP | high | 同一 VRF 中多接口配置同一 IPv4 地址；anycast 等设计需复核 |
| ROUTE-SELF-NEXTHOP | high | 静态路由下一跳等于同一 VRF 内本机接口地址 |
| NAT-ACL-UNDEFINED | high | NAT 选流 ACL 未见定义 |
| NAT-POOL-UNDEFINED | medium | NAT 地址池引用未见定义 |
| NAT-INBOUND-MAPPING | medium | 完整解析的静态/服务器映射存在；不直接认定公网暴露 |
| PARSE-INCOMPLETE | info | 有未建模/格式错误行；缺少其他告警不代表安全 |
| STP-DISABLED | high | 全局、接口或 VLAN 的受支持语法显式关闭 STP；`confirmed-config` 仅确认配置，不确认存在环路 |
| STP-EDGE-TRUNK | medium | 非显式 shutdown / routed 接口同时配置 Trunk 与 edge / PortFast；服务器 Trunk 可能合法，`needs-review` |
| STP-BPDU-FILTER | high | 非显式 shutdown / routed 接口显式启用 BPDU 过滤；需核对连接对象与平台语义 |
| STP-BPDU-FILTER-DEFAULT | low | 全局启用默认 BPDU 过滤；与接口强制过滤分开，核对边缘识别与回退行为 |
| OSPF-ROUTER-ID | high | 显式 Router ID 不是有效的非零 IPv4 标识；不检查运行时自动选取的 ID |
| OSPF-DUPLICATE-ROUTER-ID | low | 同一 VRF 的不同本机进程显式共用 Router ID；独立 OSPF 域可能允许，需人工核对 |
| OSPF-BROAD-NETWORK | medium | 已识别连续 wildcard 的 Network 选择范围为 `/8` 或更宽；它选择接口，不等同于发布整个范围 |
| OSPF-AUTH-REVIEW | low | 对受支持的进程/区域/接口继承不能确认有效认证模式，或接口引用未见进程；仅 `needs-review`，不宣称邻居未认证 |

ACL 覆盖判断只处理已解析 IPv4 条件。非连续 wildcard 保留为原始范围，不强行转换 CIDR；仅相同 wildcard 文本可认作相同范围。time-range、established、对象组、ICMP 类型等额外条件会关闭该规则的覆盖与宽泛放通推断。Huawei/H3C ACL 的默认动作取决于应用功能与设备版本，报告不采用 Cisco 的统一 implicit deny 假设。

清单中的 `shutdown=null`、`mode=null`、`transport=null` 等表示输入未显式给出已识别设置，不表示启用/关闭。建议命令不含真实凭据。

## 同类发现与建议命令（v0.2.2 源码）

`VLAN-UNDEFINED` 按 VLAN ID 合并：同一 VLAN 只出现一项，列出全部关联端口和原始配置行；不同 VLAN 分开。同端口同时以 access / native 引用该 VLAN 时只计一个端口。已识别的批量 / 范围 VLAN 定义纳入检查；“输入未见定义”保持 `needs-review`，需先确认完整导出、VLAN 数据库或动态创建情况。

其他发现仅在白名单规则具有相同严重度、确认程度和整改条件时合并，例如多个端口的 native VLAN 1 或多个 VTY 段的同类设置。ACL 顺序、OSPF 进程 / 区域、NAT 映射和路由等独立问题保留各自发现。严重度与总数统计按合并后的发现计数，涉及处数单列；完整 `affected_objects`、`occurrences` 与证据不会丢失。

建议分为只读核查命令、已知参数的候选整改脚本、需要补齐参数的模板及适用前提。先核查设备版本和实际状态，再决定是否整改；`<参数名>` 不能原样执行。未知拓扑、业务地址、ACL 策略和密钥保留人工决策。工具不连接设备，不执行命令，也不自动保存配置。

## STP / OSPF 的离线边界

STP 支持三厂商的显式模式、边缘端口和 BPDU 设置，以及受支持的 `no` / `undo` 命令覆盖。Cisco 支持 VLAN 生成树启停；Huawei / H3C 支持全局与接口启停。没有启停命令保持未知，不能用版本默认值推断已关闭。缺少 BPDU Guard 不产生“一定未防护”的规则，实际根桥、拓扑与环路仍需运行状态验证。

v0.2.2 源码增加锐捷 RGOS 已支持语法的显式 `no spanning-tree` 判断；`switchport protected` 仅记录端口隔离，不用于证明 STP 安全。确认的关闭配置仍需结合型号、拓扑和 `show spanning-tree` 核对影响。

OSPF 以 IPv4 进程、VRF / VPN 实例、Router ID、区域、Network、接口绑定、passive / silent 接口与认证模式为范围。已识别的区域认证可被接口设置覆盖；完全被动的进程不会仅因无认证模式产生邻接风险推断。接口映射和缺失配置仍可能需要复核。认证模式存在不证明密钥有效、双方一致或邻居已建立。

非连续 wildcard 不强行转换 CIDR；未支持的 OSPF 细节、其他路由协议和复杂 STP 语法保留警告。八个新 ID 针对单设备输入，不能检查跨设备 Router ID 冲突、两端 VLAN 一致性或整个网络合规。

六域状态 `checked / needs-review / not-observed` 表示观察内容与检查覆盖。规则 `confirmed-config` 与情报 `cpe-version-match` 具有不同含义；后者需要产品版本和本地 NVD 条件，不证明当前设备已遭利用。详情见 [情报说明](INTELLIGENCE.md)和 [AI 说明](AI.md)。
