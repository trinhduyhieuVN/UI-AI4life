import { $, root, curRole } from '../state.js';
import { api } from '../api.js';
import { toast, toastApiError } from './toasts.js';
import { popAt, closePops } from './menus.js';
import { escapeHtml } from '../util.js';

const ALABEL = {
  login: 'Đăng nhập', logout: 'Đăng xuất', role_change: 'Đổi vai trò', review: 'Gán nhãn rà soát',
  export: 'Xuất dữ liệu', import_backup: 'Import cục bộ', restore_backup: 'Khôi phục backup',
};

function detailTxt(a) {
  const d = a.detail || {};
  if (a.action === 'role_change') return (d.from || '?') + ' → ' + (d.to || '?') + (d.via === 'restore' ? ' (khôi phục)' : '');
  if (a.action === 'review') return (d.label || '') + ' · ' + (d.event_id || '');
  if (a.action === 'export') return d.kind === 'signals' ? 'CSV tín hiệu' : 'CSV nến';
  if (a.action === 'import_backup') return 'nhận ' + (d.imported || 0) + ', bỏ qua ' + (d.skipped || 0);
  if (a.action === 'restore_backup') return 'watch ' + (d.watchlist || 0) + ' · view ' + (d.views || 0) + ' · nhãn ' + (d.reviews || 0);
  return '';
}

/* Nhật ký kiểm toán máy chủ — chỉ compliance/regulator (cap audit). */
export function openAudit() {
  closePops();
  if (!curRole().audit) { toast('Vai trò hiện tại không xem nhật ký kiểm toán.', { kind: 'warn', ms: 2600 }); return; }
  const p = document.createElement('div'); p.className = 'nq-pop nq-auditpop';
  p.innerHTML =
    '<h4>Nhật ký kiểm toán</h4>' +
    '<div class="nq-audit-b" id="nq-audit-b">Đang tải…</div>' +
    '<div class="nq-data-note">200 bản ghi gần nhất trên máy chủ: đăng nhập, đổi vai trò, gán nhãn, xuất và khôi phục dữ liệu.</div>';
  const ub = $('nq-user').getBoundingClientRect(), rr = root.getBoundingClientRect();
  popAt(p, ub.right - 340, ub.bottom + 6);
  p.style.left = Math.max(8, Math.min(ub.right - rr.left - 340, rr.width - 356)) + 'px';
  p.style.top = (ub.bottom - rr.top + 6) + 'px';
  api('/audit').then(r => {
    const b = p.querySelector('#nq-audit-b');
    if (!b) return;
    if (!r.audit.length) { b.innerHTML = '<div class="nq-data-empty">Chưa có bản ghi nào.</div>'; return; }
    b.innerHTML = r.audit.map(a =>
      '<div class="nq-audit-row" data-action="' + escapeHtml(a.action) + '">' +
      '<span class="nq-audit-t">' + escapeHtml(String(a.at).replace('T', ' ').slice(0, 16)) + '</span>' +
      '<b class="nq-audit-u">' + escapeHtml(a.username || '—') + '</b>' +
      '<span class="nq-audit-a">' + escapeHtml(ALABEL[a.action] || a.action) + '</span>' +
      '<span class="nq-audit-d">' + escapeHtml(detailTxt(a)) + '</span>' +
      '</div>').join('');
  }).catch(e => { const b = p.querySelector('#nq-audit-b'); if (b) b.innerHTML = ''; toastApiError(e); });
}