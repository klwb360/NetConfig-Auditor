# 验证记录

日期：2026-10-02。执行环境：Python 3.12，Linux。

| 检查 | 结果 | 覆盖内容 |
|---|---|---|
| `python -m unittest discover -s tests -v` | 67 项通过 | 三厂商解析、VLAN、路由、ACL、NAT、VTY、证据行号、缺失默认值处理、误报边界、脱敏、HTML/Markdown 转义、CLI、本地 HTTP API |
| `python tools/reproduce_upstream.py` | 3 项通过 | HTTP 关闭命令误判、SSH 字符串比较 TypeError、跨 VTY 段的 Telnet 漏报，均使用固定方法摘录与解析替身 |
| `python -m compileall -q netaudit` | 通过 | Python 语法 |
| `node --check netaudit/web/app.js` | 通过 | 网页脚本语法 |
| 标准 setuptools wheel 构建与隔离导入 | 通过 | 纯 Python wheel、本地静态资源入包、命令行模块可加载 |
| 三厂商样例 CLI 导出 | 通过 | JSON/Markdown/HTML 报告、清单和密码隐藏 |

测试中的 HTTP 服务仅监听测试机回环地址，检查非法 Host、跨域 Origin、缺失令牌、异常 JSON、路径穿越及正常审计导出。无需第三方服务、真实配置或设备账号。

真实设备/转发行为、不同型号与软件版本、浏览器视觉及端到端点击流程尚未验收。当前环境没有可用浏览器二进制，网页验证采用脚本语法、静态资源响应与 HTTP API 集成测试。Python 3.10/3.13 的运行结果以 GitHub Actions 为准，不能将本地 Python 3.12 结果等同全部版本已验证。

CI 使用只读仓库权限，checkout 和 setup-python 固定为检索时核实的提交 SHA。运行测试、上游隔离复现和 wheel 构建，不导出真实网络配置到构建日志。
