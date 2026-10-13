# 10：v1.1.1 名称、暗黑与单厂商高亮交付

日期：2026-10-13（Asia/Shanghai）。程序版本 **1.1.1**，正式名称 **NetConfig Auditor**。

## 已完成并验证

- 用户确认的新名称覆盖网页、CLI、Windows 产品信息和新发行资产；旧 BAT、模块、浏览器偏好、会话头和缓存兼容。设备原始 hostname 与配置保持。
- 暗黑主背景 `#111111`、面板 `#1b1b1b`、输入框 `#161616`；单厂商不显示语法底色与行侧标签，混合厂商继续提示，共享 / 不确定语法保守处理。主页截图为真实源码程序、合成示例。
- [PR #3](https://github.com/klwb360/NetConfig-Auditor/pull/3)、[PR #4](https://github.com/klwb360/NetConfig-Auditor/pull/4)；正式 [v1.1.1 Release](https://github.com/klwb360/NetConfig-Auditor/releases/tag/v1.1.1)。
- 固定 EXE 源码 `5ffe0051ff7929dd7bfd8bfbca593af8a355b1b3`；Windows `38350727838`、Linux `38350727805`、发布 `38351238049`。28 项真实进程检查、6 项清洁运行检查；源码真实浏览器证据另存 `../acceptance/v1.1.1/source-browser-single-vendor.json`，旧源码外观证据保持。
- 三运行附件与永久 `docs/releases/v1.1.1/record.json` / manifest、最新公开 Release 及实际下载文件的身份、大小与 SHA-256 一致。旧已发行记录与 EXE 未修改。
- 当前主页下载、DELIVERY、CHANGELOG、PROJECT_STATUS 与发布资料目录均已更新。
- Windows11发行单EXE实际浏览器验证标题、暗黑背景和单一/混合高亮切换通过，子进程PATH限制为System32。证据 ../acceptance/v1.1.1/final-main/frozen-windows11-branding.json；两种EXE产品属性均通过。

## 恢复和下一步

先读取本检查点、PROJECT_STATUS 和 DELIVERY，核对公开发行仍指向上述源码。所有仓库步骤完成后，将最新独立 EXE 下载到 Windows 默认下载目录并核验大小 / SHA-256，保存本机下载回执，保留原程序；不重建或替换既有发行文件。

普通账户、Explorer / 默认浏览器双击、独立物理无 Python 桌面仍是人工验收；源码浏览器证据不替代冻结 EXE 的桌面验证。工具离线处理配置，不修改真实设备；未知语法需复核，合成评测不能推广为真实网络准确率。旧 NetAudit 删除由用户自行完成。
