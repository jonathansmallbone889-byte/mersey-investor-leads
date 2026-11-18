---
name: lead-finder
description: Find new local businesses for Mersey Stars outreach and hand them to Jonathan as one import link for his outreach app. Use when Jonathan types /lead-finder, or asks to find, research or add new businesses, leads or prospects (e.g. "/lead-finder 10 cafés and groomers in Crosby").
---

# /lead-finder

Find independent businesses in Jonathan's areas, build a short honest profile of each from their **own website**, and return **one import link** that adds them all to the outreach app's "To check" list. Jonathan sends every message himself. **Nothing is ever sent automatically.**

Read `CLAUDE.md` first for the offer, the outreach process and Jonathan's rules.

## Input

From Jonathan's message, take:
- **Types** (cafés, salons, nail bars, barbers, dog groomers, gyms, tattoo studios, trades, shops). If none are given, use cafés, salons, nail bars, barbers, dog groomers and gyms.
- **Areas.** If none are given, use Crosby, Waterloo, Formby, Maghull, Southport, Wavertree, Aigburth, Childwall, West Derby, Allerton, Woolton and Liverpool city centre, and pick two or three per run.
- **How many.** Default 10, at most 15 per run, so each one is checked properly.

If Jonathan names businesses to skip, leave them out. The app also skips names already on his list.

## Step 1: Find (search)

Use web search: one search per type and area, e.g. `independent dog groomer Crosby Liverpool`. Booking sites (Fresha, Treatwell, Booksy), local guides and the businesses' own sites are good sources.

Keep only businesses that:
- are independent: no chains or franchises
- are in the areas asked for
- look open: recent activity on their site or booking page, and no "permanently closed" note. If unsure, say so in `note`.

Don't guess Google ratings or review counts. Leave them out. Jonathan checks them in the app (4.0–4.8★, under 100 reviews).

## Step 2: Profile (their own website)

For each business, find its **own website or booking page** and read it (WebFetch, or the web-fetch agent). Record:
- `name`, `type` (the app's values: salon, nails, barber, groomer, cafe, takeaway, gym, tattoo, trade, shop, other), `area`, `address` (street and area), `website`
- `ig`: **only if their own website or booking page links to an Instagram profile.** Copy that exact link into `ig`, and the page it was on into `ig_source`. Never guess or search for a username. If there's no link, leave it out, and Jonathan uses "Find their Instagram" in the app.
- `compliments`: up to 3 short, friendly compliments (under 15 words, one emoji each) about something **real and specific on their site**, such as a speciality, how long they've been going, or something they're proud of. Put where it came from in `source`, e.g. `"Their website: 'family-run since 1998'"`. Never invent details. If nothing specific is there, leave compliments out.

## Step 3: Email (only if published)

Only record an `email` the business publishes on its own website. Don't guess addresses or use email-finding tools.

Note for Jonathan: cold marketing emails to sole traders and partnerships need consent (PECR). Most of these businesses are best contacted on Instagram.

## Step 4: Hand over (no sending)

1. Write the businesses as a JSON list to a file in the scratchpad (fields as above, plus an optional `note`).
2. Run `python3 .claude/skills/lead-finder/make_link.py <file>` to get the import link.
3. Reply to Jonathan with:
   - a short table: business, type, area, Instagram (✓ found on their site, or "find in app"), and whether a compliment was found
   - the import link, which he opens on his phone in the same browser as the outreach app
   - any doubts (possibly closed, maybe a chain, outside the area)
   - a reminder to check each Google rating in the app before following
   - the sources used, as links

## Rules

- **Never send anything:** no DMs, emails or form submissions. Automated Instagram DMs break Instagram's rules.
- **Never invent:** no guessed ratings, reviews, Instagram usernames, emails or compliments. Blank is better than wrong.
- Only public business information. No personal social accounts, home addresses or private phone numbers.
- Keep runs small and careful. Ten good businesses beat thirty doubtful ones.
