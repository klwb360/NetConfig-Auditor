@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONDONTWRITEBYTECODE=1"
set "NETAUDIT_FROM_EXPLORER="

rem Only an argument-free Explorer double-click may pause on error.
rem A plain cmd /c call from automation is not evidence of a double-click.
if not "%~1"=="" goto launch
for /f "delims=" %%E in ('powershell.exe -NoProfile -NonInteractive -Command "$self=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $PID); $shell=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $self.ParentProcessId); $parent=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $shell.ParentProcessId); $levels=0; while ($parent.Name -ieq 'cmd.exe' -and $levels -lt 3) { $shell=$parent; $parent=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $shell.ParentProcessId); $levels++ }; if ($parent.Name -ieq 'explorer.exe' -and $shell.CommandLine -match '(?i)(?:^|\s)/c(?:\s|$)') { 'EXPLORER' }" 2^>nul') do if "%%E"=="EXPLORER" set "NETAUDIT_FROM_EXPLORER=1"

:launch
cd /d "%~dp0"
if errorlevel 1 goto directory_error
if exist "NetAudit.exe" goto exe
if not exist "netaudit\__main__.py" goto source_error

py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 goto python_launcher
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 goto python
python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 goto python3

1>&2 echo 错误：源码版需要 Python 3.10 或更新版本，当前未检测到可用版本。
1>&2 echo 普通用户请下载 Windows 便携 EXE ZIP 包，解压后双击 Start-NetAudit.bat。
1>&2 echo 便携包获取入口：https://github.com/klwb360/NetAudit/releases/latest
1>&2 echo 私人仓库需要先登录具有访问权限的 GitHub 账号。详见同目录使用说明。
set "NETAUDIT_EXIT=2"
goto finish

:exe
"%~dp0NetAudit.exe" %*
set "NETAUDIT_EXIT=%ERRORLEVEL%"
goto finish

:python_launcher
py -3 -m netaudit %*
set "NETAUDIT_EXIT=%ERRORLEVEL%"
goto finish

:python
python -m netaudit %*
set "NETAUDIT_EXIT=%ERRORLEVEL%"
goto finish

:python3
python3 -m netaudit %*
set "NETAUDIT_EXIT=%ERRORLEVEL%"
goto finish

:directory_error
1>&2 echo 错误：无法进入 NetAudit 所在目录。请将整个文件夹解压到可访问的位置。
set "NETAUDIT_EXIT=2"
goto finish

:source_error
1>&2 echo 错误：未找到 NetAudit.exe 或完整源码。请完整解压 Windows 便携 ZIP 包。
1>&2 echo 下载入口：https://github.com/klwb360/NetAudit/releases/latest
set "NETAUDIT_EXIT=2"

:finish
if "%NETAUDIT_EXIT%"=="0" exit /b 0
1>&2 echo NetAudit 已退出，退出码：%NETAUDIT_EXIT%。
if "%NETAUDIT_FROM_EXPLORER%"=="1" pause
exit /b %NETAUDIT_EXIT%
