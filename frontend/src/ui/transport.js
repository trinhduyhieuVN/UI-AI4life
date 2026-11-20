import { S, D, $, root, curRole, SPEEDS } from '../state.js';
import { nfmt, vfmt, hhmm, hhmmss, fmtDate, fmtDateShort, rgba } from '../util.js';
import { PAL } from './theme.js';
import { tickSound, audio } from '../sound.js';
import { chgInfo } from '../data.js';
import { renderList, renderViews } from './rail.js';
import { syncTypeBtn, ctDef, haArr } from '../chart/types.js';
import { renderSignals } from '../signals.js';
import { persist } from '../prefs.js';
import { toast } from './toasts.js';

export function defaultCount() {
  if (S.tf === '1D') return Math.max(11, D.total);
  return S.tf === '1m' ? 120 : S.tf === '5m' ? 60 : S.tf === '15m' ? 26 : 7;
}
export function clampView() {
  const maxCount = S.tf === '1D' ? Math.max(11, D.total) : 390;
  const minCount = S.tf === '1D' ? 4 : 8;
  S.view.count = Math.max(minCount, Math.min(S.view.count, maxCount));
  const maxStart = Math.max(0, D.total - S.view.count * 0.18);
  S.view.start = Math.max(0, Math.min(S.view.start, maxStart));
}
export function followView() {
  if (!S.follow) return;
  const target = S.cursor - S.view.count * 0.80;
  S.view.start = Math.max(0, Math.min(target, Math.max(0, D.total - S.view.count * 0.18)));
}
export function setCursor(v, silent) {
  const old = S.cursor;
  S.cursor = Math.max(0, Math.min(Math.round(v), D.total - 1));
  if (S.cursor > old && !silent) tickSound(D.bars[S.cursor].c >= D.bars[S.cursor].o);
  followView(); D.dirty = true; D.sigDirty = true; syncTransport(); syncHeader();
}
export function setPlaying(p) {
  if (p && S.cursor >= D.total - 1) setCursor(0, true);
  S.playing = p; D.dirty = true; syncTransport();
  if (p) audio();
}
export function stepSpeed(d) {
  S.spd = Math.max(0, Math.min(SPEEDS.length - 1, curRole().maxSpd, S.spd + d));
  $('nq-c-speed').value = S.spd; syncSpeed(); persist(); D.dirty = true;
}
export function syncSpeed() {
  const v = SPEEDS[S.spd]; const txt = (v < 1 ? v.toFixed(1) : v) + '×';
  $('nq-spd-v').textContent = txt; $('nq-o-speed').textContent = txt;
  setRangeFill($('nq-c-speed'));
}
export function setRangeFill(el) {
  const min = +el.min, max = +el.max, v = +el.value;
  el.style.setProperty('--p', ((v - min) / (max - min) * 100) + '%');
}

export function tg(id, on) { const e = $(id); e.setAttribute('aria-pressed', on ? 'true' : 'false'); e.setAttribute('aria-checked', on ? 'true' : 'false'); }
export function syncControls() {
  $('nq-c-tf').value = S.tf; $('nq-sort').value = S.sort;
  $('nq-c-density').value = Math.round(S.density * 100); $('nq-o-density').textContent = Math.round(S.density * 100) + '%';
  $('nq-c-zoom').value = Math.round(S.view.count); $('nq-o-zoom').textContent = Math.round(S.view.count);
  $('nq-c-vol').value = Math.round(S.volFrac * 100); $('nq-o-vol').textContent = Math.round(S.volFrac * 100) + '%';
  $('nq-c-glow').value = Math.round(S.glow * 100); $('nq-o-glow').textContent = Math.round(S.glow * 100) + '%';
  $('nq-c-speed').value = S.spd;
  $('nq-ma1-v').textContent = S.ma1; $('nq-ma2-v').textContent = S.ma2;
  $('nq-rate-v').textContent = S.rate.toFixed(1);
  tg('nq-t-follow', S.follow); tg('nq-t-loop', S.loop); tg('nq-t-ma1', S.ma1On); tg('nq-t-ma2', S.ma2On);
  tg('nq-t-vwap', S.vwap); tg('nq-t-grid', S.grid); tg('nq-t-cross', S.cross); tg('nq-t-future', S.future); tg('nq-t-sound', S.sound);
  $('nq-sound').setAttribute('aria-pressed', S.sound ? 'true' : 'false');
  $('nq-sound').setAttribute('aria-label', S.sound ? 'Tắt âm thanh' : 'Bật âm thanh');
  $('nq-sound').title = 'Âm thanh: ' + (S.sound ? 'bật' : 'tắt');
  $('nq-sound').style.color = S.sound ? PAL.cy : PAL.dim;
  $('nq-selectmode').setAttribute('aria-pressed', S.selectMode ? 'true' : 'false');
  ['nq-c-density', 'nq-c-zoom', 'nq-c-vol', 'nq-c-glow', 'nq-c-speed', 'nq-scrub'].forEach(id => setRangeFill($(id)));
  syncSpeed();
}
export function bindToggle(id, key, after) {
  $(id).addEventListener('click', () => {
    if (key === 'future' && curRole().forceFuture) { tg(id, true); toast('Vai trò ' + curRole().label + ' bắt buộc khoá nhìn trước — không thể tắt trong quy trình mô phỏng này.', { kind: 'warn', ms: 3200 }); return; }
    S[key] = !S[key]; tg(id, S[key]); D.dirty = true; persist(); syncHeader(); if (after) after();
  });
}

export function buildSessionSelect() {
  const sel = $('nq-session'); sel.innerHTML = '';
  D.SESSIONS.forEach((d, i) => { const o = document.createElement('option'); o.value = i; o.textContent = fmtDate(d); sel.appendChild(o); });
  sel.value = S.si;
}

let legendMarkup, playIconState;
export function syncHeader() {
  const ci = chgInfo();
  const meta = D.SYM[S.sym] || { n: '', sec: '' };
  $('nq-ch-sym').textContent = S.sym;
  $('nq-ch-name').textContent = meta.n + ' · ' + meta.sec;
  const pxE = $('nq-ch-px'); pxE.textContent = nfmt(ci.px, 2); pxE.style.color = ci.up ? PAL.up : PAL.dn;
  const ch = $('nq-ch-chg');
  ch.textContent = (ci.d >= 0 ? '+' : '') + nfmt(ci.d, 2) + '  (' + (ci.p >= 0 ? '+' : '') + nfmt(ci.p, 2) + '%)';
  ch.style.color = ci.up ? PAL.up : PAL.dn;
  ch.style.background = rgba(ci.up ? PAL.up : PAL.dn, PAL.light ? 0.15 : 0.13);
  const idx = S.hover != null ? S.hover : S.cursor, b = (S.type === 'ha' ? haArr()[idx] : D.bars[idx]);
  const oh = $('nq-ohlc');
  if (b) {
    const u = b.c >= b.o, cl = u ? PAL.up : PAL.dn;
    oh.innerHTML = (S.type === 'ha' ? '<span style="color:' + PAL.mg + ';font-weight:700">HA</span>' : '') +
      '<span>O<b style="color:' + cl + '">' + nfmt(b.o, 2) + '</b></span>' +
      '<span>H<b style="color:' + cl + '">' + nfmt(b.h, 2) + '</b></span>' +
      '<span>L<b style="color:' + cl + '">' + nfmt(b.l, 2) + '</b></span>' +
      '<span>C<b style="color:' + cl + '">' + nfmt(b.c, 2) + '</b></span>' +
      '<span>V<b>' + vfmt(b.v) + '</b></span>' +
      '<span>' + (S.tf === '1D' ? fmtDate(D.SESSIONS[idx] || '') : hhmm(b.t)) + '</span>';
  } else oh.innerHTML = '';
  const lg = $('nq-legend');
  const legend =
    '<span class="nq-lg ct"><i style="background:' + PAL.mg + '"></i>' + ctDef(S.type).s + '</span>' +
    '<span class="nq-lg' + (S.ma1On ? '' : ' off') + '"><i style="background:' + PAL.am + '"></i>MA' + S.ma1 + '</span>' +
    '<span class="nq-lg' + (S.ma2On ? '' : ' off') + '"><i style="background:' + PAL.vi + '"></i>MA' + S.ma2 + '</span>' +
    '<span class="nq-lg' + (S.vwap ? '' : ' off') + '"><i style="background:' + PAL.cy + '"></i>VWAP</span>' +
    '<span class="nq-lg"><i style="background:' + PAL.up + '"></i>TĂNG</span>' +
    '<span class="nq-lg"><i style="background:' + PAL.dn + '"></i>GIẢM</span>' +
    '<span class="nq-lg"><i style="background:' + PAL.mg + '"></i>NẾN PHÁT LẠI</span>' +
    (S.tf !== '1D' ? '<span class="nq-lg"><i style="background:' + PAL.am + '"></i>' + (D.historical ? 'CẢNH BÁO DHGNN + EBM' : 'TÍN HIỆU MẪU') + '</span>' : '');
  if (legendMarkup !== legend) { lg.innerHTML = legend; legendMarkup = legend; }
}
export function syncTransport() {
  const bars = D.bars, total = D.total, SESSIONS = D.SESSIONS, SESS_UTC = D.SESS_UTC;
  if (playIconState !== S.playing) {
    playIconState = S.playing;
    $('nq-play').innerHTML = S.playing
      ? '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 5h3.6v14H7zM13.4 5H17v14h-3.6z"/></svg>'
      : '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.2v13.6L19 12z"/></svg>';
    $('nq-play').setAttribute('aria-label', S.playing ? 'Tạm dừng' : 'Phát');
  }
  const sc = $('nq-scrub'); sc.value = S.cursor; setRangeFill(sc);
  const pct = total > 1 ? Math.round(S.cursor / (total - 1) * 100) : 0;
  $('nq-sc-pct').textContent = pct + '%';
  $('nq-sc-a').textContent = S.tf === '1D' ? fmtDateShort(SESSIONS[0]) : (D.historical ? hhmm(SESS_UTC[S.si]) : (bars[0] ? hhmm(bars[0].t) : '09:30'));
  $('nq-sc-b').textContent = S.tf === '1D' ? fmtDateShort(SESSIONS[S.si]) : (bars[total - 1] ? hhmm(bars[total - 1].t) : '16:00');
  $('nq-b-tf').textContent = S.tf;
  $('nq-b-count').textContent = (S.cursor + 1) + '/' + total + ' nến';
  const st = $('nq-b-state');
  st.textContent = S.playing ? 'ĐANG PHÁT' : (S.cursor >= total - 1 ? 'HẾT PHIÊN' : 'TẠM DỪNG');
  st.classList.toggle('hot', S.playing);
  $('nq-follow').hidden = S.follow;
  let clockMs;
  if (S.tf === '1D') { clockMs = SESS_UTC[Math.min(S.cursor, SESSIONS.length - 1)]; $('nq-clock').innerHTML = fmtDate(SESSIONS[Math.min(S.cursor, SESSIONS.length - 1)]) + '<small>ET</small>'; }
  else { clockMs = bars[S.cursor] ? bars[S.cursor].t : SESS_UTC[S.si]; $('nq-clock').innerHTML = hhmmss(clockMs) + '<small>ET</small>'; }
  $('nq-sig-asof').textContent = 'As-of ' + (S.tf === '1D' ? fmtDate(SESSIONS[Math.min(S.cursor, S.si)]) : hhmm(clockMs));
  $('nq-st-sym').textContent = S.sym; $('nq-st-tf').textContent = S.tf;
  $('nq-st-bars').textContent = (S.cursor + 1) + '/' + total + ' nến đã hiện';
  $('nq-st-sess').textContent = 'Phiên ' + fmtDate(SESSIONS[S.si]);
  $('nq-rail-sess').textContent = fmtDate(SESSIONS[S.si]);
  $('nq-rail-sub').textContent = (S.cursor + 1) + '/' + total + ' nến · khung ' + S.tf;
}
export function syncAll() { syncHeader(); syncTransport(); syncSpeed(); renderList(); renderViews(); syncControls(); syncTypeBtn(); renderSignals(); }
