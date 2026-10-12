# 检查点03：功能、TDD与独立验收

## 新增与修复

- parser/model/rules：路由与NAT完整性、严格参数验证、未知语义保留、精确撤销。
- H3C逆向grammar：官方short undo server/outbound与Huawei差异；独立复核发现后新增7失败回归，修复转绿。
- simulator：不完整Route只读摘要明确提示待复核，1项RED→GREEN。
- CLI/config_io/batch：严格多编码、50份批量、错误隔离、相对来源/哈希/行号、逐设备和汇总JSON/HTML。
- 金标准：dataset v1.1，50配置、25风险规则正反配对、1870字段，expected独立标注。
- 学习：408笔记、24题问答、演示与指标说明。

## 实际验证

- Windows Python3.12.15：466 pytest、506 subtests通过；Git系统autocrlf=true保留，打包测试显式隔离archive预期。
- 50例：字段1870/1870，TP26/FP0/FN0，precision/recall100%；只代表冻结合成数据范围。
- unknown匹配8、额外1、缺失0：H3C静态路由description仍保守提示，未修改gold迎合结果。
- Python应用包覆盖门禁>=80%通过，详细CI报告还待运行。
- 厂商分类27组通过；公开发布目标/既有发布维护70项测试通过。
- 未验证新的冻结EXE；不得把上述源码结果推定为EXE通过。

## 下一步

独立复核收尾，提交各模块，运行本机固定Python3.12.10/PyInstaller6.22.3及GitHub Windows冻结验收，核对清理CPython缓存后的独立runner结果，提交标注新增/修复的PR，再执行最终旧仓库身份和迁移数据校验。
