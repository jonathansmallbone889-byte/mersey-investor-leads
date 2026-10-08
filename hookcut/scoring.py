"""Built-in virality scoring, used when Claude isn't configured (and for score breakdowns)."""
import math
import re
from collections import Counter

STOP = set("""a about above after again all also am an and any are as at be because been before being below between
both but by can could did do does doing down during each few for from further get gets got had has have having he her
here hers him his how i if in into is it its itself just know let like ll me more most much my no nor not now of off on
once only or other our out over own really right same say says she should so some such than that thats the their them
then there these they thing things this those through to too under until up us very want was way we well were what when
where which while who whom why will with would you your youre yeah okay ok gonna kind sort mean actually basically
literally going got dont didnt doesnt isnt its im ive youve were theyre thats theres heres whats lot little bit one two
make made think thought people really just""".split())

HOOK = re.compile(r"^(here'?s|the (truth|secret|problem|reason|biggest|one|real)|nobody|no one|most people|stop|never|"
                  r"why|how|what if|imagine|i (quit|lost|made|spent|was|never)|if you|you (need|should|have|won'?t)|"
                  r"this is|the best|the worst|everyone|don'?t)\b", re.I)
EMOTION = re.compile(r"\b(insane|crazy|shocking|terrified|scared|love|hate|disaster|broke|failed|fired|quit|million|"
                     r"billion|cried|angry|obsessed|brutal|wild|unbelievable|incredible|huge|massive|secret|"
                     r"mistake|regret|best|worst|never|always|everything|nothing|dead|dying|lie|lied|truth)\b", re.I)
VALUE = re.compile(r"\b(how to|step|steps|the key|lesson|rule|framework|tip|trick|strategy|system|habit|"
                   r"here'?s how|the reason|because|that'?s why|percent|%|\$\d|\d)\b", re.I)
PAYOFF = re.compile(r"\b(that'?s why|so the|the lesson|the point|remember|turns out|in the end|which means|"
                    r"that'?s (it|the)|and that|never|always)\b", re.I)
DANGLING = re.compile(r"^(and|but|so|because|which|that|it|this|he|she|they|them|also|then|or|like|plus|as)\b", re.I)
CALLBACK = re.compile(r"\b(as i said|like i (said|mentioned)|earlier|we talked about|going back to)\b", re.I)

WEIGHTS = {"hook": .30, "standalone": .18, "emotion": .14, "value": .16, "payoff": .12, "pacing": .10}
LABELS = {
    "hook": "Strong opening hook", "standalone": "Makes sense on its own", "emotion": "Emotional charge",
    "value": "Clear takeaway", "payoff": "Lands on a payoff", "pacing": "Fast, tight pacing",
}

LENGTHS = {"auto": (20, 60), "short": (12, 30), "medium": (30, 60), "long": (60, 90)}


def tokens(text):
    return [w for w in re.findall(r"[a-z][a-z0-9']+", text.lower().replace("’", "'"))
            if len(w) > 2 and w.replace("'", "") not in STOP]


def _features(sents, words_count, dur):
    first, last = sents[0]["text"], sents[-1]["text"]
    joined = " ".join(s["text"] for s in sents)
    first_words = len(first.split())

    hook = 0.15
    if first.rstrip().endswith("?"):
        hook += .35
    if HOOK.search(first):
        hook += .35
    if re.search(r"\d", first):
        hook += .15
    if re.search(r"\byou\b", first, re.I):
        hook += .1
    if first_words <= 16:
        hook += .1
    if DANGLING.search(first):
        hook -= .45

    standalone = 1.0
    if DANGLING.search(first):
        standalone -= .5
    if CALLBACK.search(joined):
        standalone -= .3
    if len(last.split()) < 4:
        standalone -= .1

    per = max(words_count, 1) / 30
    emotion = min(1.0, len(EMOTION.findall(joined)) / (per * 1.5) + joined.count("!") * .1)
    value = min(1.0, len(VALUE.findall(joined)) / (per * 2))
    payoff = .3 + (.4 if PAYOFF.search(last) else 0) + (.3 if last.rstrip().endswith((".", "!")) else 0)
    wps = words_count / max(dur, 1)
    pacing = 1 - min(1.0, abs(wps - 3.0) / 1.6)
    clamp = lambda v: max(0.0, min(1.0, v))
    return {k: clamp(v) for k, v in dict(hook=hook, standalone=standalone, emotion=emotion,
                                         value=value, payoff=payoff, pacing=pacing).items()}


def score_range(sents):
    words_count = sum(len(s["text"].split()) for s in sents)
    dur = sents[-1]["end"] - sents[0]["start"]
    f = _features(sents, words_count, dur)
    total = sum(f[k] * w for k, w in WEIGHTS.items())
    score = int(round(35 + 64 * total))
    return max(1, min(99, score)), f


def _title(sents):
    best = max(sents[:3], key=lambda s: (s["text"].endswith("?"), bool(HOOK.search(s["text"])), -len(s["text"])))
    t = best["text"].strip().rstrip(".")
    if len(t) > 70:
        t = t[:67].rsplit(" ", 1)[0] + "…"
    return t[0].upper() + t[1:] if t else "Untitled clip"


def hashtags_from(text, extra=()):
    counts = Counter(tokens(text))
    tags = []
    for w, _ in counts.most_common(12):
        tag = re.sub(r"[^a-z0-9]", "", w)
        if len(tag) > 3 and tag not in tags:
            tags.append(tag)
        if len(tags) == 4:
            break
    tags += [t for t in extra if t not in tags]
    return ["#" + t for t in tags + ["shorts", "viral", "fyp"]][:8]


def find_clips(sents, max_clips=8, bounds=LENGTHS["auto"]):
    lo, hi = bounds
    cands = []
    for i in range(len(sents)):
        for j in range(i, len(sents)):
            dur = sents[j]["end"] - sents[i]["start"]
            if dur > hi:
                break
            if dur >= lo:
                score, f = score_range(sents[i:j + 1])
                cands.append((score, i, j, f))
    cands.sort(key=lambda c: -c[0])
    chosen = []
    for score, i, j, f in cands:
        s, e = sents[i]["start"], sents[j]["end"]
        if all(min(e, c["end"]) - max(s, c["start"]) < 0.2 * min(e - s, c["end"] - c["start"]) for c in chosen):
            top = sorted(f, key=lambda k: -f[k] * WEIGHTS[k])[:3]
            text = " ".join(x["text"] for x in sents[i:j + 1])
            chosen.append({
                "start_sentence": i, "end_sentence": j, "start": s, "end": e, "score": score,
                "title": _title(sents[i:j + 1]),
                "hook": " ".join(sents[i]["text"].split()[:8]).rstrip(".,"),
                "reason": "; ".join(LABELS[k] for k in top if f[k] >= .5) or "Best available segment",
                "post_caption": _title(sents[i:j + 1]) + (" 👀" if f["hook"] > .6 else ""),
                "hashtags": [{"tag": t, "trending": False} for t in hashtags_from(text)],
                "breakdown": {k: round(v * 100) for k, v in f.items()},
            })
        if len(chosen) >= max_clips:
            break
    return chosen
