# NetAudit Windows 使用说明

1. **下载**：登录有权访问私人仓库的 GitHub 账号，打开 [最新 Release](https://github.com/klwb360/NetAudit/releases/latest)，在 **Assets** 下载名称含 `windows-x64` 和 `portable` 的 ZIP。各个正式版本的构建与验收记录保留在发布页；旧版 v0.2.0 与 v0.1.0 也保留下载。
2. **解压**：从 Release 下载的便携 ZIP **解压一次**，找到 `Start-NetAudit.bat` 与 `NetAudit.exe`。建议选择自己的桌面或文档文件夹；中文和带空格的路径均支持。不要在 ZIP 预览窗口内直接运行。
3. **双击**：打开解压后的文件夹，双击 `Start-NetAudit.bat` 或 `NetAudit.exe`。程序自动打开默认浏览器。若没有自动打开，复制启动窗口显示的 `http://127.0.0.1:端口` 地址到浏览器。
4. **导入配置**：点击“导入配置文件”，选择 UTF-8 的 `.cfg`、`.conf` 或 `.txt` 文件，选择 Cisco、华为或 H3C。也可粘贴配置，或先使用“载入示例”。
5. **查看与导出**：点击“开始审计”，查看发现、原始行号与建议，使用严重度筛选；点击 JSON、Markdown 或 HTML 下载报告。v0.2.0 增加 VLAN、STP、OSPF、ACL、NAT、Management Plane 的检查覆盖、情报状态与来源。

## 新版网页工作区

v0.2.1 界面优化版已发布。新版按“准备配置 → 开始审计 → 分区查看 → 导出报告”组织：

1. 顶部显示审计概览和入门提示。宽屏左侧导入或粘贴配置，选择厂商；“设备版本与本地情报”“本机 AI 辅助解释”是可选折叠项。
2. 点击“开始审计”，通过可见的操作 / 状态栏确认正在处理或已经完成。需要填写的问题会在此提示。
3. 在右侧页签查看“安全发现”“网络架构”“漏洞情报”“AI 建议”；在“安全发现”内筛选严重度，核对证据与建议。
4. 打开“报告与清单”查看未建模行、解析清单，并下载 JSON、Markdown 或 HTML；“使用帮助”提供输入、关闭和迁移提示。

窄屏会将输入与结果依次堆叠。切换页签或严重度只调整展示；修改配置、厂商、设备版本、情报或 AI 设置后，请重新点击“开始审计”，再查看与导出。配置不持久保存，刷新页面需要重新导入；默认审计不依赖云端服务，可选 AI 仍需自行运行本机 Ollama。

## 本地运行与便携使用

**情报与 AI**：默认使用随包 CISA KEV 离线快照，不联网。需要核对产品漏洞时，在网页导入精确设备信息和本地 NVD JSON；只有充分产品版本证据才确认匹配。用户可导入更新后的 KEV 文件；显式 CLI `intel-update` 才下载官方数据。AI 默认关闭，只有自行运行本机 Ollama 并明确填写已有模型名称后启用；未安装模型也能完成审计。模型解释仅供人审，不自动整改。详见 [情报说明](INTELLIGENCE.md)和 [AI 说明](AI.md)。

**关闭**：回到启动的命令行窗口按 Ctrl+C（或关闭该窗口）。关闭浏览器标签页不会停止程序。配置处理全部在本机完成，普通使用设计为无需管理员权限；首次访问可能需要几秒，尤其单 EXE 版本。

**迁移**：复制整个便携文件夹到另一台 Windows 电脑，继续双击使用。`_internal` 等运行库目录必须随 `NetAudit.exe` 一起复制；目标电脑不需要安装 Python。默认临时目录使用 Windows 用户临时目录，网页上传的配置不会保存到程序文件夹。导出报告请选择自己有写入权限的目录。

**单 EXE**：名称含 `windows-x64` 和 `onefile` 的 ZIP 内提供独立 `NetAudit.exe`，也有 BAT、示例、许可证及对应源码。该 EXE 可以单独运行；再次分发时请同时提供 ZIP 中的许可证、归属说明与对应源码。优先选择便携文件夹版本，启动更快，也便于排查问题。

**Actions 备份下载**：[Windows 构建列表](https://github.com/klwb360/NetAudit/actions/workflows/netaudit-windows.yml) 仍提供成功构建的产物，有保留期限。Actions 下载包含外层 ZIP，先解压外层，再解压其中 `portable.zip`；Release 直接提供内部 ZIP，只需解压一次。两种入口以对应清单的源码提交和 SHA-256 为准。

**校验下载**：产物中的 `SHA256SUMS.txt` 记录分发文件的 SHA-256；构建清单记录源提交与实际环境。可在 PowerShell 使用 `Get-FileHash .\文件名.zip -Algorithm SHA256` 对比。

**源码包提示 Python 缺失**：源码版 BAT 需要 Python 3.10 或更新版本；若不希望安装 Python，请按第 1 步获取成功构建的便携 EXE 包。无需安装 Git、pip 或 PyInstaller。

命令行使用示例（在便携文件夹中打开命令提示符）：

```bat
Start-NetAudit.bat serve --no-browser
Start-NetAudit.bat audit "D:\网络配置\设备.cfg" --vendor cisco --format html --out "D:\审计报告\设备.html"
NetAudit.exe audit "D:\网络配置\设备.cfg" --format json --out "D:\审计报告\设备.json" --fail-on high
```

传入参数时 BAT 不会暂停。退出码沿用 CLI：0 成功，1 达到指定严重度，2 输入/参数/文件错误或严格模式发现未建模行。审计结论仍需结合设备版本与业务核对，支持范围和 GPL-3.0-only 来源说明见 README、LICENSE 与 NOTICE。
