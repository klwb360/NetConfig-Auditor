# v0.2.3 构建与验收资料

[下载运行文件](https://github.com/klwb360/NetAudit/releases/tag/v0.2.3) · [固定版本源码](https://github.com/klwb360/NetAudit/tree/v0.2.3)

Release 提供便携 ZIP、单 EXE 配套 ZIP、独立 EXE。两个运行 ZIP 内都包含完整对应源码、许可证和归属说明；独立源码 ZIP 的原始字节可从包内取得，具体路径与 SHA-256 见 [record.json](record.json)。

| 原始资料 | 用途 |
|---|---|
| [SHA256SUMS.txt](SHA256SUMS.txt) | 原始交付中其余八个文件的校验值；仍包含独立源码包与工程记录，并非仅列出当前三个下载附件 |
| [manifest.json](manifest.json) | 源码提交、构建环境、固定依赖、文件信息与验收结果 |
| [smoke-source.json](smoke-source.json) | 源码运行方式的实际进程验收 |
| [smoke-onedir.json](smoke-onedir.json) | 便携文件夹 EXE 的实际进程验收 |
| [smoke-onefile.json](smoke-onefile.json) | 单文件 EXE 的实际进程验收 |

这五份文件按原始字节永久保留。[record.json](record.json) 记录完整九文件的大小、SHA-256、来源构建与源码恢复位置。构建产物依旧包含九份交付文件，Release 下载区只展示三个运行文件。

源码提交：`7900be2b84104fe2f9e75ab186bb21d1d034c7e6`。原 [Windows 构建](https://github.com/klwb360/NetAudit/actions/runs/37749761790) 的验收范围以清单和报告为准；整理附件不新增 Windows 验收，也不重新构建、替换 EXE 或移动版本标签。Actions 原始产物有保留期限，本目录不依赖它长期保存。

| 运行文件 | SHA-256 |
|---|---|
| `NetAudit-0.2.3-windows-x64-7900be2b8410-onefile.exe` | `33542174e6e653531455d0356ce960e612b564ba884c3d63c8dfaeca7cd774ba` |
| `NetAudit-0.2.3-windows-x64-7900be2b8410-onefile.zip` | `98be1ba058d3adee585d806d1b4ad8451ac1e2a41ea3e4dd0d4a83c087c8c2b4` |
| `NetAudit-0.2.3-windows-x64-7900be2b8410-portable.zip` | `157417b75ec71aafe782d338c4d14e298c96011b5acf0e67f6753945b8807325` |
