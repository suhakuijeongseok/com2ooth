@echo off
setlocal
cd /d "%~dp0"
where node.exe >nul 2>nul
if errorlevel 1 goto no_node
echo Starting Baseball Timing Game...
echo URL: http://127.0.0.1:8765/game/
echo Press Ctrl+C to stop the server.
echo.
start "" "http://127.0.0.1:8765/game/"
node.exe "%~dp0game\server.js"
if errorlevel 1 goto server_error
goto end
:no_node
echo ERROR: Node.js was not found.
echo Install Node.js and run this file again.
pause
exit /b 1
:server_error
echo.
echo ERROR: The game server could not start.
echo Another game server may already be using port 8765.
pause
exit /b 1
:end
endlocal
