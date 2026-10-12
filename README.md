# NetConfig Auditor · 多厂商网络配置审计与练习

在本机导入 Huawei VRP、H3C Comware、Cisco IOS/IOS XE 或锐捷 RGOS 配置，查看配置风险、证据行号和修复建议。支持中文网页、CLI、离线命令练习与 Windows EXE；不会连接或修改真实设备。

项目复用 NetAudit，并保留 GPL-3.0-only 许可证、上游归属、原始 Git 历史、七个版本标签和全部 21 个历史运行附件。[迁移与校验](docs/migration/legacy-release-receipt.json) · [项目状态](PROJECT_STATUS.md) · [恢复检查点](docs/checkpoints/)。

## 1.1.0 新增与修复

- **批量审计**：目录导入、可选递归、逐文件失败隔离、逐设备及汇总 JSON/HTML。
- **编码导入**：CLI 支持 UTF-8/BOM、GBK/GB18030、带 BOM 的 UTF-16；可手动指定编码，不静默丢弃非法字节。
- **来源追溯**：报告记录来源相对路径、SHA-256、编码与原配置行号；同名文件不会相互覆盖。
- **解析修复**：路由/NAT 未支持参数保留并标为待复核，增加地址/端口/掩码验证，纠正接口 NAT 的伪映射，精确处理撤销。
- **量化验收**：50 份独立人工标注合成配置，字段准确率、规则精确率/召回率与未知项单列；pytest 和覆盖率门禁。
- **学习与恢复**：408 笔记、24 道项目问答、演示案例、状态文件与逐步恢复记录。

**[正式v1.1.0 Windows下载](https://github.com/klwb360/NetConfig-Auditor/releases/tag/v1.1.0)** 已发布，包含本轮批量功能。历史v1.0.1及更早版本保留原字节。实际验证、环境边界和校验值见[交付记录](DELIVERY.md)，[逐项完成度](docs/FEATURE_MATRIX.md)与[下一阶段](docs/NEXT_PHASE.md)可用于恢复工作。

## 源码与命令行

Python 3.10 或更新版本，推荐 3.12；普通运行没有第三方 Python 包依赖。

```bash
cd network-config-auditor
python -m netaudit
python -m netaudit audit examples/huawei.cfg --format html --out reports/huawei.html
python -m netaudit audit device.cfg --encoding gb18030 --format json --out reports/device.json
python -m netaudit audit-batch examples --out-dir reports/batch
python -m netaudit audit-batch configs --recursive --encoding auto --strict --fail-on high --out-dir reports/all
```

无参数启动中文本地网页；也可使用 `serve --no-browser`。网页仍每次导入一台设备的 UTF-8 配置；批量与多编码入口位于 CLI，冻结 EXE 接受相同参数。

批量默认扫描 `.cfg/.conf/.config/.txt` 和无扩展名文件，每份最多 2 MiB。输出目录必须位于输入目录之外，拒绝输入符号链接或目录联接。一份失败后继续其余配置，并在汇总中记录失败。输出包含 `batch.json`、`batch.html` 及每份设备报告。

退出码：0 表示调用完成；1 表示发现达到 `--fail-on` 风险阈值；2 表示参数、输入、输出或严格解析错误。0 不表示网络安全；缺少告警、未知配置或待复核项均不能作为安全证明。

## 保留的功能

接口、IPv4、VLAN/Trunk、基础静态路由、ACL、部分 NAT、管理面及 STP/OSPF 的结构化清单；35 个配置规则 ID；JSON/HTML/Markdown；主题与风险折叠；核查命令和整改模板；原文保留的配置练习、中文单一目标草案、预览/应用/撤销；官方 KEV 离线快照、可选本地 NVD/CPE 匹配及显式启用的本机 Ollama 解释。

NAT 的 VRF、route-map、部分服务名、接口公网地址和其它扩展语义仍需人工核对。复杂策略、完整动态路由和 IPv6 未完整覆盖。练习不模拟 ping、转发、链路、STP 收敛或 OSPF 邻居；AI 不改变规则结论。

## 验证与学习

```bash
python -m pip install -e ".[test]"
python -m coverage run -m pytest -q
python -m coverage report --fail-under=80
python tools/benchmark_acceptance.py --out reports/acceptance.json
node tests/vendor_syntax_cases.js
```

验收阈值保持：支持字段准确率 >=95%、规则 precision >=90%、核心 Python 覆盖率 >=80%，recall 单列。合成数据上的分数不代表真实配置的普遍性能。[验收方法与范围](docs/ACCEPTANCE.md) · [数据集](network-config-auditor/benchmarks/) · [演示](docs/DEMO.md) · [408 笔记](docs/LEARNING_408.md) · [24 道问答](docs/PROJECT_QA.md)。

Windows 构建分别验收源码、onedir 和 onefile；另外在独立 hosted Windows runner 中清除标准 CPython 安装缓存后检查冻结 EXE 的版本、50 文件批量、JSON/HTML 和来源追溯。实际执行结果以 CI 与交付记录为准；Windows Server CI 和 Windows11 冻结CLI已实测；人工 Explorer 双击、真实浏览器交互、普通账户及独立物理无Python桌面仍需分别验收。

## 数据保护与文档

网页仅监听 `127.0.0.1`，配置处理在本机完成，默认不联网。报告仍含网络结构；模拟导出配置保留原始凭据。真实配置放在被忽略的 `configs/`，报告放在 `reports/`，公开反馈使用合成或人工脱敏样例。

[架构](docs/ARCHITECTURE.md) · [CLI 与支持范围](network-config-auditor/README.md) · [规则](network-config-auditor/docs/RULES.md) · [Windows 使用](network-config-auditor/docs/WINDOWS.md) · [排错](docs/TROUBLESHOOTING.md) · [发布](docs/RELEASING.md) · [许可证](LICENSE) · [归属](NOTICE)。

分发 EXE 时保留许可证、归属、对应源码和运行库。历史资产直接复制且未重建；历史 Actions 链接描述原私有仓库执行，删除旧库后以永久档案及迁移回执核验。
