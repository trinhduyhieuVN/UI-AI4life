import { historicalWatch } from './history.js';
export const root = document.getElementById('nq-root');
export const $ = id => document.getElementById(id);

export const SPEEDS = [0.5, 1, 2, 4, 8, 16, 32, 64];
export const MINUTES = 390;
/* 09:30 America/New_York; every session in this window is EST (UTC-5). */
export const ET_OFFSET = 5 * 3600 * 1000;
export const TFS = { '1m': 1, '5m': 5, '15m': 15, '1h': 60, '1D': 0 };

/* Trạng thái phiên phát lại — giá trị chart lấy từ máy chủ qua restorePrefs. */
export const S = {
  sym: 'AAPL', si: 0, tf: '5m', type: 'hollow', cursor: 0, playing: false, spd: 1, rate: 2,
  follow: true, loop: false, density: .70, volFrac: .26, glow: .30,
  ma1: 9, ma2: 21, ma1On: true, ma2On: true, vwap: true, grid: true, cross: true, future: true, sound: true,
  view: { start: 0, count: 90 }, hover: null, selectMode: false, selected: {}, query: '', sort: 'manual',
  activeView: null, dirty: true, sigFilter: 'all', blind: false,
};

/* Runtime chung: dữ liệu thị trường tải từ API + cache + hook nối module. */
export const D = {
  SESSIONS: [], SESS_UTC: [], SYMBOLS: [], SYM: {},
  bars: [], total: 0,
  dirty: true, sigDirty: true, acc: 0, lastT: 0, lastSigRender: 0, lastSigKey: '',
  QCACHE: {}, HAC: {},
  seriesCache: new Map(), sigCache: new Map(),
  resume: null, watch: [], views: [], reviews: {},
  hooks: {},
};

export let USER = null;
export let prefsCache = null;
export let capsCache = null;

/* Fail-closed: chưa có caps từ máy chủ thì coi như observer (chỉ đọc). */
const FALLBACK_CAPS = {
  id: 'observer', label: 'Quan sát', short: '',
  controls: false, rail: 'ro', views: false, addSymbol: false, selectMode: false, sort: false,
  types: ['line', 'area', 'candles'], tfs: ['5m'], maxSpd: 3,
  ctl: { speed: true }, acts: {},
  signals: 'headlines', sigScope: 'symbol', review: false, blind: false, sigCSV: false,
  forceFuture: true, dataManager: false, drawerEdit: false, png: false, csv: false, audit: false,
};

export function curRole() { return capsCache || FALLBACK_CAPS; }
export function prefs() { return prefsCache; }

export function setSession(me) {
  USER = me ? me.user : null;
  prefsCache = me ? me.prefs : null;
  capsCache = me ? me.caps : null;
  D.watch = me && me.watch ? me.watch.slice() : [];
  if (me && D.historical) D.watch = historicalWatch();
  D.views = me && me.views ? me.views.map(v => ({ id: null, name: v.name, symbols: v.symbols || [], sort: v.sort || 'manual', tf: v.tf || '5m' })) : [];
  D.reviews = me && me.reviews ? me.reviews : {};
  if (!me) { D.QCACHE = {}; D.sigCache.clear(); }
}
