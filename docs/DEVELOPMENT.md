# 开发与构建

NetAudit 的源码在 [`network-config-auditor/`](../network-config-auditor/)。运行时只使用 Python 标准库，需要 Python **3.10 或更新版本**；安装 Python 包、Node.js 或 PyInstaller 都不是普通源码运行的前提。模块职责见 [架构说明](ARCHITECTURE.md)。

## 获取源码与开发环境

```bash
git clone https://github.com/klwb360/NetConfig-Auditor.git
cd NetAudit/network-config-auditor
python -m venv .venv
```

私人仓库需要当前账号具备读取权限。Windows 可使用 `py -3`，Linux/macOS 可使用 `python3` 创建虚拟环境。随后激活环境：

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# Linux / macOS
source .venv/bin/activate
```

也可直接调用虚拟环境中的 Python，无需激活。以下命令都在 `network-config-auditor/` 中执行：

```bash
# 无参数启动本地网页并打开浏览器
python -m netaudit

# 保持服务运行，不自动打开浏览器
python -m netaudit serve --no-browser

# 用明确的中文目标生成草案，不应用修改
python -m netaudit plan examples/cisco.cfg --vendor cisco --goal "创建 VLAN 20"

# 模拟命令并另存成功的候选配置
python -m netaudit simulate examples/cisco.cfg --vendor cisco --command "configure terminal" --command "vlan 20" --command "end" --out reports/practice.cfg

# 使用合成配置导出报告
python -m netaudit audit examples/cisco.cfg --vendor cisco --format json --out reports/cisco.json
```

服务只监听 `127.0.0.1`，默认端口 8765。端口不可用时会显示另一个实际地址；按 Ctrl+C 关闭服务。若希望使用 `netaudit` 命令，可选安装开发入口：

```bash
python -m pip install -e .
netaudit --help
```

Editable 安装会使用 `pyproject.toml` 中的 setuptools 构建后端，可能需要下载构建工具；程序本身没有第三方运行依赖。真实配置放在被忽略的 `configs/`，导出报告放在 `reports/`。提交测试用例前使用合成数据，并检查凭据、地址和设备名是否需要替换。

## 修改后的验证

```bash
python -m unittest discover -s tests -v
python tools/reproduce_upstream.py
python -m compileall -q netaudit
```

单元测试覆盖解析、规则、报告、CLI、本地 HTTP API 和便携启动，以及 STP / OSPF 的显式与未知状态、CPE 版本适用性、KEV 来源与输入限制、AI 失败降级和统一审计流程。v1.0.0 增加模拟视图、依赖阻止、整批回滚、原文保留、中文目标、API 与 CLI；具体通过结果以 [TESTING.md](../network-config-auditor/docs/TESTING.md) 为准。AI 协议替身不等于真实模型或桌面交互验收。HTTP 集成测试需要环境允许监听回环地址；若沙箱禁止创建 socket，应记录限制，不能将跳过的检查算作通过。上游复现脚本只隔离复现三个固定缺陷，不代表运行过完整上游程序。

修改网页 JavaScript 后，若已安装 Node.js，可检查语法：

```bash
node --check netaudit/web/app.js
node --check netaudit/web/simulator.js
```

Node.js 仅用于这项检查。Python 包构建可使用：

```bash
python -m pip wheel . --no-deps --wheel-dir dist
```

Wheel 构建仍会安装隔离的构建依赖；检查 wheel 中包含 `netaudit/web/index.html`、`app.js`、`simulator.js`、`style.css`，以及 `netaudit/data/` 中的 KEV 快照与来源/许可资料。这一结果验证 Python 包，不验证 Windows EXE。历史验证记录见 [TESTING.md](../network-config-auditor/docs/TESTING.md)，已交付构建的环境、结果和限制见 [DELIVERY.md](../DELIVERY.md)。

网页使用原生 HTML、CSS 和 JavaScript，审计沿用报告 schema 1.1。修改布局或交互后，核对主题、六页签的 ARIA、键盘焦点、宽窄屏布局、输入保留、真实下载，以及输入更改后旧结果不可导出的行为。v1.0.0 还需检查默认不审计、原始输入和已应用副本分离、预览不能自动应用、失败不能应用、撤销/重置、配置下载及按需审计所选对象。文件读取、草案、预览和审计均为异步操作，慢响应不能覆盖新输入或已结束的会话。Chromium headless 自动化不能代替 Windows 人工桌面验收。

## 扩展模拟练习

`netaudit.simulator.simulate_configuration()` 是无状态入口，接收原文、厂商、命令及 `context`，返回候选而不持久化。`netaudit.simulation_goals.plan_goal()` 完整匹配单一中文目标，并用同一引擎验证草案。HTTP 分别调用 `/api/simulate` 与 `/api/plan`；这两条路径不进入审计或 AI。CLI 对应 `simulate` / `plan`，命令帮助可用 `python -m netaudit simulate --help` 查看。

`simulate --commands commands.txt` 与可重复的 `--command` 互斥，`--context context.json` 读取单独的视图对象文件。成功时 `--out` 原子写入候选并保留原有行尾；失败批次返回 2、不写输出。JSON 标准输出包含未脱敏 `config`，测试和 CI 日志只使用合成配置。原始输入、命令文件或视图文件不得被输出覆盖。

新增功能需维持以下约束：

- 练习只改变配置副本，不添加设备连接、shell 执行或虚构的链路/协议运行结果。尚未支持的语法不能描述为实机禁止。
- 先核对视图、厂商、参数与依赖，再修改原文；不要把已脱敏解析清单序列化为配置。未改动凭据、未知行、注释和 CRLF 应保留。
- 任一命令失败回滚整批配置与视图；覆盖先成功后失败、反向命令、幂等及拒绝未知块编辑的用例。
- 中文草案只支持能完整解释的目标；参数不足、否定或多个动作不能部分执行。增加模板时覆盖缺参和歧义，并验证所有厂商的实际命令。
- 网页独立维护备份、当前副本、候选和撤销历史，明确应用才接受候选；新输入使旧请求失效。只允许主题偏好进入浏览器存储，配置与历史留在内存。

完整范围与语义见 [SIMULATOR.md](../network-config-auditor/docs/SIMULATOR.md) 和 [架构说明](ARCHITECTURE.md)。

## 扩展审计流程

CLI 的 `audit` 与网页显式审计调用 `netaudit.pipeline.audit_configuration()`：解析配置 → 架构与规则 → 本地 CVE / KEV → 可选 AI → 同一报告结构。保留 `netaudit.rules.audit(config)` 的底层调用能力；它只执行架构与规则，不隐式联网或调用模型。报告 schema 1.1 保留旧字段，并增加 `architecture`、`intelligence`、`ai` 与 `pipeline`。

新解析或规则应保留原始行号、脱敏证据和 unknown / explicit-off 区别；六域覆盖状态不能用作“已安全”分数。情报匹配需要精确 CPE 与明确版本，本地 NVD 的复杂环境条件或无法比较版本必须降级待核对。默认读取随包官方 KEV，显式更新下载才联网，不能将配置传给更新服务。详情见 [架构说明](ARCHITECTURE.md)、[情报说明](../network-config-auditor/docs/INTELLIGENCE.md)和 [AI 说明](../network-config-auditor/docs/AI.md)。

AI 只接受回环地址的本机 Ollama，必须由用户选定模型并明确启用；不使用规则建议伪装模型输出。测试应验证配置与凭据不进入模型请求、模型不能改写规则/CVE 确认状态、HTML 转义以及超时/无模型后的报告可用性。使用真实 Ollama 前需另外记录安装版本、模型、运行环境和人工审阅，不能用 mock 成功冒充实际模型验收。

## Windows 便携包构建

构建需要 **Windows x64、Python 3.12.10 x64 和 Git**。Linux/macOS 上运行源码或构建 wheel 不能生成本项目经过验收的 Windows EXE。使用干净的 Git checkout：

```powershell
git status --porcelain --untracked-files=all
# 确认无输出；提交必要修改或移出无关文件
cd network-config-auditor
python tools/build_windows.py
```

上例的 `git status` 在仓库根目录执行；如果已在项目目录，不要再次 `cd`。构建脚本会拒绝未提交或未跟踪的非忽略文件，以保证 EXE 对应 Git HEAD 中的源码。普通开发环境里的额外包不会作为构建输入；脚本自动创建临时独立 venv，按 [`requirements-build-windows.txt`](../network-config-auditor/requirements-build-windows.txt) 安装固定的八项构建依赖，并核对已安装版本与 `pip check`。锁文件属于构建环境，不是运行时依赖清单。

流程依次是：归档当前提交源码 → 验收源码 → 生成并验收 onedir → 生成并验收 onefile → 收集许可证 → 打包并计算 SHA-256。v1.0.0 的每种运行方式都需加载四份网页资源并验证模拟和草案 API；源码成功不能代替 EXE 验收。任一步失败都会停止，不要绕过验收直接分发构建目录。输出位于 `network-config-auditor/dist/windows/`，包含便携 ZIP、onefile ZIP、单 EXE、对应源码 ZIP、构建清单、验收 JSON 与 `SHA256SUMS.txt`。脚本会清理指定的 `build/windows/` 和 `dist/windows/` 生成目录，避免在这些目录保存手工资料。

源码归档包含项目和仓库工作流，不包含 `.git`。要重建历史提交，请 clone 后 checkout 构建清单中的完整提交。仅持有源码 ZIP 时可以在归档根目录初始化 Git 并提交后构建，但清单将记录新的本地提交，不能声称与原提交或 EXE 字节相同。固定依赖也不保证 Windows runner 镜像更新后二进制逐字节一致。

打包资源路径、PyInstaller 官方依据及验收边界见 [PORTABILITY.md](../network-config-auditor/docs/PORTABILITY.md)。自动验收检查浏览器启动调用、本地资源与进程退出；Explorer 实际双击、浏览器视觉交互和保存对话框仍需桌面人工验证。

## GitHub Actions

| 工作流 | 触发方式 | 检查与产物 |
|---|---|---|
| [Network Config Auditor](../.github/workflows/network-config-auditor.yml) | push / pull request 修改项目目录或该工作流 | Linux Python 3.10、3.12、3.13：单元测试、上游复现、wheel 构建 |
| [NetAudit Windows portable](../.github/workflows/netaudit-windows.yml) | main 分支 push 修改项目目录或 Windows 工作流；也可手动运行 | Windows Server 2022、Python 3.12.10 x64：单元测试、源码/onedir/onefile 验收与上传 |
| [NetAudit release](../.github/workflows/netaudit-release.yml) | main 修改发布工作流或 `.github/release-source.json`；也可手动运行 | 验证成功 Windows 构建的九个原始文件，上传草稿、下载回验后发布 Release |

只修改根目录说明或根 `docs/` 不会自动触发上述工作流。需要重新生成便携包时，进入 [Windows Actions 页面](https://github.com/klwb360/NetConfig-Auditor/actions/workflows/netaudit-windows.yml)，选择 **Run workflow** 和所需分支；用于正式发布的构建必须来自 main。验收失败时如已生成 JSON 报告，会上传 `NetAudit-windows-diagnostics-<完整提交>`（保留 14 天），用于定位失败；其中没有可分发的 EXE。成功后在该次运行的 **Artifacts** 下载 `NetAudit-windows-x64-<完整提交>`；公开仓库附件可直接下载，当前保留期为 90 天。以对应运行的清单和校验和为准，不把旧文件的哈希用于新构建。

历史 [v0.2.1](https://github.com/klwb360/NetConfig-Auditor/releases/tag/v0.2.1)，标签与 EXE 对应源码为 `befb38bbecbbaa9d0d97c48c922e50e18c42f462`。[Windows 构建 37136065995](https://github.com/klwb360/NetAudit/actions/runs/37136065995) 通过 192 项单元测试与 28 项真实进程验收（源码 10、onedir 9、onefile 9），[Linux 构建 37136065998](https://github.com/klwb360/NetAudit/actions/runs/37136065998) 三个 Python 版本通过；Linux Chromium 65 项网页检查通过。[发布运行 37136432263](https://github.com/klwb360/NetAudit/actions/runs/37136432263) 的 14 项保护测试与 9 个附件下载回验通过。AI 本机协议替身和 NVD 合成格式用例不等于真实模型或真实 NVD 适用范围验收。

历史 [v0.2.0](https://github.com/klwb360/NetConfig-Auditor/releases/tag/v0.2.0) 的标签与 EXE 对应 `8a9840601d6c51dbdaff1fbbf62aeaf84cc0b490`：[Windows 构建 37120272682](https://github.com/klwb360/NetAudit/actions/runs/37120272682) 通过 192 项单元测试与 28 项进程验收，[Linux 构建 37120272642](https://github.com/klwb360/NetAudit/actions/runs/37120272642) 三个 Python 版本通过，Linux Chromium 24 项网页检查通过；[发布运行 37120600936](https://github.com/klwb360/NetAudit/actions/runs/37120600936) 的 14 项保护测试与 9 个附件下载回验通过。v0.2.0 和 v0.1.0 的下载、文件与 SHA-256 保留。

普通用户优先从 [最新 Release](https://github.com/klwb360/NetConfig-Auditor/releases/latest) 下载便携 ZIP，只需解压一次。Actions 下载是外层产物 ZIP，开发或备份使用时需先解压外层，再解压内部便携 ZIP。发布工作流复用成功构建的字节，不重新构建 EXE；输入、版本标签和重试规则见 [发布指南](RELEASING.md)。

规则或解析修改应补充能区分正确情况、误报和未知条件的测试，并更新 [规则目录](../network-config-auditor/docs/RULES.md)或支持范围。报告字段变更还需检查网页、JSON、Markdown、HTML 与命令行调用者的兼容性，保留原许可证和来源说明。
