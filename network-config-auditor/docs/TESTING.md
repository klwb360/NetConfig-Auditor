# 验证记录

## 已交付版本验收（2026-10-03）

独立仓库的已验收构建对应源码提交 `16fb4254150f0cfd48014b3b628efc805dec0095`；后续文档提交不改变该次 EXE 对应的源码。

| 环境与检查 | 结果 | 证据 |
|---|---|---|
| Windows Server 2022 10.0.20348 AMD64；Python 3.12.10 x64、PyInstaller 6.22.3；runner image 20260927.320.1 | 78 项单元测试、25 项实际进程验收通过（源码 9、onedir 8、onefile 8） | [Windows 构建 37101723226](https://github.com/klwb360/NetAudit/actions/runs/37101723226) |
| Linux；Python 3.10 / 3.12 / 3.13 | 三个版本的 CI 检查全部通过 | [Linux 构建 37101723192](https://github.com/klwb360/NetAudit/actions/runs/37101723192) |

Windows 验收覆盖三厂商、三种报告、中文与空格路径、BAT/CLI 退出码及无暂停、端口冲突回退、完整网页资源、无参数启动和浏览器调用、只读应用目录、退出后无遗留服务，以及 onefile 临时目录清理。下载后还核对了外层 ZIP 和所有产物 SHA-256、ZIP CRC、包内文件哈希、Windows x64 PE、对应源码与许可证。文件名、下载入口和校验值见 [交付记录](https://github.com/klwb360/NetAudit/blob/main/DELIVERY.md)。

冻结版进程通过移除 Python 相关环境变量并限制 PATH，验证使用随包运行库；构建 runner 本身仍安装 Python。这不能等同于物理无 Python 电脑的实测。普通非管理员 Windows 账户、Windows 10/11、ARM64、资源管理器真实双击、系统默认浏览器可视交互及文件选择/下载对话框尚未实测。真实设备型号、软件版本和转发行为也未验收。

## 原版基线（2026-10-02）

以下为便携化前的历史记录：执行环境 Python 3.12、Linux，67 项测试通过；该交付版本的完整测试集结果见上表；后续提交的测试数量和结果以对应 CI 运行记录为准。

| 检查 | 结果 | 覆盖内容 |
|---|---|---|
| `python -m unittest discover -s tests -v` | 67 项通过 | 三厂商解析、VLAN、路由、ACL、NAT、VTY、证据行号、缺失默认值处理、误报边界、脱敏、HTML/Markdown 转义、CLI、本地 HTTP API |
| `python tools/reproduce_upstream.py` | 3 项通过 | HTTP 关闭命令误判、SSH 字符串比较 TypeError、跨 VTY 段的 Telnet 漏报，均使用固定方法摘录与解析替身 |
| `python -m compileall -q netaudit` | 通过 | Python 语法 |
| `node --check netaudit/web/app.js` | 通过 | 网页脚本语法 |
| 标准 setuptools wheel 构建与隔离导入 | 通过 | 纯 Python wheel、本地静态资源入包、命令行模块可加载 |
| 三厂商样例 CLI 导出 | 通过 | JSON/Markdown/HTML 报告、清单和密码隐藏 |

测试中的 HTTP 服务仅监听测试机回环地址，检查非法 Host、跨域 Origin、缺失令牌、异常 JSON、路径穿越及正常审计导出。无需第三方服务、真实配置或设备账号。

基线执行环境没有可用浏览器二进制，网页验证采用脚本语法、静态资源响应与 HTTP API 集成测试。该记录只代表当时的本地 Python 3.12 检查；后续 Python 3.10/3.12/3.13 的 CI 成功记录见上表。

CI 使用只读仓库权限，checkout 和 setup-python 固定为检索时核实的提交 SHA。运行测试、上游隔离复现和 wheel 构建，不导出真实网络配置到构建日志。
