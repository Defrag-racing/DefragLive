@echo off
setlocal EnableDelayedExpansion

:: Ensure log file exists
if not exist restart_log.txt echo Log started at %date% %time% > restart_log.txt

:loop
:: Log restart attempt
echo Restarting bot.py at %date% %time% >> restart_log.txt

:: Start bot.py
start "bot.py" python bot.py

:: Wait briefly for the PID file to be created
timeout /t 2 /nobreak

:: Read the PID from the file
if exist bot_pid.txt (
    set /p BOT_PID=<bot_pid.txt
    echo bot.py started with PID !BOT_PID! >> restart_log.txt
) else (
    echo Failed to find bot.py PID at %date% %time% >> restart_log.txt
    timeout /t 10 /nobreak
    goto loop
)

:: Wait 5 hours (18,000 seconds)
timeout /t 18000 /nobreak

:: Kill only the specific bot.py process
taskkill /PID !BOT_PID! /F >> restart_log.txt 2>&1
if %ERRORLEVEL% neq 0 (
    echo Failed to terminate bot.py with PID !BOT_PID! at %date% %time% >> restart_log.txt
)
timeout /t 10 /nobreak

:: Clean up the PID file
del bot_pid.txt

goto loop