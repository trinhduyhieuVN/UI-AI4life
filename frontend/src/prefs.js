import { S, D, $, root, prefs, curRole } from './state.js';
import { api } from './api.js';
import { applyTheme } from './ui/theme.js';
import { toast } from './ui/toasts.js';
import { CTYPES } from './chart/types.js';

/* /me trả prefs phẳng: {role,theme,future} + chart_json spread.
   Tài khoản mới chart_json="{}" → mọi giá trị chart phải có default. */
export function restorePrefs() {
  const p = prefs(); if (!p) return;
  const ov = p.overlays || {}, sl = p.sliders || {};
  S.tf = p.tf || '5m';
  S.type = CTYPES.some(t => t.id === p.type) ? p.type : 'hollow';
  S.spd = p.spd == null ? 1 : p.spd;
  S.rate = sl.rate == null ? 2 : sl.rate;
  S.density = (sl.density == null ? 70 : sl.density) / 100;
  S.volFrac = (sl.vol == null ? 26 : sl.vol) / 100;
  S.glow = (p.glow == null ? 30 : p.glow) / 100;
  S.ma1 = ov.ma1 || 9; S.ma2 = ov.ma2 || 21;
  S.vwap = ov.vwap !== false; S.grid = ov.grid !== false; S.cross = ov.cross !== false;
  S.future = p.future !== false;
  S.sound = p.sound !== false;
  S.view.count = sl.zoom == null ? 90 : sl.zoom;
  /* Không có trong schema máy chủ — mặc định theo phiên. */
  S.ma1On = true; S.ma2On = true; S.follow = true; S.loop = false; S.sort = 'manual';
  if (curRole().forceFuture) S.future = true;
  applyTheme(p.theme || 'workbench');
}

let persistTimer = null;
export function persist() {
  if (!prefs()) return;
  clearTimeout(persistTimer);
  persistTimer = setTimeout(flushPersist, 400);
}
export function flushPersist() {
  clearTimeout(persistTimer); persistTimer = null;
  if (!prefs()) return;
  const theme = root.getAttribute('data-theme');
  const body = {
    theme, future: S.future,
    chart: {
      type: S.type, tf: S.tf, spd: S.spd, theme,
      overlays: { ma1: S.ma1, ma2: S.ma2, vwap: S.vwap, grid: S.grid, cross: S.cross },
      sliders: { rate: S.rate, density: Math.round(S.density * 100), zoom: Math.round(S.view.count), vol: Math.round(S.volFrac * 100) },
      glow: Math.round(S.glow * 100), sound: S.sound,
    },
  };
  api('/prefs', { method: 'PUT', body }).then(r => {
    const p = prefs(); if (!p) return;
    p.theme = r.theme; p.future = r.future;
    Object.assign(p, r.chart || {});
  }).catch(e => {
    if (e.status === 409 && e.cap === 'forceFuture') { S.future = true; return; }
    if (e.status !== 401) toast(e.message);
  });
}