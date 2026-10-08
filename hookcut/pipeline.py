"""Job store and the link -> clips pipeline."""
import glob
import json
import os
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import ai
import render
import scoring
import transcript

DATA = Path(os.getenv("HOOKCUT_DATA", Path(__file__).parent / "data"))
JOBS = DATA / "jobs"
JOBS.mkdir(parents=True, exist_ok=True)
MAX_MINUTES = float(os.getenv("HOOKCUT_MAX_MINUTES", "180"))
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")

STAGES = ["download", "transcribe", "find", "hashtags", "render"]
STAGE_LABELS = {
    "download": "Fetching video", "transcribe": "Transcribing speech", "find": "Finding viral moments",
    "hashtags": "Researching trending hashtags", "render": "Rendering clips",
}

_lock = threading.Lock()
_jobs = {}
_pool = ThreadPoolExecutor(max_workers=int(os.getenv("HOOKCUT_WORKERS", "1")))


def _dir(job_id):
    return JOBS / job_id


def save(job):
    job["updated"] = time.time()
    with _lock:
        _jobs[job["id"]] = job
        tmp = _dir(job["id"]) / "job.json.tmp"
        tmp.write_text(json.dumps(job))
        tmp.replace(_dir(job["id"]) / "job.json")


def get(job_id):
    with _lock:
        if job_id in _jobs:
            return _jobs[job_id]
    p = _dir(job_id) / "job.json"
    if p.exists() and job_id.isalnum():
        job = json.loads(p.read_text())
        with _lock:
            _jobs[job_id] = job
        return job
    return None


def snapshot(job_id):
    """A consistent copy of a job for the API (the worker thread keeps mutating the live one)."""
    job = get(job_id)
    if job is None:
        return None
    with _lock:
        return json.loads(json.dumps(job))


def recent(limit=30):
    out = []
    for p in sorted(JOBS.glob("*/job.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            j = json.loads(p.read_text())
            out.append({k: j.get(k) for k in ("id", "status", "created", "source", "video")}
                       | {"clips": len(j.get("clips", []))})
        except (OSError, ValueError):
            pass
    return out


def create(options, source_url=None, upload_name=None):
    job_id = uuid.uuid4().hex[:12]
    _dir(job_id).mkdir(parents=True)
    job = {
        "id": job_id, "status": "queued", "created": time.time(), "error": None,
        "source": source_url or upload_name, "options": options,
        "stage": None, "stages": {s: "pending" for s in STAGES}, "detail": "Waiting in queue…",
        "progress": 0, "video": None, "clips": [], "ai": ai.available(), "notes": [],
    }
    save(job)
    return job


def start(job, upload_path=None):
    _pool.submit(_run, job["id"], upload_path)


def _stage(job, name, detail="", progress=None):
    if job["stage"] and job["stage"] != name and job["stages"][job["stage"]] == "active":
        job["stages"][job["stage"]] = "done"
    job["stage"] = name
    job["stages"][name] = "active"
    job["detail"] = detail
    if progress is not None:
        job["progress"] = progress
    save(job)


# ---------- download ----------

def _download(job, url):
    import yt_dlp

    d = _dir(job["id"])
    common = {"quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True}
    if os.getenv("YTDLP_COOKIES"):
        common["cookiefile"] = os.getenv("YTDLP_COOKIES")

    with yt_dlp.YoutubeDL(common) as y:
        info = y.extract_info(url, download=False)
    if info.get("_type") == "playlist":
        raise RuntimeError("That link is a playlist. Paste a link to a single video.")
    if info.get("is_live"):
        raise RuntimeError("Live streams can't be clipped until they've finished.")
    if (info.get("duration") or 0) > MAX_MINUTES * 60:
        raise RuntimeError(f"That video is longer than {MAX_MINUTES:.0f} minutes, the current limit.")

    def hook(p):
        if p.get("status") == "downloading":
            total = p.get("total_bytes") or p.get("total_bytes_estimate") or 0
            if total:
                pct = p.get("downloaded_bytes", 0) / total
                job["detail"] = f"Downloading… {pct * 100:.0f}%"
                job["progress"] = round(pct * 15)
                if int(pct * 100) % 5 == 0:
                    save(job)

    opts = dict(common, outtmpl=str(d / "source.%(ext)s"), merge_output_format="mp4", progress_hooks=[hook],
                format="bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b")
    with yt_dlp.YoutubeDL(opts) as y:
        y.download([url])

    # Platform captions (YouTube's carry word timings) are optional; transcription covers their absence.
    try:
        sub_opts = dict(common, skip_download=True, writesubtitles=True, writeautomaticsub=True,
                        subtitlesformat="json3", subtitleslangs=[".*-orig", "en", "en-.*"],
                        outtmpl=str(d / "subs.%(ext)s"))
        with yt_dlp.YoutubeDL(sub_opts) as y:
            y.download([url])
    except Exception:  # noqa: BLE001 - captions are a bonus; Whisper is the fallback
        pass

    files = [f for f in glob.glob(str(d / "source.*")) if not f.endswith((".part", ".ytdl"))]
    if not files:
        raise RuntimeError("The video downloaded, but no playable file was found.")
    meta = {k: info.get(k) for k in ("title", "uploader", "description", "duration", "webpage_url",
                                     "extractor_key", "view_count", "tags")}
    return Path(files[0]), meta


# ---------- transcription ----------

_whisper = None


def _transcribe_whisper(job, path, duration):
    global _whisper
    from faster_whisper import WhisperModel

    if _whisper is None:
        job["detail"] = f"Loading speech model ({WHISPER_MODEL})…"
        save(job)
        _whisper = WhisperModel(WHISPER_MODEL, device=os.getenv("WHISPER_DEVICE", "auto"),
                                compute_type=os.getenv("WHISPER_COMPUTE", "int8"))
    segments, info = _whisper.transcribe(str(path), word_timestamps=True, vad_filter=True)
    words, last = [], 0
    total = duration or info.duration or 1
    for seg in segments:
        for w in seg.words or []:
            words.append({"start": w.start, "end": w.end, "text": w.word.strip()})
        if time.time() - last > 2:
            pct = min(1.0, seg.end / total)
            job["detail"] = f"Transcribing… {pct * 100:.0f}%"
            job["progress"] = 15 + round(pct * 40)
            save(job)
            last = time.time()
    return [w for w in words if w["text"]], info.language


def _words_for(job, src, meta):
    d = _dir(job["id"])
    pasted = job["options"].get("transcript", "").strip()
    if pasted:
        job["notes"].append("Used the transcript you provided.")
        return transcript.from_text(pasted, meta.get("duration")), "provided"
    subs = sorted(glob.glob(str(d / "subs.*.json3")), key=lambda f: ("-orig" not in f, f))
    for f in subs:
        words = transcript.from_json3(f)
        if len(words) > 20:
            return words, "platform captions"
    words, lang = _transcribe_whisper(job, src, meta.get("duration"))
    return words, f"Whisper ({lang})"


# ---------- the pipeline ----------

def _run(job_id, upload_path=None):
    job = get(job_id)
    opts = job["options"]
    d = _dir(job_id)
    try:
        job["status"] = "running"
        _stage(job, "download", "Fetching video…", 2)
        if upload_path:
            src, meta = Path(upload_path), {"title": Path(job["source"]).stem.replace("_", " ")}
        else:
            src, meta = _download(job, job["source"])
        info = render.probe(src)
        meta["duration"] = meta.get("duration") or info["duration"]
        job["video"] = {"title": meta.get("title"), "uploader": meta.get("uploader"),
                        "duration": meta["duration"], "url": meta.get("webpage_url") or job["source"],
                        "width": info["width"], "height": info["height"]}
        save(job)

        _stage(job, "transcribe", "Transcribing…", 15)
        words, how = _words_for(job, src, meta)
        if len(words) < 15:
            raise RuntimeError("Couldn't find enough speech in this video to make clips.")
        (d / "words.json").write_text(json.dumps(words))
        sents = transcript.sentences(words)
        job["transcript_source"] = how

        _stage(job, "find", "Scoring every moment for virality…", 56)
        length = opts.get("length", "auto")
        lo, hi = scoring.LENGTHS.get(length, scoring.LENGTHS["auto"])
        n = int(opts.get("max_clips", 8))
        if meta["duration"] < lo * 1.5:
            lo, hi = max(5, meta["duration"] * 0.2), max(10, meta["duration"] * 0.9)
        clips, topic, niche = [], "", ""
        if ai.available():
            try:
                topic, niche, clips = ai.select_clips(sents, meta, lo, hi, n)
            except Exception as e:  # noqa: BLE001 - fall back to built-in scoring
                job["notes"].append(f"Claude clip selection failed ({e}); used built-in scoring instead.")
        if not clips:
            clips = scoring.find_clips(sents, n, (lo, hi))
        if not clips:
            raise RuntimeError("No clip-worthy moments of the chosen length were found. Try another clip length.")
        for c in clips:
            seg = sents[c["start_sentence"]:c["end_sentence"] + 1]
            if "breakdown" not in c:
                c["breakdown"] = {k: round(v * 100) for k, v in scoring.score_range(seg)[1].items()}
            c.setdefault("hashtags", [{"tag": t, "trending": False}
                                      for t in scoring.hashtags_from(" ".join(s["text"] for s in seg))])
            c["text"] = " ".join(s["text"] for s in seg)
            c["start"] = max(0.0, c["start"] - 0.12)
            c["end"] = min(meta["duration"], c["end"] + 0.35)
        clips.sort(key=lambda c: -c["score"])
        job["clips"] = clips
        save(job)

        if ai.available():
            _stage(job, "hashtags", "Searching what's trending this week…", 62)
            try:
                ai.trending_hashtags(meta, topic or meta.get("title", ""), niche, clips)
            except Exception as e:  # noqa: BLE001
                job["notes"].append(f"Live hashtag research failed ({e}); showing topic hashtags instead.")
        else:
            job["stages"]["hashtags"] = "skipped"
            job["notes"].append("Add an ANTHROPIC_API_KEY to rank clips with Claude and pull live trending hashtags.")
        save(job)

        _stage(job, "render", "Rendering clips…", 65)
        for k, c in enumerate(clips):
            job["detail"] = f"Rendering clip {k + 1} of {len(clips)}…"
            job["progress"] = 65 + round(35 * k / len(clips))
            save(job)
            _render_one(job, k, src, words, info)
        job["stages"]["render"] = "done"
        job["status"] = "done"
        job["progress"] = 100
        job["detail"] = f"{len(clips)} clips ready"
        save(job)
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        job["status"] = "error"
        job["error"] = _friendly(e)
        for c in job.get("clips", []):
            if c.get("status") in ("rendering", "queued"):
                c["status"] = "error"
                c["error"] = "Stopped because the project failed."
        if job["stage"]:
            job["stages"][job["stage"]] = "error"
        save(job)


def _friendly(e):
    msg = str(e)
    low = msg.lower()
    if "sign in to confirm" in low or "bot" in low and "youtube" in low:
        return ("YouTube asked for a sign-in check. Set YTDLP_COOKIES to an exported cookies.txt file, "
                "or download the video and upload it instead.")
    if "unsupported url" in low:
        return "That link isn't supported. Paste a link to a single video, or upload the file."
    if "private" in low or "unavailable" in low:
        return "That video is private or unavailable."
    return msg.replace("ERROR: ", "")[:400]


def _source_file(job_id):
    files = [f for f in glob.glob(str(_dir(job_id) / "source.*")) if not f.endswith((".part", ".ytdl"))]
    return Path(files[0]) if files else None


def _render_one(job, k, src, words, info=None):
    c = job["clips"][k]
    opts = job["options"]
    name = f"clip{k + 1:02d}_{uuid.uuid4().hex[:4]}"
    out = _dir(job["id"]) / f"{name}.mp4"
    c["status"] = "rendering"
    save(job)
    used = render.render_clip(src, out, c["start"], c["end"], words,
                              style=c.get("style") or opts.get("style", "bold"),
                              layout=c.get("layout") or opts.get("layout", "auto"),
                              hook=c.get("hook") if opts.get("hook_overlay", True) else None, info=info)
    for old in ("file", "thumb", "srt"):
        if c.get(old):
            (_dir(job["id"]) / c[old]).unlink(missing_ok=True)
    clip_words = [w for w in words if w["end"] > c["start"] and w["start"] < c["end"]]
    (out.with_suffix(".srt")).write_text(transcript.to_srt(clip_words, offset=c["start"]), encoding="utf-8")
    out.with_suffix(".ass").unlink(missing_ok=True)
    c.update(file=out.name, thumb=out.with_suffix(".jpg").name, srt=out.with_suffix(".srt").name,
             layout_used=used, status="ready", duration=round(c["end"] - c["start"], 1))
    save(job)


def rerender(job_id, k, changes):
    job = get(job_id)
    c = job["clips"][k]
    dur = job["video"]["duration"]
    for key in ("style", "layout", "hook"):
        if key in changes and changes[key] is not None:
            c[key] = changes[key]
    if changes.get("start") is not None:
        c["start"] = max(0.0, float(changes["start"]))
    if changes.get("end") is not None:
        c["end"] = min(dur, float(changes["end"]))
    if c["end"] - c["start"] < 3:
        raise ValueError("A clip needs to be at least 3 seconds long.")
    c["status"] = "queued"
    save(job)

    def work():
        try:
            words = json.loads((_dir(job_id) / "words.json").read_text())
            _render_one(job, k, _source_file(job_id), words)
        except Exception as e:  # noqa: BLE001
            c["status"] = "error"
            c["error"] = str(e)[:300]
            save(job)
    _pool.submit(work)
