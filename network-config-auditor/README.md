# NetAudit · 网络配置审计工具

输入一台 Cisco、华为或 H3C 交换机/路由器的完整配置，得到带原始行号的 **配置问题、安全风险、修改建议**，并查看接口、VLAN、路由、ACL、NAT 的结构化清单。提供中文本地网页与命令行，运行时仅使用 Python 标准库。

本项目审计了 [pynipper-ng](https://github.com/syn-4ck/pynipper-ng)，保留并改写其插件基类，重建了三厂商解析、审计规则和报告模块。来源、固定提交和改动见 [NOTICE](NOTICE)；审计详情见 [代码审计报告](docs/UPSTREAM_AUDIT.md)。项目采用 GPL-3.0-only。

## 最快开始

Windows 普通用户建议使用便携包：**下载 → 解压 → 双击 `Start-NetAudit.bat` → 导入配置 → 查看与导出**。便携 EXE 包自带 Python 运行库，无需安装 Python、配置开发环境或使用管理员权限。下载方法、关闭与迁移说明见 [Windows 使用说明](docs/WINDOWS.md)。构建方法与实际验收边界见 [便携化记录](docs/PORTABILITY.md)。

源码版 Windows 也可双击 `Start-NetAudit.bat`，需要 Python **3.10 或更新版本**。BAT 会优先运行同目录的 `NetAudit.exe`，否则检测 Python。

需要 Python **3.10 或更新版本**。在仓库根目录进入本项目：

```bash
cd network-config-auditor
python -m netaudit serve
```

无参数运行 `python -m netaudit` 或双击 EXE，会启动网页并自动打开默认浏览器。`serve` 同样默认打开浏览器；使用 `python -m netaudit serve --no-browser` 可关闭此行为。默认访问 **http://127.0.0.1:8765**，端口占用时自动选择空闲端口，以启动窗口显示的实际地址为准。

选择厂商，粘贴配置或导入 UTF-8 文本，点击“开始审计”。可先点击“载入示例”。界面支持严重度筛选、查看完整解析清单、导出 JSON / Markdown / HTML。关闭程序请回到启动窗口按 **Ctrl+C**；关闭网页标签页不会停止服务。迁移时复制整个解压文件夹。

Windows 通常可将 `python` 替换为 `py -3`；Linux/macOS 通常可替换为 `python3`。不安装依赖也可以直接运行。

```bash
# Cisco 样例 → HTML 报告
python -m netaudit audit examples/cisco.cfg --format html --out reports/cisco.html

# 华为配置 → 完整结构化 JSON
python -m netaudit audit examples/huawei.cfg --vendor huawei --format json --out reports/huawei.json

# H3C 配置 → Markdown 报告
python -m netaudit audit examples/h3c.cfg --vendor h3c --format md --out reports/h3c.md

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

## 配置如何取得

从设备导出完整运行配置：Cisco 使用 `show running-config`，华为/H3C 使用 `display current-configuration`。导出时关闭分页、去掉命令提示符/分页符/终端颜色转义，保存为 UTF-8 文本。一次输入一台设备，不要拼接多台配置。

厂商有独有语法时可自动识别。华为/H3C 有很多共享命令，只有 `sysname` 等共享语法时请明确选择厂商。混合厂商标记会拒绝自动猜测。

## 支持范围

| 类别 | Cisco IOS / IOS XE | Huawei VRP | H3C Comware |
|---|---|---|---|
| 接口 | 地址、secondary、VRF、shutdown、描述、switchport、ACL 绑定、NAT 角色 | 地址/sub、VPN 实例、shutdown、描述、link-type、ACL 绑定 | 地址/sub、VPN 实例、shutdown、描述、link-type、ACL 绑定 |
| VLAN | VLAN 定义，access/native，trunk 列表与 add/remove/except | vlan batch、default/PVID、allow-pass 与 undo | VLAN 定义、access/PVID、permit 与 undo |
| 静态路由 | ip route，VRF、下一跳、出接口、管理距离 | ip route-static、VPN 实例、下一跳、preference | ip route-static、VPN 实例、下一跳、preference |
| 动态路由 | OSPF/BGP/RIP 进程与配置原文 | OSPF/BGP 进程与配置原文 | OSPF/BGP 进程与配置原文 |
| IPv4 ACL | 数字/命名 standard/extended，any/host/wildcard，协议、基本端口条件、log | basic/advanced，rule 序号，source/destination、基本端口条件 | basic/advanced，rule 序号，source/destination、基本端口条件 |
| NAT | inside/outside、source list、pool、static 与 TCP/UDP 端口映射 | nat outbound、address-group、nat server | nat outbound、address-group、nat server |
| 管理面 | HTTP、SSH 参数、VTY、密码类型、community | HTTP、Telnet、VTY、密码类型、community | HTTP、Telnet、VTY、密码类型、community |

当前以常见 IPv4 配置为目标。Cisco ASA/NX-OS、IPv6、接口 range、ACL object-group、复杂 time-range/established、route-map/PBR、完整动态路由语义、USG 安全策略、现代 NAT 的全部变体尚未建模。动态路由子命令保留在清单并提示人工审查。

未建模行会出现在 `inventory.warnings`，最多展示 200 行，并保留实际总数。解析器识别行数表示识别的结构/命令范围，并非所有字段语义覆盖率。未知条件的 ACL 规则不参与覆盖推断，也不会直接判作 unrestricted permit；`match-order auto` 不进行遮蔽推断。审计不足不能当成“已安全”。

## 报告如何判断

- `confirmed-config`：有明确配置证据。实际影响仍依赖网络可达性与运行状态。
- `needs-review`：需结合版本、拓扑或业务目的核对，例如静态 NAT 映射、Trunk VLAN 范围、缺少来源 ACL。
- 严重度：`critical / high / medium / low / info`。详情见 [规则目录](docs/RULES.md)。
- NAT 选流 ACL 会单独标注，宽泛选流不会当成防火墙已放通。
- 各 VTY 段独立审查；安全段不会掩盖另一段 Telnet 或不认证配置。
- 同一前缀的多条静态路由可能是 ECMP/浮动路由，工具不会直接认定冲突。
- 建议命令是审阅模板；工具不会连接设备或下发配置。先核对 NOS 版本、业务和管理回退路径。

JSON 顶层含 `device`、`summary`、`findings`、`inventory`、`limitations`。每项发现包含 `rule_id`、`severity`、`problem`、`risk`、`recommendation`、`confidence`、`evidence` 和可选建议命令。证据行号从 1 开始，按照原始输入计数。

接口的 `allowed_vlan_ranges` 使用闭区间列表，例如 `[[10, 12], [20, 20]]` 表示 10、11、12、20；`[[1, 4094]]` 表示 all，`[]` 表示 none，`null` 表示没有已识别的显式允许列表。这样全 VLAN Trunk 不会使报告膨胀。

## 本地运行与配置保护

网页服务只监听 `127.0.0.1`；校验 Host、Origin 和每次启动生成的会话令牌，不启用跨域读取。页面、样式、脚本均在本地，无第三方 CDN。网页不会持久保存上传配置，也不记录配置请求；用户导出报告时会主动写入下载目录。

凭据在保留证据和清单前隐藏，HTML 输出使用转义，网页使用 `textContent`。自动脱敏覆盖常见 password/secret、SNMP community、key/key-string 和认证密钥语法；不保证识别所有自定义敏感字段。报告仍含地址、设备名和网络结构，应按内部配置资料保护。真实配置放在被忽略的 `configs/`，报告放在 `reports/`；仓库示例全部为合成数据。

资源限制：每份输入 2 MiB / 30000 行、512 个接口、每 ACL 256 条规则、总计 2048 条 ACL 规则。超限拒绝输出部分结果。Web 同时最多执行 4 个审计请求。

## 验证

```bash
python -m unittest discover -s tests -v
python tools/reproduce_upstream.py
```

测试覆盖三厂商解析、ACL 覆盖顺序、NAT 选流语义、多个 VTY 范围、原始行号、脱敏、HTML 转义、CLI 退出码、文件权限及本地服务的来源/Host/令牌限制。上游复现脚本使用固定源码方法与只实现正则查询的解析替身，隔离复现三个已确认缺陷；不代表安装旧依赖后跑过完整上游程序。

新增规则可在 `netaudit/rules.py` 继承 `GenericPlugin`，并加入显式 `PLUGINS` 注册表。新增解析需补充能覆盖误报/漏报边界的 fixture 与测试。
