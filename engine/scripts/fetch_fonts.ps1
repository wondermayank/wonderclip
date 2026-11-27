# Downloads the caption fonts (Google Fonts, SIL Open Font License) into backend/assets/fonts.
# Static TTFs only: libass picks weights reliably from static files, not from variable fonts.
$dest = Join-Path (Split-Path -Parent $PSScriptRoot) "backend\assets\fonts"
New-Item -ItemType Directory -Force (Join-Path $dest "licenses") | Out-Null
$base = "https://github.com/google/fonts/raw/main/ofl"
$files = @{
  "poppins"     = @("Poppins-Regular.ttf", "Poppins-Bold.ttf", "OFL.txt")
  "anton"       = @("Anton-Regular.ttf", "OFL.txt")
  "bebasneue"   = @("BebasNeue-Regular.ttf", "OFL.txt")
  "archivoblack"= @("ArchivoBlack-Regular.ttf", "OFL.txt")
  "lilitaone"   = @("LilitaOne-Regular.ttf", "OFL.txt")
  "bangers"     = @("Bangers-Regular.ttf", "OFL.txt")
  "mukta"       = @("Mukta-Regular.ttf", "Mukta-Bold.ttf", "OFL.txt")
  "hind"        = @("Hind-Regular.ttf", "Hind-Bold.ttf", "OFL.txt")
  "kalam"       = @("Kalam-Regular.ttf", "Kalam-Bold.ttf", "OFL.txt")
}
foreach ($dir in $files.Keys) {
  foreach ($f in $files[$dir]) {
    $out = if ($f -eq "OFL.txt") { Join-Path $dest "licenses\LICENSE-$dir.txt" } else { Join-Path $dest $f }
    if (Test-Path $out) { continue }
    cmd /c "curl -sSfL -o `"$out`" $base/$dir/$f"
    if ($LASTEXITCODE -ne 0) { Write-Error "failed: $dir/$f"; exit 1 }
  }
}
Get-ChildItem $dest | Select-Object Name, Length
