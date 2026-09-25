@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem BULUT kipi: RAG, OCR ve LLM uzakta (RunPod pod'u) calisir; burada yalniz
rem web katmani (:8000) acilir. Adresler ve parolalar local\.env.bulut'tan
rem okunur - once local\.env.bulut.example dosyasini kopyalayip doldurunuz.
rem Tamamen yerel calismak icin MAHIR_BASLAT.cmd kullaniniz.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0MAHIR_BASLAT.ps1" -Kip bulut
pause
