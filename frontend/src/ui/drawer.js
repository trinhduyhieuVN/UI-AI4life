import { S, D, $, root, curRole } from '../state.js';
import { nfmt, vfmt, fmtDate, escapeHtml, rgba } from '../util.js';
import { PAL } from './theme.js';
import { drawerStats, quote, peekSeries, ensureSeries } from '../data.js';
import { selectSymbol, addSymbol, removeSymbols } from './rail.js';

let drawerSym = null;
export function getDrawerSym() { return drawerSym; }

export async function openDrawer(sym) {
  drawerSym = sym;
  const meta = D.SYM[sym] || { n: '', sec: '' };
  const sparkTf = S.tf === '1D' ? '1m' : S.tf;
  const [st] = await Promise.all([drawerStats(sym, S.si), ensureSeries(sym, S.si, S.tf), ensureSeries(sym, S.si, sparkTf)]);
  if (drawerSym !== sym) return;
  const q = quote(sym);
  const range = st.open ? (st.high - st.low) / st.open * 100 : 0;
  const vsPrev = st.prev ? (st.close - st.prev) / st.prev * 100 : 0;
  const d = $('nq-drawer');
  d.innerHTML =
    '<div class="nq-dr-h"><div style="flex:1;min-width:0"><b>' + sym + '</b><span>' + escapeHtml(meta.n) + '</span>' +
      '<div style="margin-top:7px;display:flex;gap:5px;flex-wrap:wrap"><span class="nq-tag">' + escapeHtml(meta.sec) + '</span><span class="nq-tag" style="background:' + rgba(PAL.cy, .14) + ';color:' + PAL.cy + ';border-color:' + rgba(PAL.cy, .35) + '">NASDAQ</span></div></div>' +
      '<button class="nq-btn ico sm" id="nq-dr-x" aria-label="Đóng"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg></button></div>' +
    '<div class="nq-dr-b">' +
      '<div class="nq-dr-px"><b style="color:' + (q.up ? PAL.up : PAL.dn) + '">' + nfmt(q.px, 2) + '</b>' +
        '<i style="color:' + (q.up ? PAL.up : PAL.dn) + ';background:' + rgba(q.up ? PAL.up : PAL.dn, PAL.light ? 0.15 : 0.13) + '">' + (q.p >= 0 ? '+' : '') + nfmt(q.p, 2) + '%</i></div>' +
      '<div style="font-size:11px;color:var(--dim);margin-top:-8px">Tại nến ' + (S.cursor + 1) + '/' + D.total + ' · ' + S.tf + ' · phiên ' + fmtDate(D.SESSIONS[S.si]) + '</div>' +
      '<canvas id="nq-dr-spark"></canvas>' +
      '<div class="nq-stats">' +
        stat('Mở cửa', nfmt(st.open, 2)) + stat('Đóng cửa', nfmt(st.close, 2)) +
        stat('Cao nhất', nfmt(st.high, 2)) + stat('Thấp nhất', nfmt(st.low, 2)) +
        stat('Biên độ phiên', nfmt(range, 2) + '%') + stat('So với phiên trước', (vsPrev >= 0 ? '+' : '') + nfmt(vsPrev, 2) + '%') +
        stat('Khối lượng phiên', vfmt(st.vol)) + stat('VWAP phiên', nfmt(st.vwap, 2)) +
      '</div>' +
      '<div style="font-size:11.5px;color:var(--dim);line-height:1.65;border-top:1px solid var(--line);padding-top:12px">' +
        'Số liệu mẫu sinh tất định trên máy chủ từ hạt giống <span class="nq-mono" style="color:var(--dim)">' + sym + '|' + D.SESSIONS[S.si] + '</span>, không phải dữ liệu sàn thật. Khi nối Databento, khối này đọc từ <span class="nq-mono" style="color:var(--dim)">ohlcv-1m / ohlcv-1d</span> của XNAS.ITCH.</div>' +
    '</div>' +
    '<div class="nq-dr-f">' +
      '<button class="nq-btn pri" id="nq-dr-open">Mở biểu đồ</button>' +
      (curRole().drawerEdit ? (D.watch.indexOf(sym) >= 0 ? '<button class="nq-btn dgr" id="nq-dr-rm">Bỏ khỏi danh sách</button>' : '<button class="nq-btn" id="nq-dr-add">Thêm vào danh sách</button>') : '') +
    '</div>';
  d.hidden = false; $('nq-scrim').hidden = false;
  d.querySelector('#nq-dr-x').addEventListener('click', closeDrawer);
  d.querySelector('#nq-dr-open').addEventListener('click', () => { selectSymbol(sym); closeDrawer(); });
  const rm = d.querySelector('#nq-dr-rm'), ad = d.querySelector('#nq-dr-add');
  if (rm) rm.addEventListener('click', () => { removeSymbols([sym]); closeDrawer(); });
  if (ad) ad.addEventListener('click', () => { addSymbol(sym); closeDrawer(); });
  drawDrawerSpark(sym);
}
function stat(k, v) { return '<div class="nq-stat"><span>' + k + '</span><b>' + v + '</b></div>'; }
export function drawDrawerSpark(sym) {
  const c = $('nq-dr-spark'); if (!c) return;
  const ser = peekSeries(sym, S.si, S.tf === '1D' ? '1m' : S.tf);
  if (!ser || !ser.length) return;
  const W = c.clientWidth || 340, H = 88, dpr = Math.min(2, window.devicePixelRatio || 1);
  c.width = W * dpr; c.height = H * dpr; const x = c.getContext('2d'); x.setTransform(dpr, 0, 0, dpr, 0, 0);
  x.clearRect(0, 0, W, H);
  let n = Math.min(S.cursor + 1, ser.length); if (n < 2) n = Math.min(2, ser.length);
  const vals = []; for (let i = 0; i < n; i++) vals.push(ser[i].c);
  let lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals); if (hi - lo < 1e-9) hi = lo + 1;
  const pad = 15;
  const X = i => pad + i / (vals.length - 1) * (W - pad * 2);
  const Y = v => H - pad - (v - lo) / (hi - lo) * (H - pad * 2);
  const up = vals[vals.length - 1] >= vals[0], col = up ? PAL.up : PAL.dn;
  const g = x.createLinearGradient(0, 0, 0, H); g.addColorStop(0, rgba(col, 0.30)); g.addColorStop(1, rgba(col, 0));
  x.beginPath(); x.moveTo(X(0), H - pad);
  for (let i = 0; i < vals.length; i++) x.lineTo(X(i), Y(vals[i]));
  x.lineTo(X(vals.length - 1), H - pad); x.closePath(); x.fillStyle = g; x.fill();
  x.beginPath(); for (let i = 0; i < vals.length; i++) { if (i === 0) x.moveTo(X(i), Y(vals[i])); else x.lineTo(X(i), Y(vals[i])); }
  x.strokeStyle = col; x.lineWidth = 1.7; x.lineJoin = 'round'; if (!PAL.light) { x.shadowColor = rgba(col, .6); x.shadowBlur = 8; } x.stroke(); x.shadowBlur = 0;
  x.fillStyle = col; x.beginPath(); x.arc(X(vals.length - 1), Y(vals[vals.length - 1]), 3, 0, 6.2832); x.fill();
  x.fillStyle = PAL.dim; x.font = '600 11px ' + getComputedStyle(root).getPropertyValue('--mono');
  x.textAlign = 'left'; x.textBaseline = 'top'; x.fillText(nfmt(hi, 2), pad, 2);
  x.textBaseline = 'bottom'; x.fillText(nfmt(lo, 2), pad, H - 2);
}
export function closeDrawer() { $('nq-drawer').hidden = true; $('nq-scrim').hidden = true; drawerSym = null; }