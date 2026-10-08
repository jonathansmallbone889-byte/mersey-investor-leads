"""Claude-powered clip selection and live trending-hashtag research."""
import datetime
import json
import os

import anthropic

MODEL = os.getenv("HOOKCUT_MODEL", "claude-opus-5-5")
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def available():
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


_client = None


def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(timeout=600, max_retries=3)
    return _client


class AIError(RuntimeError):
    pass


def _check(resp):
    if resp.stop_reason == "refusal":
        why = getattr(resp.stop_details, "explanation", None) if resp.stop_details else None
        raise AIError("Claude declined this video" + (f": {why}" if why else "."))
    if resp.stop_reason == "max_tokens":
        raise AIError("Claude's answer was cut off. Try fewer clips.")


def _call(stream=False, **kw):
    """Send a request with server-side refusal fallbacks, retrying without them if the account rejects the beta."""
    def run(extra):
        if stream:
            with client().beta.messages.stream(**kw, **extra) as st:
                return st.get_final_message()
        return client().beta.messages.create(**kw, **extra)
    try:
        return run({"betas": [FALLBACK_BETA], "fallbacks": "default"})
    except anthropic.BadRequestError as e:
        if "fallback" not in str(e).lower():
            raise
        return run({})


def _text(resp):
    return "".join(b.text for b in resp.content if b.type == "text")


CLIP_SCHEMA = {
    "type": "object",
    "properties": {
        "video_topic": {"type": "string"},
        "niche": {"type": "string"},
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_sentence": {"type": "integer"},
                    "end_sentence": {"type": "integer"},
                    "score": {"type": "integer"},
                    "title": {"type": "string"},
                    "hook": {"type": "string"},
                    "reason": {"type": "string"},
                    "post_caption": {"type": "string"},
                    "topics": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["start_sentence", "end_sentence", "score", "title", "hook", "reason",
                             "post_caption", "topics"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["video_topic", "niche", "clips"],
    "additionalProperties": False,
}


def select_clips(sents, meta, min_len, max_len, max_clips):
    """Ask Claude for the most viral self-contained moments, as sentence ranges."""
    lines = [f"[{i}] {s['start']:.1f}-{s['end']:.1f}s: {s['text']}" for i, s in enumerate(sents)]
    prompt = f"""You are a short-form video editor who has cut thousands of clips that went viral on TikTok,
YouTube Shorts and Instagram Reels. From the transcript below, pick up to {max_clips} clips with the highest
chance of going viral as standalone vertical videos.

Video title: {meta.get('title') or 'unknown'}
Channel: {meta.get('uploader') or 'unknown'}
Description: {(meta.get('description') or '')[:1500]}

Rules for each clip:
- It is a contiguous range of transcript sentences [start_sentence..end_sentence] (inclusive, by index).
- Duration (end time of last sentence minus start time of first) must be between {min_len} and {max_len} seconds.
- The first sentence must hook a scroller within 2 seconds: a bold claim, a question, a surprising number,
  conflict, or a story opening. Never start on a word that depends on earlier context ("and", "so", "he", "that").
- It must make sense to someone who never saw the full video, and end on a payoff (punchline, answer, lesson
  or cliffhanger), not mid-thought.
- Clips must not overlap.

For each clip give:
- score: 0-100 predicted virality, calibrated so only truly exceptional moments score above 90.
- title: a punchy on-screen/video title, max 60 characters, written like a top creator would.
- hook: the 3-8 word text overlay shown in the first 3 seconds.
- reason: one sentence on why this moment will perform.
- post_caption: the caption to post with the clip (1-2 sentences, no hashtags, may end with a question to drive comments).
- topics: 2-4 short topic phrases a hashtag researcher could search for.

Also give video_topic (one line) and niche (e.g. "personal finance", "true crime", "fitness").
Order clips from most to least viral.

Transcript:
{chr(10).join(lines)}"""
    resp = _call(
        stream=True,
        model=MODEL,
        max_tokens=32000,
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": CLIP_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    _check(resp)
    data = json.loads(_text(resp))

    clips, used = [], []
    for c in data["clips"]:
        i, j = c["start_sentence"], c["end_sentence"]
        if not (0 <= i <= j < len(sents)):
            continue
        s, e = sents[i]["start"], sents[j]["end"]
        if e - s < min_len * 0.6 or e - s > max_len * 1.3:
            continue
        if any(min(e, ue) - max(s, us) > 1 for us, ue in used):
            continue
        used.append((s, e))
        c.update(start=s, end=e, score=max(1, min(99, int(c["score"]))))
        clips.append(c)
    clips.sort(key=lambda c: -c["score"])
    return data.get("video_topic", ""), data.get("niche", ""), clips


def trending_hashtags(meta, topic, niche, clips):
    """Search the web for hashtags trending right now, and assign the best ones to each clip."""
    today = datetime.date.today().strftime("%B %d, %Y")
    listing = "\n".join(f"{n}. {c['title']} | topics: {', '.join(c.get('topics', []))}" for n, c in enumerate(clips))
    prompt = f"""Today is {today}. I'm posting short vertical clips from this video on TikTok, Instagram Reels and
YouTube Shorts.

Video: {meta.get('title') or topic}
Topic: {topic}
Niche: {niche}

Clips:
{listing}

Use web search to find which hashtags are trending or growing right now (this week/month) in this niche and
for these specific topics on TikTok, Instagram and YouTube Shorts. Check recent sources such as TikTok Creative
Center trend reports, social media trend roundups and news about current trends. Prefer specific, active niche
hashtags over generic ones like #fyp.

Then for each clip pick 6-8 hashtags: a mix of 2-3 currently trending ones that genuinely fit the clip, 2-3
niche/topic tags, and at most 1-2 broad discovery tags. Mark trending=true only for tags your search shows are
trending now, and give a short note saying where you saw it.

Reply with only a JSON object, no other text:
{{"clips": [{{"index": 0, "hashtags": [{{"tag": "#example", "trending": true, "note": "short source note"}}]}}]}}"""
    messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 8}]
    for _ in range(5):
        resp = _call(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "medium"},
            tools=tools,
            messages=messages,
        )
        if resp.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": resp.content}]
    _check(resp)
    text = _text(resp)
    try:
        data = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except ValueError as e:
        raise AIError("Couldn't read the hashtag research result.") from e

    by_index = {c.get("index"): c.get("hashtags", []) for c in data.get("clips", [])}
    for n, clip in enumerate(clips):
        tags = []
        for h in by_index.get(n, []):
            tag = "#" + str(h.get("tag", "")).lstrip("#").replace(" ", "")
            if len(tag) > 1 and tag.lower() not in {t["tag"].lower() for t in tags}:
                tags.append({"tag": tag, "trending": bool(h.get("trending")), "note": h.get("note", "")})
        if tags:
            tags.sort(key=lambda t: not t["trending"])
            clip["hashtags"] = tags[:8]
