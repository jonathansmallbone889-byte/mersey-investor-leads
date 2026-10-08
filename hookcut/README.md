# HookCut

Paste a link to a long video (YouTube, TikTok, Instagram, X, Facebook, Twitch VODs, Vimeo, podcasts and
[1,000+ other sites](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md)) or upload a file.
HookCut finds the moments most likely to go viral, ranks them from most to least viral, and renders each one
as a 1080×1920 vertical clip with animated word-by-word captions, a hook title, a post caption and hashtags
that are trending right now for that video's niche.

## What it does

1. **Fetch**: downloads the video with yt-dlp (or takes your upload).
2. **Transcribe**: uses the platform's own captions when they exist (fast, word-timed on YouTube),
   otherwise transcribes locally with Whisper (faster-whisper, word timestamps). You can also paste a transcript.
3. **Find viral moments**: Claude reads the whole transcript and picks self-contained moments that open on a
   hook and end on a payoff, scores each 0–100, and writes a title, an on-screen hook and a post caption.
   Without an API key, a built-in scorer does the ranking (hook, standalone sense, emotion, takeaway,
   payoff, pacing).
4. **Trending hashtags**: Claude runs live web searches for what's trending this week in the video's niche
   on TikTok, Reels and Shorts, and assigns tags per clip. Tags the search found trending are marked.
5. **Render**: ffmpeg cuts each clip to 9:16. **Face crop** follows the speaker's face. **Fit + blur** keeps
   wide shots and screen recordings whole over a blurred background. **Auto** picks between them per clip.
   Captions are burned in (Bold pop, Karaoke, Clean, or off) with the active word highlighted.

You can trim, rewrite the hook, or change caption style and framing per clip, then re-render it. Every clip
downloads as an MP4 with a matching SRT.

## Run it

### Docker (recommended)

```bash
cd hookcut
cp .env.example .env          # add your ANTHROPIC_API_KEY
docker build -t hookcut .
docker run -p 8000:8000 --env-file .env -v hookcut-data:/data hookcut
```

Open http://localhost:8000.

### Without Docker

Needs Python 3.10+ and ffmpeg on your PATH.

```bash
cd hookcut
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn app:app --port 8000
```

The first transcription downloads the Whisper model (about 500 MB for `small`).

### Hosting

It's a normal Python web app, so it runs on any VPS or on Render, Railway or Fly.io with the Dockerfile.
Give it a persistent volume at `/data` and at least 2 CPU cores and 4 GB of RAM. A GPU makes Whisper much
faster: set `WHISPER_DEVICE=cuda`.

## Settings

| Variable | Default | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | (none) | Turns on Claude ranking and live trending-hashtag research |
| `HOOKCUT_MODEL` | `claude-opus-5-5` | Claude model used |
| `WHISPER_MODEL` | `small` | `tiny`, `base`, `small`, `medium`, `large-v3`. Bigger is more accurate and slower |
| `WHISPER_DEVICE` | `auto` | `cpu` or `cuda` |
| `HOOKCUT_MAX_MINUTES` | `180` | Longest video accepted |
| `HOOKCUT_WORKERS` | `1` | Projects processed at once |
| `YTDLP_COOKIES` | (none) | Path to an exported `cookies.txt`, for when YouTube asks for a sign-in check |
| `HOOKCUT_FONT` | `Montserrat Black` | Caption font (must be installed, or put TTF files in `hookcut/fonts/`) |

## Notes

- **YouTube sign-in checks.** YouTube sometimes blocks downloads from server IP addresses. If a link fails
  with a sign-in message, export cookies from a logged-in browser into `cookies.txt` and set `YTDLP_COOKIES`,
  or download the video yourself and upload it.
- **Rights.** Only clip videos you own or have permission to repost.
- **Speed.** With platform captions, a 1-hour video usually becomes clips in a few minutes. Whisper on CPU
  takes roughly 1/4 to 1/2 of the video's length with the `small` model.
