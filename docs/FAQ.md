# 常见问题

面向 Windows 便携版用户。当前正式版本为 v0.2.1；旧版 v0.2.0 与 v0.1.0 保留。下载入口是 [最新 Release](https://github.com/klwb360/NetAudit/releases/latest)；文件、校验值与实测范围见 [下载与交付记录](../DELIVERY.md)。

## 如何下载并开始使用？

使用有访问权限的 GitHub 账号登录，在 [v0.2.1 发布页](https://github.com/klwb360/NetAudit/releases/tag/v0.2.1) 的 **Assets** 下载名称以 `-portable.zip` 结尾的文件，也可点击 [推荐便携 ZIP](https://github.com/klwb360/NetAudit/releases/download/v0.2.1/NetAudit-0.2.1-windows-x64-befb38bbecbb-portable.zip)。解压一次，进入便携文件夹，双击 `Start-NetAudit.bat` 或 `NetAudit.exe`；在网页导入配置、选择厂商并开始审计。不要在 ZIP 预览窗口内运行。

普通使用无需下载 GitHub 自动生成的 “Source code”。两个运行 ZIP 内的 `*-source-*.zip` 是分发所对应的完整源码，供查阅、修改与重建；Release 已移除重复的独立源码附件，版本标签仍固定到构建提交。

## 为什么 Release 只剩三个运行附件？

v0.2.1、v0.2.0、v0.1.0 均保留 `portable.zip`、`onefile.zip` 和 `onefile.exe`，运行文件与原版本标签不变。校验文件 `SHA256SUMS.txt`、构建清单 `manifest.json` 和三份 `smoke-*.json` 验收报告永久保存在仓库 [发布档案](releases/README.md)，可按版本查看。原校验文件仍覆盖完整九文件构建产物，其中独立源码 ZIP 可从运行 ZIP 内取得。GitHub 自动生成的 “Source code” ZIP/tar.gz 无法单独隐藏。

## 新版网页如何查看结果？

先在配置区导入或粘贴文本并开始审计，再切换安全发现、网络架构、漏洞情报、AI 建议、报告与清单、使用帮助六个页签；窄屏按顺序堆叠配置与结果。严重度筛选和页签切换不会减少完整导出的内容。修改配置、厂商或情报/模型设置后，旧结果与导出会失效，需要重新审计；高级设置只在需要设备版本核对或本机 AI 时填写。

带截图的操作介绍见 [新版网页怎么用](../README.md#新版网页怎么用)。

## 为什么有的下载包需要解压两次？

从 Release 下载的便携 ZIP 只需解压一次。开发或备份使用的 [Windows Actions 产物](https://github.com/klwb360/NetAudit/actions/workflows/netaudit-windows.yml) 有外层 ZIP，需先解压外层，再解压其中的 `portable.zip`，才能找到 EXE。Actions 产物有保留期限；Release 下载仍需要私人仓库访问权限。

## portable 和 onefile 有什么区别？

| 版本 | 如何使用 |
|---|---|
| `portable.zip` | 推荐。解压后保留整个文件夹；`NetAudit.exe` 依赖同目录的 `_internal`，不能只复制 EXE。 |
| `onefile.zip` / `onefile.exe` | EXE 内含运行库，启动时会解压到用户临时目录，首次启动可能多等几秒。ZIP 还提供说明、示例、许可证和对应源码。 |

单 EXE 可以独立运行；再次分发时请同时提供许可证、归属说明与对应源码。源码 ZIP 用于查阅、修改和重建，普通使用无需解压源码。

## 需要安装 Python 或使用管理员权限吗？

便携 EXE 自带 Python 运行库；源码版 BAT 需要 Python 3.10 或更新版本。普通使用设计为无需管理员权限，报告请选择自己有写入权限的位置。

v0.2.1 在 Windows Server 2022 x64 完成 192 项单元测试与 28 项真实进程验收；Linux Chromium 65 项网页自动检查通过，Linux Python 3.10 / 3.12 / 3.13 检查通过。Windows 10/11、ARM64、普通非管理员账户、物理上未安装 Python 的独立电脑及 Windows 真实浏览器交互尚未实测；详见 [交付记录](../DELIVERY.md)。旧版 v0.2.0 的 192 项测试、28 项进程验收和 24 项网页检查保持历史记录。

## 配置文件如何准备，支持哪些设备？

一次导入一台设备的完整 UTF-8 配置。Cisco 使用 `show running-config`，华为/H3C 使用 `display current-configuration`；导出时去掉分页符、终端提示符和颜色控制字符。

支持 Cisco IOS/IOS XE、Huawei VRP、H3C Comware 的常见 IPv4 配置。华为和 H3C 共享不少语法，不能自动识别时请明确选择厂商。Cisco ASA/NX-OS、IPv6、复杂策略与完整动态路由语义等尚未完整建模，具体范围见 [项目说明](../network-config-auditor/README.md#支持范围)。

## 没有发现问题，是否说明配置安全？

审计仅覆盖当前解析能力和规则。`confirmed-config` 表示有配置证据，`needs-review` 表示需结合设备版本、拓扑或业务人工核对；未建模配置行也需检查。严重度筛选仅调整网页中展示的发现，完整报告仍用于整体复核。工具不会连接设备或下发建议命令。

## 六个架构领域的状态是什么意思？

VLAN、STP、OSPF、ACL、NAT、Management Plane 分别列出已观察到的配置、覆盖说明和相关规则。`checked` 表示已检查观察到的受支持内容；`needs-review` 表示有发现或相关未建模语法；`not-observed` 表示输入未观察到该领域。任何状态都不能证明实时拓扑、邻居或整个网络已安全。

STP 未写启停命令时保持未知，OSPF Network 是接口选择条件；工具不会将配置推断成当前根桥、邻居或实际路由状态。

## CVE / KEV 是否会自动联网，是否能确认设备已被入侵？

默认读取随包的 CISA 官方 KEV 离线快照，不联网。快照日期和来源可在报告中查看；它不是实时、完整的漏洞库。用户显式运行 `intel-update` 才下载官方 KEV，且不上传配置或设备信息。更新后的文件需通过 `--kev-file` 或网页本地导入使用。

KEV 表示相关漏洞在现实中已有利用记录，不表示当前设备受影响或已被入侵。需要精确产品 CPE、明确版本和本地 NVD CVE 2.0 数据才能核对适用性；未知版本、仅输入 CVE 编号或复杂条件保持待核对候选。没有匹配项不能证明不存在漏洞。格式和示例见 [情报说明](../network-config-auditor/docs/INTELLIGENCE.md)。

## AI 是否必须安装，会把配置发到云端吗？

AI 是可选解释功能。默认关闭，没有本机模型也能完成配置审计与报告导出。当前只支持本机 Ollama：自行安装、启动 Ollama 并准备模型后，在网页明确启用并填写模型名，或 CLI 使用 `--ai-model`。地址仅允许本机回环地址，不能配置远程云端服务。

规则自带的风险与建议来自确定性审计，不称作 AI 输出。AI 解释不能新增已确认漏洞、改变规则严重度或替代人工复核；请求失败会在报告标记原因，并保留规则和情报结果。实际发送字段、模型输出和本机模型验收范围见 [AI 说明](../network-config-auditor/docs/AI.md)。

## 配置会上传到哪里，报告如何保存？

配置在本机处理，网页只访问本机 `127.0.0.1`，上传内容不会持久保存到程序目录。显式开启 AI 后才调用本机模型，显式更新 KEV 才访问官方数据源。点击 JSON、Markdown 或 HTML 导出，文件下载位置由浏览器决定。JSON 适合程序读取，Markdown 适合文档编辑，HTML 可用浏览器查看。

报告包含设备名、地址和网络结构；常见凭据会脱敏，但不能保证识别所有敏感字段。请按内部配置资料保护，公开反馈问题时使用合成或人工脱敏的样例。

## 如何关闭，如何迁移到另一台电脑？

回到启动的命令行窗口按 Ctrl+C。关闭浏览器标签页不会停止服务。下次运行请使用启动窗口显示的地址；端口被占用时地址可能变化。

迁移便携版时复制整个解压文件夹，包括 `_internal`；用户自行保存的配置和报告也需另外复制。程序文件夹可以位于只读位置，运行所需临时数据使用用户临时目录，导出位置仍需可写。

## 能否只用命令行，不打开浏览器？

可以。在便携文件夹中打开命令提示符：

```bat
Start-NetAudit.bat serve --no-browser
NetAudit.exe audit "D:\网络配置\设备.cfg" --vendor huawei --format html --out "D:\审计报告\设备.html"
```

传入参数时 BAT 不会暂停。三种报告格式参数为 `json`、`md`、`html`；完整用法见 [项目说明](../network-config-auditor/README.md#最快开始)。遇到问题请看 [故障排查](TROUBLESHOOTING.md)。
