# Stops the ClipMitra engine (leaves Ollama running; quit it from the tray if you like).
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Write-Host "ClipMitra engine stopped."
