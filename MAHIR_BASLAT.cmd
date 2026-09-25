@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem %* : terminalden `MAHIR_BASLAT.cmd -Kip bulut` de calissin. Cift
rem tiklamada arguman gelmez ve betik varsayilan `-Kip yerel` ile acilir.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0MAHIR_BASLAT.ps1" %*
pause
