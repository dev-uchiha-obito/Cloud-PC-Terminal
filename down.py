#!/usr/bin/env python3
"""
download_decrypt_mpd.py

Usage:
    python3 download_decrypt_mpd.py

This script:
- Downloads best video and best audio from a DASH MPD using yt-dlp
- Decrypts them using mp4decrypt (Bento4) with given Widevine keys
- Merges the decrypted video+audio into final_output.mp4 using ffmpeg

Requirements (install on your system):
- yt-dlp (https://github.com/yt-dlp/yt-dlp)
- mp4decrypt (Bento4) - provides mp4decrypt
- ffmpeg

The script contains default MPD and KEYS set from user input; you can edit them or pass via variables below.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# -----------------------
# ====== CONFIG =========
# -----------------------
MPD = "https://media-cdn.classplusapp.com/drm/wv/65af90731ffd3734c4a70d00/e80761cf731ebf4e82c29de281fc5bd1/e80761cf731ebf4e82c29de281fc5bd1.mpd?key=162856104&hdnts=URLPrefix=aHR0cHM6Ly9tZWRpYS1jZG4uY2xhc3NwbHVzYXBwLmNvbS9kcm0vd3YvNjVhZjkwNzMxZmZkMzczNGM0YTcwZDAwL2U4MDc2MWNmNzMxZWJmNGU4MmMyOWRlMjgxZmM1YmQx~Expires=1758283526~hmac=f31053c294bd6db8695671d174a06a6961085e774b0a09ff7d3553d8a3d31d87"

# List of KID:KEY strings (as provided). Keep as-is.
KEYS = [
    "833cac330e3f5243bb92b6b1a1f0b830:33eb631c7784af4a6cc9267ed8cbffb0",
    "af975c9bf15c521e8ca7946fa5d846eb:b5c26089aca357bfcbff3d6b4a0480a9",
    "4b4c8d2ef8885b7db7e8cbaa35157229:f860fe5061896ee121bf09b8050fea67",
    "6f5bc63cfb4c527983544e2be87c3ee3:b626a566974683745075058387989f9b",
    "829e92634faa53d3825d17710a11d8e7:68287246dd16c51cc36232d577f4108a",
]

# final output filename
OUTPUT = "final_output.mp4"

# -----------------------
# ====== Helpers =========
# -----------------------
def which_or_exit(cmd):
    path = shutil.which(cmd)
    if not path:
        print(f"[ERROR] Required tool '{cmd}' not found in PATH. Install it and re-run.", file=sys.stderr)
        sys.exit(1)
    return path

def run(cmd, **kwargs):
    print(">>>", " ".join(cmd))
    subprocess.run(cmd, check=True, **kwargs)

# -----------------------
# ====== Main flow =======
# -----------------------
def main():
    # Check tools
    yt_dlp = which_or_exit("yt-dlp")
    mp4decrypt = which_or_exit("mp4decrypt")
    ffmpeg = which_or_exit("ffmpeg")

    # Create temp dir
    tmp = Path(tempfile.mkdtemp(prefix="mpd_dl_"))
    print(f"[INFO] Using temp dir: {tmp}")

    video_enc = tmp / "video.encrypted.mp4"
    audio_enc = tmp / "audio.encrypted.m4a"
    video_dec = tmp / "video.decrypted.mp4"
    audio_dec = tmp / "audio.decrypted.m4a"

    try:
        # 1) List formats (optional info)
        print("\n[STEP] Listing available formats (yt-dlp -F) ...")
        try:
            run([yt_dlp, "-F", MPD], stdout=None)
        except subprocess.CalledProcessError:
            # listing could fail with exit code but still prints; continue
            pass

        # 2) Download bestvideo
        print("\n[STEP] Downloading best video (encrypted) ...")
        # We request bestvideo and save to fixed filename
        run([yt_dlp, "-f", "bestvideo", "-o", str(video_enc), MPD])

        # 3) Download bestaudio
        print("\n[STEP] Downloading best audio (encrypted) ...")
        run([yt_dlp, "-f", "bestaudio", "-o", str(audio_enc), MPD])

        # Validate files exist
        if not video_enc.exists():
            print(f"[ERROR] Encrypted video not found at {video_enc}", file=sys.stderr)
            sys.exit(1)
        if not audio_enc.exists():
            print(f"[WARNING] Encrypted audio not found at {audio_enc} — trying to continue (maybe audio is muxed).")

        # 4) Decrypt using mp4decrypt
        print("\n[STEP] Decrypting tracks with mp4decrypt ...")
        key_args = []
        for k in KEYS:
            key_args += ["--key", k]

        # Decrypt video if exists
        if video_enc.exists():
            run([mp4decrypt] + key_args + [str(video_enc), str(video_dec)])
        # Decrypt audio if exists
        if audio_enc.exists():
            run([mp4decrypt] + key_args + [str(audio_enc), str(audio_dec)])
        else:
            # In some cases yt-dlp merged into a single file; try to detect and decrypt any mp4 generated
            merged_candidates = list(tmp.glob("*.mp4"))
            merged_candidates = [p for p in merged_candidates if p.name != video_dec.name]
            if merged_candidates:
                print(f"[INFO] Found candidate merged encrypted file(s): {merged_candidates}")
                # try decrypt first candidate
                run([mp4decrypt] + key_args + [str(merged_candidates[0]), str(video_dec)])
            else:
                print("[ERROR] No audio encrypted file found and no merged encrypted mp4 candidate. Exiting.", file=sys.stderr)
                sys.exit(1)

        # 5) Merge decrypted audio+video into final_output.mp4
        print("\n[STEP] Merging decrypted tracks into", OUTPUT)
        if video_dec.exists() and audio_dec.exists():
            run([ffmpeg, "-y", "-i", str(video_dec), "-i", str(audio_dec), "-c", "copy", OUTPUT])
        elif video_dec.exists() and not audio_dec.exists():
            # maybe video file already contains audio post-decrypt
            print("[INFO] audio decrypted absent — copying decrypted video to final output.")
            shutil.copy2(video_dec, OUTPUT)
        else:
            print("[ERROR] Decrypted video not found. Cannot create final output.", file=sys.stderr)
            sys.exit(1)

        print("\n[SUCCESS] Final file created:", OUTPUT)
        print("[CLEANUP] Temporary dir (kept):", tmp)
        print("If you want to remove temp files, delete the folder above.")

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] A command failed with return code {e.returncode}: {e}", file=sys.stderr)
        print("Check logs above for the failing command.")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Unexpected: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
git push origin main
