# 发布 Windows 便携版

发布使用 [`NetAudit release` 工作流](../.github/workflows/netaudit-release.yml)和 [`tools/publish_release.py`](../tools/publish_release.py)，校验已经通过 Windows 验收的完整原始产物，将工程记录永久归档，再把三个运行文件上传为 Release。发布不重新构建或替换 EXE。仓库保持私人，下载 Release 也需要访问权限。

当前版本：[v0.2.1](https://github.com/klwb360/NetAudit/releases/tag/v0.2.1)。构建源码为 `befb38bbecbbaa9d0d97c48c922e50e18c42f462`，[Windows run 37136065995](https://github.com/klwb360/NetAudit/actions/runs/37136065995) 通过 192 项应用测试与 28 项真实进程检查；首次 [发布 run 37136432263](https://github.com/klwb360/NetAudit/actions/runs/37136432263) 通过 14 项保护测试和当时全部 9 个附件下载回验。界面另有 Linux Chromium 65 项实际检查通过。版本标签指向 EXE 构建源码，而不是后来的发布元数据或文档提交。下载、SHA-256 与验收边界见 [DELIVERY.md](../DELIVERY.md)。当前版、旧 [v0.2.0](https://github.com/klwb360/NetAudit/releases/tag/v0.2.0) 与 [v0.1.0](https://github.com/klwb360/NetAudit/releases/tag/v0.1.0) 均保留原来的三个运行文件，不移动标签或覆盖；其他记录见 [发布档案](releases/README.md)。

## 发布下一个版本

1. 修改代码时同步项目版本：[`pyproject.toml`](../network-config-auditor/pyproject.toml) 的 `[project].version` 与 [`netaudit/__init__.py`](../network-config-auditor/netaudit/__init__.py) 的 `__version__`。CLI、报告与清单从同一版本常量读取。版本使用 `X.Y.Z`，例如 `0.2.2`；不要复用已经发布的版本标签。
2. 提交到 main，等待 [NetAudit Windows portable](https://github.com/klwb360/NetAudit/actions/workflows/netaudit-windows.yml) 构建成功。只修改根文档不会自动构建，需要时手动 **Run workflow** 并选择 main。
3. 记录成功运行的 run ID 和该运行的完整 40 位源码 SHA。确认 `NetAudit-windows-x64-<完整SHA>` 产物尚未过期，`manifest.json` 的版本、源码提交和实际验收报告与本次构建一致。
4. 打开 [NetAudit release](https://github.com/klwb360/NetAudit/actions/workflows/netaudit-release.yml)，点击 **Run workflow**，选择 **main**，填写下列三个输入。留空时使用 `.github/release-source.json` 已锁定的发行来源；新版本应填写全部三项。

| 输入 | 填写内容 |
|---|---|
| `tag` | `vX.Y.Z`，必须等于 `v` 加构建清单的 `application_version` |
| `run_id` | 成功的 Windows 构建运行 ID，不是 artifact ID 或 job ID |
| `source_commit` | 该 Windows 运行对应的完整 40 位 Git SHA |

5. 等待发布运行成功，检查 Release 的 **Assets** 恰有三个运行附件、源码标签及下载链接，再检查 `docs/releases/<tag>/` 的校验文件、清单、三份验收报告、归档记录与说明。最后更新首页及交付记录。用户下载 `*-portable.zip` 后只需解压一次。

发布工作流只能在 main 执行，也可由 main 修改发布工作流或 [`.github/release-source.json`](../.github/release-source.json) 自动触发。该 JSON 提供未填写输入时使用的默认发布来源，并锁定指定验收产物的 ID 与外层 SHA-256；未来版本优先填写手动输入，避免无意重用旧来源。源码构建与发布器提交可以不同，但标签始终指向 `source_commit`。

## 发布前实际检查什么

发布器要求来源仓库为当前私人仓库，Windows run 已完成且成功、来自 main，工作流为 `netaudit-windows.yml`，事件为 push 或 workflow_dispatch。它验证 GitHub 记录的外层产物 SHA-256、ZIP CRC、文件名、清单、每个文件的校验值和大小。

Windows Actions 来源产物必须恰有九个文件，构建与完整验收清单保持不变：

| 文件 | 用途 |
|---|---|
| `NetAudit-<版本>-windows-x64-<前12位SHA>-portable.zip` | 推荐便携文件夹版 |
| 同前缀 `-onefile.zip`、`-onefile.exe` | 单 EXE 配套包与独立 EXE |
| `NetAudit-<版本>-source-<前12位SHA>.zip` | 对应源码 |
| `manifest.json` | 源码、构建环境、依赖、文件元信息与验收结果 |
| `SHA256SUMS.txt` | 其余八个文件的 SHA-256 |
| `smoke-source.json`、`smoke-onedir.json`、`smoke-onefile.json` | 三种运行方式的验收报告 |

清单必须记录干净源码、对应 run/attempt 和 Windows AMD64 环境，三份独立报告须与清单一致。v0.1.0 要求至少源码 9 项、onedir 8 项、onefile 8 项；v0.2.0 起新增完整流程验收，要求至少源码 10 项、onedir 9 项、onefile 9 项，报告中的全部检查均须通过。包含停服记录的检查必须没有剩余进程、没有强制清理且端口已关闭。

发布器核对两个运行 ZIP 内的对应源码与独立源码 ZIP 字节一致。五份工程记录按原始字节永久保存到仓库 `docs/releases/<tag>/`，同时保存归档记录和说明；写入后从远端回读核对。已有归档必须匹配，不覆盖冲突内容。原始 `SHA256SUMS.txt` 继续记录完整九文件产物中的其余八个文件，包含可从运行 ZIP 内取得的源码 ZIP。

创建或确认版本标签后，只上传以下三个文件到草稿 Release：

- `NetAudit-<版本>-windows-x64-<前12位SHA>-portable.zip`
- `NetAudit-<版本>-windows-x64-<前12位SHA>-onefile.zip`
- `NetAudit-<版本>-windows-x64-<前12位SHA>-onefile.exe`

逐个下载回验这三个资产的大小与 SHA-256，工程归档及运行文件均通过后，才将草稿转为正式 Release 并设置为 latest。源码继续随两个运行 ZIP 提供，标签固定到构建源码。GitHub 自动附带的 “Source code” ZIP/tar.gz 无法单独隐藏；它们不属于上传附件集合。这里“发布”仍是私人仓库内提供下载，不改变仓库可见性。

## 整理已发布版本

[`NetAudit release curation` 工作流](../.github/workflows/netaudit-release-curation.yml)及 [`tools/curate_releases.py`](../tools/curate_releases.py)用于整理 v0.2.1、v0.2.0、v0.1.0，锁定每个原始附件的 ID、文件名、大小和 SHA-256。先确认五份工程记录已永久归档且可从远端完整回读，核对两个运行 ZIP 内的对应源码，再更新 Release 的资料入口，并删除重复源码 ZIP 和五份已归档的记录附件。每个版本最终恰保留三个原运行附件，版本标签、运行文件字节及最新版本选择保持不变。

整理中断后可重新运行，同样检查归档和已保留文件；不以 Actions 的限时产物替代永久档案。该操作不重建 EXE，也不能视为新增 Windows 运行验收。

## 失败与重试

- 构建失败、校验不符、标签与清单版本不符时停止。首次发布必须有尚未过期的成功 Windows 构建产物；不使用失败构建。
- 已有标签必须解析到同一源码提交；指向另一提交时拒绝操作，不移动标签。
- 永久归档失败或冲突时停止，不发布或删除来源附件。上传或回验失败时 Release 保持草稿。同一输入可重试，补齐缺失运行资产并再次验证已有资产；已有资产内容不符时停止，不覆盖。
- 已正式发布的版本不由发布器覆盖。相同输入重试验证三个运行附件与永久工程档案；若缺失或不匹配，拒绝修改。历史九附件版本使用上面的专用整理工作流迁移，发布器不自动删除附件。需要新运行文件字节时提升版本，重新构建并发布新标签。
- 已整理的正式 Release 可在 Actions 原产物过期后，使用永久档案和运行 ZIP 中的源码恢复完整九文件内容并复核；此时无法重新下载外层 Actions ZIP，日志会明确说明该限制，不允许借此首次发布。

Windows 构建固定依赖不等于字节级可重现；发布器保持原验收文件的字节不变。Windows Server 2022 x64 的自动验收也不能代替 Windows 10/11、普通账户、物理无 Python 电脑、真实 Explorer 双击和浏览器可视交互验收。具体范围与未测项目继续保留在 [交付记录](../DELIVERY.md)和 [发布档案](releases/README.md)中。
