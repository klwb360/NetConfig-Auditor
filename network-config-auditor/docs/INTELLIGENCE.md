# CVE 与 KEV 情报

NetAudit 将配置审计、产品漏洞适用性和已知利用记录分别展示。配置中的 Cisco、Huawei 或 H3C 品牌不能证明设备型号或固件版本。工具不会按品牌给设备套用 CVE，也不会把 KEV 条目写成“设备已被攻陷”。

默认分析完全在本机进行，不访问互联网。发行包包含 CISA 官方 KEV 快照；NVD 数据由用户显式导入。CVE 适用性仍需实际设备信息和厂商公告复核。

## 内置 KEV 的来源

- 发布机构：[CISA](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)。
- 原始 JSON：[cisagov/kev-data 官方仓库](https://raw.githubusercontent.com/cisagov/kev-data/develop/known_exploited_vulnerabilities.json)。
- 随包快照：`2026.10.02`，发布于 `2026-10-02T15:19:38.2945Z`，共 **1733 条**。
- 原始文件 SHA-256：`d2c8c6cb23291b46ff2b086197641a6b1fa35e6b746bba714cc280a1778f9e48`。
- 文件位置：`netaudit/data/kev.json`，来源与获取时间见 `kev-source.json`。
- 数据采用 **CC0 1.0**；完整条款见 `netaudit/data/KEV-LICENSE.txt`，归属说明见 `KEV-NOTICE.txt`。此许可不覆盖数据中的第三方链接，也不改变 NetAudit 的 GPL-3.0-only 许可。

载入内置快照时检查 SHA-256。日期超过 30 天、缺失或明显晚于本机日期时，报告提示核对时效。SHA-256 检查文件完整性，不能认证用户导入数据的出处。

## 设备信息与导入格式

设备元数据使用 JSON，例如：

```json
{
  "cpe": "cpe:2.3:o:cisco:ios_xe:17.3.1:*:*:*:*:*:*:*",
  "cve_ids": ["CVE-2023-20198"]
}
```

这个例子只演示元数据格式，不是该版本受到 CVE-2023-20198 影响的判断。`cpe` 应根据实际型号、系统版本和官方 CPE 标识填写。`cve_ids` 是用户提供的待核查编号；单独提供编号不会产生版本适用性确认。最多可提供 256 个编号。

KEV 导入接受 CISA 的 `catalogVersion`、`dateReleased`、`count` 和 `vulnerabilities` 格式。NVD 导入接受 [CVE API 2.0](https://nvd.nist.gov/developers/vulnerabilities) 的对象，其中 `vulnerabilities` 是 `{"cve": ...}` 列表，`cve.configurations` 保留产品 CPE、布尔条件和版本边界。请从官方 NVD 导出相关产品或待核查 CVE 的完整记录子集；不要只复制标题、描述或品牌关键词。

每个 KEV / NVD JSON 最大 **16 MiB**，最多 50,000 条；完整 NVD 数据库通常超出该限制。顶层必须是 UTF-8 JSON 对象，重复 CVE、错误编号、错误布尔值或过深嵌套会被拒绝。不会因为删除不支持的条件而将条目变成“适用”。

## 如何理解结果

| 结果 | 含义 |
| --- | --- |
| `matches` / `cpe-version-match` | 明确 CPE 与版本符合已载入 NVD 的简单 OR 条件；需继续核对厂商公告与设备功能。 |
| `candidates` / `needs-review` | 产品相关，但版本未知、复杂 AND / 否定 / 环境条件、版本边界或平台属性无法可靠判断。 |
| `candidates` / `user-provided-candidate` | 用户提供 CVE 编号，但尚未证明当前产品和版本适用。 |
| `known_exploited: true` | 同一 CVE 在载入的 CISA KEV 中有已知真实利用记录。 |
| `no-matches` | 本次载入的情报未发现明确命中；不代表设备安全，也不代表完整漏洞覆盖。 |
| `not-configured` | 缺少用于判定版本适用性的设备 CPE 或 NVD 记录。 |

支持明确 CPE 和简单 OR 适用路径。CPE 的 part 必须为 `a`、`o` 或 `h`；厂商或产品为 `*`、`-` 或带通配符时只提示待复核，不能确认匹配。数值版本边界采用按段比较，例如 `16.12.1`；`16.12.1a`、包含转义字符等厂商专用版本排序不会被猜测。复杂 AND、否定、环境约束和无法比较的版本保留为待复核；某条明确 OR 路径已经满足时，可按该路径命中。NVD 标记 `Rejected` 的记录不会作为有效漏洞命中。

KEV 的 `requiredAction` 是官方建议；`dueDate` 是美国联邦机构指令适用期限，不是本工具给所有用户强制设定的整改期限。

## 显式更新与联网范围

CLI 和网页均可导入用户选取的本地 KEV / NVD JSON。显式 KEV 更新入口只向上面固定的 CISA 官方原始文件地址发送下载请求，不发送配置、主机名、IP、CPE 或 CVE 候选。更新文件写入用户指定位置或用户缓存目录，普通启动不会改写安装文件夹。

网络不可用时仍可使用内置快照和本地导入。此次开发环境实际取得了官方 KEV；访问 NVD 官方 API 被环境代理返回 403，因此 NVD 匹配验收使用明确标为合成的 2.0 格式测试数据，未声称已下载或验证真实 NVD 适用范围。

报告记录来源、快照日期、条目数、时效、来源类型和可取得的文件 SHA-256，方便复核。默认分析过程中不上传任何配置。
