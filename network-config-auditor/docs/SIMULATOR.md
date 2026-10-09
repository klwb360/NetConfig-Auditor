# 配置模拟与学习练习

NetAudit v1.0.0 可以在导入备份的副本上练习命令，解释当前能否执行、会改变什么，以及下一步应做什么。支持 Cisco、华为、H3C、锐捷 RGOS 已建模的配置语法，处理在本机完成。

## 五步开始

1. 双击 `NetAudit.exe` 或 `Start-NetAudit.bat`，拖入一台设备的 UTF-8 备份，确认厂商后点击 **载入模拟**。
2. 在中文目标区输入一个明确目标，例如“把接口 GigabitEthernet0/1 加入 VLAN 20”，点击 **生成命令草案**。接口名需要与备份一致；也可直接在模拟命令行输入命令。
3. 将草案放入命令区，点击 **预览运行**，阅读每条结果、简短理由与配置差异。预览不会自动修改练习副本。
4. 确认可应用后点击 **应用本次预览**。可继续练习、撤销上一步、重置为原始备份，或导出模拟配置 `.cfg`。
5. 想检查风险时，主动点击 **审查当前模拟配置**，再查看并导出 JSON / Markdown / HTML 报告。生成草案、预览和应用都不会自动审计。

练习只保存在当前页面，关闭页面会清除；撤销最多 20 步，累计不超过 16 MiB。配置导出保留原文和凭据，请按敏感备份保管。页面差异和命令结果会脱敏。关闭浏览器不会关闭服务；回到启动窗口按 Ctrl+C 才会停止程序。

## 看懂结果

| 结果 | 意思 | 建议 |
|---|---|---|
| 已模拟 / 可应用 | 当前命令已建模，视图与配置前提满足 | 阅读差异，再应用到练习副本 |
| 只读查看 / 进入视图 / 无需修改 | 查看状态、切换视图，或配置已经符合要求 | 按当前视图继续练习 |
| 当前不能执行 | 存在配置依赖或冲突，例如引用未创建的 VLAN | 先完成提示的前置操作 |
| 参数错误 | 地址、掩码、VLAN 范围或格式不合法 | 修正参数后重新预览 |
| 暂不支持 | 本版尚未建模该命令，不能可靠判断 | 查设备文档；不要把它理解为设备一定不支持 |

**一批命令中只要有一条失败，整批配置和视图变化都会回滚。** 例如先创建 VLAN 20、再让端口引用不存在的 VLAN 999，会回到运行前状态，VLAN 20 也不会留下。未知的原配置按原文保留，未知的新命令不会写入候选配置。

“可应用”仅表示本工具的检查通过，不保证真实设备的型号、固件、授权和业务环境允许执行。

## 中文目标示例

每次提出一个目标，提供实际接口名、VLAN 和地址等参数。本版使用本地目标模板，并把生成的草案交给同一模拟引擎验证；无需模型或联网。信息不全时给出待补充的问题，不替你猜测业务参数。

- `创建 VLAN 20`
- `把接口 GigabitEthernet0/1 加入 VLAN 20`
- `把接口 GigabitEthernet0/1 设置为 trunk，允许 VLAN 10,20`
- `关闭接口 GigabitEthernet0/1`
- `给接口 GigabitEthernet0/1 配置 IP 地址 192.0.2.1/24`
- `添加静态路由 192.0.2.0/24 下一跳 198.51.100.1`
- `关闭 HTTP`

上例中的文档地址不能直接用于真实业务。二层接口配置 IP、删除仍被引用的 VLAN 等目标会被阻止，先按提示处理前提。复杂的多步骤业务要求应拆成几个单目标，逐步观察变化。

## 模拟命令行示例

下例用于备份中已存在 `GigabitEthernet0/1` 的 Cisco / 锐捷配置；已有三层地址或未知作用域等情况可能被阻止。

```text
configure terminal
vlan 20
exit
interface GigabitEthernet0/1
switchport mode access
switchport access vlan 20
end
show vlan brief
```

华为对应示例：

```text
system-view
vlan 20
quit
interface GigabitEthernet0/1
port link-type access
port default vlan 20
return
display vlan
```

H3C 的接入 VLAN 命令是 `port access vlan 20`。接口名以实际备份为准。每批命令最多 200 行 / 64 KiB，配置最多 2 MiB / 30000 行。当前视图中的“可以练哪些命令”会给出相应模板。

已支持的范围包括视图切换、VLAN 创建与有依赖检查的删除、已存在接口的描述 / 管理启停 / 二层模式 / VLAN / 静态 IPv4、部分 STP 配置、静态路由、有限 ACL 与绑定、有限管理服务与 VTY 配置。各厂商语法不同，以模拟器明确接受的形式为准；没有建模的语法拒绝修改。

它不模拟数据包转发、ping、物理链路、STP 收敛、OSPF 邻居、重启、性能或真实业务中断，也不连接设备。OSPF、NAT 等原有配置仍可交给原审计功能检查，但不代表本版提供相应协议的运行仿真。创建新物理接口、修改凭据和未建模的复杂配置需要另行核对设备能力。

## 在 Windows 命令行中使用

路径带中文或空格时加双引号；源码版把 `NetAudit.exe` 替换成 `python -m netaudit`。

```bat
NetAudit.exe plan "备份 配置.cfg" --vendor cisco --goal "把接口 GigabitEthernet0/1 加入 VLAN 20"
NetAudit.exe simulate "备份 配置.cfg" --vendor cisco --commands "练习 命令.txt" --out "候选 配置.cfg"
NetAudit.exe simulate "备份 配置.cfg" --vendor cisco --command "configure terminal" --command "vlan 20" --command "end"
NetAudit.exe audit "候选 配置.cfg" --vendor cisco --format html --out "审查 报告.html"
```

`plan` 仅生成草案；状态为 `ready` 时退出码为 0，其余为 2。`simulate` 输出 JSON，成功退出码为 0，失败批次为 2。省略命令可查看当前配置状态；`--context` 可读取上次结果中的 `context` 对象 JSON，继续指定视图。CLI 调用不会暂停等按键。

成功的 `--out` 才写出候选配置，保留原配置换行；失败不创建输出，也不覆盖已有输出。输出路径不得指向输入配置、命令文件或上下文文件。标准输出 JSON 的 `config` 字段和导出的 `.cfg` 都含原始敏感内容，收集日志时应按备份处理。CLI 不会自动调用审计，最后一条 `audit` 是显式选择。

## 验证与适用范围

Windows 构建须分别验证源码、onedir 和 onefile 的模拟 API、中文目标、完整网页资源、实际 CLI 子进程、批次回滚、原文保留及干净停服，发布器对 v1.0.0 起强制检查这些证据。是否完成实际构建、运行环境与未测试项，以该 Release 对应的 `manifest.json`、三份 `smoke-*.json` 及[验证记录](TESTING.md)为准。源码测试通过不等于 Windows EXE 验收通过。
