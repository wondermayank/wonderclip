"""Generate the Phase 5 test videos into backend/temp/phase5/ (idempotent).

Sources already on disk: backend/temp/landscape_face_test.mp4 (real face, Hindi audio, moving),
the creator reel in backend/uploads (vertical, Hindi), and Windows SAPI voices (English, known text).

    backend/.venv/Scripts/python scripts/phase5_fixtures.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
OUT = BACKEND / "temp" / "phase5"
LANDSCAPE = BACKEND / "temp" / "landscape_face_test.mp4"
SCRIPT = (ROOT / "scripts" / "sample_script.txt").read_text("utf-8")
EXTRA = (ROOT / "scripts" / "sample_script_extra.txt").read_text("utf-8")


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def duration(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def speak(text: str, wav: Path, voice: str = "Microsoft David Desktop", rate: int = 0) -> None:
    txt = wav.with_suffix(".txt")
    txt.write_text(text, "utf-8")
    ps = ("Add-Type -AssemblyName System.Speech;"
          "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
          f"$s.SelectVoice('{voice}'); $s.Rate = {rate};"
          f"$s.SetOutputToWaveFile('{wav}');"
          f"$s.Speak([IO.File]::ReadAllText('{txt}')); $s.Dispose()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    txt.unlink()


def reel() -> Path:
    db = BACKEND / "data" / "clipmitra.db"
    import sqlite3
    row = sqlite3.connect(db).execute(
        "select id, ext from uploads where filename like 'my reel%' or filename like '%reel%' limit 1").fetchone()
    if not row:
        sys.exit("creator reel not found in uploads (upload it once through the app)")
    return BACKEND / "uploads" / f"{row[0]}{row[1]}"


def make(name: str, build) -> Path:
    p = OUT / name
    if not p.exists():
        print("building", name, flush=True)
        build(p)
    return p


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    truths: dict[str, str] = {}

    # --- 1. milestone: ~5 min English talk over a moving real face (landscape) ----------------
    def long5(p: Path) -> None:
        wav = OUT / "long.wav"
        speak(SCRIPT + "\n\n" + EXTRA, wav, rate=1)  # rate 0 runs 301 s, just over the limit
        d = duration(wav)
        if d > 299:
            sys.exit(f"long speech is {d:.0f}s, over the 5-minute limit — shorten sample_script_extra.txt")
        ff("-stream_loop", "-1", "-i", str(LANDSCAPE), "-i", str(wav), "-map", "0:v", "-map", "1:a",
           "-t", f"{d:.2f}", "-c:v", "h264_nvenc", "-cq", "24", "-c:a", "aac", str(p))
        wav.unlink()
    make("long_5min_en.mp4", long5)
    truths["long_5min_en.mp4"] = SCRIPT + " " + EXTRA

    # --- 2. resolutions / frame rates (same 65 s Hindi talking head) ---------------------------
    for name, vf, extra in [
        ("res_480p25.mp4", "scale=854:480,fps=25", []),
        ("res_720p60.mp4", "scale=1280:720,fps=60", []),
        ("res_4k30.mp4", "scale=3840:2160:flags=lanczos", []),
        ("square_1080.mp4", "crop=1080:1080:(iw-1080)/2:0", []),
    ]:
        make(name, lambda p, vf=vf: ff("-i", str(LANDSCAPE), "-vf", vf, "-c:v", "h264_nvenc", "-cq", "22",
                                       "-c:a", "copy", str(p)))

    # --- 3. phone video stored sideways + rotation flag (common for iPhone .mov) ---------------
    def rotated(p: Path) -> None:
        tmp = OUT / "_sideways.mp4"
        # store pixels rotated 90° clockwise (1920x1080), then flag "display rotated" so players show it upright
        ff("-i", str(reel()), "-vf", "transpose=1", "-c:v", "h264_nvenc", "-cq", "22", "-c:a", "copy", str(tmp))
        ff("-display_rotation", "90", "-i", str(tmp), "-c", "copy", str(p))
        tmp.unlink()
    make("phone_rotated.mov", rotated)

    # --- 4. two people in frame (same speaker mirrored) -----------------------------------------
    make("two_faces.mp4", lambda p: ff(
        "-f", "lavfi", "-i", "color=c=0x22222c:s=1920x1080:r=30", "-i", str(reel()),
        "-filter_complex", "[1:v]scale=-2:1080,split[a][b];[b]hflip[bf];"
                           "[0:v][a]overlay=x=230:y=0:shortest=1[t];[t][bf]overlay=x=1080:y=0",
        "-map", "1:a", "-c:v", "h264_nvenc", "-cq", "22", "-c:a", "aac", "-t", "65", str(p)))

    # --- 5. different voice + noisy audio (known text -> word error rate) -------------------------
    half = " ".join(SCRIPT.split()[:330])

    def female(p: Path) -> None:
        wav = OUT / "zira.wav"
        speak(half, wav, "Microsoft Zira Desktop", rate=1)
        ff("-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30", "-i", str(wav), "-shortest",
           "-c:v", "h264_nvenc", "-c:a", "aac", str(p))
        wav.unlink()
    make("voice_female.mp4", female)
    truths["voice_female.mp4"] = half

    def clean_and_noisy(p: Path) -> None:
        wav = OUT / "david_half.wav"
        speak(half, wav)
        ff("-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30", "-i", str(wav), "-shortest",
           "-c:v", "h264_nvenc", "-c:a", "aac", str(OUT / "voice_male_clean.mp4"))
        # pink noise + low hum mixed under the speech (~5 dB SNR) — a noisy room
        ff("-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30", "-i", str(wav),
           "-f", "lavfi", "-i", "anoisesrc=color=pink:amplitude=0.22:sample_rate=22050",
           "-f", "lavfi", "-i", "sine=frequency=100:sample_rate=22050",
           "-filter_complex", "[2:a]volume=1[n];[3:a]volume=0.12[h];[1:a][n][h]amix=inputs=3:duration=first:normalize=0[a]",
           "-map", "0:v", "-map", "[a]", "-shortest", "-c:v", "h264_nvenc", "-c:a", "aac", str(p))
        wav.unlink()
    make("voice_male_noisy.mp4", clean_and_noisy)
    truths["voice_male_clean.mp4"] = half
    truths["voice_male_noisy.mp4"] = half  # pink noise ~7 dB below speech (measured: speech -20.5, noise -27.4 dBFS)

    # Harder: noise as loud as the speech (0 dB SNR) and louder than it (-5 dB SNR).
    for name, amp in [("voice_male_snr0.mp4", 0.49), ("voice_male_snr-5.mp4", 0.87)]:
        make(name, lambda p, amp=amp: ff(
            "-i", str(OUT / "voice_male_clean.mp4"),
            "-f", "lavfi", "-i", f"anoisesrc=color=pink:amplitude={amp}:sample_rate=22050",
            "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:normalize=0[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", str(p)))
        truths[name] = half

    # --- 6. failure inputs ------------------------------------------------------------------------
    def corrupt(p: Path) -> None:
        data = (OUT / "res_480p25.mp4").read_bytes()
        p.write_bytes(data[: len(data) // 3])  # truncated: moov atom at the end is lost
    make("corrupt_truncated.mp4", corrupt)
    make("no_speech_music.mp4", lambda p: ff(
        "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=40",
        "-f", "lavfi", "-i", "sine=frequency=220:duration=40", "-f", "lavfi", "-i", "sine=frequency=330:duration=40",
        "-filter_complex", "[1:a][2:a]amix=inputs=2[a]", "-map", "0:v", "-map", "[a]",
        "-c:v", "h264_nvenc", "-c:a", "aac", str(p)))
    make("too_long_31m.mp4", lambda p: ff(  # limit is 30 min (+1 s tolerance)
        "-f", "lavfi", "-i", "testsrc2=s=320x180:r=5:d=1860", "-f", "lavfi", "-i", "sine=f=300:d=1860",
        "-c:v", "h264_nvenc", "-c:a", "aac", "-b:a", "32k", str(p)))

    (OUT / "truths.json").write_text(json.dumps(truths, indent=1), "utf-8")
    for f in sorted(OUT.glob("*.m*")):
        print(f"{f.name:28} {f.stat().st_size / 1e6:7.1f} MB")


if __name__ == "__main__":
    main()
