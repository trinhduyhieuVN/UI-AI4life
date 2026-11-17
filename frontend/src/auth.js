import { $, root, S, D, setSession } from './state.js';
import { api } from './api.js';
import { toast } from './ui/toasts.js';
import { applyTheme, PAL } from './ui/theme.js';

export const ROLE_ORDER = ['observer', 'retail', 'institutional', 'compliance', 'regulator', 'quant'];
export const ROLE_META = {
  observer: { label: 'Quan sát', short: 'Công chúng — xem lại phiên và tiêu đề tín hiệu mẫu. Chỉ đọc, không xuất dữ liệu.' },
  retail: { label: 'NĐT cá nhân', short: 'Nhà đầu tư cá nhân — biểu đồ, watchlist và cảnh báo mẫu diễn giải dễ hiểu. Không phải khuyến nghị mua bán.' },
  institutional: { label: 'NĐT tổ chức & rủi ro', short: 'Tổ chức & quản trị rủi ro — điểm số, ngưỡng q98, phân rã lỗi theo feature và xuất CSV. Dữ liệu mô phỏng.' },
  compliance: { label: 'Tuân thủ CTCK', short: 'Tuân thủ công ty chứng khoán — hàng đợi cảnh báo, nhãn rà soát, lý do chặn và outbox. Quy trình mô phỏng, khoá nhìn trước bắt buộc.' },
  regulator: { label: 'Giám sát sở/QLNN', short: 'Giám sát sở giao dịch / cơ quan quản lý — quét bất thường toàn bộ 50 mã, chất lượng nguồn và outbox. Mô phỏng, không phải giám sát thị trường thật.' },
  quant: { label: 'Nghiên cứu/quant', short: 'Nghiên cứu / quant — toàn bộ công cụ, điểm số thô, phân rã error_/share_ và siêu dữ liệu mô hình trên dữ liệu mẫu.' },
};

let liRoleDirty = false;

export function buildRoleSelects() {
  ['nq-li-role', 'nq-rg-role'].forEach(id => {
    const sel = $(id); sel.innerHTML = '';
    ROLE_ORDER.forEach(rid => {
      const o = document.createElement('option'); o.value = rid; o.textContent = ROLE_META[rid].label; sel.appendChild(o);
    });
    sel.value = 'retail'; syncRoleDesc(id);
  });
  liRoleDirty = false;
}

export function syncRoleDesc(id) {
  const r = ROLE_META[$(id).value] || ROLE_META.retail;
  $(id + '-desc').textContent = r.short;
}

export function setTab(which) {
  const login = which === 'login';
  $('nq-tab-login').setAttribute('aria-selected', login ? 'true' : 'false');
  $('nq-tab-reg').setAttribute('aria-selected', login ? 'false' : 'true');
  $('nq-form-login').hidden = !login; $('nq-form-reg').hidden = login;
  $('nq-li-err').textContent = ''; $('nq-rg-err').textContent = '';
}

function pwStrength(p) {
  let s = 0;
  if (p.length >= 8) s++; if (p.length >= 12) s++;
  if (/[A-Z]/.test(p) && /[a-z]/.test(p)) s++; if (/\d/.test(p)) s++; if (/[^\w\s]/.test(p)) s++;
  return Math.min(4, s);
}

export function showAuth() {
  $('nq-app').hidden = true; $('nq-auth').hidden = false;
  $('nq-toasts').innerHTML = '';
  ['nq-li-u', 'nq-li-p', 'nq-rg-u', 'nq-rg-p', 'nq-rg-p2'].forEach(i => $(i).removeAttribute('aria-invalid'));
  $('nq-li-err').textContent = ''; $('nq-rg-err').textContent = '';
  $('nq-rg-role').value = 'retail'; syncRoleDesc('nq-rg-role');
  syncRoleDesc('nq-li-role');
}

/* Vào app: vai trò lấy từ máy chủ (me.caps), không phải từ picker. */
export function enterApp(me) {
  setSession(me);
  $('nq-auth').hidden = true; $('nq-app').hidden = false;
  root.setAttribute('data-role', me.user.role);
  const chip = $('nq-rolechip');
  chip.textContent = (me.caps && me.caps.label) || ROLE_META[me.user.role].label;
  chip.title = (me.caps && me.caps.short) || '';
  $('nq-uname').textContent = me.user.username;
  $('nq-av').textContent = me.user.username.slice(0, 1).toUpperCase();
  applyTheme(me.prefs.theme || 'workbench');
  $('nq-li-role').value = me.user.role; syncRoleDesc('nq-li-role');
  liRoleDirty = false;
  if (D.hooks.onEnter) D.hooks.onEnter(me);
}

async function loginAs(name, pw) {
  await api('/auth/login', { method: 'POST', body: { username: name, password: pw } });
  let me = await api('/auth/me');
  const pick = $('nq-li-role').value;
  if (liRoleDirty && ROLE_META[pick] && pick !== me.user.role) {
    await api('/prefs', { method: 'PUT', body: { role: pick } });
    me = await api('/auth/me');
  }
  enterApp(me);
  toast('Xin chào ' + me.user.username + ' — phiên phát lại đã sẵn sàng', { kind: 'ok' });
}

async function doLogin(name, pw) {
  const err = $('nq-li-err'); err.textContent = '';
  if (!name) { err.textContent = 'Nhập tên đăng nhập.'; $('nq-li-u').setAttribute('aria-invalid', 'true'); return; }
  $('nq-li-u').removeAttribute('aria-invalid');
  const btn = $('nq-form-login').querySelector('button[type=submit]');
  btn.disabled = true; btn.textContent = 'Đang kiểm tra…';
  try {
    await loginAs(name, pw);
    $('nq-li-p').value = ''; $('nq-li-p').removeAttribute('aria-invalid');
  } catch (e) {
    if (e.status === 401) {
      err.textContent = 'Sai tên đăng nhập hoặc mật khẩu.';
      $('nq-li-p').setAttribute('aria-invalid', 'true'); $('nq-li-p').value = ''; $('nq-li-p').focus();
    } else {
      err.textContent = e.message;
    }
  } finally {
    btn.disabled = false; btn.textContent = 'Đăng nhập';
  }
}

async function doRegister(name, email, pw, pw2) {
  const err = $('nq-rg-err'); err.textContent = '';
  ['nq-rg-u', 'nq-rg-p', 'nq-rg-p2'].forEach(i => $(i).removeAttribute('aria-invalid'));
  if (!/^[a-zA-Z0-9_]{3,24}$/.test(name)) { err.textContent = 'Tên đăng nhập 3–24 ký tự, chỉ a-z A-Z 0-9 _.'; $('nq-rg-u').setAttribute('aria-invalid', 'true'); return; }
  if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { err.textContent = 'Email không hợp lệ.'; return; }
  if (pw.length < 8) { err.textContent = 'Mật khẩu cần tối thiểu 8 ký tự.'; $('nq-rg-p').setAttribute('aria-invalid', 'true'); return; }
  if (pw !== pw2) { err.textContent = 'Hai mật khẩu chưa khớp.'; $('nq-rg-p2').setAttribute('aria-invalid', 'true'); return; }
  const btn = $('nq-form-reg').querySelector('button[type=submit]');
  btn.disabled = true; btn.textContent = 'Đang tạo…';
  try {
    await api('/auth/register', { method: 'POST', body: { username: name, email, password: pw, role: $('nq-rg-role').value } });
    await loginAs(name.toLowerCase(), pw);
  } catch (e) {
    err.textContent = e.message;
    if (e.status === 409) $('nq-rg-u').setAttribute('aria-invalid', 'true');
  } finally {
    btn.disabled = false; btn.textContent = 'Tạo tài khoản & đăng nhập';
  }
}

export async function logout() {
  try { await api('/auth/logout', { method: 'POST' }); } catch (e) { /* phiên đã hết hạn */ }
  S.playing = false; D.resume = null;
  setSession(null);
  if (D.hooks.onLeave) D.hooks.onLeave();
  $('nq-li-u').value = ''; $('nq-li-p').value = '';
  showAuth(); setTab('login');
}

export function wireAuth() {
  $('nq-tab-login').addEventListener('click', () => setTab('login'));
  $('nq-tab-reg').addEventListener('click', () => setTab('register'));
  $('nq-form-login').addEventListener('submit', e => { e.preventDefault(); doLogin($('nq-li-u').value.trim(), $('nq-li-p').value); });
  $('nq-form-reg').addEventListener('submit', e => { e.preventDefault(); doRegister($('nq-rg-u').value.trim(), $('nq-rg-e').value.trim(), $('nq-rg-p').value, $('nq-rg-p2').value); });
  $('nq-demo').addEventListener('click', async () => {
    const btn = $('nq-demo'); btn.disabled = true;
    try { await loginAs('demo', 'demo1234'); }
    catch (e) { $('nq-li-err').textContent = e.message; }
    finally { btn.disabled = false; }
  });
  buildRoleSelects();
  $('nq-li-role').addEventListener('change', () => { liRoleDirty = true; syncRoleDesc('nq-li-role'); });
  $('nq-rg-role').addEventListener('change', () => syncRoleDesc('nq-rg-role'));
  $('nq-rg-p').addEventListener('input', function () {
    const s = pwStrength(this.value), m = $('nq-rg-meter');
    m.style.width = (s / 4 * 100) + '%';
    m.style.background = s <= 1 ? PAL.dn : s === 2 ? PAL.am : s === 3 ? PAL.cy : PAL.up;
  });
  root.querySelectorAll('[data-pw]').forEach(b => {
    b.addEventListener('click', () => {
      const t = $(b.dataset.pw);
      t.type = t.type === 'password' ? 'text' : 'password';
      b.style.color = t.type === 'text' ? PAL.cy : '';
    });
  });
}