# openclaw-skills

Reusable skill scripts for [The Mentor](https://github.com/sn0rp) — a personal OpenClaw assistant.

Skills here are invoked from Discord and other channels. Each skill directory contains a `SKILL.md` (procedure instructions) and a `scripts/` directory with the implementation.

## Skills

| Skill | Description |
|-------|-------------|
| [ytdl](./ytdl/) | Download YouTube audio as MP3 and deliver to NAS |

## Setup notes

- Designed to run on the OpenClaw host (`openclaw.snorp.dev`)
- NAS credentials are stored at `/root/.nas-smb-credentials` (not included)
- Scripts use the `sn0rp` git identity; adjust for your own setup
