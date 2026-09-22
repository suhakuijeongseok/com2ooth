@echo off
chcp 65001 >nul
cd /d "%~dp0"

where node >nul 2>nul
if errorlevel 1 (
  echo [오류] Node.js를 찾을 수 없습니다.
  echo Node.js를 설치한 뒤 다시 실행해 주세요.
  pause
  exit /b 1
)

echo 야구 게임 서버를 시작합니다.
echo 브라우저 주소: http://localhost:8765/game/
echo.
echo 서버를 종료하려면 이 창에서 Ctrl+C를 누르세요.
echo.

start "" "http://localhost:8765/game/"
node "%~dp0game\server.js"

if errorlevel 1 (
  echo.
  echo 서버 실행 중 오류가 발생했습니다.
  pause
)
