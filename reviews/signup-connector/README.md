# Mersey Stars sign-up connector

A small Google Apps Script that runs on your own Google account. When a business joins as a founding business on the Mersey Stars page, it:

- **emails you straight away** at jonathansmallbone889@gmail.com (with "[Visit wanted]" in the subject if they asked for a set-up visit; press Reply to answer them)
- **adds a row to a Google Sheet**: business, contact, and their Google rating and review count on the day they joined
- **emails you once a day at about 9am** when a business is due its 4-week or 8-week check, so you can record its new rating and review count next to the starting numbers. That before-and-after record is your proof that Mersey Stars works.

It's free and needs no server, Formspree or other outside service. The sign-ups only go to your Google account.

Until it's set up, the sign-up form still works: it opens the business's email app or WhatsApp with their details filled in.

## Setup (about 10 minutes)

### 1. Make the tracker sheet and add the script

1. Go to <https://sheets.new> while signed in to the Google account you want to use. Name the sheet **Mersey Stars founding businesses**.
2. Click **Extensions → Apps Script**.
3. Delete the sample code, paste in all of [`Code.gs`](Code.gs), and click the **Save** icon.

### 2. Run the one-time setup

1. In the toolbar's function menu, choose **setup**, then click **Run**.
2. Google asks for permission. Click **Review permissions**, choose your account, then **Advanced → Go to (project name) (unsafe) → Allow**. The "unsafe" warning appears because you wrote this script yourself rather than downloading a published app. It only asks to send email as you, edit this spreadsheet and run a daily timer.
3. Back in the sheet, a **Founding businesses** tab appears with column headings.

### 3. Publish it as a web app

1. Click **Deploy → New deployment**.
2. Click the gear icon next to "Select type" and choose **Web app**.
3. Set **Execute as** to **Me**, and **Who has access** to **Anyone**.
4. Click **Deploy** and copy the **Web app URL**. It looks like `https://script.google.com/macros/s/AKfy…/exec`.

"Anyone" only means the page can send sign-ups to this address. Nobody can read your sheet through it.

### 4. Connect the page

Open [`../index.html`](../index.html), find this line:

```js
var SIGNUP_URL = '';
```

and paste your web app URL between the quotes. Commit, then push to the site. (You can also send the URL to Claude and ask for it to be added.)

### 5. Test it

1. Open the web app URL in your browser. It should say `{"ok":true,"service":"Mersey Stars sign-ups"}`.
2. Fill in the founding business form on the live site with a test business.
3. Within a minute you should get the email, and a new row should appear in the sheet. Delete the test row afterwards.

## Changing the script later

If you edit `Code.gs`, publish the change with **Deploy → Manage deployments → (pencil) Edit → Version: New version → Deploy**. That keeps the same web app URL, so the page doesn't need changing.

## Limits

Google lets a personal Gmail account send about 100 emails a day from scripts. That's far more than this needs.
