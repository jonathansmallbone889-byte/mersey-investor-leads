"""Transcript helpers: parse captions from any source into timed words and sentences."""
import json
import re

# A word is {"start": float, "end": float, "text": str}.


def _spread(text, start, end):
    """Split a caption line into words, sharing its time span by word length."""
    tokens = text.split()
    if not tokens:
        return []
    end = max(end, start + 0.2 * len(tokens))
    weights = [len(t) + 2 for t in tokens]
    total = sum(weights)
    words, t = [], start
    for tok, w in zip(tokens, weights):
        dur = (end - start) * w / total
        words.append({"start": round(t, 3), "end": round(t + dur, 3), "text": tok})
        t += dur
    return words


def _clean(words):
    words = [w for w in words if w["text"].strip()]
    words.sort(key=lambda w: w["start"])
    out = []
    for w in words:
        w["text"] = w["text"].strip()
        if out and abs(out[-1]["start"] - w["start"]) < 0.01 and out[-1]["text"] == w["text"]:
            continue
        out.append(w)
    for a, b in zip(out, out[1:]):
        if a["end"] > b["start"]:
            a["end"] = b["start"]
        if a["end"] <= a["start"]:
            a["end"] = a["start"] + 0.05
    return out


def from_json3(path):
    """YouTube json3 captions (auto captions carry per-word offsets)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    pieces = []
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs:
            continue
        t0 = ev.get("tStartMs", 0) / 1000
        end = t0 + ev.get("dDurationMs", 0) / 1000
        for s in segs:
            text = s.get("utf8", "")
            if text.strip():
                pieces.append([t0 + s.get("tOffsetMs", 0) / 1000, end, text])
    pieces.sort(key=lambda p: p[0])
    words = []
    for i, (start, end, text) in enumerate(pieces):
        nxt = pieces[i + 1][0] if i + 1 < len(pieces) else end
        stop = min(end, nxt) if nxt > start else end
        words += _spread(text.replace("\n", " "), start, max(stop, start + 0.15))
    return _clean(words)


_TS = r"(\d{1,2}:)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?"


def _secs(ts):
    parts = ts.replace(",", ".").split(":")
    return sum(float(p) * 60 ** i for i, p in enumerate(reversed(parts)))


def from_text(raw, duration=None):
    """SRT, VTT, '0:12 text' lines, or plain text (timed at ~2.6 words/sec)."""
    raw = raw.replace("\r", "").strip()
    cues = re.findall(rf"({_TS})\s*-->\s*({_TS})[^\n]*\n(.*?)(?=\n\s*\n|\Z)", raw, re.S)
    words = []
    if cues:
        for c in cues:  # groups: start, start-hours, end, end-hours, text
            a, b, text = c[0], c[2], c[4]
            text = re.sub(r"<[^>]+>", "", text).replace("\n", " ")
            words += _spread(text, _secs(a), _secs(b))
        return _clean(words)

    lines = [l.strip() for l in raw.split("\n") if l.strip()]
    stamped = []
    pending = None
    for line in lines:
        m = re.match(rf"^\[?({_TS})\]?\s*[-–:]?\s*(.*)$", line)
        if m:
            if m.group(3):
                stamped.append([_secs(m.group(1)), m.group(3)])
            else:
                pending = _secs(m.group(1))
        elif pending is not None:
            stamped.append([pending, line])
            pending = None
        elif stamped:
            stamped[-1][1] += " " + line
    if stamped:
        for i, (t, text) in enumerate(stamped):
            nxt = stamped[i + 1][0] if i + 1 < len(stamped) else t + len(text.split()) / 2.6
            words += _spread(text, t, nxt)
        return _clean(words)

    t = 0.0
    for tok in raw.split():
        d = (len(tok) + 2) / 13.0
        words.append({"start": t, "end": t + d, "text": tok})
        t += d
    if duration and t > 0:
        k = duration / t
        for w in words:
            w["start"] *= k
            w["end"] *= k
    return _clean(words)


def sentences(words, max_words=40):
    """Group words into sentences, breaking on punctuation, long pauses or length."""
    out, cur = [], []
    for i, w in enumerate(words):
        cur.append(i)
        nxt = words[i + 1] if i + 1 < len(words) else None
        ends = re.search(r"[.!?…][\"')\]]*$", w["text"])
        pause = nxt is not None and nxt["start"] - w["end"] > 1.2
        if ends or pause or len(cur) >= max_words or nxt is None:
            out.append({
                "i0": cur[0],
                "i1": cur[-1],
                "start": words[cur[0]]["start"],
                "end": words[cur[-1]]["end"],
                "text": " ".join(words[k]["text"] for k in cur),
            })
            cur = []
    return out


def to_srt(words, offset=0.0, per_line=7):
    def fmt(t):
        t = max(0.0, t)
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    blocks = []
    for n, k in enumerate(range(0, len(words), per_line), 1):
        chunk = words[k:k + per_line]
        blocks.append(f"{n}\n{fmt(chunk[0]['start'] - offset)} --> {fmt(chunk[-1]['end'] - offset)}\n"
                      + " ".join(w["text"] for w in chunk) + "\n")
    return "\n".join(blocks)
