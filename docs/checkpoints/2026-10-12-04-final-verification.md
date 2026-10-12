# 检查点04：最终回归与Windows冻结验收

- 最终代码：`caf3717a131f6ca7cd8c6b477628ba528a6b129e`，Windows471+506、Linux每版本470+1跳过+506。
- 覆盖：行93.10%、分支88.17%、综合91.41%，门禁80%。
- 公开CI：Windows38226564521、Linux38226564305/38226557637均成功。
- Windows实际构建源码：PR自动合并提交 `3789bff692bede73c0be723a3f1e9feea174c050`；九文件artifact11735878519 SHA `1cce7847d092cfd4665f7b9c2926f031910d205140d24db23e4fa735b7830a67`。
- 源码/onedir/onefile28真实进程检查；clean-runtime独立runner6检查，两种冻结包各50文件。
- 本地Windows11构建18f8550，28检查及两种EXE各50金标准，源码及冻结指标1870/1870、TP26/FP0/FN0。
- 修复Windows BAT CRLF执行错误，隔离Windows py launcher路径，保护gold原始换行字节；新增5项测试。独立复核无剩余P0/P1。
- 新产物和报告存入用户工作区outputs，固定验收报告在 `docs/acceptance/v1.1.0/`。
- 尚未执行：PR合并、主分支1.1.0成功构建/正式发布、旧仓库删除。
- 清理约束：旧仓库ID1402731653/private、旧main535653c、完整Git/21附件/元数据备份、公开目标ID1415268968需再次核验。当前Git OAuth缺delete_repo；浏览器未登录。不得删除Codex-code，不得把GitHub权限限制说成用户未授权。
- 下一步：更新PR新增/修复/证据，合并保留历史，等待主分支CI并正式发布；最后尝试已授权的精确旧仓库删除。必要登录或权限动作仅在工作已具体可审阅后请求。
