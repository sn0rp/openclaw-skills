# ytdl — YouTube → NAS Music Downloader

## Trigger

Any message that contains a YouTube URL (`youtube.com/watch?v=` or `youtu.be/`) addressed to The Mentor in a Discord channel. Canonical invocation format (from a dedicated `#ytdl` channel):

```
@The Mentor <YouTube-URL> [subdirectory]
```

Examples:
```
@The Mentor https://www.youtube.com/watch?v=E4rhGUfd_c4
@The Mentor https://www.youtube.com/watch?v=E4rhGUfd_c4&list=PLxxx  charli-xcx
@The Mentor https://youtu.be/E4rhGUfd_c4 chillwave
```

The subdirectory argument (if given) is placed after the URL, separated by whitespace. It becomes a subdirectory of `Music/` on the NAS.

---

## Steps

### 1 — Parse message

Extract:
- `URL` — first token matching `https?://(www\.)?youtube\.com/watch\?` or `https?://youtu\.be/`
- `SUBDIR` — next whitespace-separated token after the URL, if present (ignore `@The Mentor` prefix and any trailing punctuation)

If no URL is found, reply: "I don't see a YouTube link in there. Give me a URL and I'll grab it."

### 2 — Run the download script

```bash
python3 /usr/local/lib/ytdl-nas.py "<URL>" ["<SUBDIR>"]
```

Capture both stdout and stderr.

### 3 — Report

**On SUCCESS** (stdout starts with `SUCCESS:`):

Parse the path from stdout: `SUCCESS:nas.snorp.dev/Documents/Music/<path>`

Reply in Discord:
```
✅ Downloaded to nas.snorp.dev/Documents/Music/<path>
```

**On failure** (non-zero exit or stdout starts with `*_ERROR:`):

Reply with a concise error summary drawn from stderr, e.g.:
```
❌ Download failed: [error text]
```

---

## Script location

`/usr/local/lib/ytdl-nas.py` (source: `scripts/ytdl-nas.py` in this repo)

The script handles internally:
- URL cleaning (strips all params except `v=`)
- yt-dlp metadata fetch (title + uploader)
- Filename normalisation:
  - Strips "(Official Video)", "[Lyrics]", "(HQ)", "| Official", etc.
  - If cleaned title lacks ` - ` separator → prepends uploader: `{uploader} - {title}`
  - Removes filesystem-unsafe characters
- yt-dlp download as best-quality MP3 via ffmpeg conversion
- smbclient upload to `//nas.snorp.dev/Documents` share, path `Music[/SUBDIR]`
- Creates subdirectory if missing (mkdir ignores "already exists")
- Verifies file exists on NAS after upload
- Cleans up local temp file automatically (tempfile context manager)

---

## Dependencies

| Tool | Location | Notes |
|------|----------|-------|
| yt-dlp | `/usr/local/bin/yt-dlp` | Install: `curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp && chmod +x /usr/local/bin/yt-dlp` |
| ffmpeg | `/usr/bin/ffmpeg` | `apt install ffmpeg` |
| smbclient | `/usr/bin/smbclient` | `apt install smbclient` |
| Node.js | `/usr/bin/node` | Used as yt-dlp JS runtime; `apt install nodejs` |
| SMB credentials | `/root/.nas-smb-credentials` | `username=snorp\npassword=...` |

NAS shares: `//nas.snorp.dev/Documents` → `Music/` subdirectory.

---

## Filename normalisation logic

Strips (case-insensitive, bracketed or unbracketed):
- `(Official Video)`, `[Official Music Video]`, `(Official Audio)`, `(Official)`
- `(Lyrics)`, `[Lyric Video]`, `[Lyrics]`
- `(Visualizer)`, `(HQ)`, `(HD)`, `(4K)`, `(720p)`, `(1080p)`
- `| Official …` and `- Official …` trailing suffixes

Artist detection:
- If cleaned title contains ` - ` with content on both sides → already has artist/title, use as-is
- Otherwise → format as `{uploader} - {cleaned_title}`

---

## Re-installing / updating yt-dlp

The script does **not** auto-update yt-dlp on every run. To update manually:

```bash
yt-dlp -U
```

Or reinstall from the GitHub releases URL above. Update when downloads start failing with extraction errors.

---

## Error codes from script

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Bad args or metadata fetch failed |
| 2 | yt-dlp download failed |
| 3 | No MP3 found after download |
| 4 | SMB upload failed |
| 5 | NAS verify failed (file not found after upload) |
