# 发布 Windows 便携版

发布使用 [`NetAudit release` 工作流](../.github/workflows/netaudit-release.yml)和 [`tools/publish_release.py`](../tools/publish_release.py)，将已经通过 Windows 验收的原始产物上传为 Release，不重新构建或替换 EXE。仓库保持私人，下载 Release 也需要访问权限。

当前版本：[v0.1.0](https://github.com/klwb360/NetAudit/releases/tag/v0.1.0)。其构建源码是 `f2002b79bd6da91e2a29f741c8483951e20bba86`，成功 [Windows run 为 37116561468](https://github.com/klwb360/NetAudit/actions/runs/37116561468)，[发布 run 为 37118017366](https://github.com/klwb360/NetAudit/actions/runs/37118017366)。版本标签指向构建源码提交，而不是后来加入发布脚本或更新说明的提交。下载、SHA-256 与验收边界见 [DELIVERY.md](../DELIVERY.md)。

## 发布下一个版本

1. 修改代码时同步项目版本：[`pyproject.toml`](../network-config-auditor/pyproject.toml) 的 `[project].version`、[`netaudit/__init__.py`](../network-config-auditor/netaudit/__init__.py) 的 `__version__`，以及 [`rules.py`](../network-config-auditor/netaudit/rules.py) 中报告的 `tool_version`。版本使用 `X.Y.Z`，例如 `0.1.1`；不要复用已经发布的版本标签。
2. 提交到 main，等待 [NetAudit Windows portable](https://github.com/klwb360/NetAudit/actions/workflows/netaudit-windows.yml) 构建成功。只修改根文档不会自动构建，需要时手动 **Run workflow** 并选择 main。
3. 记录成功运行的 run ID 和该运行的完整 40 位源码 SHA。确认 `NetAudit-windows-x64-<完整SHA>` 产物尚未过期，`manifest.json` 的版本、源码提交和实际验收报告与本次构建一致。
4. 打开 [NetAudit release](https://github.com/klwb360/NetAudit/actions/workflows/netaudit-release.yml)，点击 **Run workflow**，选择 **main**，填写下列三个输入。留空时使用 `.github/release-source.json` 已锁定的发行来源；新版本应填写全部三项。

| 输入 | 填写内容 |
|---|---|
| `tag` | `vX.Y.Z`，必须等于 `v` 加构建清单的 `application_version` |
| `run_id` | 成功的 Windows 构建运行 ID，不是 artifact ID 或 job ID |
| `source_commit` | 该 Windows 运行对应的完整 40 位 Git SHA |

5. 等待发布运行成功，检查 Release 的 **Assets**、源码标签、校验文件和下载链接，再更新首页及交付记录。用户下载 `*-portable.zip` 后只需解压一次。

发布工作流只能在 main 执行，也可由 main 修改发布工作流或 [`.github/release-source.json`](../.github/release-source.json) 自动触发。该 JSON 提供未填写输入时使用的默认发布来源，并锁定指定验收产物的 ID 与外层 SHA-256；未来版本优先填写手动输入，避免无意重用旧来源。源码构建与发布器提交可以不同，但标签始终指向 `source_commit`。

## 发布前实际检查什么

发布器要求来源仓库为当前私人仓库，Windows run 已完成且成功、来自 main，工作流为 `netaudit-windows.yml`，事件为 push 或 workflow_dispatch。它验证 GitHub 记录的外层产物 SHA-256、ZIP CRC、文件名、清单、每个文件的校验值和大小。

来源产物必须恰有九个文件：

| 文件 | 用途 |
|---|---|
| `NetAudit-<版本>-windows-x64-<前12位SHA>-portable.zip` | 推荐便携文件夹版 |
| 同前缀 `-onefile.zip`、`-onefile.exe` | 单 EXE 配套包与独立 EXE |
| `NetAudit-<版本>-source-<前12位SHA>.zip` | 对应源码 |
| `manifest.json` | 源码、构建环境、依赖、文件元信息与验收结果 |
| `SHA256SUMS.txt` | 其余八个文件的 SHA-256 |
| `smoke-source.json`、`smoke-onedir.json`、`smoke-onefile.json` | 三种运行方式的验收报告 |

清单必须记录干净源码、对应 run/attempt 和 Windows AMD64 环境，三份独立报告须与清单一致。v0.1.0 要求至少源码 9 项、onedir 8 项、onefile 8 项；v0.2.0 新增完整流程验收，要求至少源码 10 项、onedir 9 项、onefile 9 项，报告中的全部检查均须通过。包含停服记录的检查必须没有剩余进程、没有强制清理且端口已关闭。

随后创建或确认版本标签，上传到草稿 Release，并逐个下载回验九个资产的大小与 SHA-256。只有全部通过，才将草稿转为正式 Release 并设置为 latest。这里“发布”仍是私人仓库内提供下载，不改变仓库可见性。

## 失败与重试

- 构建失败、产物过期、校验不符、标签与清单版本不符时停止。先解决来源问题，不使用失败的 Windows 构建。
- 已有标签必须解析到同一源码提交；指向另一提交时拒绝操作，不移动标签。
- 上传或回验失败时 Release 保持草稿。同一输入可重试，补齐缺失资产并再次验证已有资产；已有资产内容不符时停止，不覆盖。
- 已正式发布的版本不会被更新或覆盖。相同输入重试只验证完整资产；若正式版本资产缺失或不匹配，发布器拒绝修改。需要新字节时提升版本，重新构建并发布新标签。

Windows 构建固定依赖不等于字节级可重现；发布器保持原验收文件的字节不变。Windows Server 2022 x64 的自动验收也不能代替 Windows 10/11、普通账户、物理无 Python 电脑、真实 Explorer 双击和浏览器可视交互验收。具体范围与未测项目继续保留在 [交付记录](../DELIVERY.md)和发布资产中。
