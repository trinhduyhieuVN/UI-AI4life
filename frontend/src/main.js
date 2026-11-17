import { $, root, S, D, SPEEDS, curRole, setSession } from './state.js';
import { api } from './api.js';
import { wireAuth, showAuth, enterApp } from './auth.js';
import { applyTheme, PAL } from './ui/theme.js';
import { toast } from './ui/toasts.js';
import { fmtDate } from './util.js';
import { audio, blip, chime, tickSound } from './sound.js';
import { loadMeta, loadSeries, prefetchWatch, fetchViews } from './data.js';
import { isOffline } from './offline.js';
import { restorePrefs, persist } from './prefs.js';
import { applyRole } from './roles.js';
import {
  defaultCount, clampView, followView, setCursor, setPlaying, stepSpeed, syncSpeed,
  setRangeFill, tg, syncControls, bindToggle, buildSessionSelect, syncHeader, syncTransport, syncAll,
} from './ui/transport.js';
import { renderList, renderViews, addDialog, saveViewPop, selectSymbol, removeSymbols, resetList } from './ui/rail.js';
import { typeMenu } from './chart/types.js';
import { renderSignals, saveReview, exportSignalsCSV } from './signals.js';
import { cv, geo, mouse, ptr, wrap, renderChart, exportPNG, exportCSV } from './chart/renderer.js';
import { userMenu, closePops } from './ui/menus.js';
import { dataAuthPop } from './ui/migrate.js';
import { closeDrawer, drawDrawerSpark, getDrawerSym } from './ui/drawer.js';

/* ---------- activity ping: phát hiện 401 giữa phiên phát ---------- */
let lastTouch = 0;
function touch(force) {
  const now = Date.now(), gap = force ? 700 : 5000;
  if (now - lastTouch < gap) return;
  lastTouch = now;
  api('/auth/me').catch(() => { /* 401 → sự kiện nq-unauth */ });
}

/* ---------- main loop (single rAF) ---------- */
function loop(t) {
  requestAnimationFrame(loop);
  const dt = D.lastT ? Math.min(500, t - D.lastT) : 16; D.lastT = t;
  if (S.playing && D.total > 0) {
    touch();
    D.acc += dt / 1000 * S.rate * SPEEDS[S.spd];
    let guard = 0;
    while (D.acc >= 1 && guard < 900) {
      D.acc -= 1; guard++;
      if (S.cursor >= D.total - 1) {
        if (S.loop) { S.cursor = 0; followView(); continue; }
        S.playing = false; D.acc = 0; chime();
        toast('Đã phát hết phiên ' + fmtDate(D.SESSIONS[S.si]) + ' · ' + S.sym, { kind: 'ok' });
        syncTransport();
        break;
      }
      S.cursor++;
      tickSound(D.bars[S.cursor].c >= D.bars[S.cursor].o);
    }
    followView(); D.dirty = true; D.sigDirty = true; syncTransport(); syncHeader();
  }
  if (S.playing || S.cursor < D.total - 1 || S.glow > 0.05) D.dirty = true;
  if (D.dirty) { renderChart(); D.dirty = false; }
  if (D.sigDirty && t - D.lastSigRender > 150) { D.lastSigRender = t; D.sigDirty = false; renderSignals(); }
}

/* ---------- hooks nối auth ↔ phần còn lại của app ---------- */
async function onEnter() {
  try {
    await loadMeta();
    restorePrefs();
    const resume = D.resume; D.resume = null;
    if (resume && D.SYM[resume.sym]) { S.sym = resume.sym; S.si = resume.si; }
    else { S.sym = D.watch[0] || (D.SYMBOLS[0] && D.SYMBOLS[0].s) || 'AAPL'; S.si = 0; }
    applyRole();
    buildSessionSelect();
    $('nq-session').value = S.si;
    await fetchViews();
    await loadSeries(true);
    if (resume) setCursor(resume.cursor, true);
    prefetchWatch();
    syncAll();
    D.dirty = true;
    if (window.innerWidth <= 820) $('nq-signal').classList.add('collapsed');
  } catch (e) { if (e.status !== 401) toast(e.message); }
}
function onLeave() { closeDrawer(); closePops(); }

/* ---------- chart interaction ---------- */
function wireChart() {
  cv.addEventListener('wheel', ev => {
    ev.preventDefault();
    const r = cv.getBoundingClientRect(), mx = ev.clientX - r.left;
    const plotW = r.width - geo.padL - geo.padR;
    const frac = Math.max(0, Math.min(1, (mx - geo.padL) / plotW));
    const anchor = S.view.start + frac * S.view.count;
    const f = ev.deltaY > 0 ? 1.14 : 1 / 1.14;
    const maxCount = S.tf === '1D' ? Math.max(11, D.total) : 390;
    S.view.count = Math.max(S.tf === '1D' ? 4 : 8, Math.min(maxCount, S.view.count * f));
    S.view.start = anchor - frac * S.view.count;
    clampView(); $('nq-c-zoom').value = Math.round(S.view.count); $('nq-o-zoom').textContent = Math.round(S.view.count); setRangeFill($('nq-c-zoom'));
    D.dirty = true;
  }, { passive: false });
  cv.addEventListener('pointerdown', ev => {
    cv.setPointerCapture(ev.pointerId);
    ptr.pointers[ev.pointerId] = { x: ev.clientX, y: ev.clientY };
    const ids = Object.keys(ptr.pointers);
    if (ids.length === 2) { const a = ptr.pointers[ids[0]], b = ptr.pointers[ids[1]]; ptr.pinchDist = Math.hypot(a.x - b.x, a.y - b.y); }
    else { ptr.panning = true; ptr.panX = ev.clientX; ptr.panStart = S.view.start; ptr.moved = 0; }
  });
  cv.addEventListener('pointermove', ev => {
    const r = cv.getBoundingClientRect();
    mouse.x = ev.clientX - r.left; mouse.y = ev.clientY - r.top; mouse.in = true;
    if (ptr.pointers[ev.pointerId]) ptr.pointers[ev.pointerId] = { x: ev.clientX, y: ev.clientY };
    const ids = Object.keys(ptr.pointers);
    if (ids.length === 2 && ptr.pinchDist > 0) {
      const a = ptr.pointers[ids[0]], b = ptr.pointers[ids[1]], d = Math.hypot(a.x - b.x, a.y - b.y);
      if (d > 4) {
        const maxCount = S.tf === '1D' ? Math.max(11, D.total) : 390;
        S.view.count = Math.max(S.tf === '1D' ? 4 : 8, Math.min(maxCount, S.view.count * (ptr.pinchDist / d))); ptr.pinchDist = d; clampView();
        $('nq-c-zoom').value = Math.round(S.view.count); $('nq-o-zoom').textContent = Math.round(S.view.count); setRangeFill($('nq-c-zoom'));
      }
      D.dirty = true; return;
    }
    if (ptr.panning) {
      const dx = ev.clientX - ptr.panX; ptr.moved += Math.abs(dx);
      const plotW = r.width - geo.padL - geo.padR, bw = plotW / S.view.count;
      S.view.start = ptr.panStart - dx / bw;
      if (ptr.moved > 4) { S.follow = false; tg('nq-t-follow', false); $('nq-follow').hidden = false; }
      clampView(); D.dirty = true;
    }
    D.dirty = true; syncHeader();
  });
  function endPointer(ev) {
    delete ptr.pointers[ev.pointerId];
    if (Object.keys(ptr.pointers).length < 2) ptr.pinchDist = 0;
    if (Object.keys(ptr.pointers).length === 0) ptr.panning = false;
  }
  cv.addEventListener('pointerup', endPointer);
  cv.addEventListener('pointercancel', endPointer);
  cv.addEventListener('pointerleave', () => { mouse.in = false; S.hover = null; D.dirty = true; syncHeader(); });
  cv.addEventListener('dblclick', () => { S.follow = true; tg('nq-t-follow', true); S.view.count = defaultCount(); followView(); clampView(); syncControls(); D.dirty = true; });
}

/* ---------- wiring ---------- */
function wire() {
  $('nq-typebtn').addEventListener('click', typeMenu);
  $('nq-data-auth').addEventListener('click', dataAuthPop);

  /* top */
  $('nq-session').addEventListener('change', function () {
    S.si = +this.value; D.acc = 0; D.QCACHE = {};
    loadSeries(true).then(() => toast('Phiên ' + fmtDate(D.SESSIONS[S.si]), { ms: 2000 }))
      .catch(e => { if (e.status !== 401) toast(e.message); });
    renderList(); D.dirty = true; persist(); touch(true);
  });
  $('nq-sound').addEventListener('click', () => { S.sound = !S.sound; tg('nq-t-sound', S.sound); syncControls(); persist(); if (S.sound) { audio(); blip(880, 0.08, 0.04); } toast('Âm thanh ' + (S.sound ? 'bật' : 'tắt'), { ms: 1800 }); });
  $('nq-user').addEventListener('click', userMenu);
  $('nq-railtoggle').addEventListener('click', () => $('nq-rail').classList.toggle('open'));

  /* rail */
  $('nq-q').addEventListener('input', function () { S.query = this.value; renderList(); });
  $('nq-sort').addEventListener('change', function () { if (curRole().rail !== 'rw') { this.value = S.sort; return; } S.sort = this.value; S.activeView = null; persist(); renderList(); renderViews(); });
  $('nq-selectmode').addEventListener('click', function () { if (!curRole().selectMode) return; S.selectMode = !S.selectMode; if (!S.selectMode) S.selected = {}; this.setAttribute('aria-pressed', S.selectMode ? 'true' : 'false'); renderList(); });
  $('nq-adddlg').addEventListener('click', addDialog);
  $('nq-bulk-del').addEventListener('click', () => { const k = Object.keys(S.selected); if (k.length) removeSymbols(k); });
  $('nq-bulk-clear').addEventListener('click', () => { S.selected = {}; renderList(); });
  $('nq-saveview').addEventListener('click', saveViewPop);
  $('nq-resetlist').addEventListener('click', resetList);

  /* transport */
  $('nq-play').addEventListener('click', () => { setPlaying(!S.playing); touch(true); });
  $('nq-prev').addEventListener('click', () => { setPlaying(false); setCursor(S.cursor - 1, true); touch(true); });
  $('nq-next').addEventListener('click', () => { setPlaying(false); setCursor(S.cursor + 1, true); touch(true); });
  $('nq-start').addEventListener('click', () => { setPlaying(false); S.cursor = 0; D.acc = 0; followView(); D.dirty = true; D.sigDirty = true; syncTransport(); syncHeader(); touch(true); });
  $('nq-end').addEventListener('click', () => { setPlaying(false); S.cursor = D.total - 1; D.acc = 0; followView(); D.dirty = true; D.sigDirty = true; syncTransport(); syncHeader(); touch(true); });
  $('nq-scrub').addEventListener('input', function () { const v = +this.value; setPlaying(false); setCursor(v, true); touch(true); });
  $('nq-spd-dn').addEventListener('click', () => stepSpeed(-1));
  $('nq-spd-up').addEventListener('click', () => stepSpeed(1));
  $('nq-follow').addEventListener('click', () => { S.follow = true; tg('nq-t-follow', true); followView(); clampView(); $('nq-follow').hidden = true; D.dirty = true; persist(); });

  /* signal panel */
  $('nq-sig-t').addEventListener('click', function () {
    const col = $('nq-signal').classList.toggle('collapsed');
    this.setAttribute('aria-expanded', col ? 'false' : 'true'); D.dirty = true;
  });
  $('nq-sig-f').addEventListener('click', e => {
    const c = e.target.closest('[data-f]'); if (!c) return;
    S.sigFilter = c.getAttribute('data-f'); D.sigDirty = true; renderSignals();
  });
  $('nq-sig-blind').addEventListener('click', () => {
    if (!curRole().blind) return;
    S.blind = !S.blind; D.sigDirty = true; renderSignals();
    toast(S.blind ? 'Rà soát mù BẬT — điểm số & ngưỡng bị ẩn, CSV tín hiệu tạm khoá' : 'Rà soát mù TẮT — điểm số hiện lại', { kind: S.blind ? 'warn' : 'ok', ms: 2600 });
  });
  $('nq-sig-csv').addEventListener('click', exportSignalsCSV);
  $('nq-sig-b').addEventListener('click', e => {
    const lab = e.target.closest('[data-lab]');
    if (lab) { const row = lab.closest('[data-eid]'); if (row) saveReview(row.getAttribute('data-eid'), lab.getAttribute('data-lab')); return; }
    const rw = e.target.closest('[data-sym]'); if (!rw) return;
    const sym = rw.getAttribute('data-sym');
    if (D.watch.indexOf(sym) >= 0) selectSymbol(sym);
    else toast(sym + ' nằm ngoài watchlist của bạn — hàng giám sát chỉ xem, không tự thêm mã.', { ms: 2600 });
  });

  /* controls */
  $('nq-c-speed').addEventListener('input', function () { S.spd = Math.max(0, Math.min(curRole().maxSpd, +this.value)); this.value = S.spd; syncSpeed(); persist(); });
  $('nq-c-tf').addEventListener('change', function () {
    if (curRole().tfs.indexOf(this.value) < 0) { this.value = S.tf; toast('Vai trò ' + curRole().label + ' chỉ dùng khung ' + curRole().tfs.join(', ') + '.', { kind: 'warn', ms: 2600 }); return; }
    S.tf = this.value; D.acc = 0; D.QCACHE = {};
    loadSeries(true).then(() => toast('Khung ' + S.tf + ' · ' + D.total + ' nến', { ms: 2000 }))
      .catch(e => { if (e.status !== 401) toast(e.message); });
    persist(); renderList(); D.dirty = true;
  });
  $('nq-c-density').addEventListener('input', function () { S.density = +this.value / 100; $('nq-o-density').textContent = this.value + '%'; setRangeFill(this); D.dirty = true; persist(); });
  $('nq-c-zoom').addEventListener('input', function () { S.view.count = +this.value; $('nq-o-zoom').textContent = this.value; setRangeFill(this); clampView(); D.dirty = true; });
  $('nq-c-vol').addEventListener('input', function () { S.volFrac = +this.value / 100; $('nq-o-vol').textContent = this.value + '%'; setRangeFill(this); D.dirty = true; persist(); });
  $('nq-c-theme').addEventListener('change', function () { applyTheme(this.value); syncControls(); renderList(); persist(); const ds = getDrawerSym(); if (ds) drawDrawerSpark(ds); });
  $('nq-c-glow').addEventListener('input', function () { S.glow = +this.value / 100; $('nq-o-glow').textContent = this.value + '%'; setRangeFill(this); D.dirty = true; persist(); });
  bindToggle('nq-t-follow', 'follow', () => { $('nq-follow').hidden = S.follow; if (S.follow) { followView(); clampView(); } persist(); });
  bindToggle('nq-t-loop', 'loop');
  bindToggle('nq-t-ma1', 'ma1On'); bindToggle('nq-t-ma2', 'ma2On');
  bindToggle('nq-t-vwap', 'vwap'); bindToggle('nq-t-grid', 'grid'); bindToggle('nq-t-cross', 'cross'); bindToggle('nq-t-future', 'future');
  bindToggle('nq-t-sound', 'sound', () => { syncControls(); if (S.sound) { audio(); blip(880, 0.08, 0.04); } });
  function stepMA(key, vid, d) { S[key] = Math.max(2, Math.min(200, S[key] + d)); $(vid).textContent = S[key]; D.dirty = true; persist(); syncHeader(); }
  $('nq-ma1-dn').addEventListener('click', () => stepMA('ma1', 'nq-ma1-v', -1));
  $('nq-ma1-up').addEventListener('click', () => stepMA('ma1', 'nq-ma1-v', 1));
  $('nq-ma2-dn').addEventListener('click', () => stepMA('ma2', 'nq-ma2-v', -1));
  $('nq-ma2-up').addEventListener('click', () => stepMA('ma2', 'nq-ma2-v', 1));
  $('nq-rate-dn').addEventListener('click', () => { S.rate = Math.max(0.2, +(S.rate - 0.2).toFixed(1)); $('nq-rate-v').textContent = S.rate.toFixed(1); persist(); });
  $('nq-rate-up').addEventListener('click', () => { S.rate = Math.min(12, +(S.rate + 0.2).toFixed(1)); $('nq-rate-v').textContent = S.rate.toFixed(1); persist(); });

  /* actions */
  $('nq-a-reset').addEventListener('click', () => {
    setPlaying(false); S.cursor = 0; D.acc = 0; S.follow = true; tg('nq-t-follow', true);
    S.view.count = defaultCount(); S.view.start = 0;
    syncControls(); D.dirty = true; toast('Đã đặt lại phiên phát', { ms: 2000 });
  });
  $('nq-a-random').addEventListener('click', () => {
    const pool = D.watch.length ? D.watch : D.SYMBOLS.map(x => x.s);
    const sym = pool[Math.floor(Math.random() * pool.length)];
    S.si = Math.floor(Math.random() * D.SESSIONS.length); $('nq-session').value = S.si;
    S.sym = sym; D.acc = 0; D.QCACHE = {}; S.follow = true; tg('nq-t-follow', true);
    loadSeries(true).then(() => {
      renderList(); setPlaying(true);
      toast('Ngẫu nhiên: ' + sym + ' · phiên ' + fmtDate(D.SESSIONS[S.si]), { kind: 'ok', ms: 2600 });
    }).catch(e => { if (e.status !== 401) toast(e.message); });
  });
  $('nq-a-png').addEventListener('click', exportPNG);
  $('nq-a-csv').addEventListener('click', exportCSV);
  $('nq-a-full').addEventListener('click', () => {
    const el = document.querySelector('.nq-stage');
    if (!document.fullscreenElement) { (el.requestFullscreen || el.webkitRequestFullscreen || function () {}).call(el); }
    else document.exitFullscreen && document.exitFullscreen();
  });
  $('nq-scrim').addEventListener('click', () => { closeDrawer(); $('nq-rail').classList.remove('open'); });

  /* keyboard */
  document.addEventListener('keydown', e => {
    if ($('nq-app').hidden) return;
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'SELECT' || t.tagName === 'TEXTAREA')) return;
    if (t && t.closest && t.closest('.nq-pop,.nq-menu') && e.key !== 'Escape') return;
    if (e.key === ' ') { e.preventDefault(); setPlaying(!S.playing); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); setPlaying(false); setCursor(S.cursor - (e.shiftKey ? 10 : 1), true); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); setPlaying(false); setCursor(S.cursor + (e.shiftKey ? 10 : 1), true); }
    else if (e.key === '+' || e.key === '=') stepSpeed(1);
    else if (e.key === '-' || e.key === '_') stepSpeed(-1);
    else if (e.key === 'r' || e.key === 'R') $('nq-a-reset').click();
    else if (e.key === 'f' || e.key === 'F') { if (!$('nq-follow').hidden) $('nq-follow').click(); }
    else if (e.key === 'Home') { e.preventDefault(); $('nq-start').click(); }
    else if (e.key === 'End') { e.preventDefault(); $('nq-end').click(); }
    else if (e.key === 'Escape') { closeDrawer(); closePops(); $('nq-rail').classList.remove('open'); }
  });

  /* resize */
  if (window.ResizeObserver) {
    const ro = new ResizeObserver(() => { D.dirty = true; const ds = getDrawerSym(); if (ds) drawDrawerSpark(ds); });
    ro.observe(wrap); ro.observe(root);
  }
  window.addEventListener('resize', () => { D.dirty = true; const ds = getDrawerSym(); if (ds) drawDrawerSpark(ds); });
  document.addEventListener('fullscreenchange', () => { setTimeout(() => { D.dirty = true; }, 60); });
}

/* ---------- boot ---------- */
/* Online lại: máy chủ thắng — nạp lại prefs/caps, giữ nguyên sym/si/cursor đang xem. */
async function resyncServer() {
  try {
    const me = await api('/auth/me');
    const prevTf = S.tf;
    setSession(me);
    restorePrefs();
    applyRole();
    if (S.tf !== prevTf) await loadSeries(false);
    syncAll(); renderList(); renderViews();
  } catch (e) { /* vẫn offline hoặc hết phiên — nq-unauth xử lý */ }
}

async function boot() {
  D.hooks.onEnter = onEnter;
  D.hooks.onLeave = onLeave;
  D.hooks.onQuoteReady = () => renderList();
  wireAuth();
  wire();
  wireChart();
  applyTheme('workbench');
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
  let installEvt = null;
  window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); installEvt = e; $('nq-install').hidden = false; });
  window.addEventListener('appinstalled', () => { installEvt = null; $('nq-install').hidden = true; });
  $('nq-install').addEventListener('click', () => {
    if (!installEvt) return;
    installEvt.prompt();
    installEvt.userChoice.finally(() => { installEvt = null; $('nq-install').hidden = true; });
  });
  const syncOfflineBanner = () => { $('nq-offline-banner').hidden = !isOffline(); };
  window.addEventListener('offline', syncOfflineBanner);
  window.addEventListener('online', () => { syncOfflineBanner(); resyncServer(); });
  syncOfflineBanner();
  try {
    const me = await api('/auth/me');
    enterApp(me);
  } catch (e) {
    showAuth();
  }
  requestAnimationFrame(loop);
  document.addEventListener('pointerdown', function once() { if (S.sound) audio(); document.removeEventListener('pointerdown', once); }, { once: true });
}

/* 401 giữa phiên: lưu vị trí phát, về màn auth; đăng nhập lại sẽ khôi phục. */
window.addEventListener('nq-unauth', () => {
  if (!$('nq-app').hidden) {
    D.resume = { sym: S.sym, si: S.si, cursor: S.cursor };
    S.playing = false;
    setSession(null);
    closeDrawer(); closePops();
    showAuth();
    toast('Phiên đăng nhập đã hết hạn — vui lòng đăng nhập lại.', { kind: 'warn' });
  }
});

boot();