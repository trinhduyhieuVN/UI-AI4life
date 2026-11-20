import { $, D, S, TFS, USER } from './state.js';
import { api } from './api.js';

const sessions = new Map();
const minutes = new Map();
const names = { AAPL: 'Apple', CMCSA: 'Comcast', CSCO: 'Cisco Systems', DISCA: 'Discovery',
  FOXA: 'Fox Corporation', INTC: 'Intel', MSFT: 'Microsoft', VIAC: 'ViacomCBS' };

export function initHistory(rows) {
  for (const row of rows) {
    if (!sessions.has(row.symbol)) sessions.set(row.symbol, new Map());
    sessions.get(row.symbol).set(row.day, row);
  }
  D.historical = true;
  $('nq-signal').classList.add('historical');
  D.SYMBOLS = [...sessions.keys()].sort().map(s => ({ s, n: names[s] || s, sec: 'XNAS.ITCH' }));
  D.SYM = Object.fromEntries(D.SYMBOLS.map(x => [x.s, x]));
  D.watch = historicalWatch();
  for (const badge of document.querySelectorAll('.nq-src')) {
    badge.replaceChildren(document.createElement('i'), 'PHÁT LẠI LỊCH SỬ');
    badge.title = 'Giao dịch MBO lịch sử · Databento XNAS.ITCH';
  }
  $('nq-st-src').textContent = 'Nguồn: Databento XNAS.ITCH · MBO lịch sử';
  $('nq-signal').setAttribute('aria-label', 'Điểm bất thường DHGNN + EBM');
}

const watchKey = () => 'nq-history-watch:' + USER.username;
export function historicalWatch() {
  const saved = JSON.parse(localStorage.getItem(watchKey()) || 'null');
  return (Array.isArray(saved) ? saved : [...sessions.keys()]).filter(s => sessions.has(s));
}
export function saveHistoryWatch(list) { localStorage.setItem(watchKey(), JSON.stringify(list)); }
export function sessionFor(sym, day) { return sessions.get(sym)?.get(day); }

export function selectHistoryDates(sym, preferred) {
  const days = [...sessions.get(sym).keys()].sort();
  D.SESSIONS = days;
  D.SESS_UTC = days.map(d => sessionFor(sym, d).open_ms);
  S.si = days.includes(preferred) ? days.indexOf(preferred) : days.length - 1;
}

function minuteBars(sym, day) {
  const key = sym + '|' + day;
  if (!minutes.has(key)) {
    const request = api('/historical/bars?' + new URLSearchParams({ symbol: sym, day }))
      .then(r => r.bars).catch(e => { minutes.delete(key); throw e; });
    minutes.set(key, request);
  }
  return minutes.get(key);
}

function groupBars(rows, size, day) {
  const bars = [];
  let lastClose = null;
  for (let i = 0; i < rows.length; i += size) {
    const group = rows.slice(i, i + size), end = group.at(-1);
    const trades = group.filter(b => b.c != null);
    const close = trades.at(-1)?.c ?? lastClose;
    bars.push({ t: end.t, minute: end.minute, day,
      o: trades[0]?.o ?? lastClose, c: close,
      h: trades.length ? Math.max(...trades.map(b => b.h)) : lastClose,
      l: trades.length ? Math.min(...trades.map(b => b.l)) : lastClose,
      v: group.reduce((v, b) => v + b.v, 0) });
    lastClose = close;
  }
  return bars;
}

export async function historySeries(sym, day, tf) {
  if (!sessionFor(sym, day)) return [];
  if (tf === '1D') {
    const dates = [...sessions.get(sym).keys()].filter(d => d <= day).sort();
    return (await Promise.all(dates.map(async d => groupBars(await minuteBars(sym, d), 390, d)))).flat();
  }
  return groupBars(await minuteBars(sym, day), TFS[tf], day);
}
