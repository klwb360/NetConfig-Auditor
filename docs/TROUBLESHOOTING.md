# NetConfig Auditor 故障排查

本文对应 v1.1.1 源码。先确认从 [最新 Release](https://github.com/klwb360/NetConfig-Auditor/releases/latest) 的 **Assets** 下载了 `*-portable.zip`，并完整解压一次。若使用开发或备份用的 Actions 产物，需要先解压外层 ZIP，再解压内部便携 ZIP。完整下载步骤见 [常见问题](FAQ.md)，实际校验与验收范围见 [交付记录](../DELIVERY.md)。

## 无法下载或解压后没有程序

当前仓库公开，无需 GitHub 登录即可下载。优先在 [最新 Release](https://github.com/klwb360/NetConfig-Auditor/releases/latest) 的 **Assets** 下载便携 ZIP；下载失败时检查网络及发布页中的具体附件。GitHub 自动生成的 “Source code” 只包含源码，不包含 Windows EXE。

## 双击后没有正常启动

| 现象 | 检查与处理 |
|---|---|
| 提示需要 Python 3.10 或更新版本 | 当前运行的是源码版，或 EXE 没有与 BAT 放在同一目录。普通用户下载便携 EXE 包并完整解压；无需安装 Python、pip 或 PyInstaller。 |
| 提示找不到 EXE 或完整源码 | 确认已经完整解压 Release 的便携 ZIP，且运行的是其中的 BAT；使用 Actions 包时还需解压内部 `portable.zip`。不要只下载单个 BAT。 |
| EXE 提示缺少运行库、`base_library.zip` 或模块 | 重新完整解压便携 ZIP，保留 `_internal`。可用产物内的 SHA-256 清单检查文件；不要混用不同构建的 EXE 和运行库。 |
| 启动窗口一闪而过 | 在解压文件夹中打开命令提示符，运行 `Start-NetConfig-Auditor.bat`，保留窗口中的错误信息。BAT 仅在识别到无参数 Explorer 双击且启动错误时暂停，不能依赖所有启动方式都会停住。 |
| 单 EXE 等待较久或解压失败 | 等待几秒；确认用户临时目录有可写空间。优先使用便携文件夹版；只读程序目录不要求可写，但临时目录仍需可写。 |

中文和带空格的路径已在 Windows runner 验收。命令行中的配置、报告或程序路径含空格时，请使用双引号：

```bat
"D:\网络工具\NetConfig Auditor 便携版\NetConfig-Auditor.exe" audit "D:\设备配置\核心交换机.cfg" --vendor cisco --format md --out "D:\审计报告\核心交换机.md"
```

## 浏览器没有打开，或网页不能访问

查看启动窗口中的实际 `http://127.0.0.1:端口` 地址，复制到浏览器。默认端口是 8765；被占用或不可用时程序会选择空闲端口，旧地址可能不再适用。

需要手动管理浏览器或指定端口时，在便携文件夹中运行：

```bat
Start-NetConfig-Auditor.bat serve --no-browser
Start-NetConfig-Auditor.bat serve --port 9000 --no-browser
```

若网页显示连接失败，检查启动窗口是否仍在运行。若页面提示会话或来源错误，重新打开当前启动窗口中的完整地址并刷新页面；服务仅供本机浏览器访问，不应通过远程 IP 或其他站点嵌入。网页样式或脚本缺失时，重新完整解压匹配版本的便携包。

## 配置不能导入或厂商识别失败

将原始配置保存为 UTF-8 文本；CLI 同时接受带 UTF-8 BOM 的文件。网页可导入 `.cfg`、`.conf`、`.txt`，也可直接粘贴。不要把 Word、PDF、截图或压缩文件作为配置输入。

一次输入一台设备，去掉提示符、分页符和终端控制字符。华为与 H3C 配置可能只包含共享命令，请明确选择厂商；混合厂商标记会拒绝自动猜测。可先使用网页“载入示例”确认基本流程。

每份配置限制为 2 MiB、30000 行，另有接口与 ACL 数量限制，详见 [项目说明](../network-config-auditor/README.md#本地运行与配置保护)。未建模行不代表文件损坏；查看清单中的警告并核对 [支持范围](../network-config-auditor/README.md#支持范围)。

## 报告没有保存，或命令返回非零退出码

网页导出请检查浏览器下载列表与下载目录；CLI 使用 `--out` 明确指定自己可写的位置。输入配置和输出报告不能是同一个文件。格式参数是 `json`、`md`、`html`，其中 Markdown 使用 `md`。

| 退出码 | 含义 |
|---|---|
| 0 | 调用成功；仍需查看审计结果，不能据此认定配置安全。 |
| 1 | 使用 `--fail-on` 后，发现达到指定严重度的问题；报告已按要求输出。 |
| 2 | 参数、输入、编码、文件或启动错误；也可能是 `--strict` 检出未建模行，此时仍输出报告。请查看窗口中的具体提示。 |

传入参数时 BAT 不会 `pause`，可用于自动化。源码 CLI 的更多示例见 [项目说明](../network-config-auditor/README.md#最快开始)。

## 网页关了，程序仍在运行

关闭网页不会关闭服务。回到对应启动窗口按 Ctrl+C，等待程序退出；再次启动后使用新窗口显示的地址。不要仅靠关闭标签页判断退出状态。

## 仍无法解决时如何反馈

在公开 [仓库 Issues](https://github.com/klwb360/NetConfig-Auditor/issues) 提供 Windows 版本、使用的文件名或源码提交、启动方式、实际提示与复现步骤。可附 SHA-256 校验结果及脱敏的最小配置样例；不要提交真实凭据、完整内部配置或未经检查的报告。

目前真实验收环境为 Windows Server 2022 x64。Windows 10/11、普通非管理员账户、物理无 Python 电脑、真实 Explorer 双击与可视浏览器交互尚未实测，不能把当前记录视为这些环境的验收结论。详细边界见 [交付记录](../DELIVERY.md)。
