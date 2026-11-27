<#
  Wonder Clips — one-click installer for Windows 10/11.

  Run in PowerShell:
      irm https://raw.githubusercontent.com/wondermayank/wonderclip/main/engine/install.ps1 | iex

  What it does (safe to run again to update; your videos and clips are kept):
    1. Installs FFmpeg, Ollama, Deno (for YouTube links) and uv with winget (skips what you have)
    2. Downloads Wonder Clips into %LOCALAPPDATA%\ClipMitra\app
    3. Creates a Python 3.12 environment and installs the engine's packages
    4. Downloads the AI models: Qwen3-4B (Ollama, ~2.5 GB), Whisper large-v3-turbo (~1.6 GB),
       MediaPipe face landmarker (~4 MB)
    5. Adds a "Wonder Clips" shortcut to the Desktop and Start menu
  Then double-click "Wonder Clips": it starts the engine and opens https://clips.wondermayank.in
  Everything runs on your computer. Nothing is uploaded anywhere.
#>
param(
  [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "ClipMitra"),
  [string]$Source = "https://github.com/wondermayank/wonderclip/archive/refs/heads/main.zip",  # or a local .zip/folder
  [switch]$SkipModels,      # tests: don't download the large models
  [switch]$NoShortcuts,
  [switch]$FromSetup        # run by ClipMitra-Setup.exe: keep the window open on errors
)
$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Installing Wonder Clips"
New-Item -ItemType Directory -Force $InstallRoot | Out-Null
try { Start-Transcript -Path (Join-Path $InstallRoot "install.log") -Force | Out-Null } catch { }  # for support
trap {
  try { Write-Host ($_ | Out-String) } catch { }   # full error (with line number) goes into install.log
  Write-Host "`nWonder Clips could not be installed:" -ForegroundColor Red
  Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
  Write-Host "`nCheck your internet connection and run the installer again. If it keeps failing, see"
  Write-Host "https://github.com/wondermayank/wonderclip#for-users"
  if ($FromSetup) { Read-Host "`nPress Enter to close" }
  exit 1
}
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest is 10x faster without the progress bar

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Magenta }
function Ok($msg) { Write-Host "    $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }
function Refresh-Path {
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
function Has($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Run($exe, [string[]]$argv) {
  # Native tools print progress on stderr; only the exit code decides success.
  # Start-Process does not quote arguments: quote any with spaces (e.g. C:\Users\First Last\...).
  $quoted = $argv | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }
  # Capture the tool's own output so it lands in install.log (the transcript doesn't see child output).
  $out = [IO.Path]::GetTempFileName(); $err = [IO.Path]::GetTempFileName()
  $p = Start-Process -FilePath $exe -ArgumentList $quoted -NoNewWindow -Wait -PassThru `
         -RedirectStandardOutput $out -RedirectStandardError $err
  $text = ((Get-Content $out -Raw -ErrorAction SilentlyContinue) + (Get-Content $err -Raw -ErrorAction SilentlyContinue))
  Remove-Item $out, $err -ErrorAction SilentlyContinue
  $lines = @($text -split "`r?`n" | Where-Object { $_.Trim() })
  if ($lines) { $lines | Select-Object -Last 15 | ForEach-Object { Write-Host "      $_" -ForegroundColor DarkGray } }
  if ($p.ExitCode -ne 0) { throw "$exe $($argv -join ' ') failed (exit $($p.ExitCode)): $($lines | Select-Object -Last 3)" }
}

Write-Host "Wonder Clips installer" -ForegroundColor White
Write-Host "Install folder: $InstallRoot"

# ---------------------------------------------------------------- 0. checks
Step "Checking your computer"
if (-not [Environment]::Is64BitOperatingSystem) { throw "Wonder Clips needs 64-bit Windows." }
if (-not (Has winget)) { throw "winget is missing. Install 'App Installer' from the Microsoft Store, then run this again." }
$gpu = $null
if (Has nvidia-smi) { $gpu = (& nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>$null | Select-Object -First 1) }
if ($gpu) { Ok "NVIDIA GPU: $gpu" } else { Warn "No NVIDIA GPU found: Wonder Clips will run on the CPU (works, but several times slower)." }
$free = (Get-PSDrive ($InstallRoot.Substring(0, 1))).Free / 1GB
if (-not $SkipModels -and $free -lt 8) { throw ("Need about 8 GB free disk space; only {0:N1} GB available." -f $free) }

# ---------------------------------------------------------------- 1. tools
Step "Installing tools (FFmpeg, Ollama, Deno, uv)"
$tools = @(
  @{ cmd = "ffmpeg"; id = "Gyan.FFmpeg" },
  @{ cmd = "ollama"; id = "Ollama.Ollama"; extra = (Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe") },
  @{ cmd = "deno"; id = "DenoLand.Deno" },
  @{ cmd = "uv"; id = "astral-sh.uv" }
)
Refresh-Path   # this window may predate tools installed elsewhere (or by an earlier run)
foreach ($t in $tools) {
  $present = { (Has $t.cmd) -or ($t.extra -and (Test-Path $t.extra)) }
  if (& $present) { Ok "$($t.cmd): already installed"; continue }
  Write-Host "    installing $($t.id)…"
  $p = Start-Process -FilePath "winget" -NoNewWindow -Wait -PassThru -ArgumentList @(
    "install", "--id", $t.id, "-e", "--silent", "--accept-source-agreements", "--accept-package-agreements")
  Refresh-Path
  # winget returns non-zero for "already installed / no newer version" — what matters is that the tool exists now
  if (-not (& $present)) { throw "Installing $($t.id) failed (winget exit $($p.ExitCode)). Install it manually and run this again." }
  Ok "$($t.cmd): installed"
}
Refresh-Path
$ollama = if (Has ollama) { (Get-Command ollama).Source } else { Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe" }
if (-not (Has uv)) { throw "uv was installed but isn't on PATH yet. Close this window, open a new PowerShell and run the installer again." }

# ---------------------------------------------------------------- 2. app files
# A running engine keeps files in the app folder open, which would block the update.
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
  $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)"
  if ($proc.CommandLine -match "uvicorn\s+app\.main:app") {
    Stop-Process -Id $proc.ProcessId -Force
    Ok "stopped the running Wonder Clips engine for the update"
  }
}
Start-Sleep -Milliseconds 500
Step "Downloading Wonder Clips"
$app = Join-Path $InstallRoot "app"
$data = Join-Path $InstallRoot "data"
New-Item -ItemType Directory -Force $InstallRoot, $data | Out-Null
$staging = Join-Path $InstallRoot "_new"
Remove-Item -Recurse -Force $staging -ErrorAction SilentlyContinue
if (Test-Path $Source -PathType Container) {
  Copy-Item -Recurse $Source $staging
} else {
  $zip = Join-Path $InstallRoot "clipmitra.zip"
  if (Test-Path $Source -PathType Leaf) { Copy-Item $Source $zip } else { Invoke-WebRequest $Source -OutFile $zip }
  Expand-Archive $zip (Join-Path $InstallRoot "_unzip") -Force
  $unz = (Get-ChildItem (Join-Path $InstallRoot "_unzip") -Directory | Select-Object -First 1).FullName
  if (Test-Path (Join-Path $unz "engine")) { $unz = Join-Path $unz "engine" }   # repo layout: engine/ + web/
  Move-Item $unz $staging
  Remove-Item -Recurse -Force $zip, (Join-Path $InstallRoot "_unzip")
}
# keep the existing Python environment on updates (saves a big re-download)
$oldVenv = Join-Path $app "backend\.venv"
if (Test-Path $oldVenv) { Move-Item $oldVenv (Join-Path $staging "backend\.venv") }
Remove-Item -Recurse -Force $app -ErrorAction SilentlyContinue
Move-Item $staging $app
Ok "app: $app"

# Data lives outside the app folder so updates never touch your videos, clips or models.
$envFile = Join-Path $app "backend\.env"
@"
CLIPMITRA_UPLOAD_DIR=$data\uploads
CLIPMITRA_OUTPUT_DIR=$data\outputs
CLIPMITRA_TEMP_DIR=$data\temp
CLIPMITRA_MODEL_DIR=$data\models
CLIPMITRA_DB_PATH=$data\clipmitra.db
"@ | Set-Content -Encoding ascii $envFile

# ---------------------------------------------------------------- 3. python
Step "Setting up the engine (Python 3.12 + packages, a few minutes the first time)"
Push-Location (Join-Path $app "backend")
if (-not (Test-Path ".venv\Scripts\python.exe")) { Run "uv" @("venv", "--python", "3.12", ".venv") }
Run "uv" @("pip", "install", "--python", ".venv\Scripts\python.exe", "-r", "requirements.txt")
Pop-Location
$py = Join-Path $app "backend\.venv\Scripts\python.exe"
Ok "engine ready"

# ---------------------------------------------------------------- 4. models
if ($SkipModels) {
  Warn "Skipping model downloads (-SkipModels)."
} else {
  Step "Downloading AI models (about 4 GB in total; this is the slow part)"
  $mp = Join-Path $data "models\mediapipe"
  New-Item -ItemType Directory -Force $mp | Out-Null
  $task = Join-Path $mp "face_landmarker.task"
  if (-not (Test-Path $task)) {
    Invoke-WebRequest "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task" -OutFile $task
  }
  Ok "face tracker"
  # Ollama must be running to pull
  try { Invoke-RestMethod "http://127.0.0.1:11434/api/version" -TimeoutSec 2 | Out-Null } catch {
    $trayApp = Join-Path (Split-Path $ollama) "ollama app.exe"
    if (Test-Path $trayApp) { Start-Process $trayApp } else { Start-Process $ollama -ArgumentList "serve" -WindowStyle Hidden }
    for ($i = 0; $i -lt 30; $i++) { try { Invoke-RestMethod "http://127.0.0.1:11434/api/version" -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep 1 } }
  }
  Run $ollama @("pull", "qwen3:4b")
  Ok "Qwen3-4B"
  Run $py @((Join-Path $app "scripts\download_models.py"))
  Ok "Whisper large-v3-turbo"
}

# ---------------------------------------------------------------- 5. shortcuts
$start = Join-Path $app "scripts\start_clipmitra.ps1"
if (-not $NoShortcuts) {
  Step "Adding Wonder Clips shortcuts"
  $ws = New-Object -ComObject WScript.Shell
  foreach ($dir in @([Environment]::GetFolderPath("Desktop"), (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"))) {
    $lnk = $ws.CreateShortcut((Join-Path $dir "Wonder Clips.lnk"))
    $lnk.TargetPath = "powershell.exe"
    $lnk.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$start`""
    $lnk.WorkingDirectory = $app
    $lnk.Description = "Start Wonder Clips and open it in your browser"
    $lnk.Save()
  }
  Ok "Desktop + Start menu: Wonder Clips"
}

if ($FromSetup) { Step "Done! You can close this window." ; exit 0 }
Step "Done!"
Write-Host "    Double-click 'Wonder Clips' on your Desktop. It opens https://clips.wondermayank.in"
Write-Host "    The first time, your browser asks to allow access to apps on this device: choose Allow."
