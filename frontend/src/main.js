import { $, root, setSession } from './state.js';
import { api } from './api.js';
import { wireAuth, showAuth, enterApp, logout } from './auth.js';
import { applyTheme } from './ui/theme.js';
import { toast } from './ui/toasts.js';

function closePops() {
  root.querySelectorAll('.nq-menu').forEach(m => m.remove());
}

/* Menu tối giản cho T10; đổi vai trò/mật khẩu/dữ liệu nối ở T11/T12/T17. */
function userMenu() {
  closePops();
  const m = document.createElement('div'); m.className = 'nq-menu';
  m.innerHTML = '<button data-a="new">Tài khoản khác</button><hr><button data-a="out" class="dgr">Đăng xuất</button>';
  const ur = $('nq-user').getBoundingClientRect(), rr = root.getBoundingClientRect();
  m.style.left = Math.max(8, Math.min(ur.right - rr.left - 184, rr.width - 192)) + 'px';
  m.style.top = (ur.bottom - rr.top + 6) + 'px';
  m.addEventListener('click', e => {
    const a = e.target.closest('[data-a]'); if (!a) return;
    closePops();
    if (a.dataset.a === 'out') logout();
    if (a.dataset.a === 'new') { logout().then(() => { $('nq-tab-reg').click(); }); }
  });
  root.appendChild(m);
}

function wireShell() {
  $('nq-user').addEventListener('click', userMenu);
  $('nq-railtoggle').addEventListener('click', () => $('nq-rail').classList.toggle('open'));
  document.addEventListener('click', e => {
    if (!e.target.closest('.nq-menu') && !e.target.closest('#nq-user')) closePops();
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closePops(); });
}

async function boot() {
  wireAuth();
  wireShell();
  applyTheme('workbench');
  try {
    const me = await api('/auth/me');
    enterApp(me);
  } catch (e) {
    showAuth();
  }
}

window.addEventListener('nq-unauth', () => {
  if (!$('nq-app').hidden) {
    setSession(null);
    showAuth();
    toast('Phiên đăng nhập đã hết hạn — vui lòng đăng nhập lại.', { kind: 'warn' });
  }
});

boot();