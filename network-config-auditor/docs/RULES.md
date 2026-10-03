# 审计规则目录

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

ACL 覆盖判断只处理已解析 IPv4 条件。非连续 wildcard 保留为原始范围，不强行转换 CIDR；仅相同 wildcard 文本可认作相同范围。time-range、established、对象组、ICMP 类型等额外条件会关闭该规则的覆盖与宽泛放通推断。Huawei/H3C ACL 的默认动作取决于应用功能与设备版本，报告不采用 Cisco 的统一 implicit deny 假设。

清单中的 `shutdown=null`、`mode=null`、`transport=null` 等表示输入未显式给出已识别设置，不表示启用/关闭。建议命令不含真实凭据。
