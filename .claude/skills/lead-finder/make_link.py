#!/usr/bin/env python3
"""Turn a JSON list of found businesses into an import link for the outreach app.

Usage: python3 make_link.py leads.json

Each item: name, type, area, address, website, email, ig, ig_source,
compliments (list of {"text": ..., "source": ...}), note.
Only name is required. Unknown types become "other".
"""
import base64
import json
import sys

APP = "https://jonathansmallbone889-byte.github.io/mersey-investor-leads/outreach/"
TYPES = {"salon", "nails", "barber", "groomer", "cafe", "takeaway", "gym", "tattoo", "trade", "shop", "other"}
ALIASES = {"café": "cafe", "cafes": "cafe", "cafés": "cafe", "coffee": "cafe", "restaurant": "cafe", "bakery": "cafe",
           "hair": "salon", "hairdresser": "salon", "beauty": "salon", "salons": "salon", "nail": "nails", "nail bar": "nails",
           "barbers": "barber", "dog groomer": "groomer", "groomers": "groomer", "grooming": "groomer",
           "gyms": "gym", "pt": "gym", "fitness": "gym", "tattoo studio": "tattoo", "trades": "trade", "shops": "shop"}


def kind(t):
    t = (t or "").strip().lower()
    t = ALIASES.get(t, t)
    return t if t in TYPES else "other"


def handle(v):
    v = (v or "").strip()
    if "instagram.com/" in v:
        v = v.split("instagram.com/", 1)[1]
    return v.strip("/@ ").split("/")[0].split("?")[0]


def lead(x, today):
    notes = ["Found by /lead-finder " + today + ". Check the Google rating and reviews before following."]
    if x.get("website"):
        notes.append("Website: " + x["website"])
    if x.get("email"):
        notes.append("Email (published on their site): " + x["email"])
    if x.get("note"):
        notes.append(x["note"])
    o = {
        "name": x["name"].strip(),
        "type": kind(x.get("type")),
        "area": x.get("area", ""),
        "address": x.get("address", ""),
        "notes": "\n".join(notes),
    }
    h = handle(x.get("ig"))
    if h and x.get("ig_source"):
        # Only usernames linked from the business's own website or booking page. Jonathan still confirms it.
        o["ig"] = h
        o["igSrc"] = x["ig_source"]
        o["igOk"] = False
    comps = [c for c in x.get("compliments", []) if c.get("text")]
    if comps:
        o["aiComps"] = [{"t": c["text"], "why": c.get("source", "")} for c in comps[:3]]
        o["compliment"] = comps[0]["text"]
        o["compSrc"] = "web"
    return o


def main():
    import datetime
    today = datetime.date.today().strftime("%-d %b %Y")
    data = json.load(open(sys.argv[1]))
    leads = [lead(x, today) for x in data if x.get("name")]
    raw = json.dumps(leads, ensure_ascii=False).encode("utf-8")
    print(APP + "#import=" + base64.urlsafe_b64encode(raw).decode().rstrip("="))
    print(f"{len(leads)} businesses", file=sys.stderr)


if __name__ == "__main__":
    main()
