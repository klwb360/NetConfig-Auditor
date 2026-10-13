@echo off
rem Compatibility entry point; the canonical launcher preserves CLI exit codes.
call "%~dp0Start-NetConfig-Auditor.bat" %*
exit /b %ERRORLEVEL%
