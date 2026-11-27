# Builds a test video with real (synthesised) speech for end-to-end pipeline runs.
# Output: backend/temp/sample_podcast.mp4  (~4-5 min, 1920x1080, Windows SAPI voice)
$root = Split-Path -Parent $PSScriptRoot
$wav = "$root\backend\temp\sample_speech.wav"
$out = "$root\backend\temp\sample_podcast.mp4"
$text = Get-Content "$PSScriptRoot\sample_script.txt" -Raw

Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = 0
$s.SetOutputToWaveFile($wav)
$s.Speak($text)
$s.Dispose()

cmd /c "ffmpeg -y -v error -f lavfi -i testsrc2=s=1920x1080:r=30 -i `"$wav`" -shortest -c:v libx264 -preset veryfast -crf 28 -c:a aac -b:a 128k `"$out`""
Remove-Item $wav
ffprobe -v error -show_entries format=duration -of csv=p=0 $out
