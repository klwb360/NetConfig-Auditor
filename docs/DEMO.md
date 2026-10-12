# 离线演示脚本

演示约 8–12 分钟，在仓库根目录进入 `network-config-auditor`。以下 `python` 应为 Python 3.10 或更新版本；项目实现验收使用 Python 3.12。所有操作只读取配置或写入单独报告/练习副本，不连接设备，不执行情报更新，也不启用 AI。

## 1. 先预测一份配置（约 2 分钟）

打开 `benchmarks/configs/huawei-07-vlan-undefined-risk.cfg`，让参与者指出主机名、上联 IPv4 地址、学生端口及其 VLAN。预期学生端口引用 VLAN 30，当前输入没有 VLAN 30 定义。

```powershell
python -m netaudit audit benchmarks/configs/huawei-07-vlan-undefined-risk.cfg --vendor huawei --format md --out reports/demo-vlan.md
python -m netaudit audit benchmarks/configs/huawei-08-vlan-undefined-control.cfg --vendor huawei --format json --out reports/demo-vlan-control.json
```

打开两个报告，核对 `VLAN-UNDEFINED` 的对象及证据。风险例出现该规则，控制例因为已有受支持的定义而不出现。解释“输入未见定义”和“设备运行时不存在”之间需要哪些证据。

## 2. 说明未知条件（约 2 分钟）

```powershell
python -m netaudit audit benchmarks/configs/cisco-18-acl-shadow-control.cfg --vendor cisco --format json --out reports/demo-unknown.json
```

展示 `established` 所在原始行、`warnings` 与 `PARSE-INCOMPLETE`。解析器不能完整解释该 ACL 条件，应停止相应遮蔽推断。让参与者回答：没有 `ACL-SHADOW` 为什么不能证明策略完整或安全？

可运行严格模式展示退出码：

```powershell
python -m netaudit audit benchmarks/configs/cisco-18-acl-shadow-control.cfg --vendor cisco --strict --format md --out reports/demo-strict.md
```

该已知未知例应保存报告并返回 2。严格模式拒绝把未建模行当作完整成功，不删除已有报告。

## 3. 在副本里练习（约 2 分钟）

```powershell
python -m netaudit plan examples/huawei.cfg --vendor huawei --goal "创建 VLAN 99"
python -m netaudit simulate examples/huawei.cfg --vendor huawei --command "system-view" --command "vlan 99" --command "quit" --out reports/demo-practice.cfg
```

展示命令草案与模拟差异，再确认原始 `examples/huawei.cfg` 保留。完整练习导出是配置副本，可能含原输入敏感内容；审计报告采用脱敏输出。草案验证和模拟成功只说明本模拟器支持该练习，不宣称设备会接受或业务能转发。

如果参与者想用网页，可以运行 `python -m netaudit serve`，在本机界面导入同一备份并练习；不需要设备地址和登录凭据。页面操作属于人工演示项，不能把 CLI 检查当作浏览器验收已完成。

## 4. 看批量结果（约 1 分钟）

```powershell
python -m netaudit audit-batch examples --out-dir reports/demo-batch
```

打开 `reports/demo-batch/batch.html` 与 `batch.json`，展示逐文件结果、严重度和错误隔离。这个批量命令使用自动厂商识别，与金标准中清单显式指定厂商的评价口径不同；短配置的厂商不能可靠区分时，需要核对或显式指定。

## 5. 运行独立验收（约 2 分钟）

```powershell
python -m unittest discover -s tests -p test_acceptance_metrics.py -v
python tools/benchmark_acceptance.py --out reports/acceptance.json
```

展示清单中的 Cisco18/Huawei16/H3C16 和 25 个正反风险配对，说明 expected 是独立人工写下的语义值。先看字段分母与风险 TP/FP/FN，再看 recall、未知匹配和逐例原文。

报告阈值固定为字段准确率 95%、风险 precision 90%；不能因失败而删样例或降阈值。无数据分母的 precision/recall 为 `null`，不显示虚假的 100%。模块中 OSPF 进程字段为范围外，其 `fields` 是 `null`；不能借风险例通过宣称所有 OSPF 字段都已验收。

首次数据实测字段与风险指标均为 100%，只说明这组人工合成、支持范围内的片段结果。未知提示可以单列存在，当前 H3C 路由描述参数可能被保守标记为未完整建模；查看报告实际结果，不把演示材料中的历史数字当作最新测量。

## 演示验收记录

| 项目 | 自动可验证 | 人工/设备步骤 |
|---|---|---|
| 配置字段与风险 | 金标准及计分测试 | 解释配置业务原意 |
| 报告与 CLI | 输出文件、JSON 内容、退出码 | 可读性与演讲流程 |
| 网页 | 另行浏览器验证 | 上传、练习、审计、主题体验 |
| 批量 | 逐文件结果、错误隔离 | 实际目录与命名习惯 |
| 设备运行 | 本演示未执行 | 型号版本、命令接受、转发表和流量 |

演示时据实填写已完成与未执行项。不要把单元测试、CLI 演示或合成配置验收说成真实设备端到端验证。
