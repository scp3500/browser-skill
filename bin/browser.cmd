@echo off
REM browser.cmd — 短指令浏览器控制台
REM 输入 browser 即可查看用法

python "%~dp0..\browser_daemon.py" %*
