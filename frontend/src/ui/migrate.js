import { $, S, D, root, curRole, setSession } from '../state.js';
import { api, apiBlob } from '../api.js';
import { toast, toastApiError } from './toasts.js';
import { popAt, closePops } from './menus.js';
import { renderList, renderViews } from './rail.js';
import { fetchViews, loadSeries } from '../data.js';
import { restorePrefs } from '../prefs.js';
import { applyRole } from '../roles.js';
import { download } from '../chart/renderer.js';
import { setTab } from '../auth.js';
import { syncAll } from './transport.js';

const LOCAL_KEY = 'nqreplay.v1';

/* Data manager: migration cục bộ → server (T12) + backup/restore v2 (T17). */
export function dataPop() {
  closePops();
  if (!curRole().dataManager) { toast('Vai trò hiện tại không quản lý dữ liệu.', { kind: 'warn' }); return; }
  const hasLocal = !!localStorage.getItem(LOCAL_KEY);
  const p = document.createElement('div'); p.className = 'nq-pop nq-datapop';
  p.innerHTML =
    '<h4>Quản lý dữ liệu</h4>' +
    '<div class="nq-data-note" style="border-top:0;margin-top:0;padding-top:0">Đưa watchlist, khung nhìn và nhãn rà soát từ trình duyệt này lên máy chủ. Tài khoản trùng tên được gộp; mật khẩu cũ nâng cấp dần lên argon2id khi đăng nhập.</div>' +
    '<div class="nq-data-act" style="grid-template-columns:1fr">' +
      '<button class="nq-btn pri" id="nq-mig-import"' + (hasLocal ? '' : ' disabled') + '>Đưa dữ liệu cục bộ lên server</button>' +
    '</div>' +
    (hasLocal ? '' : '<div class="nq-data-empty">Không tìm thấy dữ liệu cục bộ (nqreplay.v1) trên trình duyệt này.</div>') +
    '<div class="nq-data-act">' +
      '<button class="nq-btn" id="nq-backup-dl">Tải backup JSON</button>' +
      '<button class="nq-btn" id="nq-restore-btn">Khôi phục từ file…</button>' +
    '</div>' +
    '<input type="file" id="nq-restore-file" accept=".json,application/json" hidden>' +
    '<div class="nq-data-note">Backup v2 gồm prefs/watchlist/views/reviews của mọi tài khoản, không kèm mật khẩu. Khôi phục ghi đè dữ liệu tài khoản đang đăng nhập bằng mục trùng tên trong file.</div>';
  const ub = $('nq-user').getBoundingClientRect(), rr = root.getBoundingClientRect();
  popAt(p, ub.right - 300, ub.bottom + 6);
  p.style.left = Math.max(8, Math.min(ub.right - rr.left - 300, rr.width - 332)) + 'px';
  p.style.top = (ub.bottom - rr.top + 6) + 'px';
  p.querySelector('#nq-mig-import').addEventListener('click', importLocalPack);
  p.querySelector('#nq-backup-dl').addEventListener('click', () => {
    apiBlob('/data/backup').then(blob => {
      download('nasdaq-replay-backup-' + new Date().toISOString().slice(0, 10) + '.json', blob);
      toast('Đã tải backup JSON v2 — giữ file ở nơi an toàn.', { kind: 'ok', ms: 3200 });
    }).catch(toastApiError);
  });
  const fi = p.querySelector('#nq-restore-file');
  p.querySelector('#nq-restore-btn').addEventListener('click', () => fi.click());
  fi.addEventListener('change', () => {
    const f = fi.files && fi.files[0];
    fi.value = '';
    if (!f) return;
    f.text().then(txt => {
      let pack;
      try { pack = JSON.parse(txt); } catch (e) { toast('File không phải JSON hợp lệ.', { kind: 'warn' }); return; }
      return api('/data/restore', { method: 'POST', body: pack }).then(res => {
        toast('Đã khôi phục: ' + res.watchlist + ' mã · ' + res.views + ' khung nhìn · ' + res.reviews + ' nhãn.', { kind: 'ok', ms: 3600 });
        return api('/auth/me').then(me => {
          const prevTf = S.tf;
          setSession(me); restorePrefs(); applyRole();
          return fetchViews()
            .then(() => (S.tf !== prevTf ? loadSeries(false) : null))
            .then(() => { syncAll(); D.dirty = true; });
        });
      });
    }).catch(toastApiError);
  });
}

/* Trước đăng nhập: lối thoát privacy — dữ liệu nằm ở đâu, vào đâu để quản lý. */
export function dataAuthPop() {
  closePops();
  const hasLocal = !!localStorage.getItem(LOCAL_KEY);
  const p = document.createElement('div'); p.className = 'nq-pop nq-datapop';
  p.innerHTML =
    '<h4>Dữ liệu & sao lưu</h4>' +
    '<div class="nq-data-note" style="border-top:0;margin-top:0;padding-top:0">Tài khoản, watchlist và nhãn rà soát nằm trên máy chủ tự chạy của bạn — không gửi đi đâu khác. Đăng nhập để tải backup JSON, khôi phục, hoặc đưa dữ liệu cục bộ cũ lên server.</div>' +
    (hasLocal ? '<div class="nq-data-note">Trình duyệt này còn dữ liệu cục bộ (nqreplay.v1) — đưa lên server sau khi đăng nhập.</div>' : '') +
    '<div class="nq-data-act" style="grid-template-columns:1fr"><button class="nq-btn pri" id="nq-da-login">Đến đăng nhập</button></div>';
  const rr = root.getBoundingClientRect();
  popAt(p, rr.left + rr.width / 2, rr.top + 140);
  p.querySelector('#nq-da-login').addEventListener('click', () => { closePops(); setTab('login'); $('nq-li-u').focus(); });
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