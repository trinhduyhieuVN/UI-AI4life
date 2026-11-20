import { S, D, $, curRole } from './state.js';
import { api, ApiError } from './api.js';
import { isOffline, loadOffline, saveSession, OFFLINE_NODATA_MSG } from './offline.js';
import { clampView, followView, defaultCount, syncAll, buildSessionSelect } from './ui/transport.js';
import { historySeries, sessionFor, selectHistoryDates, historicalWatch, saveHistoryWatch } from './history.js';

let metaPromise = null;
export function loadMeta() {
  if (D.SESSIONS.length) return Promise.resolve();
  if (metaPromise) return metaPromise;
  metaPromise = Promise.all([api('/symbols'), api('/sessions')]).then(([sy, se]) => {
    D.SYMBOLS = sy.symbols.map(x => ({ s: x.symbol, n: x.name, sec: x.sector }));
    D.SYM = {}; D.SYMBOLS.forEach(x => { D.SYM[x.s] = x; });
    D.SESSIONS = se.sessions;
    D.SESS_UTC = D.SESSIONS.map(d => { const p = d.split('-'); return Date.UTC(+p[0], +p[1] - 1, +p[2], 14, 30, 0); });
  }).catch(e => { metaPromise = null; throw e; });
  return metaPromise;
}

const seriesPending = new Map();
export function peekSeries(sym, si, tf) { return D.seriesCache.get(sym + '|' + D.SESSIONS[si] + '|' + tf) || null; }
export function ensureSeries(sym, si, tf) {
  const key = sym + '|' + D.SESSIONS[si] + '|' + tf;
  if (D.historical && !sessionFor(sym, D.SESSIONS[si])) return Promise.resolve([]);
  if (D.seriesCache.has(key)) return Promise.resolve(D.seriesCache.get(key));
  if (seriesPending.has(key)) return seriesPending.get(key);
  const request = D.historical ? historySeries(sym, D.SESSIONS[si], tf).then(bars => ({ bars }))
    : api('/bars?symbol=' + encodeURIComponent(sym) + '&date=' + encodeURIComponent(D.SESSIONS[si]) + '&tf=' + encodeURIComponent(tf));
  const p = request
    .then(r => { D.seriesCache.set(key, r.bars); seriesPending.delete(key); return r.bars; })
    .catch(async e => {
      seriesPending.delete(key);
      if (!D.historical && isOffline()) {
        const rec = await loadOffline(sym, si);
        if (rec && rec.tf === tf && rec.bars && rec.bars.length) { D.seriesCache.set(key, rec.bars); return rec.bars; }
        throw new ApiError(0, OFFLINE_NODATA_MSG);
      }
      throw e;
    });
  seriesPending.set(key, p);
  return p;
}

let loadToken = 0;
export async function loadSeries(resetCursor) {
  const tok = ++loadToken;
  if (D.historical) {
    S.playing = false; D.acc = 0; S.hover = null;
    D.bars = []; D.total = 0; D.HAC = {}; D.QCACHE = {}; S.cursor = 0;
    $('nq-sig-b').textContent = 'Đang tải phiên…';
    selectHistoryDates(S.sym, D.SESSIONS[S.si]);
    buildSessionSelect();
  }
  const tf = S.tf;
  const bars = await ensureSeries(S.sym, S.si, tf);
  if (tok !== loadToken) return;
  D.bars = bars; D.total = bars.length; D.HAC = {};
  if (!D.historical) saveSession(S.sym, S.si, bars, null);
  const maxCount = tf === '1D' ? Math.max(11, D.total) : 390;
  $('nq-c-zoom').max = maxCount;
  $('nq-c-zoom').min = tf === '1D' ? 4 : 14;
  if (resetCursor) {
    /* warm start mid-session so the first paint is a living chart, not one candle */
    S.cursor = D.historical ? 0 : Math.max(0, Math.floor(D.total * 0.45));
    S.view.count = defaultCount(); S.view.start = 0;
  }
  S.cursor = Math.max(0, Math.min(S.cursor, D.total - 1));
  S.view.count = Math.min(S.view.count, maxCount);
  $('nq-scrub').max = Math.max(0, D.total - 1);
  clampView(); followView(); D.dirty = true; D.sigDirty = true; syncAll();
}

export function quote(sym) {
  const key = sym + '|' + S.si + '|' + S.tf + '|' + S.cursor;
  if (D.QCACHE[key]) return D.QCACHE[key];
  const ser = peekSeries(sym, S.si, S.tf);
  if (!ser || !ser.length) {
    if (!D.historical || sessionFor(sym, D.SESSIONS[S.si])) ensureSeries(sym, S.si, S.tf).then(() => { if (D.hooks.onQuoteReady) D.hooks.onQuoteReady(); }).catch(() => {});
    return { px: null, d: 0, p: 0, up: true, vol: 0, spark: [], ready: false };
  }
  const idx = Math.min(S.cursor, ser.length - 1);
  const ref = S.tf === '1D' ? (S.si > 0 && ser[S.si - 1] ? ser[S.si - 1].c : ser[0].o) : ser[0].o;
  const px = ser[idx] ? ser[idx].c : ser[0].o;
  const d = px - ref, p = ref ? d / ref * 100 : 0;
  let vol = 0; for (let i = 0; i <= idx && i < ser.length; i++) vol += ser[i].v;
  const spark = []; for (let i = Math.max(0, idx - 38); i <= idx; i++) if (ser[i]) spark.push(ser[i].c);
  const q = { px, d, p, up: d >= 0, vol, spark, ready: true };
  D.QCACHE[key] = q; return q;
}

export function chgInfo() {
  const bars = D.bars;
  if (!bars.length) return { px: null, ref: null, d: 0, p: 0, up: true };
  const ref = S.tf === '1D' ? (S.si > 0 && bars[S.si - 1] ? bars[S.si - 1].c : bars[0].o) : bars[0].o;
  const px = S.cursor >= 0 && bars[S.cursor] ? bars[S.cursor].c : bars[0].o;
  const d = px - ref, p = ref ? d / ref * 100 : 0;
  return { px, ref, d, p, up: d >= 0 };
}

export function prefetchWatch() {
  Promise.allSettled(D.watch.map(s => ensureSeries(s, S.si, S.tf)))
    .then(() => { if (D.hooks.onQuoteReady) D.hooks.onQuoteReady(); });
}

/* ---------- watchlist mutations (server-backed) ---------- */
export async function apiAddSymbol(sym) {
  if (D.historical) return saveHistoryWatch([...new Set([...historicalWatch(), sym])]);
  return api('/watchlist', { method: 'POST', body: { symbol: sym } });
}
export async function apiRemoveSymbol(sym) {
  if (D.historical) return saveHistoryWatch(historicalWatch().filter(s => s !== sym));
  return api('/watchlist/' + encodeURIComponent(sym), { method: 'DELETE' });
}
export async function apiOrder(symbols) {
  if (D.historical) return saveHistoryWatch(symbols);
  return api('/watchlist/order', { method: 'PUT', body: { symbols } });
}
/* /order đòi cùng tập thành viên → thay danh sách = DELETE phần bỏ + POST phần thêm + ORDER. */
export async function replaceWatch(newList) {
  const cur = D.watch.slice();
  for (const s of cur.filter(x => newList.indexOf(x) < 0)) await apiRemoveSymbol(s);
  for (const s of newList.filter(x => cur.indexOf(x) < 0)) await apiAddSymbol(s);
  await apiOrder(newList);
  D.watch = newList.slice();
}

/* ---------- views (server-backed, numeric row ids) ---------- */
export async function fetchViews() {
  if (!curRole().views) { D.views = []; return; }
  const r = await api('/views');
  D.views = r.views.map(v => ({
    id: v.id, name: v.name,
    symbols: (v.config && v.config.symbols) || [],
    sort: (v.config && v.config.sort) || 'manual',
    tf: (v.config && v.config.tf) || '5m',
  }));
}
export function apiSaveView(name, config) { return api('/views', { method: 'POST', body: { name, config } }); }
export function apiRenameView(vid, name) { return api('/views/' + vid, { method: 'PUT', body: { name } }); }
export function apiDeleteView(vid) { return api('/views/' + vid, { method: 'DELETE' }); }

/* ---------- drawer stats (exact, from 1m series) ---------- */
export async function drawerStats(sym, si) {
  const shownBar = D.bars[S.cursor];
  const index = D.historical && shownBar ? D.SESSIONS.indexOf(shownBar.day) : si;
  const all = await ensureSeries(sym, index, '1m');
  const m1 = D.historical ? all.filter(b => b.t <= shownBar.t) : all;
  const open = m1[0].o, close = m1[m1.length - 1].c;
  let high = -Infinity, low = Infinity, vol = 0, pv = 0;
  for (const b of m1) { if (b.h > high) high = b.h; if (b.l < low) low = b.l; vol += b.v; pv += (b.h + b.l + b.c) / 3 * b.v; }
  const vwap = vol ? pv / vol : open;
  let prev = open;
  if (index > 0) { const d1 = await ensureSeries(sym, index - 1, '1D'); if (d1.length) prev = d1.at(-1).c; }
  return { open, close, high, low, vol, vwap, prev };
}
