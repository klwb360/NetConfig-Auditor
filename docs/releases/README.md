# 构建与验收资料

普通使用请从 [最新 Release](https://github.com/klwb360/NetAudit/releases/latest) 下载便携 ZIP，解压后双击。这里长期保存各版本原始校验文件、构建清单和三种运行方式的验收记录。

| 版本 | 永久资料 | 对应源码 |
|---|---|---|
| v0.2.3 | [原始记录与校验](v0.2.3/README.md) | [固定标签](https://github.com/klwb360/NetAudit/tree/v0.2.3) |
| v0.2.2 | [原始记录与校验](v0.2.2/README.md) | [固定标签](https://github.com/klwb360/NetAudit/tree/v0.2.2) |
| v0.2.1 | [原始记录与校验](v0.2.1/README.md) | [固定标签](https://github.com/klwb360/NetAudit/tree/v0.2.1) |
| v0.2.0 | [原始记录与校验](v0.2.0/README.md) | [固定标签](https://github.com/klwb360/NetAudit/tree/v0.2.0) |
| v0.1.0 | [原始记录与校验](v0.1.0/README.md) | [固定标签](https://github.com/klwb360/NetAudit/tree/v0.1.0) |

Release 仅保留便携 ZIP、单 EXE 配套 ZIP和独立 EXE。源码按原始字节包含在两个运行 ZIP 内，保留许可证与归属说明；版本标签仍指向各自 EXE 的构建提交。GitHub 自动生成的 Source code ZIP/tar.gz 由平台提供，不能单独隐藏。

各版本的 SHA256SUMS.txt 仍校验原始交付中其余八个文件，包含现已归档的工程资料；文件没有被改写为只列三个下载附件。record.json 额外保存完整九文件身份、大小、SHA-256、原构建产物信息及包内源码路径。

2026-10-03 实际整理：[GitHub Actions 37139629554](https://github.com/klwb360/NetAudit/actions/runs/37139629554) 的 52 项保护测试通过，全部三个版本永久归档及原始九文件预检通过后移除 18 个冗余附件，最终三个版本各保留三个原运行文件。见 [原始执行记录](organization-2026-10-03.json)；运行文件 ID、大小、SHA-256、固定标签与 latest v0.2.1 保持不变。
