"""Cut a clip to 9:16 with face-aware reframing, burned-in animated captions and a hook title."""
import json
import os
import re
import statistics
import subprocess
from pathlib import Path

W, H = 1080, 1920
FONTS_DIR = Path(__file__).parent / "fonts"
CAPTION_FONT = os.getenv("HOOKCUT_FONT", "Montserrat Black")

# Colours are ASS &HAABBGGRR.
STYLES = {
    "bold": {"size": 92, "upper": True, "per": 3, "color": "&H00FFFFFF", "active": "&H0000E1FF",
             "outline": 8, "box": False, "pop": 112},
    "karaoke": {"size": 84, "upper": True, "per": 4, "color": "&H00FFFFFF", "active": "&H0055E43B",
                "outline": 7, "box": False, "pop": 100},
    "clean": {"size": 64, "upper": False, "per": 6, "color": "&H00D8D8D8", "active": "&H00FFFFFF",
              "outline": 0, "box": True, "pop": 100},
    "none": None,
}


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:stream_side_data=rotation:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    st = data["streams"][0]
    w, h = st["width"], st["height"]
    rot = 0
    for sd in st.get("side_data_list", []):
        rot = abs(int(sd.get("rotation", 0)))
    if rot in (90, 270):
        w, h = h, w
    return {"width": w, "height": h, "duration": float(data["format"].get("duration", 0))}


def has_audio(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return bool(out.strip())


def face_focus(path, start, end, samples=12):
    """Median horizontal centre (0-1) of the largest face across the clip, or None when no face is found."""
    try:
        return _face_focus(path, start, end, samples)
    except Exception:  # noqa: BLE001 - no detector or unreadable frames: fall back to the blur layout
        return None


def _face_focus(path, start, end, samples):
    import cv2

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(str(path))
    centres = []
    for k in range(samples):
        t = start + (end - start) * (k + 0.5) / samples
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        h, w = frame.shape[:2]
        scale = 480 / max(w, 1)
        small = cv2.resize(frame, (480, int(h * scale)))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(30, 30))
        if len(faces):
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])
            centres.append((x + fw / 2) / 480)
    cap.release()
    if len(centres) < max(2, samples // 4):
        return None
    return statistics.median(centres)


def _ass_time(t):
    t = max(0.0, t)
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _esc(text):
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def _chunks(words, per):
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if (len(cur) >= per or nxt is None or re.search(r"[.!?,;:]$", w["text"])
                or (nxt and nxt["start"] - w["end"] > 0.7)):
            out.append(cur)
            cur = []
    return out


def build_ass(words, start, end, style="bold", hook=None, caption_y=0.70):
    """ASS subtitles with the active word highlighted, timed relative to the clip start."""
    st = STYLES.get(style) or None
    font = CAPTION_FONT
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0",
        "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
    ]
    if st:
        border, back = (3, "&H66000000") if st["box"] else (1, "&H80000000")
        outline = 14 if st["box"] else st["outline"]
        lines.append(f"Style: Cap,{font},{st['size']},{st['color']},{st['color']},&H00000000,{back},1,0,0,0,100,100,"
                     f"1,0,{border},{outline},{0 if st['box'] else 3},5,90,90,0,1")
    lines.append(f"Style: Hook,{font},64,&H00111111,&H00111111,&H00FFFFFF,&H00FFFFFF,1,0,0,0,100,100,0,0,3,22,0,8,"
                 "110,110,0,1")
    lines += ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]

    if hook:
        lines.append(f"Dialogue: 1,{_ass_time(0)},{_ass_time(min(3.2, end - start))},Hook,,0,0,0,,"
                     f"{{\\an8\\pos({W // 2},{int(H * 0.12)})\\fad(120,250)}}{_esc(hook)}")

    if st:
        y = int(H * caption_y)
        clip_words = [w for w in words if w["end"] > start and w["start"] < end]
        chunks = _chunks(clip_words, st["per"])
        for ci, chunk in enumerate(chunks):
            # Hold the last word briefly, but never past the start of the next caption line.
            hold = chunk[-1]["end"] + 0.15
            if ci + 1 < len(chunks):
                hold = min(hold, chunks[ci + 1][0]["start"])
            texts = [_esc(w["text"].upper() if st["upper"] else w["text"]) for w in chunk]
            for k, w in enumerate(chunk):
                a = (chunk[0]["start"] if k == 0 else w["start"]) - start
                b = (chunk[k + 1]["start"] if k + 1 < len(chunk) else hold) - start
                if b <= a:
                    continue
                parts = []
                for n, t in enumerate(texts):
                    if n == k:
                        pop = f"\\fscx{st['pop']}\\fscy{st['pop']}" if st["pop"] != 100 else ""
                        parts.append(f"{{\\c{st['active']}{pop}}}{t}{{\\r}}")
                    else:
                        parts.append(t)
                lines.append(f"Dialogue: 0,{_ass_time(a)},{_ass_time(b)},Cap,,0,0,0,,"
                             f"{{\\an5\\pos({W // 2},{y})}}" + " ".join(parts))
    return "\n".join(lines) + "\n"


def _ff_path(p):
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def render_clip(src, out, start, end, words, style="bold", layout="auto", hook=None, info=None):
    """Render one 1080x1920 MP4 plus a JPG thumbnail. Returns the layout actually used."""
    info = info or probe(src)
    sw, sh = info["width"], info["height"]
    dur = end - start
    out = Path(out)
    ass = out.with_suffix(".ass")
    ass.write_text(build_ass(words, start, end, style, hook), encoding="utf-8")

    vertical = sw / sh <= 0.62
    focus = None
    if layout in ("auto", "crop") and not vertical:
        focus = face_focus(src, start, end)
    if layout == "auto":
        layout = "fill" if vertical else ("crop" if focus is not None else "blur")

    subs = f"subtitles='{_ff_path(ass)}'"
    if FONTS_DIR.is_dir():
        subs += f":fontsdir='{_ff_path(FONTS_DIR)}'"
    if layout == "crop":
        cw = min(sw, int(sh * 9 / 16) // 2 * 2)
        x = int(min(max((focus if focus is not None else 0.5) * sw - cw / 2, 0), sw - cw))
        graph = f"[0:v]crop={cw}:{sh}:{x}:0,scale={W}:{H},setsar=1,{subs}[v]"
    elif layout == "fill":
        graph = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,{subs}[v]")
    else:  # blur: full frame centred over a blurred, zoomed copy of itself
        graph = (f"[0:v]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                 f"boxblur=24:3,eq=brightness=-0.12[bg];[b]scale={W}:-2[fg];"
                 f"[bg][fg]overlay=0:(H-h)/2,setsar=1,{subs}[v]")

    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{dur:.3f}",
           "-filter_complex", graph, "-map", "[v]"]
    if has_audio(src):
        cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "160k", "-ar", "44100"]
    cmd += ["-c:v", "libx264", "-preset", os.getenv("HOOKCUT_PRESET", "veryfast"), "-crf", "21",
            "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart", str(out)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + res.stderr.strip()[-600:])
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{min(1.0, dur / 2):.2f}", "-i", str(out),
                    "-frames:v", "1", "-q:v", "4", "-vf", "scale=360:-2", str(out.with_suffix(".jpg"))],
                   capture_output=True)
    return layout
