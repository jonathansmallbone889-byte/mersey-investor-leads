# Runway Xero connector

A small Cloudflare Worker that lets Runway pull a forecast straight from Xero. It reads:

- unpaid invoices
- paid-invoice history (to learn how late each client pays)
- unpaid bills
- repeating invoices and bills
- bank balances

It stores nothing. Each sync signs in, reads the data once and hands it back to the Runway page in the URL fragment, which never reaches a server. It only asks Xero for read-only access.

## Setup (about 15 minutes, all in the browser)

### 1. Create the worker on Cloudflare

1. Sign up or log in at <https://dash.cloudflare.com> (the free plan is fine).
2. Go to **Workers & Pages → Create → Create Worker**, name it `runway-xero`, then click **Deploy**.
3. Click **Edit code**, delete the sample code, paste in all of [`worker.js`](worker.js), and click **Deploy**.
4. Note the worker's address, e.g. `https://runway-xero.yourname.workers.dev`.

### 2. Create the Xero app

1. Go to <https://developer.xero.com/app/manage> and log in with your Xero account.
2. Click **New app**:
   - **App name:** Runway
   - **Integration type:** Web app
   - **Company or application URL:** your website
   - **Redirect URI:** your worker address followed by `/callback`, e.g. `https://runway-xero.yourname.workers.dev/callback`
3. Create the app, open **Configuration**, and click **Generate a secret**.
4. Keep this tab open. You need the **Client id** and the **Client secret** next.

> The client secret works like a password. Paste it only into Cloudflare. Never put it in chat, email, or this repository.

### 3. Give the worker the keys

In Cloudflare, open the worker, go to **Settings → Variables and Secrets**, and add:

| Name | Type | Value |
|---|---|---|
| `XERO_CLIENT_ID` | Text | the Client id from Xero |
| `XERO_CLIENT_SECRET` | **Secret** | the Client secret from Xero |
| `ALLOWED_ORIGIN` | Text | where Runway is hosted, e.g. `https://jonathansmallbone889-byte.github.io` (just the origin, no path) |

Save, then deploy again if Cloudflare asks you to.

### 4. Point Runway at the worker

In `runway/index.html`, set the connector address:

```js
var XERO_CONNECTOR = 'https://runway-xero.yourname.workers.dev';
```

The worker address isn't secret, so it's safe to commit. A **Sync from Xero** button then appears in Runway's import card.

## Notes

- **Permissions requested:** `accounting.invoices.read` and `accounting.reports.banksummary.read`. These are Xero's granular read-only scopes, which apps created since March 2026 must use. To change them, add an `XERO_SCOPES` variable.
- **Multiple organisations:** if you have several Xero organisations, the sync uses the one you most recently approved.
- **Unapproved apps:** Xero limits how many organisations an app can connect to until it passes Xero's app certification. That's fine for your own business or a small pilot.
- **Disconnecting:** go to Xero → Settings → Connected apps.
- **Deploying with the command line instead:** run `npx wrangler deploy` in this folder, then `npx wrangler secret put XERO_CLIENT_SECRET`, and so on.
