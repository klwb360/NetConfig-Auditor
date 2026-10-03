# 常见问题

面向 Windows 便携版用户。下载入口是 [最新 Release](https://github.com/klwb360/NetAudit/releases/latest)；文件、校验值与实测范围见 [下载与交付记录](../DELIVERY.md)。

## 如何下载并开始使用？

使用有访问权限的 GitHub 账号登录，在 [v0.1.0 发布页](https://github.com/klwb360/NetAudit/releases/tag/v0.1.0) 的 **Assets** 下载名称以 `-portable.zip` 结尾的文件，也可点击 [推荐便携 ZIP](https://github.com/klwb360/NetAudit/releases/download/v0.1.0/NetAudit-0.1.0-windows-x64-f2002b79bd6d-portable.zip)。解压一次，进入便携文件夹，双击 `Start-NetAudit.bat` 或 `NetAudit.exe`；在网页导入配置、选择厂商并开始审计。不要在 ZIP 预览窗口内运行。

普通使用无需下载 GitHub 自动生成的 “Source code”。Release 随附的 `*-source-*.zip` 是分发所对应的源码，供查阅、修改与重建。

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

当前实际验收在 Windows Server 2022 x64 完成。Windows 10/11、普通非管理员账户、物理上未安装 Python 的独立电脑及真实浏览器交互尚未实测；详见 [交付记录](../DELIVERY.md)。

## 配置文件如何准备，支持哪些设备？

一次导入一台设备的完整 UTF-8 配置。Cisco 使用 `show running-config`，华为/H3C 使用 `display current-configuration`；导出时去掉分页符、终端提示符和颜色控制字符。

支持 Cisco IOS/IOS XE、Huawei VRP、H3C Comware 的常见 IPv4 配置。华为和 H3C 共享不少语法，不能自动识别时请明确选择厂商。Cisco ASA/NX-OS、IPv6、复杂策略与完整动态路由语义等尚未完整建模，具体范围见 [项目说明](../network-config-auditor/README.md#支持范围)。

## 没有发现问题，是否说明配置安全？

审计仅覆盖当前解析能力和规则。`confirmed-config` 表示有配置证据，`needs-review` 表示需结合设备版本、拓扑或业务人工核对；未建模配置行也需检查。严重度筛选仅调整网页中展示的发现，完整报告仍用于整体复核。工具不会连接设备或下发建议命令。

## 配置会上传到哪里，报告如何保存？

配置在本机处理，网页只访问本机 `127.0.0.1`，上传内容不会持久保存到程序目录。点击 JSON、Markdown 或 HTML 导出，文件下载位置由浏览器决定。JSON 适合程序读取，Markdown 适合文档编辑，HTML 可用浏览器查看。

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
