# 网络配置审计项目选型与代码审计

审计日期：2026-10-02。目标：在现有项目审计基础上，改写支持华为、Cisco、H3C 交换机/路由器配置的离线审计工具。

## 项目比较

| 项目 | 已核实能力 | 许可证 / 适用情况 | 本次使用 |
|---|---|---|---|
| [syn-4ck/pynipper-ng](https://github.com/syn-4ck/pynipper-ng) | 离线配置弱项规则、HTML/JSON 报告，审计版本设备枚举仅 Cisco IOS | GPL-3.0；与审计报告目标接近，解析和判断需要重写 | 选为代码审计与改写来源 |
| [netdevops/hier_config](https://github.com/netdevops/hier_config) | 配置层级树、查询、比较与变更生成，README 列出 IOS、VRP、H3C/Comware | MIT；适合配置差异与未来精细解析 | 阅读 README/许可证；未进行完整源码审计、未引入依赖 |
| [mpenning/ciscoconfparse](https://github.com/mpenning/ciscoconfparse) | 分层配置查询、解析、修改；上游 pynipper 依赖它 | 页面标注 GPL 系列许可；需要自行编写语义规则 | 功能比较；未做完整源码审计 |
| [Tes3awy/cisco-config-auditor](https://github.com/Tes3awy/cisco-config-auditor) | 面向 Cisco IOS XE 的配置审计 | 仓库可见 LICENSE；本次未按其代码衍生 | 检索候选与目录检查 |

没有把上述比较候选视作已全部安全审计。检索只能确认本次找到的项目，不能证明 GitHub 不存在完整三厂商替代工具。

## 固定审计对象与方法

**pynipper-ng 提交：`58957659205bcf656f1f209b26be51d1d508b9f9`**。

读取其配置解析、HTTP/SSH 插件、插件装载、报告生成与 HTML 模板、设备类型、依赖、setup、CLI、README 和许可证。缺陷位置与下表对应固定提交；即使上游将来更新，仍可复核。

执行 `python tools/reproduce_upstream.py` 可隔离复现 U-01～U-03。复现使用固定方法摘录、正则查询解析替身及已知返回值；未安装旧依赖，未运行完整上游程序或连接真实设备。复现说明控制流/类型问题，不替代上游全量动态测试。

## 发现与改写

| 编号 | 影响等级 | 固定源码位置 | 确认方式与影响 | 改写处理 |
|---|---|---|---|---|
| U-01 | high，审计正确性 | `src/analyze/cisco/ios/plugins/http_plugin.py:13–22` | `_has_http` 先查非锚定 `ip http server`，该正则也匹配 `no ip http server`；禁用服务被误报开启；隔离复现成功 | 精确匹配受支持启/停命令，采用最终显式状态，不猜测缺失默认值 |
| U-02 | high，可用性 | `src/analyze/cisco/ios/plugins/ssh_plugin.py:48–68` | 解析重试次数返回 str，随后与 int 5 做 `>` 比较；配置值为 `3` 时触发 TypeError；隔离复现成功 | 显式整数转换与错误处理，添加有效/无效数值回归 |
| U-03 | high，漏报 | `src/analyze/cisco/ios/cisco_parser/parse_config.py:121–129`；SSH 插件亦有全局查询 | 任一 VTY 存在 SSH-only 即全局判定未启用 Telnet，掩盖其他 VTY 的 Telnet；隔离复现成功 | 将每个 VTY 配置块作为独立对象审计 |
| U-04 | medium，报告信任边界 | `src/report/templates/html_template.html` | HTML 报告加载 HTTP 第三方 jQuery；远程资源改变或链路被篡改可影响报告。`vuln.summary|safe` 还对外部漏洞摘要跳过转义；未证明可从本地 hostname 注入 | 本地资源、HTML 转义、CSP、网页 textContent；移除外部漏洞信息加载 |
| U-05 | medium，误报与故障 | `src/analyze/cisco/ios/plugins/http_plugin.py:37–45,81–90` | HTTP access-class 被强制转换为 int，命名 ACL 有 ValueError 风险；相关子检查不以 HTTP 启用为前提 | ACL 用字符串标识，按实际绑定分析；管理服务仅在明确启用时报告 |
| U-06 | medium，结果可靠性 | `src/analyze/cisco/ios/cisco_parser/parse_config.py:26–41` | 不完整版本主动补 `(1)`，可能让漏洞关联采用未经配置证实的版本 | 首版不做 CVE 自动断言；版本与实时状态需另行确认 |
| U-07 | medium，维护性/供给链 | `requirements.txt`、`setup.py` | 固定旧 Jinja2/requests/CiscoConfParse 等，setup 依赖 pip 私有内部 API；未执行 SCA，因此不报未经核实的具体 CVE | 标准库运行时，setuptools 常规打包，无动态外部插件导入 |
| U-08 | medium，证据质量 | 解析/插件/issue 数据结构 | 各检查重复读取配置，问题未附原始行号；有限的 Cisco-only 设备枚举不能直接满足三厂商清单需求 | 一次解析为 IR，逐项保留原始行号，列出未建模行，补齐三厂商基础语法 |

`src/report/report.py` 本身开启 Jinja2 自动转义，因此不能将所有配置字段都说成存在 XSS。U-04 只针对明确外部脚本/`safe` 位置与信任边界。动态插件导入来自安装包目录，未证实配置文件能让攻击者任意执行 Python，不报告这种推测漏洞。

## 改写后的范围与自查

保留并修改 GPL 插件基类接口，其余实现为新的标准库模块。三厂商统一清单、证据、严重度、判断置信度、修改建议、中文网页和 CLI。ACL 绑定类型区分过滤、VTY 和 NAT 选流；仅明确条件参与覆盖判断。GPL 全文和作者来源保留在 LICENSE、NOTICE 与源码头部。

输入视为不可信文本，不执行命令，不解释用户提供的 Python，不加载用户提供的插件，不连接设备。网页限定本机回环，Host/Origin/令牌校验，无跨域放开；输入资源有上限，密码先隐藏再保留到报告；导出 HTML 转义、文件原子写入及输入覆盖保护。

功能与安全边界测试见 [测试说明](TESTING.md)。真实设备型号/软件版本的完整配置与转发行为未做实机验证；未知语法与动态路由子命令需人工复查。首版不声称 CIS/STIG 全量合规、CVE 扫描或任意 NOS 版本兼容。

## 主要参考

- [pynipper-ng 固定提交](https://github.com/syn-4ck/pynipper-ng/tree/58957659205bcf656f1f209b26be51d1d508b9f9)
- [hier_config README](https://github.com/netdevops/hier_config) 与 MIT LICENSE
- [Cisco NAT 配置说明](https://www.cisco.com/c/en/us/td/docs/ios/12_4t/ip_addr/configuration/guide/htaddrs.html)
- [Huawei traffic-filter 命令](https://info.support.huawei.com/hedex/api/pages/EDOC1100334321/AEM1020X/05/resources/dc/traffic-filter_interface_view.html)
- [Huawei nat outbound 命令](https://info.support.huawei.com/hedex/api/pages/EDOC1100277378/AZL1115J/07/resources/dc/nat_outbound.html)
- [Huawei port trunk allow-pass vlan 命令](https://info.support.huawei.com/hedex/api/pages/EDOC1100210438/AEK0901G/09/resources/dc/port_trunk_allow-pass_vlan.html)
- [H3C NAT 配置示例](https://zhiliao.h3c.com/EnclosureTechDoc/ziliao/16163219914605.pdf)

厂商参考仅用于核对所支持命令；平台间默认动作、资源约束及变更方法仍需对应型号手册。
