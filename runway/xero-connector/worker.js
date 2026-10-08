// Runway ⇄ Xero connector (Cloudflare Worker).
//
// Signs the user in to Xero, reads what Runway needs for a cash forecast, and
// hands it back to the Runway page in the URL fragment. Nothing is stored:
// the access token lives only for the length of one request.
//
// Settings (Cloudflare → Worker → Settings → Variables and Secrets):
//   XERO_CLIENT_ID      Xero app client id
//   XERO_CLIENT_SECRET  Xero app client secret (type: Secret)
//   ALLOWED_ORIGIN      where Runway is hosted, e.g. https://you.github.io
//                       (comma-separate several, e.g. for local testing)
//   XERO_SCOPES         optional; defaults to the granular read-only scopes below

const AUTH_URL = 'https://login.xero.com/identity/connect/authorize';
const TOKEN_URL = 'https://identity.xero.com/connect/token';
const API = 'https://api.xero.com';
const DEFAULT_SCOPES = 'accounting.invoices.read accounting.reports.banksummary.read';
const COOKIE = '__Host-runway-xero';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/login') return login(url, env);
    if (url.pathname === '/callback') return callback(request, url, env);
    if (url.pathname === '/') return new Response('Runway Xero connector is running.', { headers: { 'content-type': 'text/plain' } });
    return new Response('Not found', { status: 404 });
  }
};

function allowedReturn(env, ret) {
  try {
    const u = new URL(ret);
    const ok = (env.ALLOWED_ORIGIN || '').split(',').map(s => s.trim().replace(/\/$/, '')).filter(Boolean);
    return ok.includes(u.origin) ? u.origin + u.pathname + u.search : null;
  } catch { return null; }
}

function login(url, env) {
  const ret = allowedReturn(env, url.searchParams.get('return') || '');
  if (!ret) return new Response('This page is not allowed to use the connector. Check ALLOWED_ORIGIN.', { status: 400 });
  if (!env.XERO_CLIENT_ID || !env.XERO_CLIENT_SECRET) return backTo(ret, { error: 'The Xero connector is missing its client id or secret.' });

  const state = [...crypto.getRandomValues(new Uint8Array(16))].map(b => b.toString(16).padStart(2, '0')).join('');
  const auth = new URL(AUTH_URL);
  auth.search = new URLSearchParams({
    response_type: 'code',
    client_id: env.XERO_CLIENT_ID,
    redirect_uri: url.origin + '/callback',
    scope: env.XERO_SCOPES || DEFAULT_SCOPES,
    state
  });
  return new Response(null, {
    status: 302,
    headers: {
      location: auth.toString(),
      'set-cookie': `${COOKIE}=${state}|${encodeURIComponent(ret)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=600`,
      'cache-control': 'no-store'
    }
  });
}

async function callback(request, url, env) {
  const cookie = (request.headers.get('cookie') || '').split(/;\s*/).find(c => c.startsWith(COOKIE + '='));
  const [state, encRet] = cookie ? cookie.slice(COOKIE.length + 1).split('|') : [];
  const ret = encRet && allowedReturn(env, decodeURIComponent(encRet));
  if (!ret) return new Response('Your sign-in session expired. Go back to Runway and try again.', { status: 400 });

  if (url.searchParams.get('error')) return backTo(ret, { error: 'Xero sign-in was cancelled.' });
  if (!state || url.searchParams.get('state') !== state) return backTo(ret, { error: 'Sign-in check failed. Please try again.' });

  try {
    const tok = await fetch(TOKEN_URL, {
      method: 'POST',
      headers: {
        authorization: 'Basic ' + btoa(env.XERO_CLIENT_ID + ':' + env.XERO_CLIENT_SECRET),
        'content-type': 'application/x-www-form-urlencoded'
      },
      body: new URLSearchParams({ grant_type: 'authorization_code', code: url.searchParams.get('code') || '', redirect_uri: url.origin + '/callback' })
    });
    if (!tok.ok) throw new Error('Xero refused the sign-in (' + tok.status + ')');
    const { access_token } = await tok.json();
    return backTo(ret, await readXero(access_token));
  } catch (e) {
    return backTo(ret, { error: String(e.message || e) });
  }
}

// Send the result back to Runway in the fragment, which never reaches any server.
function backTo(ret, data) {
  const json = JSON.stringify({ v: 1, ...data });
  const b64 = btoa(String.fromCharCode(...new TextEncoder().encode(json))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  return new Response(null, {
    status: 302,
    headers: { location: ret + '#xero=' + b64, 'set-cookie': `${COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`, 'cache-control': 'no-store' }
  });
}

async function readXero(token) {
  const conns = await api(token, null, '/connections');
  const orgs = conns.filter(c => c.tenantType === 'ORGANISATION')
    .sort((a, b) => String(b.updatedDateUtc).localeCompare(String(a.updatedDateUtc)));
  if (!orgs.length) throw new Error('No Xero organisation was connected.');
  const org = orgs[0], tid = org.tenantId, warnings = [];
  const get = (path, headers) => api(token, tid, '/api.xro/2.0' + path, headers);
  const safe = async (label, fn) => { try { return await fn(); } catch (e) { warnings.push(`Couldn't read ${label} from Xero (${e.message}).`); return null; } };

  const yearAgo = new Date(Date.now() - 365 * 86400000).toUTCString();
  const [open, bills, paid, repeating, bank] = await Promise.all([
    safe('unpaid invoices', () => pages(get, '/Invoices?where=' + encodeURIComponent('Type=="ACCREC"') + '&Statuses=AUTHORISED,SUBMITTED', 10)),
    safe('unpaid bills', () => pages(get, '/Invoices?where=' + encodeURIComponent('Type=="ACCPAY"') + '&Statuses=AUTHORISED', 10)),
    safe('payment history', () => pages(get, '/Invoices?where=' + encodeURIComponent('Type=="ACCREC"') + '&Statuses=PAID', 5, { 'if-modified-since': yearAgo })),
    safe('repeating invoices', () => get('/RepeatingInvoices?where=' + encodeURIComponent('Status=="AUTHORISED"')).then(r => r.RepeatingInvoices || [])),
    safe('bank balances', () => {
      const d = new Date().toISOString().slice(0, 10);
      return get(`/Reports/BankSummary?fromDate=${d}&toDate=${d}`);
    })
  ]);

  const inv = i => ({ contact: (i.Contact && i.Contact.Name) || '', num: i.InvoiceNumber || '', due: xd(i.DueDateString || i.DueDate) || xd(i.DateString || i.Date), owed: +i.AmountDue || 0 });
  return {
    org: org.tenantName || 'Xero',
    balance: bank ? bankTotal(bank) : null,
    receivables: (open || []).map(inv).filter(i => i.owed > 0 && i.due),
    bills: (bills || []).map(inv).filter(i => i.owed > 0 && i.due),
    paid: (paid || []).map(i => ({ contact: (i.Contact && i.Contact.Name) || '', due: xd(i.DueDateString || i.DueDate), paid: xd(i.FullyPaidOnDate) }))
      .filter(p => p.due && p.paid),
    repeating: (repeating || []).map(repeat).filter(Boolean),
    warnings
  };
}

async function api(token, tenantId, path, extra) {
  const headers = { authorization: 'Bearer ' + token, accept: 'application/json', ...(extra || {}) };
  if (tenantId) headers['xero-tenant-id'] = tenantId;
  const r = await fetch(API + path, { headers });
  if (r.status === 304) return {};
  if (!r.ok) throw new Error(r.status === 401 || r.status === 403 ? 'permission not granted' : 'error ' + r.status);
  return r.json();
}

async function pages(get, path, max, headers) {
  let all = [];
  for (let p = 1; p <= max; p++) {
    const r = await get(path + '&page=' + p, headers);
    const list = r.Invoices || [];
    all = all.concat(list);
    if (list.length < 100) break;
  }
  return all;
}

// Xero dates come as "/Date(1739491200000+0000)/" or "2026-10-12T00:00:00"
function xd(v) {
  if (!v) return null;
  const m = /\/Date\((-?\d+)/.exec(v);
  if (m) return new Date(+m[1]).toISOString().slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}/.test(v) ? v.slice(0, 10) : null;
}

function repeat(r) {
  const s = r.Schedule || {}, period = +s.Period || 1, unit = s.Unit;
  const freq = unit === 'WEEKLY' ? { 1: 'weekly', 2: 'fortnightly' }[period] : unit === 'MONTHLY' ? { 1: 'monthly', 3: 'quarterly' }[period] : null;
  const next = xd(s.NextScheduledDateString || s.NextScheduledDate);
  if (!freq || !next || !(+r.Total > 0)) return null;
  // Cash lands on the due date, not the invoice date
  let pay = new Date(next + 'T00:00:00Z'), n = +s.DueDate || 0;
  if (s.DueDateType === 'DAYSAFTERBILLDATE') pay = new Date(pay.getTime() + n * 86400000);
  else if (s.DueDateType === 'OFFOLLOWINGMONTH' && n) pay = new Date(Date.UTC(pay.getUTCFullYear(), pay.getUTCMonth() + 1, Math.min(n, 28)));
  return { dir: r.Type === 'ACCREC' ? 'in' : 'out', contact: (r.Contact && r.Contact.Name) || 'Repeating invoice', amount: +r.Total, freq, next: pay.toISOString().slice(0, 10) };
}

function bankTotal(report) {
  const rows = ((report.Reports || [])[0] || {}).Rows || [];
  const val = row => { const c = row.Cells || []; return parseFloat(c.length ? c[c.length - 1].Value : NaN); };
  let total = null, sum = 0, any = false;
  rows.forEach(sec => (sec.Rows || []).forEach(r => {
    if (r.RowType === 'SummaryRow' && isFinite(val(r))) total = val(r);
    else if (r.RowType === 'Row' && isFinite(val(r))) { sum += val(r); any = true; }
  }));
  return total != null ? total : any ? sum : null;
}
