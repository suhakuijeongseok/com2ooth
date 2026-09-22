$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$node = (Get-Command node -ErrorAction SilentlyContinue).Source
if (-not $node) { throw "Node.js를 찾을 수 없습니다." }
Write-Host "야구 게임 서버: http://localhost:8765/game/"
Write-Host "종료: Ctrl+C"
Start-Process "http://localhost:8765/game/"
& $node (Join-Path $root "game\server.js")
