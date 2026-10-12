# v1.1.0 实际验收记录

本目录保存本次源码、冻结EXE和CI验收证据；正式[公开v1.1.0](https://github.com/klwb360/NetConfig-Auditor/releases/tag/v1.1.0)已完成主分支db690b0构建，原始档案固定在[docs/releases/v1.1.0](../../releases/v1.1.0/README.md)，新的独立运行和汇总在[final-main](final-main/)。下方保留PR阶段的精确源码与早期Windows11证据，不能把两次产物SHA混用。

| 验证 | 实际结果 |
|---|---|
| Windows11/Python3.12.15最终源码 | 471 pytest、506 subtests通过 |
| Linux Python3.10/3.12/3.13 | 每版本470通过、1项Windows BAT实际执行跳过、506 subtests通过 |
| 核心代码覆盖 | 行93.10%、分支88.17%、综合91.41%，门禁80% |
| dataset v1.1独立合成金标准 | 50配置、1870字段、25条风险规则正反配对；1870/1870，TP26/FP0/FN0，精确率/召回率100% |
| Windows Server 2022冻结CI | 源码10、onedir9、onefile9实际进程检查通过 |
| 独立clean-runtime runner | 移除标准CPython缓存、仅System32 PATH；两种包各50文件、编码/来源/JSON/HTML及版本，共6检查通过 |
| 本机Windows11冻结EXE | onedir/onefile各50金标准；各1870/1870，TP26/FP0/FN0 |

最终源分支提交 `caf3717a131f6ca7cd8c6b477628ba528a6b129e`；[Windows CI 38226564521](https://github.com/klwb360/NetConfig-Auditor/actions/runs/38226564521)实际构建的是包含该提交的PR自动合并提交 `3789bff692bede73c0be723a3f1e9feea174c050`。manifest和三份smoke记录是原始构建字节，未修改。

[Linux PR检查](https://github.com/klwb360/NetConfig-Auditor/actions/runs/38226564305)、[Linux分支检查](https://github.com/klwb360/NetConfig-Auditor/actions/runs/38226557637)均成功。外层artifact及九文件完整源码/资源/校验守卫通过；摘要中保留artifact ID和SHA。

本机Windows11EXE对应 `18f85507f51b73daf9dd3ffa6dac0f70bf82564b`，之后最终提交只改变Git属性、CI PowerShell和测试，没有应用运行逻辑变更。独立Windows11构建同样通过28进程检查，但不能把两个构建的EXE字节或提交混为一谈。

数字只覆盖冻结支持范围。额外unknown警告保持可见；无风险报告不等于配置安全。GUI批量/多编码未实现，CLI已实现。普通非管理员账户、真实Explorer双击/浏览器可视交互及独立物理无Python电脑仍待人工检查。CI镜像可能仍含其它解释器，验证范围是标准CPython缓存和受限子进程PATH。
