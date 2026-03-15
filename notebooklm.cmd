@echo off
setlocal
set "ROOT=%~dp0"
set "NOTEBOOKLM_HOME=%ROOT%.notebooklm"
set "PLAYWRIGHT_BROWSERS_PATH=%ROOT%.playwright-browsers"
set "PATH=%ROOT%.venv\Scripts;%PATH%"
"%ROOT%.venv\Scripts\notebooklm.exe" %*
