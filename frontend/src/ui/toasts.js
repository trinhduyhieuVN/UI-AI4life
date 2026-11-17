import { $ } from '../state.js';

export function toast(msg, opts) {
  opts = opts || {};
  const el = document.createElement('div');
  el.className = 'nq-toast' + (opts.kind ? ' ' + opts.kind : '');
  const dot = document.createElement('i'); el.appendChild(dot);
  const sp = document.createElement('span'); sp.textContent = msg; el.appendChild(sp);
  let timer;
  function close() {
    if (!el.parentNode) return;
    el.classList.add('out');
    setTimeout(() => { if (el.parentNode) el.parentNode.removeChild(el); }, 210);
  }
  if (opts.action) {
    const b = document.createElement('button'); b.textContent = opts.action;
    b.addEventListener('click', () => { clearTimeout(timer); opts.onAction && opts.onAction(); close(); });
    el.appendChild(b);
  }
  $('nq-toasts').appendChild(el);
  timer = setTimeout(close, opts.ms || 4200);
  while ($('nq-toasts').children.length > 4) $('nq-toasts').removeChild($('nq-toasts').firstChild);
  return close;
}

const CAP_MSG = {
  csv: 'Vai trò hiện tại không xuất CSV nến.',
  sigCSV: 'Vai trò hiện tại không xuất CSV tín hiệu.',
  png: 'Vai trò hiện tại không xuất ảnh biểu đồ.',
  blind: 'Đang bật chế độ ẩn điểm — tắt rà soát mù để xuất CSV.',
  dataManager: 'Vai trò hiện tại không quản lý dữ liệu.',
  review: 'Vai trò hiện tại chỉ xem, không gán nhãn rà soát.',
  scope_watch: 'Vai trò hiện tại chỉ xem tín hiệu theo mã.',
  scope_all: 'Chỉ vai trò giám sát được quét toàn bộ mã.',
};

/* Mọi ApiError: 401 bỏ qua (đã có nq-unauth), 403 toast tiếng Việt theo cap, còn lại toast message. */
export function toastApiError(e) {
  if (!e || e.status === 401) return;
  if (e.status === 403) { toast(CAP_MSG[e.cap] || e.message || 'Vai trò hiện tại không có quyền này.', { kind: 'warn', ms: 2800 }); return; }
  toast(e.message || 'Lỗi máy chủ', { kind: 'warn' });
}