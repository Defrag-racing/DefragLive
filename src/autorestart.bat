@echo off
setlocal EnableDelayedExpansion

:: Ensure log file exists
if not exist restart_log.txt echo Log started at %date% %time% > restart_log.txt

:loop
:: Log restart attempt
echo Restarting bot.py at %date% %time% >> restart_log.txt

:: Start bot.py
start "bot.py" python bot.py

:: Wait 5 seconds for the PID file to be created with single-line countdown
echo Waiting for bot.py to create PID file...
for /l %%i in (5,-1,0) do (
    <nul set /p "=Waiting %%i seconds, press CTRL+C to quit ... "
    ping -n 2 127.0.0.1 > nul
    if %%i gtr 0 (echo.)
)
echo Done.

:: Read the PID from the file
if exist bot_pid.txt (
    set /p BOT_PID=<bot_pid.txt
    echo bot.py started with PID !BOT_PID! >> restart_log.txt
) else (
    echo Failed to find bot.py PID at %date% %time% >> restart_log.txt
    echo Retrying after 5 seconds...
    for /l %%i in (5,-1,0) do (
        <nul set /p "=Waiting %%i seconds, press CTRL+C to quit ... "
        ping -n 2 127.0.0.1 > nul
        if %%i gtr 0 (echo.)
    )
    echo Done.
    goto loop
)

:: Wait 5 hours (18,000 seconds) with timeout command
echo Waiting 5 hours before restarting bot.py...
timeout /t 18000 /nobreak
:: For testing, you can use:
:: timeout /t 30 /nobreak
echo Done.

:: Kill only the specific bot.py process
taskkill /PID !BOT_PID! /F >> restart_log.txt 2>&1
if %ERRORLEVEL% neq 0 (
    echo Failed to terminate bot.py with PID !BOT_PID! at %date% %time% >> restart_log.txt
)

:: Wait 5 seconds before next restart with single-line countdown
echo Waiting before next restart...
for /l %%i in (5,-1,0) do (
    <nul set /p "=Waiting %%i seconds, press CTRL+C to quit ... "
    ping -n 2 127.0.0.1 > nul
    if %%i gtr 0 (echo.)
)
echo Done.

:: Clean up the PID file
del bot_pid.txt

goto loop