# Mersey Investor Leads

Landing page for **AI tenant maintenance triage**, a service for landlords and property investors across Liverpool and the Wirral. Tenants email their maintenance issues; the AI flags emergencies, replies to the tenant and logs every request. The page offers a free 2-week pilot.

**Live site:** https://jonathansmallbone889-byte.github.io/mersey-investor-leads/

## What's in the repo

| File | Purpose |
|---|---|
| `index.html` | The whole site: markup, styles and the contact form script in one file. No build step or dependencies. |
| `demo.mp4` | 73-second demo of the triage workflow (n8n, Gmail, Google Sheets), shown in the "See it in action" section. |

## Hosting

The site is served by **GitHub Pages** from the root of the `main` branch. Every change merged into `main` is published automatically, usually within a minute. You can watch progress under the repo's **Actions** tab ("pages build and deployment").

If the live page still looks old after an update, your browser is showing a cached copy. Add `?v=2` (or any new number) to the end of the URL to force a fresh one.

## Contact form

The pilot enquiry form sends submissions to **Formspree**, which emails them on.

- The Formspree endpoint is set in the form's `action` attribute in `index.html`:
  ```html
  <form ... action="https://formspree.io/f/mnpnkrby" method="POST" ...>
  ```
  To switch to a different Formspree form, change that URL. It's the only place it appears.
- Submissions are sent in the background, so the visitor stays on the page and sees a thank-you or error message under the button. If JavaScript fails to load, the form still posts directly to Formspree.
- If the `action` attribute is removed, the form falls back to opening the visitor's email app with the enquiry pre-filled.
- A hidden `_gotcha` field catches spam bots. Emails arrive with the subject "Free Pilot Enquiry - [name]".
- Submissions, spam and settings are managed in the Formspree dashboard. The free plan allows 50 submissions a month.

## Editing the site

1. Edit `index.html`, either on GitHub (pencil icon) or locally.
2. To preview locally, open `index.html` in a browser. Test the form on the live site; each test counts towards the monthly Formspree limit.
3. Commit to `main`, or open a pull request and merge it, to publish.

Contact details (phone `07576 618414` and email) appear in several places: the header, hero, contact section, footer and form messages. Search the file for them when updating.

## Replacing the demo video

Keep the file small so it loads quickly on mobile. The current file is about 2 MB, 1280×576, 30 fps, with no audio. To convert a new recording with [ffmpeg](https://ffmpeg.org/):

```bash
ffmpeg -i new-recording.mp4 -an \
  -vf "scale=1280:-2:flags=lanczos,fps=30" \
  -c:v libx264 -preset slow -crf 22 -profile:v high -pix_fmt yuv420p \
  -movflags +faststart demo.mp4
```

- `-an` removes the audio. Drop it if you want to keep the sound, and also remove `muted` from the `<video>` tag in `index.html`.
- `-crf 22` sets the quality. Higher numbers give smaller files with lower quality.
- `+faststart` lets the video begin playing before it has fully downloaded.
