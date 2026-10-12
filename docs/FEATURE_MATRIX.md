# v1.1.0实际功能完成度矩阵

状态按代码、测试与固定验收证据判断。已实现仅指明确支持范围，不包含所有固件语法；目前未发现剩余P0/P1代码缺陷，已知未覆盖项单列。

| 目标 | 实际状态 | 可复用代码/证据 | 后续优先级 |
|---|---|---|---|
| Huawei/H3C/Cisco识别、指定厂商 | 已实现并验证，锐捷扩展保留 | parser.py、vendor-detection测试、50gold | P1增加版本变体 |
| 单文件/批量导入、编码 | CLI已实现并验证；GUI单UTF8 | config_io.py、batch.py、cli.py，编码与批量测试，冻结50文件 | P2网页复用 |
| Interface/IP/VLAN/Trunk | 基础语法已实现并验证 | model.py/parser.py，按模块gold字段计分 | P1复杂语法与IPv6 |
| 静态Route | 基础已验证；扩展部分支持 | complete/unparsed_tokens、28完整性测试、partial-route显示 | P1补VRF等 |
| ACL | 基础解析/绑定/审计已验证；复杂策略部分 | parser.py、rules.py、已有规则测试及正反gold | P1复杂绑定与对象组 |
| NAT | 基础映射已验证；扩展部分支持 | server/outbound、H3C undo、未知参数保留和307相关回归 | P1接口地址/服务名/VRF |
| SSH/Telnet/SNMP等管理面 | 已实现并验证 | model/parser/rules、已有测试及gold | P1更复杂基线 |
| 统一数据模型 | 已实现并兼容，dataclass复用 | model.py、单文件报告schema保持 | 不为Pydantic重复开发 |
| 安全规则引擎>=20 | 已实现并验证；现有35 ID复用 | rules.py/architecture.py，25风险规则gold正反配对 | P1扩大独立样本 |
| 编号/严重度/依据/证据/建议/状态 | 已实现并验证 | 报告与规则测试，文件及原行追溯 | P1证据复杂案例 |
| JSON/HTML及统计 | 单/批已实现并验证，MD保留 | reports.py/batch.py，HTML转义与失败隔离测试 | P2网页批量导航 |
| 未知语法/解析覆盖 | 已实现并验证；扩展持续需复核 | warnings/needs-review、strict exit2、unknown单列 | P1未知变体 |
| CLI/Web | 既有CLI/Web复用，新CLI批量已验证 | cli.py/server.py/web资源，28进程检查 | P2网页多编码/批量 |
| PyInstaller/Windows EXE | 已发行并实际运行验证；人工桌面环境待验收 | 正式1.1.0，28进程+独立runner6检查，本机Win11两模式50gold | P0补人工环境 |
| pytest/覆盖/CI | 已实现并验证 | Windows471+506、Linux470+1skip+506、工具74；综合91.41% | 持续保持门槛 |
| >=50配置量化评估 | 已实现并验证，限定合成支持范围 | benchmarks/50cfg+独立expected，1870/1870 TP26 FP0 FN0 | P1真实变体 |
| 408笔记/架构/演示/复试问答 | 已实现 | LEARNING_408、ARCHITECTURE、DEMO、24答题 | 持续积累 |
| SQLite/FastAPI/TextFSM/Pydantic/YAML | 未采用；属于后续选型 | 现有离线模型/regex/stdlib服务器满足本轮目标 | P2有具体需求再选 |
| 阶段1—5 | 基线、三厂商核心、规则、NAT管理面、批量报告和测试已交付 | 检查点01—05及gold/CI | 无需从零重复 |
| 阶段6 | 工程化/EXE/文档/公开发行已交付，人工验收保留 | 正式Release、检查点06、永久档案 | P0桌面验收 |

代码位于 `network-config-auditor/netaudit/`，测试位于 `network-config-auditor/tests/`，发行工具位于 `tools/`。详细证据见[正式发行档案](releases/v1.1.0/README.md)、[最终运行汇总](acceptance/v1.1.0/final-main/)和[验收口径](ACCEPTANCE.md)。指标阈值没有降低，未知语法没有被隐藏或认定为安全。
