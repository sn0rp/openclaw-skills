#!/usr/bin/env python3
"""
ytdl-nas: Download YouTube audio and deliver to NAS (Documents/Music).
Usage: ytdl-nas.py <URL> [subdirectory]

Exit codes:
  0 - success (prints SUCCESS:<nas_path> to stdout)
  1 - bad args / metadata fetch failed
  2 - download failed
  3 - no MP3 found after download
  4 - SMB upload failed
  5 - NAS verification failed
"""

import sys
import os
import re
import subprocess
import tempfile
from pathlib import Path

SMB_CREDENTIALS = "/root/.nas-smb-credentials"
NAS_HOST = "nas.snorp.dev"
NAS_SHARE = "Documents"
NAS_MUSIC_ROOT = "Music"
YTDLP = "/usr/local/bin/yt-dlp"


# ── URL cleaning ──────────────────────────────────────────────────────────────

def clean_url(url: str) -> str:
    """Strip all params except the video ID."""
    m = re.search(r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})', url)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"
    return url


# ── Title normalisation ───────────────────────────────────────────────────────

# Patterns applied in order; each strips a known extraneous fragment.
_STRIP_PATTERNS = [
    # (Official Video), [Official Music Video], (Lyrics), [Lyric Video], etc.
    r'\s*[\(\[]\s*(?:Official\s+)?(?:Music\s+)?'
    r'(?:Video|Audio|MV|Lyric[s]?\s*(?:Video)?|Visualizer|HQ|HD|4K|720p|1080p)\s*[\)\]]',
    # (Official), [Official]
    r'\s*[\(\[]\s*Official\s*[\)\]]',
    # | Official Video / | Official Audio suffix
    r'\s*\|\s*Official(?:\s+(?:Music\s+)?(?:Video|Audio|MV))?\s*$',
    # " - Official Video" trailing suffix
    r'\s+-\s+Official(?:\s+(?:Music\s+)?(?:Video|Audio|MV))?\s*$',
    # Collapse multiple spaces
    r'\s{2,}',
]

def clean_title(title: str) -> str:
    result = title
    for i, pat in enumerate(_STRIP_PATTERNS):
        repl = ' ' if i == len(_STRIP_PATTERNS) - 1 else ''
        result = re.sub(pat, repl, result, flags=re.IGNORECASE).strip()
    return result

def has_artist_separator(title: str) -> bool:
    """True when title already encodes 'ARTIST - SONG' or 'SONG - ARTIST'."""
    return bool(re.search(r'.+\s+-\s+.+', title))

def safe_filename(name: str) -> str:
    """Strip filesystem-unsafe characters."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name).strip(' .')


# ── SMB helpers ───────────────────────────────────────────────────────────────

def smb(commands: str, *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ['smbclient', '-A', SMB_CREDENTIALS, f'//{NAS_HOST}/{NAS_SHARE}', '-c', commands],
        capture_output=True, text=True,
        check=check,
    )


def ensure_smb_dir(path: str) -> None:
    """Create SMB directory tree, ignoring 'already exists' errors."""
    # Build path incrementally so nested subdirs are created
    parts = path.strip('/').split('/')
    current = ''
    for part in parts:
        current = f"{current}/{part}" if current else part
        smb(f'mkdir "{current}"', check=False)  # silently ignore if exists


def smb_put(local_path: Path, remote_path: str) -> None:
    result = smb(f'put "{local_path}" "{remote_path}"')
    if result.returncode != 0:
        raise RuntimeError(f"SMB put failed:\n{result.stderr}\n{result.stdout}")


def smb_verify(remote_dir: str, filename: str) -> bool:
    # smbclient ls with a specific file path; backslash for SMB path separator
    smb_path = f'{remote_dir}\\{filename}'
    result = smb(f'ls "{smb_path}"', check=False)
    return filename in result.stdout


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: ytdl-nas.py <URL> [subdirectory]", file=sys.stderr)
        sys.exit(1)

    raw_url = sys.argv[1]
    subdir = sys.argv[2].strip('/') if len(sys.argv) > 2 else None

    url = clean_url(raw_url)
    print(f"▶ URL:     {url}", file=sys.stderr)

    # ── Fetch metadata ────────────────────────────────────────────────────────
    meta = subprocess.run(
        [YTDLP, '--js-runtimes', 'node',
         '--print', '%(title)s|||%(uploader)s',
         '--no-download', url],
        capture_output=True, text=True,
    )
    if meta.returncode != 0:
        print(f"METADATA_ERROR: {meta.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    parts = meta.stdout.strip().split('|||')
    raw_title = parts[0]
    uploader  = parts[1] if len(parts) > 1 else 'Unknown'

    # ── Normalise filename ────────────────────────────────────────────────────
    cleaned = clean_title(raw_title)
    if has_artist_separator(cleaned):
        display = cleaned
    else:
        display = f"{uploader} - {cleaned}"

    filename_stem = safe_filename(display)
    print(f"▶ Title:   {raw_title!r}  →  {display!r}", file=sys.stderr)

    # ── Download ──────────────────────────────────────────────────────────────
    with tempfile.TemporaryDirectory(prefix='ytdl-') as tmpdir:
        dl = subprocess.run(
            [YTDLP, '--js-runtimes', 'node',
             '-f', 'bestaudio', '-x', '--audio-format', 'mp3',
             '-o', f'{tmpdir}/{filename_stem}.%(ext)s',
             url],
            capture_output=True, text=True,
        )
        if dl.returncode != 0:
            print(f"DOWNLOAD_ERROR:\n{dl.stderr}", file=sys.stderr)
            sys.exit(2)

        mp3s = list(Path(tmpdir).glob('*.mp3'))
        if not mp3s:
            print("ERROR: Download succeeded but no MP3 produced.", file=sys.stderr)
            print(dl.stdout, file=sys.stderr)
            sys.exit(3)

        mp3_path = mp3s[0]
        basename = mp3_path.name
        print(f"▶ File:    {basename}", file=sys.stderr)

        # ── NAS upload ────────────────────────────────────────────────────────
        nas_dest_dir = NAS_MUSIC_ROOT
        if subdir:
            nas_dest_dir = f"{NAS_MUSIC_ROOT}/{subdir}"

        ensure_smb_dir(nas_dest_dir)
        remote_path = f"{nas_dest_dir}/{basename}"
        smb_put(mp3_path, remote_path)

        # ── Verify ────────────────────────────────────────────────────────────
        if not smb_verify(nas_dest_dir, basename):
            print("VERIFY_ERROR: File not found on NAS after upload.", file=sys.stderr)
            sys.exit(5)

    # tmpdir (and local mp3) auto-deleted; print canonical destination
    print(f"SUCCESS:{NAS_HOST}/{NAS_SHARE}/{remote_path}")


if __name__ == '__main__':
    main()
