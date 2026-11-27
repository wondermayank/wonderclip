# Starts Ollama and the Wonder Clips engine in the background, then opens the app in the browser.
# Used by the "Wonder Clips" shortcut that install.ps1 creates. Safe to run when already running.
param([string]$Url = "https://clips.wondermayank.in/", [switch]$NoBrowser)
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"   # harmless on Windows; keeps the engine log readable
$app = Split-Path -Parent $PSScriptRoot          # ...\ClipMitra\app
$backend = Join-Path $app "backend"
$logDir = Join-Path (Split-Path -Parent $app) "data\logs"   # ...\ClipMitra\data\logs
New-Item -ItemType Directory -Force $logDir | Out-Null

function Up($u) { try { Invoke-RestMethod $u -TimeoutSec 2 | Out-Null; $true } catch { $false } }

# 1. Ollama (local AI for highlight finding)
if (-not (Up "http://127.0.0.1:11434/api/version")) {
  $tray = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama app.exe"
  if (Test-Path $tray) { Start-Process $tray } else { Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden }
}

# 2. ClipMitra engine on 127.0.0.1:8000 (only reachable from this computer)
if (-not (Up "http://127.0.0.1:8000/api/health")) {
  Start-Process -FilePath (Join-Path $backend ".venv\Scripts\python.exe") `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory $backend -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logDir "engine.log") -RedirectStandardError (Join-Path $logDir "engine-errors.log")
  for ($i = 0; $i -lt 60; $i++) { if (Up "http://127.0.0.1:8000/api/health") { break }; Start-Sleep -Milliseconds 500 }
}

# 3. Open the app (the page connects to the engine on this computer)
if (-not $NoBrowser) { Start-Process $Url }
