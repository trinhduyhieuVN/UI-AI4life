import { $, root, curRole } from '../state.js';
import { logout, setTab } from '../auth.js';
import { rolePop } from '../roles.js';
import { dataPop } from './migrate.js';

export function popAt(el, cx, cy) {
  root.appendChild(el);
  const r = root.getBoundingClientRect(), w = el.offsetWidth, h = el.offsetHeight;
  const x = Math.max(8, Math.min(cx - r.left - w / 2, r.width - w - 8));
  const y = Math.max(8, Math.min(cy - r.top + 8, r.height - h - 8));
  el.style.left = x + 'px'; el.style.top = y + 'px';
  setTimeout(() => { document.addEventListener('pointerdown', outsidePop, { once: true }); }, 0);
}
function outsidePop(e) {
  if (!e.target.closest('.nq-pop,.nq-menu')) closePops();
  else document.addEventListener('pointerdown', outsidePop, { once: true });
}
export function closePops() {
  const n = root.querySelectorAll('.nq-pop,.nq-menu');
  for (let i = 0; i < n.length; i++) n[i].parentNode.removeChild(n[i]);
  const tb = $('nq-typebtn'); if (tb) tb.setAttribute('aria-expanded', 'false');
}

/* Đổi vai trò + tài khoản khác + quản lý dữ liệu (theo cap) + đăng xuất. */
export function userMenu() {
  closePops();
  const r = curRole();
  const m = document.createElement('div'); m.className = 'nq-menu';
  let h = '<button data-a="role">Đổi vai trò · ' + r.label + '</button><button data-a="new">Tài khoản khác</button>';
  if (r.dataManager) h += '<button data-a="data">Quản lý dữ liệu</button>';
  h += '<hr><button data-a="out" class="dgr">Đăng xuất</button>';
  m.innerHTML = h;
  const ur = $('nq-user').getBoundingClientRect(), rr = root.getBoundingClientRect();
  popAt(m, ur.right - 184, ur.bottom + 6);
  m.style.left = Math.max(8, Math.min(ur.right - rr.left - 184, rr.width - 192)) + 'px';
  m.style.top = (ur.bottom - rr.top + 6) + 'px';
  m.addEventListener('click', e => {
    const a = e.target.closest('[data-a]'); if (!a) return; closePops();
    if (a.dataset.a === 'out') logout();
    if (a.dataset.a === 'new') logout().then(() => setTab('register'));
    if (a.dataset.a === 'role') rolePop();
    if (a.dataset.a === 'data') dataPop();
  });
}