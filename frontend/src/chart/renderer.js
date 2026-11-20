import { S, D, $, root, curRole, TFS } from '../state.js';
import { nfmt, hhmm, fmtDateShort, rgba } from '../util.js';
import { PAL } from '../ui/theme.js';
import { toast, toastApiError } from '../ui/toasts.js';
import { apiBlob } from '../api.js';
import { maArr, vwapArr } from './overlays.js';
import { haArr } from './types.js';
import { currentSymbolEvents, sigCursorMinute } from '../signals.js';

export const cv = $('nq-chart'), ctx = cv.getContext('2d'), wrap = $('nq-wrap');
export const geo = { padL: 10, padR: 64, padT: 14, padB: 24, gap: 9 };
export const mouse = { x: null, y: null, in: false };
export const ptr = { pointers: {}, pinchDist: 0, panning: false, panX: 0, panStart: 0, moved: 0 };

export function sizeCanvas() {
  const W = wrap.clientWidth, H = wrap.clientHeight, dpr = Math.min(2, window.devicePixelRatio || 1);
  if (W < 2 || H < 2) return false;
  if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { W, H };
}
export function niceStep(range, target) {
  const raw = range / target, mag = Math.pow(10, Math.floor(Math.log10(raw))), n = raw / mag;
  const s = n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10; return s * mag;
}
export function roundRect(x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.lineTo(x + w - r, y); ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r); ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h); ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r); ctx.quadraticCurveTo(x, y, x + r, y); ctx.closePath();
}

export function renderChart() {
  const sz = sizeCanvas(); if (!sz) return;
  const bars = D.bars, total = D.total, SESSIONS = D.SESSIONS;
  const W = sz.W, H = sz.H;
  ctx.clearRect(0, 0, W, H);
  const padL = geo.padL, padR = geo.padR, padT = geo.padT, padB = geo.padB, gap = geo.gap;
  const plotW = W - padL - padR;
  if (plotW < 20 || H < 60) return;
  const volH = Math.max(0, (H - padT - padB) * S.volFrac);
  const priceH = H - padT - padB - volH - (volH > 0 ? gap : 0);
  const pTop = padT, pBot = padT + priceH, vTop = pBot + gap, vBot = H - padB;
  const bw = plotW / S.view.count;
  const i0 = Math.max(0, Math.floor(S.view.start)), i1 = Math.min(total - 1, Math.ceil(S.view.start + S.view.count));
  const last = Math.min(S.cursor, i1);
  function X(i) { return padL + (i - S.view.start + 0.5) * bw; }

  /* price range over revealed visible bars + overlays */
  const src = S.type === 'ha' ? haArr() : bars;
  let lo = Infinity, hi = -Infinity, vmax = 0;
  const ma1 = S.ma1On ? maArr(S.ma1) : null, ma2 = S.ma2On ? maArr(S.ma2) : null, vw = S.vwap ? vwapArr() : null;
  for (let i = i0; i <= last; i++) {
    const b = bars[i], rb = src[i];
    if (rb.l < lo) lo = rb.l; if (rb.h > hi) hi = rb.h; if (b.v > vmax) vmax = b.v;
    if (ma1 && ma1[i] != null) { if (ma1[i] < lo) lo = ma1[i]; if (ma1[i] > hi) hi = ma1[i]; }
    if (ma2 && ma2[i] != null) { if (ma2[i] < lo) lo = ma2[i]; if (ma2[i] > hi) hi = ma2[i]; }
    if (vw && vw[i] != null) { if (vw[i] < lo) lo = vw[i]; if (vw[i] > hi) hi = vw[i]; }
  }
  if (!isFinite(lo) || !isFinite(hi)) { lo = 0; hi = 1; }
  if (hi - lo < 1e-9) { hi = lo + Math.max(0.01, lo * 0.002); lo -= Math.max(0.01, lo * 0.002); }
  const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
  function Y(p) { return pBot - (p - lo) / (hi - lo) * priceH; }
  function VY(v) { return vBot - (vmax ? v / vmax : 0) * (volH - 3); }

  /* future lock region */
  if (S.future && S.cursor < total - 1) {
    const fx = X(S.cursor + 0.5);
    if (fx < W - padR) {
      ctx.save(); ctx.beginPath(); ctx.rect(fx, pTop, W - padR - fx, vBot - pTop); ctx.clip();
      ctx.fillStyle = rgba(PAL.bg0, PAL.light ? 0.5 : 0.62); ctx.fillRect(fx, pTop, W - padR - fx, vBot - pTop);
      ctx.strokeStyle = rgba(PAL.line2, 0.5); ctx.lineWidth = 1;
      for (let d = -H; d < W; d += 11) { ctx.beginPath(); ctx.moveTo(fx + d, pTop); ctx.lineTo(fx + d + H, vBot); ctx.stroke(); }
      ctx.restore();
      ctx.save(); ctx.fillStyle = rgba(PAL.dim, 0.98); ctx.font = '700 11px ' + getComputedStyle(root).getPropertyValue('--sans');
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      const lockW = W - padR - fx, lockA = 'CHƯA DIỄN RA', lockB = 'KHOÁ NHÌN TRƯỚC', lockOne = lockA + ' · ' + lockB;
      ctx.translate((fx + W - padR) / 2, (pTop + vBot) / 2);
      if (ctx.measureText(lockOne).width < lockW - 18) { ctx.fillText(lockOne, 0, 0); }
      else if (ctx.measureText(lockB).width < lockW - 14) { ctx.fillText(lockA, 0, -8); ctx.fillText(lockB, 0, 8); }
      ctx.restore();
    }
  }

  /* grid */
  if (S.grid) {
    const step = niceStep(hi - lo, 5);
    const lpy = (S.cursor >= 0 && S.cursor < total) ? Y(bars[S.cursor].c) : null;
    const xhy = (S.cross && mouse.in && mouse.y >= pTop && mouse.y <= pBot) ? mouse.y : null;
    ctx.lineWidth = 1; ctx.strokeStyle = rgba(PAL.grid, PAL.light ? 0.95 : 0.85);
    ctx.fillStyle = PAL.dim; ctx.font = '500 11px ' + getComputedStyle(root).getPropertyValue('--mono');
    ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    for (let p = Math.ceil(lo / step) * step; p <= hi; p += step) {
      const y = Math.round(Y(p)) + 0.5;
      if (y < pTop || y > pBot) continue;
      ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
      if (lpy != null && Math.abs(y - lpy) < 14) continue;
      if (xhy != null && Math.abs(y - xhy) < 14) continue;
      ctx.fillText(nfmt(p, p < 10 ? 3 : 2), W - padR + 7, y);
    }
    const tstep = Math.max(1, Math.round(S.view.count / 7));
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    for (let i = Math.ceil(i0 / tstep) * tstep; i <= i1; i += tstep) {
      if (i < 0 || i >= total) continue;
      const x = Math.round(X(i)) + 0.5;
      if (x < padL || x > W - padR) continue;
      ctx.strokeStyle = rgba(PAL.grid, PAL.light ? 0.8 : 0.6);
      ctx.beginPath(); ctx.moveTo(x, pTop); ctx.lineTo(x, vBot); ctx.stroke();
      ctx.fillStyle = PAL.dim;
      ctx.fillText(S.tf === '1D' ? fmtDateShort(SESSIONS[i] || '') : hhmm(bars[i].t), x, vBot + 6);
    }
  }

  /* pane separator */
  if (volH > 0) {
    ctx.strokeStyle = rgba(PAL.line2, 0.75); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(padL, Math.round(pBot + gap / 2) + 0.5); ctx.lineTo(W - padR, Math.round(pBot + gap / 2) + 0.5); ctx.stroke();
    ctx.fillStyle = PAL.dim; ctx.font = '700 11px ' + getComputedStyle(root).getPropertyValue('--sans');
    ctx.textAlign = 'left'; ctx.textBaseline = 'top';
    const vlbl = 'KHỐI LƯỢNG', vlw = ctx.measureText(vlbl).width;
    ctx.fillStyle = rgba(PAL.bg0, 0.82); ctx.fillRect(padL + 1, vTop, vlw + 8, 16);
    ctx.fillStyle = PAL.dim; ctx.fillText(vlbl, padL + 5, vTop + 2);
  }

  /* volume */
  if (volH > 0) {
    const cw = Math.max(1, bw * 0.70 * S.density);
    for (let i = i0; i <= last; i++) {
      const b2 = bars[i], up = b2.c >= b2.o;
      ctx.fillStyle = rgba(up ? PAL.up : PAL.dn, PAL.light ? (up ? 0.55 : 0.52) : (up ? 0.42 : 0.40));
      const vy = VY(b2.v);
      ctx.fillRect(X(i) - cw / 2, vy, cw, Math.max(0.7, vBot - vy));
    }
  }

  /* series painter — one geometry per chart type, shared scales */
  const cw2 = Math.max(1, bw * 0.70 * S.density), wickW = Math.max(0.8, Math.min(2, cw2 * 0.14));
  const glowPx = S.glow * 16;
  function dirCol(b) { return b.c >= b.o ? PAL.up : PAL.dn; }
  function nearGlow(i, col) {
    const near = (S.cursor - i) < 3;
    if (near && glowPx > 0.5) { ctx.shadowColor = rgba(col, 0.85); ctx.shadowBlur = glowPx * (1 - (S.cursor - i) / 3.4); }
  }
  function candleBody(b, x, hollowUp) {
    const col = dirCol(b), yO = Y(b.o), yC = Y(b.c), yH = Y(b.h), yL = Y(b.l);
    ctx.strokeStyle = col; ctx.lineWidth = wickW;
    ctx.beginPath(); ctx.moveTo(x, yH); ctx.lineTo(x, yL); ctx.stroke();
    const top = Math.min(yO, yC), hgt = Math.max(1.1, Math.abs(yC - yO));
    if (cw2 <= 2.2) { ctx.fillStyle = col; ctx.fillRect(x - cw2 / 2, top, cw2, hgt); }
    else if (hollowUp && b.c >= b.o) {
      ctx.fillStyle = rgba(col, PAL.light ? 0.20 : 0.16); ctx.fillRect(x - cw2 / 2, top, cw2, hgt);
      ctx.strokeStyle = col; ctx.lineWidth = Math.max(1, cw2 * 0.13); ctx.strokeRect(x - cw2 / 2, top, cw2, hgt);
    } else { ctx.fillStyle = col; ctx.fillRect(x - cw2 / 2, top, cw2, hgt); }
  }
  function closeLine(mode) {
    ctx.strokeStyle = PAL.mg; ctx.lineWidth = 2; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    if (S.glow > 0.15) { ctx.shadowColor = rgba(PAL.mg, 0.5); ctx.shadowBlur = S.glow * 7; }
    ctx.beginPath(); let py = null;
    for (let i = i0; i <= last; i++) {
      const x = X(i), y = Y(src[i].c);
      if (py == null) ctx.moveTo(x, y); else { if (mode === 'step') ctx.lineTo(x, py); ctx.lineTo(x, y); }
      py = y;
    }
    ctx.stroke(); ctx.shadowBlur = 0;
  }
  function paintSeries() {
    let i, b, x, col;
    if (S.type === 'candles' || S.type === 'hollow' || S.type === 'ha') {
      for (i = i0; i <= last; i++) { b = src[i]; x = X(i); col = dirCol(b); ctx.save(); nearGlow(i, col); candleBody(b, x, S.type === 'hollow'); ctx.restore(); }
      return;
    }
    if (S.type === 'bars') {
      const tw = Math.max(1.2, Math.min(2.4, cw2 * 0.2));
      for (i = i0; i <= last; i++) {
        b = src[i]; x = X(i); col = dirCol(b);
        ctx.save(); nearGlow(i, col); ctx.strokeStyle = col; ctx.lineWidth = tw; ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(x, Y(b.h)); ctx.lineTo(x, Y(b.l));
        ctx.moveTo(x - cw2 / 2, Y(b.o)); ctx.lineTo(x, Y(b.o));
        ctx.moveTo(x, Y(b.c)); ctx.lineTo(x + cw2 / 2, Y(b.c)); ctx.stroke(); ctx.restore();
      }
      return;
    }
    if (S.type === 'highlow') {
      const hw = Math.max(1.6, Math.min(5, cw2 * 0.32));
      for (i = i0; i <= last; i++) { b = src[i]; x = X(i); col = dirCol(b); ctx.save(); nearGlow(i, col); ctx.strokeStyle = col; ctx.lineWidth = hw; ctx.lineCap = 'round'; ctx.beginPath(); ctx.moveTo(x, Y(b.h)); ctx.lineTo(x, Y(b.l)); ctx.stroke(); ctx.restore(); }
      return;
    }
    if (S.type === 'columns') {
      for (i = i0; i <= last; i++) { b = src[i]; x = X(i); col = dirCol(b); ctx.save(); nearGlow(i, col); ctx.fillStyle = rgba(col, PAL.light ? 0.8 : 0.72); const yv = Y(b.c); ctx.fillRect(x - cw2 / 2, yv, cw2, Math.max(1, pBot - yv)); ctx.restore(); }
      return;
    }
    if (S.type === 'hlc') {
      ctx.beginPath();
      for (i = i0; i <= last; i++) { x = X(i); if (i === i0) ctx.moveTo(x, Y(src[i].h)); else ctx.lineTo(x, Y(src[i].h)); }
      for (i = last; i >= i0; i--) ctx.lineTo(X(i), Y(src[i].l));
      ctx.closePath(); ctx.fillStyle = rgba(PAL.mg, PAL.light ? 0.14 : 0.18); ctx.fill();
      closeLine('line'); return;
    }
    if (S.type === 'area') {
      const g = ctx.createLinearGradient(0, pTop, 0, pBot);
      g.addColorStop(0, rgba(PAL.mg, PAL.light ? 0.26 : 0.32)); g.addColorStop(1, rgba(PAL.mg, 0.02));
      ctx.beginPath(); ctx.moveTo(X(i0), pBot);
      for (i = i0; i <= last; i++) ctx.lineTo(X(i), Y(src[i].c));
      ctx.lineTo(X(last), pBot); ctx.closePath(); ctx.fillStyle = g; ctx.fill();
      closeLine('line'); return;
    }
    if (S.type === 'baseline') {
      /* anchor = session open: causal, stable while scrubbing */
      const base = bars[0].o, by = Y(base);
      function side(top, hgt, col2) {
        if (hgt <= 0) return;
        ctx.save(); ctx.beginPath(); ctx.rect(padL, top, plotW, hgt); ctx.clip();
        ctx.beginPath(); ctx.moveTo(X(i0), by);
        for (let j = i0; j <= last; j++) ctx.lineTo(X(j), Y(src[j].c));
        ctx.lineTo(X(last), by); ctx.closePath();
        ctx.fillStyle = rgba(col2, PAL.light ? 0.15 : 0.17); ctx.fill(); ctx.restore();
      }
      side(pTop, by - pTop, PAL.up);
      side(Math.max(pTop, by), pBot - Math.max(pTop, by), PAL.dn);
      ctx.lineWidth = 2; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
      for (i = i0 + 1; i <= last; i++) {
        ctx.strokeStyle = ((src[i - 1].c + src[i].c) / 2 >= base) ? PAL.up : PAL.dn;
        ctx.beginPath(); ctx.moveTo(X(i - 1), Y(src[i - 1].c)); ctx.lineTo(X(i), Y(src[i].c)); ctx.stroke();
      }
      ctx.save(); ctx.setLineDash([4, 4]); ctx.strokeStyle = rgba(PAL.dim, 0.75); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(padL, by); ctx.lineTo(W - padR, by); ctx.stroke(); ctx.restore();
      if (by >= pTop && by <= pBot) {
        const bt = 'MỞ ' + nfmt(base, 2); ctx.font = '700 10.5px ' + getComputedStyle(root).getPropertyValue('--mono');
        const btw = ctx.measureText(bt).width + 10;
        ctx.fillStyle = PAL.bg4; roundRect(padL + 4, by - 8.5, btw, 17, 4); ctx.fill();
        ctx.fillStyle = PAL.hi; ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.fillText(bt, padL + 9, by + 0.5);
      }
      return;
    }
    if (S.type === 'marked') {
      closeLine('line');
      const r = Math.max(1.8, Math.min(3.2, cw2 * 0.22));
      for (i = i0; i <= last; i++) { x = X(i); ctx.beginPath(); ctx.arc(x, Y(src[i].c), r, 0, 6.2832); ctx.fillStyle = PAL.bg1; ctx.fill(); ctx.strokeStyle = PAL.mg; ctx.lineWidth = 1.4; ctx.stroke(); }
      return;
    }
    if (S.type === 'step') { closeLine('step'); return; }
    closeLine('line');
  }
  ctx.save(); ctx.beginPath(); ctx.rect(padL, pTop, plotW, priceH); ctx.clip();
  paintSeries();
  ctx.restore();

  /* overlay lines */
  function line(arr, color, label, dash) {
    if (!arr) return;
    ctx.save(); ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    if (dash) ctx.setLineDash(dash);
    if (S.glow > 0.15) { ctx.shadowColor = rgba(color, 0.5); ctx.shadowBlur = S.glow * 7; }
    ctx.beginPath(); let started = false;
    for (let i = i0; i <= last; i++) { if (arr[i] == null) continue; const x = X(i), y = Y(arr[i]); if (!started) { ctx.moveTo(x, y); started = true; } else ctx.lineTo(x, y); }
    if (started) ctx.stroke(); ctx.restore();
  }
  line(ma1, PAL.am, 'MA' + S.ma1);
  line(ma2, PAL.vi, 'MA' + S.ma2);
  line(vw, PAL.cy, 'VWAP', [5, 4]);

  /* sample-signal markers — revealed events of the current symbol only */
  if (S.tf !== '1D') {
    const sev = currentSymbolEvents(), scm = sigCursorMinute();
    ctx.save(); ctx.fillStyle = rgba(PAL.am, 0.95);
    for (let se = 0; se < sev.length; se++) {
      const ev = sev[se];
      if (ev.endIdx > scm) continue;
      const bi = Math.floor(ev.endIdx / TFS[S.tf]);
      if (bi < i0 || bi > last || !src[bi]) continue;
      const mx = X(bi), my = Math.max(pTop + 6, Y(src[bi].h) - 7);
      ctx.beginPath(); ctx.moveTo(mx, my); ctx.lineTo(mx - 4, my - 6); ctx.lineTo(mx + 4, my - 6); ctx.closePath(); ctx.fill();
    }
    ctx.restore();
  }

  /* last price marker */
  if (S.cursor >= 0 && S.cursor < total) {
    const lb = src[S.cursor], lup = lb.c >= lb.o, lc = lup ? PAL.up : PAL.dn, ly = Y(lb.c);
    if (ly >= pTop && ly <= pBot) {
      ctx.save(); ctx.setLineDash([3, 4]); ctx.strokeStyle = rgba(lc, 0.62); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(padL, ly); ctx.lineTo(W - padR, ly); ctx.stroke(); ctx.restore();
      ctx.fillStyle = lc;
      const tag = nfmt(lb.c, 2); ctx.font = '700 11px ' + getComputedStyle(root).getPropertyValue('--mono');
      const tw = ctx.measureText(tag).width + 10;
      roundRect(W - padR + 2, ly - 8.5, Math.min(tw, padR - 4), 17, 4); ctx.fill();
      ctx.fillStyle = PAL.onCy; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
      ctx.fillText(tag, W - padR + 7, ly + 0.5);
    }
    /* replay cursor */
    const cx = X(S.cursor);
    if (cx >= padL && cx <= W - padR) {
      ctx.save();
      ctx.strokeStyle = rgba(PAL.mg, 0.85); ctx.lineWidth = 1.4;
      if (S.glow > 0.1) { ctx.shadowColor = rgba(PAL.mg, 0.9); ctx.shadowBlur = S.glow * 14; }
      ctx.beginPath(); ctx.moveTo(cx, pTop); ctx.lineTo(cx, vBot); ctx.stroke();
      const cy2 = Y(lb.c);
      ctx.fillStyle = rgba(PAL.mg, 0.31);
      ctx.beginPath(); ctx.arc(cx, cy2, 7, 0, 6.2832); ctx.fill();
      ctx.fillStyle = PAL.mg; ctx.beginPath(); ctx.arc(cx, cy2, 2.7, 0, 6.2832); ctx.fill();
      ctx.restore();
    }
  }

  /* crosshair */
  if (S.cross && mouse.in && mouse.x != null && mouse.x >= padL && mouse.x <= W - padR && mouse.y >= pTop && mouse.y <= vBot) {
    let idx = Math.round((mouse.x - padL) / bw - 0.5 + S.view.start);
    idx = Math.max(0, Math.min(total - 1, idx));
    const hx = X(idx);
    ctx.save(); ctx.setLineDash([2, 4]); ctx.strokeStyle = rgba(PAL.dim, 0.85); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(hx, pTop); ctx.lineTo(hx, vBot); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(padL, mouse.y); ctx.lineTo(W - padR, mouse.y); ctx.stroke(); ctx.restore();
    if (mouse.y <= pBot) {
      const pv = lo + (pBot - mouse.y) / priceH * (hi - lo);
      ctx.fillStyle = PAL.bg4; roundRect(W - padR + 2, mouse.y - 8.5, padR - 4, 17, 4); ctx.fill();
      ctx.fillStyle = PAL.hi; ctx.font = '600 11px ' + getComputedStyle(root).getPropertyValue('--mono');
      ctx.textAlign = 'left'; ctx.textBaseline = 'middle'; ctx.fillText(nfmt(pv, 2), W - padR + 7, mouse.y + 0.5);
    }
    const tl = S.tf === '1D' ? fmtDateShort(SESSIONS[idx] || '') : hhmm(bars[idx].t);
    ctx.font = '600 11px ' + getComputedStyle(root).getPropertyValue('--mono');
    const tw2 = ctx.measureText(tl).width + 12;
    ctx.fillStyle = PAL.bg4; roundRect(Math.max(padL, Math.min(hx - tw2 / 2, W - padR - tw2)), vBot + 3, tw2, 16, 4); ctx.fill();
    ctx.fillStyle = PAL.hi; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(tl, Math.max(padL + tw2 / 2, Math.min(hx, W - padR - tw2 / 2)), vBot + 11);
    S.hover = idx;
  } else S.hover = null;

  /* frame */
  ctx.strokeStyle = rgba(PAL.line, 0.9); ctx.lineWidth = 1;
  ctx.strokeRect(padL + 0.5, pTop + 0.5, plotW - 1, vBot - pTop - 1);
}

/* ---------- export ---------- */
export function download(name, blob) {
  const a = document.createElement('a'), url = URL.createObjectURL(blob);
  a.href = url; a.download = name; document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(url); if (a.parentNode) a.parentNode.removeChild(a); }, 400);
}
export function exportPNG() {
  if (!curRole().png) { toast('Vai trò ' + curRole().label + ' không xuất ảnh biểu đồ.', { kind: 'warn', ms: 2600 }); return; }
  const hover = S.hover; S.hover = null; const mi = mouse.in; mouse.in = false;
  renderChart();
  const url = cv.toDataURL('image/png');
  mouse.in = mi; S.hover = hover; D.dirty = true;
  const a = document.createElement('a'); a.href = url; a.download = 'nasdaq-replay_' + S.sym + '_' + D.SESSIONS[S.si] + '_' + S.tf + '.png';
  document.body.appendChild(a); a.click(); a.parentNode.removeChild(a);
  toast('Đã xuất ảnh biểu đồ ' + S.sym + ' · ' + S.tf, { kind: 'ok' });
}
export function exportCSV() {
  if (D.historical) {
    if (!curRole().csv) return;
    const rows = D.bars.slice(0, S.cursor + 1).map(b => [new Date(b.t).toISOString(), b.v ? b.o : '', b.v ? b.h : '', b.v ? b.l : '', b.v ? b.c : '', b.v].join(','));
    download(S.sym + '_' + D.SESSIONS[S.si] + '_' + S.tf + '_MBO.csv', new Blob([['end_utc,open,high,low,close,volume', ...rows].join('\n')], { type: 'text/csv' }));
    return;
  }
  const p = new URLSearchParams({ symbol: S.sym, date: D.SESSIONS[S.si], tf: S.tf });
  apiBlob('/export/bars.csv?' + p.toString()).then(blob => {
    download('nasdaq-replay_' + S.sym + '_' + D.SESSIONS[S.si] + '_' + S.tf + '.csv', blob);
    toast('Đã xuất nến ' + S.sym + ' · ' + S.tf + ' ra CSV từ máy chủ', { kind: 'ok' });
  }).catch(toastApiError);
}
