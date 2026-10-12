# v1.0.0 构建与验收资料

[下载运行文件](https://github.com/klwb360/NetAudit/releases/tag/v1.0.0) · [固定版本源码](https://github.com/klwb360/NetAudit/tree/v1.0.0)

Release 提供便携 ZIP、单 EXE 配套 ZIP、独立 EXE。两个运行 ZIP 内都包含完整对应源码、许可证和归属说明；独立源码 ZIP 的原始字节可从包内取得，具体路径与 SHA-256 见 [record.json](record.json)。

| 原始资料 | 用途 |
|---|---|
| [SHA256SUMS.txt](SHA256SUMS.txt) | 原始交付中其余八个文件的校验值；仍包含独立源码包与工程记录，并非仅列出当前三个下载附件 |
| [manifest.json](manifest.json) | 源码提交、构建环境、固定依赖、文件信息与验收结果 |
| [smoke-source.json](smoke-source.json) | 源码运行方式的实际进程验收 |
| [smoke-onedir.json](smoke-onedir.json) | 便携文件夹 EXE 的实际进程验收 |
| [smoke-onefile.json](smoke-onefile.json) | 单文件 EXE 的实际进程验收 |

这五份文件按原始字节永久保留。[record.json](record.json) 记录完整九文件的大小、SHA-256、来源构建与源码恢复位置。构建产物依旧包含九份交付文件，Release 下载区只展示三个运行文件。

源码提交：`e2b4efecdc2682db8cef49d369c6fb0c9114b8b0`。原 [Windows 构建](https://github.com/klwb360/NetAudit/actions/runs/37895686338) 的验收范围以清单和报告为准；整理附件不新增 Windows 验收，也不重新构建、替换 EXE 或移动版本标签。Actions 原始产物有保留期限，本目录不依赖它长期保存。

| 运行文件 | SHA-256 |
|---|---|
| `NetAudit-1.0.0-windows-x64-e2b4efecdc26-onefile.exe` | `1aedeaa1a553d93faa4e0ce7c369209140b189930bc91382d15f0ca124ec4309` |
| `NetAudit-1.0.0-windows-x64-e2b4efecdc26-onefile.zip` | `a992be36e3e5f14f5954d199fa9e6703c018bce5ab88bc434544bce2a720d040` |
| `NetAudit-1.0.0-windows-x64-e2b4efecdc26-portable.zip` | `18a8f47a066947de218b8fe9b8f8aa26325fdc364ac62ab9e4bf9a41999d67f6` |
