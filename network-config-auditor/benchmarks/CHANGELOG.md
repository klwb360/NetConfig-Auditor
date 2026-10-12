# 金标准变更记录

## v1.1：2026-10-12，纠正 H3C NAT 控制例的厂商撤销语法

独立审查发现 `h3c-08-nat-inbound-control.cfg` 先前把创建命令的 `inside` 参数机械复制到撤销命令。这不能代表所选 H3C 普通服务器映射的合法撤销操作，属于测试输入错误。

根据 [H3C SecPath V7 R9900 NAT 命令参考](https://www.h3c.com/en/d_202511/2698500_294551_0.htm)中普通服务器映射语法，撤销按协议、外侧地址及外侧端口选择映射，不携带内侧地址。控制例改为：

```text
undo nat server protocol tcp global 203.0.113.10 443
```

创建命令、主机和接口不变。人工预期继续为 `nat=[]`，并继续禁止 `NAT-INBOUND-MAPPING`；仅补充官方来源及改动说明，没有复制程序实际输出，也没有降低阈值或删除样例。数据集 ID 升为 `campus-synthetic-gold-v1.1`，清单保存旧配置/预期的 SHA256 和变更来源，并重新冻结资产校验和。

先运行尚未修复的解析器，确认合法控制例确实暴露缺陷：风险 TP26/FP1/FN0，precision96.30%、字段99.47%，但控制例的不应报断言失败，验收退出 1。记录保存在 `reports/acceptance-red-h3c-undo.json`，先失败再修复解析实现；不以放宽金标准消除该失败。

解析实现增加 H3C 独立撤销选择器后，同一 v1.1 冻结数据重新实测为字段 1870/1870、风险 TP26/FP0/FN0，precision/recall100%，验收退出 0。未知匹配仍单列为 8、额外 1、缺失 0；额外项来自 H3C 路由描述参数的保守提示，没有调整该预期。实际结果以重新生成的 `reports/acceptance.json` 为准。

同时核对 [Huawei 接口视图 nat server 参考](https://info.support.huawei.com/hedex/api/pages/EDOC1100278054/AEL11217/08/resources/dc/nat_server.html)：该命令族的 `undo` 保留内侧主机参数，不能照搬 H3C 的外侧选择器。它与 Huawei NAT 实例/系统视图、H3C 其他复杂服务器映射语法也需分开。本版 50 例不含 Huawei NAT 撤销控制，因此这里只记录官方语法核对，不声称已在金标准中独立验收该场景。

这些配置仍为人工合成片段；官方文档核对不等于设备运行验证。
