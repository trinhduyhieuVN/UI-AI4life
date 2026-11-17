import { S, D, $, curRole } from '../state.js';
import { toast } from '../ui/toasts.js';
import { persist } from '../prefs.js';
import { popAt, closePops } from '../ui/menus.js';
import { syncHeader } from '../ui/transport.js';

export const CTYPES = [
  { id: 'bars', n: 'Hình thanh', s: 'THANH' },
  { id: 'candles', n: 'Biểu đồ nến', s: 'NẾN' },
  { id: 'hollow', n: 'Biểu đồ nến Hollow', s: 'NẾN HOLLOW' },
  { id: 'columns', n: 'Các cột', s: 'CỘT' },
  { id: 'line', n: 'Đường thẳng', s: 'ĐƯỜNG' },
  { id: 'marked', n: 'Đường có điểm đánh dấu', s: 'ĐƯỜNG + ĐIỂM' },
  { id: 'step', n: 'Đường bậc', s: 'BẬC' },
  { id: 'area', n: 'Biểu đồ vùng', s: 'VÙNG' },
  { id: 'hlc', n: 'Vùng HLC', s: 'HLC' },
  { id: 'baseline', n: 'Đường cơ sở', s: 'CƠ SỞ' },
  { id: 'highlow', n: 'Đỉnh-Đáy', s: 'ĐỈNH-ĐÁY' },
  { id: 'ha', n: 'Heikin Ashi', s: 'HEIKIN ASHI' },
];
export function ctDef(id) { for (let i = 0; i < CTYPES.length; i++) if (CTYPES[i].id === id) return CTYPES[i]; return CTYPES[2]; }

export function ctIcon(id) {
  const s = '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">';
  const f = ' fill="currentColor" stroke="none"';
  switch (id) {
    case 'bars': return s + '<path d="M4.5 2v12M4.5 5H2.5M4.5 9.5h2M11.5 3v11M11.5 6h-2M11.5 10.5h2"/></svg>';
    case 'candles': return s + '<path d="M4 1.5v2.5M4 12v2.5M11.5 2v2M11.5 11v3"/><rect x="2.4" y="4" width="3.2" height="8"' + f + '/><rect x="9.9" y="4" width="3.2" height="7"' + f + '/></svg>';
    case 'hollow': return s + '<path d="M4 1.5v2.5M4 12v2.5M11.5 2v2M11.5 11v3"/><rect x="2.4" y="4" width="3.2" height="8"/><rect x="9.9" y="4" width="3.2" height="7"' + f + '/></svg>';
    case 'columns': return s + '<path d="M2 14.5h12"/><rect x="3" y="7" width="2.6" height="7.5"' + f + '/><rect x="6.8" y="3.5" width="2.6" height="11"' + f + '/><rect x="10.6" y="9" width="2.6" height="5.5"' + f + '/></svg>';
    case 'line': return s + '<path d="M1.5 11.5l4-4.5 3 2.5 6-7"/></svg>';
    case 'marked': return s + '<path d="M1.5 11.5l4-4.5 3 2.5 6-7"/><circle cx="5.5" cy="7" r="1.4"' + f + '/><circle cx="8.5" cy="9.5" r="1.4"' + f + '/><circle cx="14.5" cy="2.5" r="1.4"' + f + '/></svg>';
    case 'step': return s + '<path d="M1.5 12h3.5V7h3.5v2.5H12V3h2.5"/></svg>';
    case 'area': return s + '<path d="M1.5 11.5l4-4.5 3 2.5 6-7V14.5H1.5Z" fill="currentColor" opacity=".22" stroke="none"/><path d="M1.5 11.5l4-4.5 3 2.5 6-7"/></svg>';
    case 'hlc': return s + '<path d="M1.5 4.5l4-2 3 3 6-4v7l-6 4-3-3-4 2Z" fill="currentColor" opacity=".22" stroke="none"/><path d="M1.5 8l4-1 3 2 6-3"/></svg>';
    case 'baseline': return s + '<path d="M1.5 8.5h13" stroke-dasharray="2.5 2.5"/><path d="M1.5 11l4-6 3 3.5 6-5"/></svg>';
    case 'highlow': return s + '<path d="M4 2.5v11M8 4.5v9M12 1.5v12" stroke-width="2"/></svg>';
    case 'ha': return s + '<path d="M4 1.5v2.5M4 11.5v3M11.5 2.5v2M11.5 10.5v3"/><rect x="2.4" y="4" width="3.2" height="7.5" rx="1.2"' + f + '/><rect x="9.9" y="4.5" width="3.2" height="6" rx="1.2"/></svg>';
  }
  return s + '</svg>';
}

export function haArr() {
  const k = S.sym + '|' + S.si + '|' + S.tf;
  if (D.HAC[k]) return D.HAC[k];
  if (Object.keys(D.HAC).length > 24) D.HAC = {};
  const out = []; let po = null, pc = null;
  for (let i = 0; i < D.bars.length; i++) {
    const b = D.bars[i];
    const hc = (b.o + b.h + b.l + b.c) / 4;
    const ho = po == null ? (b.o + b.c) / 2 : (po + pc) / 2;
    out.push({ o: ho, h: Math.max(b.h, ho, hc), l: Math.min(b.l, ho, hc), c: hc, v: b.v, t: b.t });
    po = ho; pc = hc;
  }
  D.HAC[k] = out; return out;
}

export function syncTypeBtn() {
  const b = $('nq-typebtn'); if (!b) return;
  b.innerHTML = '<span class="ct">' + ctIcon(S.type) + '</span><span class="nq-tname">' + ctDef(S.type).n + '</span>' +
    '<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" style="color:var(--dim)"><path d="m6 9 6 6 6-6"/></svg>';
  b.title = 'Kiểu biểu đồ: ' + ctDef(S.type).n;
  b.setAttribute('aria-label', 'Kiểu biểu đồ: ' + ctDef(S.type).n + '. Mở danh sách kiểu');
}

export function setCType(id) {
  if (!CTYPES.some(t => t.id === id)) return;
  if (curRole().types.indexOf(id) < 0) { toast('Kiểu biểu đồ này không khả dụng với vai trò ' + curRole().label + '.', { kind: 'warn', ms: 2600 }); return; }
  S.type = id; persist(); D.dirty = true; syncTypeBtn(); syncHeader();
}

export function typeMenu(ev) {
  closePops();
  const allowed = curRole().types;
  const list = CTYPES.filter(t => allowed.indexOf(t.id) >= 0);
  const p = document.createElement('div'); p.className = 'nq-pop nq-typemenu';
  p.setAttribute('role', 'listbox'); p.setAttribute('aria-label', 'Kiểu biểu đồ');
  let html = '';
  list.forEach((t, i) => {
    if (list.length > 6 && (i === 4 || i === 11)) html += '<hr>';
    html += '<button role="option" aria-selected="' + (t.id === S.type ? 'true' : 'false') + '" data-t="' + t.id + '">' + ctIcon(t.id) + '<span>' + t.n + '</span></button>';
  });
  p.innerHTML = html;
  const r = ev.currentTarget.getBoundingClientRect();
  popAt(p, r.left + r.width / 2, r.bottom);
  $('nq-typebtn').setAttribute('aria-expanded', 'true');
  const rows = p.querySelectorAll('button');
  (p.querySelector('[aria-selected="true"]') || rows[0]).focus();
  p.addEventListener('keydown', e => {
    const idx = Array.prototype.indexOf.call(rows, document.activeElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); rows[(idx + 1) % rows.length].focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); rows[(idx - 1 + rows.length) % rows.length].focus(); }
    else if (e.key === 'Home') { e.preventDefault(); rows[0].focus(); }
    else if (e.key === 'End') { e.preventDefault(); rows[rows.length - 1].focus(); }
    else if (e.key === 'Escape') { closePops(); $('nq-typebtn').focus(); }
  });
  p.addEventListener('click', e => {
    const b = e.target.closest('[data-t]'); if (!b) return;
    setCType(b.getAttribute('data-t')); closePops(); $('nq-typebtn').focus();
  });
}