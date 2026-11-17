import { $, root, curRole, setSession } from '../state.js';
import { api } from '../api.js';
import { toast, toastApiError } from './toasts.js';
import { popAt, closePops } from './menus.js';
import { renderList, renderViews } from './rail.js';
import { fetchViews } from '../data.js';

const LOCAL_KEY = 'nqreplay.v1';

/* T12: data manager tối thiểu — đưa dữ liệu cục bộ lên server. T17 nối backup/restore/audit. */
export function dataPop() {
  closePops();
  if (!curRole().dataManager) { toast('Vai trò hiện tại không quản lý dữ liệu.', { kind: 'warn' }); return; }
  const hasLocal = !!localStorage.getItem(LOCAL_KEY);
  const p = document.createElement('div'); p.className = 'nq-pop nq-datapop';
  p.innerHTML =
    '<h4>Quản lý dữ liệu</h4>' +
    '<div class="nq-data-note">Đưa watchlist, khung nhìn và nhãn rà soát từ trình duyệt này lên máy chủ. Tài khoản trùng tên được gộp; mật khẩu cũ nâng cấp dần lên argon2id khi đăng nhập.</div>' +
    '<div class="nq-data-act" style="grid-template-columns:1fr">' +
      '<button class="nq-btn pri" id="nq-mig-import"' + (hasLocal ? '' : ' disabled') + '>Đưa dữ liệu cục bộ lên server</button>' +
    '</div>' +
    (hasLocal ? '' : '<div class="nq-data-empty">Không tìm thấy dữ liệu cục bộ (nqreplay.v1) trên trình duyệt này.</div>');
  const ub = $('nq-user').getBoundingClientRect(), rr = root.getBoundingClientRect();
  popAt(p, ub.right - 300, ub.bottom + 6);
  p.style.left = Math.max(8, Math.min(ub.right - rr.left - 300, rr.width - 332)) + 'px';
  p.style.top = (ub.bottom - rr.top + 6) + 'px';
  p.querySelector('#nq-mig-import').addEventListener('click', importLocalPack);
}

export function importLocalPack() {
  if (!curRole().dataManager) { toast('Vai trò hiện tại không quản lý dữ liệu.', { kind: 'warn' }); return; }
  const raw = localStorage.getItem(LOCAL_KEY);
  if (!raw) { toast('Không có dữ liệu cục bộ để đưa lên server.', { kind: 'warn' }); return; }
  let pack;
  try { pack = JSON.parse(raw); } catch (e) { toast('Dữ liệu cục bộ hỏng — không đọc được JSON.', { kind: 'warn' }); return; }
  api('/data/import-backup', { method: 'POST', body: pack }).then(res => {
    toast('Đã đưa ' + res.imported + ' tài khoản cục bộ lên server' + (res.skipped ? ' (bỏ qua ' + res.skipped + ' đã có)' : '') + '.', { kind: 'ok', ms: 4200 });
    return api('/auth/me').then(me => { setSession(me); return fetchViews(); }).then(() => { renderList(); renderViews(); });
  }).catch(toastApiError);
}