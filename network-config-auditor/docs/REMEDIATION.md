# 建议命令的使用方法

本文对应正在准备的 v0.2.2 源码；已发布 v0.2.1 Windows 包尚不包含新的命令分类。建议由规则根据已建模配置生成，不需要启用 AI。NetAudit 不连接设备、不执行命令，也不自动保存设备配置。

| 报告中的内容 | 用途 |
|---|---|
| 只读核查命令 `verification_commands` | 查看设备型号、软件版本、现有配置与运行状态，确认发现是否适用。 |
| 候选整改命令 `commands` | 所需配置参数已知的完整脚本；仍需人工确认型号、版本、业务和前提。 |
| 需填参数的模板 `command_templates` | 需要业务决策、地址、VLAN 列表、账号或新密钥；必须替换所有 `<参数名>`，不能原样执行。 |
| 前提与验证 `command_notes` | 说明适用条件、管理回退和整改后需要核对的状态。 |

每个整改块包含自己的模式进入与退出，例如 `configure terminal` / `end` 或 `system-view` / `return`。多个对象合并后仍保留完整独立脚本；请按块审阅，不要去掉重复的 `interface`、`exit` 或 `quit`，也不要只复制中间一行到未知视图。

先在设备侧用 `show version` / `display version` 核对型号与版本，并通过命令行 `?` 或对应版本手册确认语法。配置参数已知不代表业务适用性已经确认；未知的管理网段、允许 VLAN、ACL 业务条件和密钥需要由管理员填写。先备份并保留 Console / 带外或备用管理会话，完成验证后再自行决定保存。

切换 SSH、VTY 本地认证或 AAA 前，先验证已有账号、权限、AAA 列表、密钥与备用会话，再用新会话验证登录。`login local` 不会创建账号。`secret` 的语法与可用算法随型号、版本变化；旧版 MD5 secret 仅适合作为过渡，应优先选择平台支持的强哈希或不可逆保护，报告不会恢复原凭据。

创建 VLAN 前，先用 `show vlan` / `display vlan` 核对完整 VLAN 数据库和业务规划；输入未见定义不等于设备未创建。调整 STP 前，复核根桥、链路角色、冗余拓扑与现有运行状态；`switchport protected` 表示端口隔离，不能替代 STP 环路防护。

## 锐捷官方参考与核对范围

本轮核对的官方网页入口：

- [SSH 与 VTY 配置](https://www.ruijie.com.cn/fw/wt/35612/)
- [VTY 来源 ACL](https://www.ruijie.com.cn/fw/wt/18881/)
- [VLAN 配置](https://www.ruijie.com.cn/fw/wt/35635/)
- [STP 配置](https://www.ruijie.com.cn/fw/wt/32511/)
- [S29 系列 RGOS 11.4 B79 命令参考入口](https://www.ruijie.com.cn/fw/wd/89534/)
- [锐捷 SNMP 命令参考](https://www-file.ruijie.com.cn/Fu/Article/061ebe5a-9073-44bb-97ac-8b2c9b4edebd/v0/%E5%AE%98%E7%BD%91%E5%8F%91%E5%B8%83/PDF/00-pdf/13-%E7%BD%91%E7%AE%A1%E4%B8%8E%E7%9B%91%E6%8E%A7.pdf?response-content-type=application%2Foctet-stream)
- [锐捷交换机排障文档：端口 BPDU 过滤开关](https://image.ruijie.com.cn/Upload/Article/09f87c2a-7c18-4ef9-ab28-22c5fa5a4094/%E9%94%90%E6%8D%B7%E4%BA%A4%E6%8D%A2%E6%9C%BA%E4%BA%A7%E5%93%81%E7%BA%BF%E6%95%85%E9%9A%9C%E4%B8%80%E6%9C%AC%E9%80%9A%EF%BC%88V1.0%EF%BC%89/%E4%BA%A4%E6%8D%A2%E6%9C%BA%E4%BA%A7%E5%93%81%E7%BA%BF%E6%95%85%E9%9A%9C%E4%B8%80%E6%9C%AC%E9%80%9AV1.0/db58fcba-a644-4901-96a0-ea258767da90.htm)
- [RG-S5700-H RGOS 11.4 B70P1 基础命令参考（不同产品系列）](https://www-file.ruijie.com.cn/Fu/Article/acd3bcee-dc12-4160-b299-a5808cbd19f9/%E5%AE%98%E7%BD%91%E5%8F%91%E5%B8%83/PDF/00-pdf/RG-S5700-H%E7%B3%BB%E5%88%97%E4%BA%A4%E6%8D%A2%E6%9C%BARGOS%2011.4%281%29B70P1%E7%89%88%E6%9C%AC%E5%91%BD%E4%BB%A4%E6%89%8B%E5%86%8C%28V1.1%29.pdf?response-content-type=application%2Foctet-stream)

这些网页和官方索引用于核对常用命令和操作模式。RGOS 端口 BPDU 过滤关闭使用 `spanning-tree bpdufilter disabled`；Cisco 的拼写不同。部分命令参考 PDF 访问受限，本轮未完成 PDF 全文核对，也未在真实设备上执行建议。B79 参考入口不能证明 RGOS 11.4 B12P24 或其他版本的全部语法兼容；请以实际设备型号、版本和设备侧 `?` 结果为准。
