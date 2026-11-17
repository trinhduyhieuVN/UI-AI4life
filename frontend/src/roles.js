import { S, D, $, root, curRole, setSession } from './state.js';
import { api } from './api.js';
import { persist } from './prefs.js';
import { loadSeries, fetchViews } from './data.js';
import { syncAll } from './ui/transport.js';
import { popAt, closePops } from './ui/menus.js';
import { ROLE_ORDER, ROLE_META } from './auth.js';
import { toast } from './ui/toasts.js';

const ROLE_ROWS = {
  speed: 'nq-c-speed', follow: 'nq-t-follow', loop: 'nq-t-loop', rate: 'nq-rate-v', tf: 'nq-c-tf',
  density: 'nq-c-density', zoom: 'nq-c-zoom', vol: 'nq-c-vol', ma1: 'nq-t-ma1', ma2: 'nq-t-ma2',
  vwap: 'nq-t-vwap', grid: 'nq-t-grid', cross: 'nq-t-cross', future: 'nq-t-future', theme: 'nq-c-theme', glow: 'nq-c-glow', sound: 'nq-t-sound',
};
const ROLE_ACTS = { reset: 'nq-a-reset', random: 'nq-a-random', png: 'nq-a-png', csv: 'nq-a-csv', full: 'nq-a-full' };

/* Chỉ dùng hidden attr — sync/zoom/keyboard vẫn truy vấn mọi id vô điều kiện. */
export function applyRole() {
  const r = curRole(); let tfChanged = false, k;
  root.setAttribute('data-role', r.id);
  if (S.spd > r.maxSpd) S.spd = r.maxSpd;
  if (r.tfs.indexOf(S.tf) < 0) { S.tf = r.tfs[0]; tfChanged = true; }
  if (r.types.indexOf(S.type) < 0) S.type = r.types[0];
  if (r.forceFuture) S.future = true;
  if (!r.selectMode) { S.selectMode = false; S.selected = {}; }
  if (!r.blind) S.blind = false;
  $('nq-controls').hidden = !r.controls;
  for (k in ROLE_ROWS) { const row = $(ROLE_ROWS[k]).closest('.nq-c'); if (row) row.hidden = !r.ctl[k]; }
  ['nq-ma1-dn', 'nq-ma1-up', 'nq-ma2-dn', 'nq-ma2-up'].forEach(id => { $(id).hidden = !r.ctl.maSteppers; });
  const secs = $('nq-ctl-scroll').querySelectorAll('.nq-sec');
  for (let s = 0; s < secs.length; s++) {
    const rows = secs[s].querySelectorAll('.nq-c'); let any = false;
    for (let j = 0; j < rows.length; j++) if (!rows[j].hidden) { any = true; break; }
    secs[s].hidden = !any;
  }
  for (k in ROLE_ACTS) $(ROLE_ACTS[k]).hidden = !r.acts[k];
  const actsWrap = $('nq-a-reset').closest('.nq-acts'), actBtns = actsWrap.querySelectorAll('button'); let anyAct = false;
  for (let a2 = 0; a2 < actBtns.length; a2++) if (!actBtns[a2].hidden) { anyAct = true; break; }
  actsWrap.closest('.nq-sec').hidden = !anyAct;
  const ft = $('nq-t-future');
  if (r.forceFuture) { ft.setAttribute('aria-disabled', 'true'); ft.title = 'Vai trò ' + r.label + ' bắt buộc khoá nhìn trước — không thể tắt.'; }
  else { ft.removeAttribute('aria-disabled'); ft.removeAttribute('title'); }
  $('nq-c-speed').max = r.maxSpd;
  $('nq-views').hidden = !r.views;
  root.querySelector('.nq-rail-f').hidden = !r.views;
  $('nq-selectmode').hidden = !r.selectMode;
  $('nq-adddlg').hidden = !r.addSymbol;
  $('nq-sort').hidden = !r.sort;
  root.querySelector('.nq-rail-tools').hidden = !r.sort && !r.addSymbol;
  const visRows = $('nq-ctl-scroll').querySelectorAll('.nq-c:not([hidden])').length;
  const visActs = actsWrap.querySelectorAll('button:not([hidden])').length;
  $('nq-ctl-count').textContent = (visRows + visActs) + ' mục';
  const chip = $('nq-rolechip'); chip.textContent = r.label; chip.title = r.short;
  D.sigDirty = true; persist();
  return tfChanged;
}

export function rolePop() {
  closePops();
  const cur = curRole();
  const m = document.createElement('div'); m.className = 'nq-menu nq-rolemenu';
  m.setAttribute('role', 'menu'); m.setAttribute('aria-label', 'Đổi vai trò');
  let html = '<div class="nq-lbl">Kiểu khách hàng</div>';
  ROLE_ORDER.forEach(id => {
    const rr = ROLE_META[id];
    html += '<button data-rid="' + id + '"' + (id === cur.id ? ' class="cur"' : '') + '><span class="nq-rck">' + (id === cur.id ? '✓' : '') + '</span><span><b>' + rr.label + '</b><small>' + rr.short + '</small></span></button>';
  });
  m.innerHTML = html;
  const ub = $('nq-user').getBoundingClientRect(), rr2 = root.getBoundingClientRect();
  popAt(m, ub.right - 260, ub.bottom + 6);
  m.style.left = Math.max(8, Math.min(ub.right - rr2.left - 260, rr2.width - 268)) + 'px';
  m.style.top = (ub.bottom - rr2.top + 6) + 'px';
  m.addEventListener('click', e => {
    const b = e.target.closest('[data-rid]'); if (!b) return;
    const id = b.getAttribute('data-rid'); closePops();
    if (id === curRole().id) return;
    switchRole(id);
  });
}

async function switchRole(id) {
  try {
    await api('/prefs', { method: 'PUT', body: { role: id } });
    const me = await api('/auth/me');
    setSession(me);
    const tfc = applyRole();
    await fetchViews();
    if (tfc) await loadSeries(true);
    syncAll(); D.dirty = true;
    toast('Đã đổi vai trò: ' + ROLE_META[id].label + ' — giao diện và bảng tín hiệu đã điều chỉnh, phiên phát giữ nguyên.', { kind: 'ok', ms: 3400 });
  } catch (e) { if (e.status !== 401) toast(e.message); }
}