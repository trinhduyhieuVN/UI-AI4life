import { S, D, $, curRole, USER, TFS, MINUTES } from './state.js';
import { api, apiBlob } from './api.js';
import { isOffline, loadOffline, saveSession } from './offline.js';
import { nfmt, hhmm, fmtDateShort, escapeHtml } from './util.js';
import { toast, toastApiError } from './ui/toasts.js';
import { download } from './chart/renderer.js';
import { renderHistorySignals, visibleHistoryScores, historyMarkers } from './history-signals.js';

export const RLABEL = { noteworthy: 'Đáng chú ý', ordinary: 'Thông thường', uncertain: 'Không chắc chắn', data_error: 'Lỗi dữ liệu' };
export const SIGMODE_TXT = {
  headlines: 'Tiêu đề cho công chúng', simple: 'Cảnh báo dễ hiểu', risk: 'Điểm số & rủi ro',
  queue: 'Hàng đợi rà soát', surveillance: 'Quét toàn thị trường', research: 'Phân rã mô hình',
};

export function sigCursorMinute() { return S.tf === '1D' ? MINUTES - 1 : Math.min(MINUTES - 1, S.cursor * TFS[S.tf] + TFS[S.tf] - 1); }

function sigKey() {
  const scope = curRole().sigScope;
  return scope + '|' + S.si + '|' + S.tf + '|' + (scope === 'symbol' ? S.sym : scope === 'watch' ? D.watch.join(',') : 'all');
}

const sigPending = new Map();
/* Lấy một lần tại mốc End (cursor=389 intraday / si cho 1D); lọc nhân quả phía client khi tua. */
export function ensureSignals() {
  /* loop() có thể render trước khi loadMeta nạp D.SESSIONS — đừng gọi /signals với date undefined. */
  const date = D.SESSIONS[S.si];
  if (!date) return Promise.resolve([]);
  const key = sigKey();
  if (D.sigCache.has(key)) return Promise.resolve(D.sigCache.get(key));
  if (sigPending.has(key)) return sigPending.get(key);
  const r = curRole();
  const params = new URLSearchParams({ date, tf: S.tf, scope: r.sigScope, cursor: S.tf === '1D' ? String(S.si) : '389' });
  if (r.sigScope === 'symbol') params.set('symbol', S.sym);
  const p = api('/signals?' + params.toString())
    .then(res => { D.sigCache.set(key, res.signals); sigPending.delete(key); D.sigDirty = true; saveSession(S.sym, S.si, null, res.signals); return res.signals; })
    .catch(async e => {
      sigPending.delete(key);
      if (isOffline()) {
        const rec = await loadOffline(S.sym, S.si);
        if (rec && rec.tf === S.tf && rec.signals && rec.signals.length) { D.sigCache.set(key, rec.signals); D.sigDirty = true; return rec.signals; }
      }
      throw e;
    });
  sigPending.set(key, p);
  return p;
}

export function revealedEvents() {
  const evs = D.sigCache.get(sigKey()) || [];
  const out = [];
  if (S.tf === '1D') {
    const upto = Math.min(S.cursor, S.si);
    for (const e of evs) if (e.si <= upto) out.push(e);
  } else {
    const cm = sigCursorMinute();
    for (const e of evs) if (e.si === S.si && e.endIdx <= cm) out.push(e);
  }
  out.sort((a, b) => b.tEnd - a.tEnd || (a.sym < b.sym ? -1 : a.sym > b.sym ? 1 : 0));
  return out;
}

export function currentSymbolEvents() {
  if (D.historical) return historyMarkers();
  const evs = D.sigCache.get(sigKey()) || [];
  if (curRole().sigScope === 'symbol') return evs;
  return evs.filter(e => e.sym === S.sym && e.si === S.si);
}

function sigRowHTML(e, r) {
  const rev = D.reviews[e.id] || null;
  const label = rev ? rev.label : e.label;
  const time = S.tf === '1D' ? fmtDateShort(D.SESSIONS[e.si]) : hhmm(e.tEnd);
  const typeTxt = e.type === 'point' ? 'Điểm' : 'Chuỗi ' + (e.endIdx - e.startIdx + 1) + '′';
  const stCls = e.suppressed ? 'sup' : (e.alert ? 'alert' : 'watch');
  const stTxt = e.suppressed ? 'Bị chặn' : (e.alert ? 'Cảnh báo' : 'Theo dõi');
  const mode = r.signals;
  let h = '<div class="nq-sig-row" data-eid="' + escapeHtml(e.id) + '" data-sym="' + e.sym + '">';
  h += '<span class="nq-sig-t">' + time + '</span><b class="nq-sig-sym">' + e.sym + '</b><span class="nq-sig-type">' + typeTxt + '</span>';
  const txt = (mode === 'headlines' || mode === 'simple') ? e.plain : (S.blind ? 'Điểm số ẩn (rà soát mù)' : (e.reason || 'dưới ngưỡng q98'));
  h += '<span class="nq-sig-txt">' + escapeHtml(txt) + '</span>';
  if (mode !== 'headlines' && mode !== 'simple')
    h += '<span class="nq-sig-score">' + (S.blind ? '•••' : nfmt(e.score, 2) + ' <i>/ ' + nfmt(e.threshold, 2) + '</i>') + '</span>';
  h += '<span class="nq-sig-st ' + stCls + '">' + stTxt + '</span>';
  h += '<span class="nq-sig-lab ' + label + '" title="' + (rev ? 'Rà soát bởi ' + escapeHtml(rev.reviewer) : 'Nhãn mẫu mặc định') + '">' + RLABEL[label] + '</span>';
  if (r.review) {
    h += '<span class="nq-sig-rev">';
    ['noteworthy', 'ordinary', 'uncertain', 'data_error'].forEach(l => {
      h += '<button data-lab="' + l + '" aria-pressed="' + (label === l ? 'true' : 'false') + '">' + RLABEL[l] + '</button>';
    });
    h += '</span>';
  }
  if (mode === 'risk' || mode === 'surveillance') {
    let top = null; for (const fk in e.features) if (!top || e.features[fk].share > e.features[top].share) top = fk;
    let det = '<b>share_' + top + '</b> ' + nfmt(e.features[top].share * 100, 1) + '%';
    if (e.suppressedReason) det += ' · chặn: <b>' + e.suppressedReason + '</b>';
    det += ' · outbox: <b>' + e.outbox + '</b> · nguồn: <b>' + e.quality + '</b>';
    h += '<span class="nq-sig-det">' + det + '</span>';
  }
  if (mode === 'queue') {
    let dq = 'outbox: <b>' + e.outbox + '</b> · nguồn: <b>' + e.quality + '</b>';
    if (e.suppressedReason) dq += ' · chặn: <b>' + e.suppressedReason + '</b>';
    if (rev) dq += ' · nhật ký: <b>' + escapeHtml(rev.reviewer) + '</b>';
    h += '<span class="nq-sig-det">' + dq + '</span>';
  }
  if (mode === 'research') {
    const parts = []; for (const fk in e.features) parts.push('error_' + fk + ' <b>' + nfmt(e.features[fk].error, 3) + '</b> · share <b>' + nfmt(e.features[fk].share * 100, 1) + '%</b>');
    h += '<span class="nq-sig-det">' + parts.join(' &nbsp;│&nbsp; ') + '<br>mô hình: <b>' + e.model + '</b> · <b>' + e.modelVersion + '</b> · outbox: <b>' + e.outbox + '</b> · nguồn: <b>' + e.quality + '</b>' + (e.suppressedReason ? ' · chặn: <b>' + e.suppressedReason + '</b>' : '') + '</span>';
  }
  return h + '</div>';
}

export function renderSignals() {
  if (D.historical) return renderHistorySignals();
  const r = curRole(), b = $('nq-sig-b');
  if (!D.sigCache.has(sigKey())) {
    ensureSignals().catch(e => { if (e.status !== 401) toast(e.message); });
  }
  const evs = revealedEvents();
  const f = S.sigFilter || 'all';
  const filt = evs.filter(e => {
    if (f === 'alert') return e.alert && !e.suppressed;
    if (f === 'suppressed') return e.suppressed;
    if (f === 'quality') return e.quality !== 'OK';
    return true;
  });
  const cap = r.sigScope === 'all' ? 60 : 40;
  const shown = filt.slice(0, cap);
  b.setAttribute('data-mode', r.signals);
  $('nq-sig-mode').textContent = SIGMODE_TXT[r.signals];
  $('nq-sig-blind').hidden = !r.blind;
  $('nq-sig-blind').setAttribute('aria-pressed', S.blind ? 'true' : 'false');
  $('nq-sig-csv').hidden = !r.sigCSV;
  $('nq-sig-csv').disabled = !!S.blind;
  const chips = $('nq-sig-f').querySelectorAll('[data-f]');
  for (let c = 0; c < chips.length; c++) chips[c].setAttribute('aria-pressed', chips[c].getAttribute('data-f') === f ? 'true' : 'false');
  let rvk = ''; for (const rk in D.reviews) rvk += rk + ':' + D.reviews[rk].label + ';';
  const key = [S.sym, S.si, S.tf, r.id, f, S.blind ? 1 : 0, evs.length, filt.length, rvk].join('|');
  if (key === D.lastSigKey) return;
  D.lastSigKey = key;
  if (!shown.length) {
    b.innerHTML = '<div class="nq-sig-empty">' + (evs.length ? 'Không có tín hiệu khớp bộ lọc hiện tại.' : 'Chưa tín hiệu mẫu nào được mở tại mốc thời gian này — tua phiên để tín hiệu xuất hiện đúng kỷ luật as-of.') + '</div>';
  } else {
    let html = ''; for (let i = 0; i < shown.length; i++) html += sigRowHTML(shown[i], r);
    b.innerHTML = html;
  }
  $('nq-sig-n').textContent = String(shown.length) + (filt.length > cap ? '/' + filt.length : '');
}

export function saveReview(id, label) {
  const r = curRole();
  if (!r.review) { toast('Vai trò hiện tại chỉ xem, không gán nhãn rà soát.', { kind: 'warn' }); return; }
  if (!RLABEL[label]) return;
  api('/reviews', { method: 'POST', body: { event_id: id, label } }).then(() => {
    D.reviews[id] = { label, reviewer: USER ? USER.username : '', at: Date.now() };
    D.sigDirty = true; renderSignals();
    toast('Đã gán nhãn “' + RLABEL[label] + '” · nhật ký rà soát mô phỏng lưu theo tài khoản', { kind: 'ok', ms: 2800 });
  }).catch(toastApiError);
}

export function exportSignalsCSV() {
  const r = curRole();
  if (D.historical) {
    if (!r.sigCSV || S.blind) return;
    const bar = D.bars[S.cursor], pts = visibleHistoryScores();
    if (!bar || pts.length !== bar.minute) { toast('Đang tải điểm tại mốc phát.'); return; }
    const rows = pts.filter(p => S.sigFilter !== 'alert' || p.energy > p.threshold)
      .map(p => [new Date(p.end_ms).toISOString(), p.energy, p.threshold, Number(p.energy > p.threshold)].join(','));
    download(S.sym + '_' + bar.day + '_DHGNN_EBM.csv', new Blob([['end_utc,energy,threshold,alert', ...rows].join('\n')], { type: 'text/csv' }));
    return;
  }
  const p = new URLSearchParams({ date: D.SESSIONS[S.si], tf: S.tf, cursor: String(S.cursor), scope: r.sigScope, blind: S.blind ? '1' : '0' });
  if (r.sigScope === 'symbol') p.set('symbol', S.sym);
  apiBlob('/export/signals.csv?' + p.toString()).then(blob => {
    download('nasdaq-signals-Mau_' + D.SESSIONS[S.si] + '.csv', blob);
    toast('Đã xuất tín hiệu MẪU ra CSV từ máy chủ (không gồm phần chưa diễn ra)', { kind: 'ok' });
  }).catch(toastApiError);
}
