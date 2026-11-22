# Mersey Stars

Jonathan runs **Mersey Stars**, a Google-review tool for local businesses in Liverpool and Merseyside (cafés, salons, nail bars, barbers, dog groomers, gyms, trades, shops). Everything is for Jonathan personally. Write to him in plain UK English, keep things simple, and give a clear recommendation.

## The two apps

Both are static, single-file HTML/JS apps (ES5 style, a `$()` helper, state in `localStorage`), served by GitHub Pages from `main`.

| Path | What it is | localStorage key |
|---|---|---|
| `reviews/` | The public website, plus the business dashboard (ask customers, QR & print, reply writer, goal). `r.html` is the customer review page; `?demo=1` makes a safe preview that sends nothing. | `mersey-stars-v1` |
| `outreach/` | Jonathan's private Instagram outreach app: Today (with "Start today's run"), Leads, Find (Google AI search that fills in a batch, plus "Add one from Instagram"), Settings. | `ms-outreach-v1` |
| `index.html` | Redirects to `reviews/`, keeping the query string and hash. | |

- **Live site:** https://jonathansmallbone889-byte.github.io/mersey-investor-leads/reviews/
- **Outreach app:** https://jonathansmallbone889-byte.github.io/mersey-investor-leads/outreach/
- **Import links:** `outreach/#import=<base64url JSON array of leads>` adds leads (`name`, `type`, `area`, `address`, `notes`) into "To check". Names already on the list are skipped. This is how to hand Jonathan new businesses.
- **Finding new businesses:** use the `/lead-finder` skill (`.claude/skills/lead-finder/`). It researches businesses from the web and their own websites, and returns one import link. It never sends anything.
- **Outreach `type` values:** `salon`, `nails`, `barber`, `groomer`, `cafe`, `takeaway`, `gym`, `tattoo`, `trade`, `shop`, `other`.

## The offer (keep everything consistent with this)

Free until **31 January 2027**, then **£25 a month for life** for founding businesses (usual price £40). No contract, only 10 founding spots. Every founding business gets a **free custom desk card** in their colours (A6, QR code to their review page). Mention it after they reply, not in the first DM.
**Promise:** if their Google reviews haven't grown by 31 January, they don't pay until they do.
Never write "no monthly fee". Don't promise a specific number of reviews.

## How outreach works

1. Find businesses: rated **4.0–4.8★** with **under 100 Google reviews**, in Jonathan's areas.
2. Follow and like their Instagram.
3. Send a short DM of about 60 words. It ends "Want to see what yours would look like? 😊", and doesn't mention QR cards in the first message.
4. When they reply, send a **preview link** to their own review page. Work by message; calls only if they ask.
5. Sign them up, then send their page link.

- **Daily DM limit:** 10.
- **Instagram usernames:** never trust a username from an AI. The Google AI search may suggest an instagram.com link only when Google shows it on the listing or website. The app keeps it only if it looks like the business name, and always marks it "check it's them" for Jonathan to confirm. "Add one from Instagram" (copying the real profile link) is always correct.

## Jonathan's rules

- Be honest everywhere: no made-up stats, results, reviews or customers. Example data must be labelled (the example business is "Lark Lane Coffee").
- Instagram posts are premium **navy and gold** carousels, 1080×1350.
- Follow Google's review policy and the DMCC Act 2024: no fake or incentivised reviews, and never hide the Google button from unhappy customers.
- No automated Instagram DMs (against Instagram's rules). Cold emails to sole traders need consent under PECR.
- Don't name competitors in marketing. Compare against "typical tools".
- Finish the work before opening a pull request, and don't open one unless Jonathan asks or the work he asked for is done.

## Working on the code

- Make edits with exact find-and-replace (each match should be unique), then syntax-check the app's script:
  `node -e "const h=require('fs').readFileSync('outreach/index.html','utf8');new Function(h.split('<script>')[1].split('</script>')[0])"` (the same check works for `reviews/index.html`).
- Test in a real browser: serve the repo with `python3 -m http.server <port>`, then use Playwright (`require('playwright')`, `chromium.launch()`) at 390px and 1366px widths. Check for JS errors and sideways scrolling, and click through the changed flows.
- Branch, commit and pull request on the session's assigned branch. Write PR descriptions in plain language, with Changes and Testing sections.
