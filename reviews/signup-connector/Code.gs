/**
 * Mersey Stars sign-up connector (Google Apps Script).
 *
 * Receives founding-business sign-ups from the Mersey Stars page, then:
 *   1. emails them to you straight away
 *   2. adds a row to this spreadsheet (your before-and-after tracker)
 *   3. once a day, emails you which businesses are due their 4-week or 8-week check
 *
 * Setup steps are in README.md next to this file.
 */

var NOTIFY_EMAIL = 'jonathansmallbone889@gmail.com';
var SHEET_NAME = 'Founding businesses';
var HEADERS = [
  'Signed up', 'Business', 'Contact', 'Phone', 'Email', 'Type', 'Area',
  'Rating at start', 'Reviews at start', 'Wants set-up visit', 'Already using app',
  'Rating at 4 weeks', 'Reviews at 4 weeks', 'Rating at 8 weeks', 'Reviews at 8 weeks',
  'Would pay £40/month?', 'Notes'
];

/** Run this once from the editor. It creates the tracker sheet and the daily reminder. */
function setup() {
  sheet_();
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'dailyCheckIns') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('dailyCheckIns').timeBased().everyDays(1).atHour(9).create();
}

function doPost(e) {
  try {
    var d = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    if (d.website) return json_({ ok: true }); // honeypot: bots fill hidden fields

    var clean = function (v, max) { return String(v == null ? '' : v).replace(/[\r\n]+/g, ' ').trim().slice(0, max || 100); };
    var s = {
      business: clean(d.business), name: clean(d.name), phone: clean(d.phone, 30), email: clean(d.email),
      type: clean(d.type), area: clean(d.area), rating: clean(d.rating, 5), count: clean(d.count, 7),
      help: d.help ? 'Yes' : 'No', inApp: d.inApp ? 'Yes' : 'No'
    };
    if (!s.business || !s.name || s.phone.replace(/\D/g, '').length < 9) return json_({ ok: false, error: 'missing' });

    var lock = LockService.getScriptLock();
    lock.waitLock(10000);
    try {
      // Formulas can be smuggled in through form fields; prefix anything that starts like one.
      var safe = function (v) { return /^[=+\-@]/.test(v) ? "'" + v : v; };
      sheet_().appendRow([new Date(), safe(s.business), safe(s.name), safe(s.phone), safe(s.email), safe(s.type), safe(s.area),
        safe(s.rating), safe(s.count), s.help, s.inApp, '', '', '', '', '', '']);
    } finally {
      lock.releaseLock();
    }

    var body = [
      'New founding business for Mersey Stars', '',
      'Business: ' + s.business,
      'Contact: ' + s.name,
      'Phone: ' + s.phone,
      'Email: ' + (s.email || '-'),
      'Type: ' + (s.type || '-'),
      'Area: ' + (s.area || '-'), '',
      'Google today: ' + (s.rating || '?') + ' stars from ' + (s.count || '?') + ' reviews',
      'Wants a set-up visit: ' + s.help,
      'Already using the app: ' + s.inApp, '',
      'Tracker: ' + SpreadsheetApp.getActiveSpreadsheet().getUrl()
    ].join('\n');
    var mail = {
      to: NOTIFY_EMAIL,
      subject: (s.help === 'Yes' ? '[Visit wanted] ' : '') + 'Founding business: ' + s.business,
      body: body
    };
    if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s.email)) mail.replyTo = s.email;
    MailApp.sendEmail(mail);

    return json_({ ok: true });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

/** Lets you open the web app address in a browser to check it's running. */
function doGet() {
  return json_({ ok: true, service: 'Mersey Stars sign-ups' });
}

/** Daily: email a list of businesses due their 4-week or 8-week check. */
function dailyCheckIns() {
  var rows = sheet_().getDataRange().getValues().slice(1);
  var now = new Date().getTime(), day = 86400000, due = [];
  rows.forEach(function (r) {
    var started = r[0] instanceof Date ? r[0].getTime() : NaN;
    if (isNaN(started)) return;
    var days = Math.floor((now - started) / day);
    var line = r[1] + ' (' + r[2] + ', ' + r[3] + '). Started at ' + (r[7] || '?') + ' stars, ' + (r[8] || '?') + ' reviews';
    if (days >= 28 && r[12] === '') due.push('4-week check: ' + line);
    else if (days >= 56 && r[14] === '') due.push('8-week check: ' + line);
  });
  if (!due.length) return;
  MailApp.sendEmail({
    to: NOTIFY_EMAIL,
    subject: 'Mersey Stars: ' + due.length + ' business' + (due.length === 1 ? '' : 'es') + ' due a check-in',
    body: 'Look up their Google rating and review count, add them to the tracker, and ask whether they would pay £40 a month.\n\n' +
      due.join('\n') + '\n\nTracker: ' + SpreadsheetApp.getActiveSpreadsheet().getUrl()
  });
}

function sheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
  if (sh.getLastRow() === 0) {
    sh.appendRow(HEADERS);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, HEADERS.length).setFontWeight('bold');
  }
  return sh;
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
