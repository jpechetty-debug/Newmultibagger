@echo off
setlocal

for /f %%i in ('powershell -NoProfile -Command "(Get-Date).ToString('yyyyMMdd_HHmmss')"') do set "STAMP=%%i"
set "BACKUP_DIR=backups\%STAMP%"

if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

set "ERR=0"
copy /Y "portfolio_history.db" "%BACKUP_DIR%\portfolio_history.db" >nul || set "ERR=1"
copy /Y "stocks.db" "%BACKUP_DIR%\stocks.db" >nul || set "ERR=1"

if "%ERR%"=="0" (
    echo Backup completed to %BACKUP_DIR%
    exit /b 0
) else (
    echo Backup failed
    exit /b 1
)
