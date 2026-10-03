# 开发与构建

NetAudit 的源码在 [`network-config-auditor/`](../network-config-auditor/)。运行时只使用 Python 标准库，需要 Python **3.10 或更新版本**；安装 Python 包、Node.js 或 PyInstaller 都不是普通源码运行的前提。模块职责见 [架构说明](ARCHITECTURE.md)。

## 获取源码与开发环境

```bash
git clone https://github.com/klwb360/NetAudit.git
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

单元测试覆盖解析、规则、报告、CLI、本地 HTTP API 和便携启动行为。HTTP 集成测试需要环境允许监听回环地址；若沙箱禁止创建 socket，应记录环境限制，不能将跳过的 HTTP 检查算作通过。上游复现脚本只隔离复现三个固定缺陷，不代表运行过完整上游程序。

修改网页 JavaScript 后，若已安装 Node.js，可检查语法：

```bash
node --check netaudit/web/app.js
```

Node.js 仅用于这项检查。Python 包构建可使用：

```bash
python -m pip wheel . --no-deps --wheel-dir dist
```

Wheel 构建仍会安装隔离的构建依赖；检查 wheel 中包含 `netaudit/web/index.html`、`app.js`、`style.css`。这一结果验证 Python 包，不验证 Windows EXE。历史验证记录见 [TESTING.md](../network-config-auditor/docs/TESTING.md)，已交付构建的环境、结果和限制见 [DELIVERY.md](../DELIVERY.md)。

## Windows 便携包构建

构建需要 **Windows x64、Python 3.12.10 x64 和 Git**。Linux/macOS 上运行源码或构建 wheel 不能生成本项目经过验收的 Windows EXE。使用干净的 Git checkout：

```powershell
git status --porcelain --untracked-files=all
# 确认无输出；提交必要修改或移出无关文件
cd network-config-auditor
python tools/build_windows.py
```

上例的 `git status` 在仓库根目录执行；如果已在项目目录，不要再次 `cd`。构建脚本会拒绝未提交或未跟踪的非忽略文件，以保证 EXE 对应 Git HEAD 中的源码。普通开发环境里的额外包不会作为构建输入；脚本自动创建临时独立 venv，按 [`requirements-build-windows.txt`](../network-config-auditor/requirements-build-windows.txt) 安装固定的八项构建依赖，并核对已安装版本与 `pip check`。锁文件属于构建环境，不是运行时依赖清单。

流程依次是：归档当前提交源码 → 验收源码 → 生成并验收 onedir → 生成并验收 onefile → 收集许可证 → 打包并计算 SHA-256。任一步失败都会停止；不要绕过验收直接分发构建目录。输出位于 `network-config-auditor/dist/windows/`，包含便携 ZIP、onefile ZIP、单 EXE、对应源码 ZIP、构建清单、验收 JSON 与 `SHA256SUMS.txt`。脚本会清理指定的 `build/windows/` 和 `dist/windows/` 生成目录，避免在这些目录保存手工资料。

源码归档包含项目和仓库工作流，不包含 `.git`。要重建历史提交，请 clone 后 checkout 构建清单中的完整提交。仅持有源码 ZIP 时可以在归档根目录初始化 Git 并提交后构建，但清单将记录新的本地提交，不能声称与原提交或 EXE 字节相同。固定依赖也不保证 Windows runner 镜像更新后二进制逐字节一致。

打包资源路径、PyInstaller 官方依据及验收边界见 [PORTABILITY.md](../network-config-auditor/docs/PORTABILITY.md)。自动验收检查浏览器启动调用、本地资源与进程退出；Explorer 实际双击、浏览器视觉交互和保存对话框仍需桌面人工验证。

## GitHub Actions

| 工作流 | 触发方式 | 检查与产物 |
|---|---|---|
| [Network Config Auditor](../.github/workflows/network-config-auditor.yml) | push / pull request 修改项目目录或该工作流 | Linux Python 3.10、3.12、3.13：单元测试、上游复现、wheel 构建 |
| [NetAudit Windows portable](../.github/workflows/netaudit-windows.yml) | main 分支 push 修改项目目录或 Windows 工作流；也可手动运行 | Windows Server 2022、Python 3.12.10 x64：单元测试、源码/onedir/onefile 验收与上传 |

只修改根目录说明或根 `docs/` 不会自动触发这两项工作流。需要重新生成便携包时，进入 [Windows Actions 页面](https://github.com/klwb360/NetAudit/actions/workflows/netaudit-windows.yml)，选择 **Run workflow** 和所需分支。验收失败时如已生成 JSON 报告，会上传 `NetAudit-windows-diagnostics-<完整提交>`（保留 14 天），用于定位失败；其中没有可分发的 EXE。成功后在该次运行的 **Artifacts** 下载 `NetAudit-windows-x64-<完整提交>`；私人仓库下载需要相应权限，当前保留期为 90 天。以对应运行的清单和校验和为准，不把旧文件的哈希用于新构建。

规则或解析修改应补充能区分正确情况、误报和未知条件的测试，并更新 [规则目录](../network-config-auditor/docs/RULES.md)或支持范围。报告字段变更还需检查网页、JSON、Markdown、HTML 与命令行调用者的兼容性，保留原许可证和来源说明。
