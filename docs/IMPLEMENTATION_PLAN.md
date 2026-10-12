# NetConfig Auditor 实施与验收计划

用户于 2026-10-12 批准实施此前的功能审查计划，并指定公开仓库 `klwb360/NetConfig-Auditor`。主项目复用 NetAudit，不删除现有功能，不连接或修改真实设备。

## 任务顺序

1. 迁移全部源码、Git 历史、七个发行标签、GPL/NOTICE 和21个历史发行附件；备份并核对内容哈希。
2. 路由/NAT完整性修复：未知尾部条件、接口形式、VRF、地址/端口验证、正反操作，先失败回归再修复。
3. 原生 `audit-batch INPUT_DIR --out-dir OUTPUT_DIR`，逐文件失败隔离、编码检测、来源路径/哈希/行号、逐设备与汇总JSON/HTML。
4. >=50份独立人工标注合成配置（Cisco18、Huawei16、H3C16），字段准确率>=95%，precision>=90%，recall单列；pytest与核心行覆盖率>=80%门禁。
5. 验证Windows发行版、记录未运行的环境验收，形成架构演示、408笔记和至少15技术问答。
6. 在PR中明确新增、修复、复用、验证及限制。迁移与交付核验完成后删除旧`klwb360/NetAudit`；不删除`Codex-code`。

## 模块边界

- P0任务拥有parser/model及必要规则/整改逻辑；批量任务拥有config_io/batch/cli；金标准任务拥有benchmarks和benchmark工具；主代理负责CI、版本、打包、迁移、集成和最终检查点。
- `decode_config_bytes(bytes, encoding='auto') -> (text, detected_encoding)`，BOM、严格UTF8、GB18030；拒绝损坏数据和控制字符。
- `audit_directory(input_dir, out_dir, *, vendor='auto', encoding='auto', recursive=False, strict=False, fail_on=None) -> dict`，默认顺序审计。
- 批量schema1.0，`devices[].source`记录相对POSIX路径、SHA256、编码；`report`嵌套原schema1.1；`status`区分ok/error，不等同于安全。
- 单文件报告保持兼容，可添加source元数据；网页和模拟功能仍复用原流程。
- 批量退出码：2输入/严格解析错误，1达到风险阈值，0调用完成。输出目录不得覆盖或嵌入输入树，拒绝输入符号链接。

## 验收原则

- 字段精度由独立标注对比，不能用识别行数或测试数量替代。
- 支持字段范围先冻结，缺失/错误/多余字段均影响分数；按厂商和模块报告。
- precision=TP/(TP+FP)，recall=TP/(TP+FN)，明确计分对象与未知状态；无预测正例不能虚报100%。
- 不降低95/90/80阈值，不删除失败样例，不将当前实现输出当作标注。
- 保留官方情报和发行档案原始字节，不改写历史校验值。
- 无Python运行实测不能用源码测试推定；记录解释器、平台、运行形式和实际执行项目。

## 恢复与提交

每个独立步骤先运行适当检查，再更新`PROJECT_STATUS.md`并写`docs/checkpoints/`，随后做对应Git提交。测试长日志放在工作目录，提交报告摘要和可复现命令。已实现且验证通过的功能直接复用。

## 已明确的实施决定

- 保留`netaudit`包名和NetAudit兼容启动器，公开产品名为NetConfig Auditor。
- 本轮不整体替换dataclass/正则解析/标准库Web；TextFSM、Pydantic、YAML、SQLite、FastAPI属于后续增量扩展。
- Git迁移采用连接新仓库初始提交与旧main的merge commit，保留原始提交和标签，不重写历史。
- 删除旧库是用户已明确授权的最终操作，执行前核验目标完整名、ID、可见性、新仓库数据和离线备份。
