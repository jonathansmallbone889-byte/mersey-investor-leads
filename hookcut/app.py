"""HookCut web server: paste a link (or upload a video), get ranked vertical clips."""
import re
import shutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import ai
import pipeline

app = FastAPI(title="HookCut")
STATIC = Path(__file__).parent / "static"
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".mp3", ".m4a", ".wav"}


class Options(BaseModel):
    length: str = Field("auto", pattern="^(auto|short|medium|long)$")
    max_clips: int = Field(8, ge=1, le=20)
    style: str = Field("bold", pattern="^(bold|karaoke|clean|none)$")
    layout: str = Field("auto", pattern="^(auto|crop|blur|fill)$")
    hook_overlay: bool = True
    transcript: str = Field("", max_length=2_000_000)


class LinkJob(Options):
    url: str


class ClipEdit(BaseModel):
    start: Optional[float] = None
    end: Optional[float] = None
    style: Optional[str] = Field(None, pattern="^(bold|karaoke|clean|none)$")
    layout: Optional[str] = Field(None, pattern="^(auto|crop|blur|fill)$")
    hook: Optional[str] = Field(None, max_length=120)


@app.get("/api/config")
def config():
    return {"ai": ai.available(), "model": ai.MODEL if ai.available() else None,
            "max_minutes": pipeline.MAX_MINUTES}


@app.post("/api/jobs")
def create_from_link(body: LinkJob):
    url = body.url.strip()
    if not re.match(r"^https?://\S+$", url):
        raise HTTPException(400, "Paste a full link starting with https://")
    job = pipeline.create(body.model_dump(exclude={"url"}), source_url=url)
    pipeline.start(job)
    return {"id": job["id"]}


@app.post("/api/upload")
def create_from_upload(file: UploadFile = File(...), length: str = Form("auto"), max_clips: int = Form(8),
                       style: str = Form("bold"), layout: str = Form("auto"), hook_overlay: bool = Form(True),
                       transcript: str = Form("")):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in VIDEO_EXT:
        raise HTTPException(400, "Upload a video or audio file (MP4, MOV, WebM, MKV, MP3…).")
    opts = Options(length=length, max_clips=max_clips, style=style, layout=layout,
                   hook_overlay=hook_overlay, transcript=transcript)
    job = pipeline.create(opts.model_dump(), upload_name=file.filename)
    dest = pipeline.JOBS / job["id"] / f"source{ext}"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f, length=4 * 1024 * 1024)
    pipeline.start(job, dest)
    return {"id": job["id"]}


@app.get("/api/jobs")
def list_jobs():
    return pipeline.recent()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = pipeline.snapshot(job_id)
    if not job:
        raise HTTPException(404, "Project not found.")
    return job


@app.post("/api/jobs/{job_id}/clips/{index}")
def edit_clip(job_id: str, index: int, body: ClipEdit):
    job = pipeline.get(job_id)
    if not job or not (0 <= index < len(job.get("clips", []))):
        raise HTTPException(404, "Clip not found.")
    if job["status"] != "done":
        raise HTTPException(409, "Wait for the project to finish before editing clips.")
    try:
        pipeline.rerender(job_id, index, body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.get("/media/{job_id}/{name}")
def media(job_id: str, name: str, download: bool = False):
    if not re.fullmatch(r"[a-f0-9]{12}", job_id) or not re.fullmatch(r"clip\d+_[a-f0-9]{4}\.(mp4|jpg|srt)", name):
        raise HTTPException(404)
    path = pipeline.JOBS / job_id / name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, filename=name if download else None)


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
