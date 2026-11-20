import { S, D, $, curRole, TFS } from '../state.js';
import { nfmt, escapeHtml } from '../util.js';
import { PAL } from './theme.js';
import { toast } from './toasts.js';
import { popAt, closePops } from './menus.js';
import { quote, loadSeries, apiAddSymbol, apiRemoveSymbol, apiOrder, replaceWatch, apiSaveView, apiRenameView, apiDeleteView } from '../data.js';
import { persist } from '../prefs.js';
import { openDrawer } from './drawer.js';
import { sessionFor } from '../history.js';

const DEFAULT_WATCH = ['AAPL', 'NVDA', 'MSFT', 'TSLA', 'AMZN', 'META', 'AVGO', 'AMD'];

export function visibleSymbols() {
  let list = D.watch.slice();
  if (S.sort === 'name') list.sort((a, b) => a < b ? -1 : 1);
  else if (S.sort === 'chg') list.sort((a, b) => quote(b).p - quote(a).p);
  else if (S.sort === 'vol') list.sort((a, b) => quote(b).vol - quote(a).vol);
  else if (S.sort === 'px') list.sort((a, b) => quote(b).px - quote(a).px);
  const q = S.query.trim().toLowerCase();
  if (q) list = list.filter(s => s.toLowerCase().indexOf(q) >= 0 || (D.SYM[s] && (D.SYM[s].n.toLowerCase().indexOf(q) >= 0 || D.SYM[s].sec.toLowerCase().indexOf(q) >= 0)));
  return list;
}
function sparkPoints(vals, w, h) {
  if (!vals || vals.length < 2) return '';
  let lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
  if (hi - lo < 1e-9) hi = lo + 1;
  return vals.map((v, i) => (i / (vals.length - 1) * w).toFixed(1) + ',' + (h - 2 - (v - lo) / (hi - lo) * (h - 4)).toFixed(1)).join(' ');
}

const rowQuotes = new WeakMap();
function updateQuote(row) {
  const q = quote(row.dataset.sym);
  if (rowQuotes.has(row) && rowQuotes.get(row) === (q.ready ? q : null)) return;
  rowQuotes.set(row, q.ready ? q : null);
  const price = row.querySelector('.nq-sym-q b'), change = price.nextElementSibling;
  price.textContent = nfmt(q.px, 2);
  change.textContent = q.ready ? (q.p >= 0 ? '+' : '') + nfmt(q.p, 2) + '%' : '—';
  change.className = q.up ? 'nq-up' : 'nq-dn';
  const line = row.querySelector('.nq-spark polyline');
  line.setAttribute('points', sparkPoints(q.spark, 120, 20));
  line.setAttribute('stroke', q.up ? PAL.up : PAL.dn);
}

export function refreshQuotes() {
  const host = $('nq-list');
  for (const row of host.querySelectorAll('.nq-sym')) updateQuote(row);
  if (['chg', 'vol', 'px'].includes(S.sort)) {
    const rows = new Map([...host.querySelectorAll('.nq-sym')].map(row => [row.dataset.sym, row]));
    visibleSymbols().forEach((sym, i) => {
      const row = rows.get(sym);
      if (row && row !== host.children[i]) host.insertBefore(row, host.children[i] || null);
    });
  }
}
export function renderList() {
  const host = $('nq-list'), list = visibleSymbols();
  host.innerHTML = '';
  if (!list.length) {
    const e = document.createElement('div'); e.className = 'nq-empty';
    e.innerHTML = S.query ? '<b>Không khớp “' + escapeHtml(S.query) + '”</b>Thử mã khác, hoặc bấm + để thêm từ ' + D.SYMBOLS.length + ' mã Nasdaq.' : '<b>Danh sách trống</b>Bấm + để thêm mã Nasdaq đầu tiên.';
    host.appendChild(e); return;
  }
  list.forEach(sym => {
    const row = document.createElement('div');
    row.className = 'nq-sym'; row.setAttribute('role', 'listitem');
    row.setAttribute('aria-current', sym === S.sym ? 'true' : 'false');
    row.dataset.sym = sym; row.draggable = (S.sort === 'manual' && curRole().rail === 'rw');
    const chk = S.selectMode ? '<button class="nq-sym-c" role="checkbox" aria-checked="' + (!!S.selected[sym]) + '" data-chk="' + sym + '" aria-label="Chọn ' + sym + '"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="m5 13 4 4L19 7"/></svg></button>' : '<span style="width:14px"></span>';
    const meta = D.SYM[sym] || { n: '' };
    row.innerHTML = chk +
      '<div class="nq-sym-id"><b>' + sym + '</b><span>' + escapeHtml(meta.n) + '</span></div>' +
      '<div class="nq-sym-q"><b></b><span></span></div>' +
      '<button class="nq-sym-info" data-info="' + sym + '" aria-label="Chi tiết ' + sym + '"><svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.6v.6"/></svg></button>' +
      '<svg class="nq-spark" viewBox="0 0 120 20" preserveAspectRatio="none" style="width:100%;height:20px"><polyline fill="none" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/></svg>';
    updateQuote(row);
    row.addEventListener('click', ev => {
      if (ev.target.closest('[data-chk]')) { toggleSelect(sym); return; }
      if (ev.target.closest('[data-info]')) {
        if (D.historical && !sessionFor(sym, D.SESSIONS[S.si])) { toast('Chọn mã để xem phiên có dữ liệu.'); return; }
        openDrawer(sym).catch(e => toast(e.message)); return;
      }
      selectSymbol(sym);
    });
    if (S.sort === 'manual' && curRole().rail === 'rw') {
      row.addEventListener('dragstart', ev => { dragSym = sym; row.classList.add('dragging'); ev.dataTransfer.effectAllowed = 'move'; try { ev.dataTransfer.setData('text/plain', sym); } catch (e) { /* noop */ } });
      row.addEventListener('dragend', () => { row.classList.remove('dragging'); clearDrop(); dragSym = null; });
      row.addEventListener('dragover', ev => { ev.preventDefault(); clearDrop(); const r = row.getBoundingClientRect(); row.classList.add(ev.clientY < r.top + r.height / 2 ? 'drop-above' : 'drop-below'); });
      row.addEventListener('dragleave', () => { row.classList.remove('drop-above', 'drop-below'); });
      row.addEventListener('drop', ev => { ev.preventDefault(); const above = row.classList.contains('drop-above'); clearDrop(); reorder(dragSym, sym, above); });
    }
    host.appendChild(row);
  });
  syncBulk();
}
let dragSym = null;
function clearDrop() { const n = $('nq-list').querySelectorAll('.drop-above,.drop-below'); for (let i = 0; i < n.length; i++) n[i].classList.remove('drop-above', 'drop-below'); }
export function reorder(from, to, above) {
  if (curRole().rail !== 'rw') return;
  if (!from || from === to) return;
  const w = D.watch.slice(), i = w.indexOf(from); let j = w.indexOf(to);
  if (i < 0 || j < 0) return;
  w.splice(i, 1); j = w.indexOf(to); w.splice(above ? j : j + 1, 0, from);
  apiOrder(w).then(() => {
    D.watch = w; S.activeView = null; renderList(); renderViews();
    toast('Đã chuyển ' + from + ' lên trên ' + to, { kind: 'ok', ms: 2200 });
  }).catch(e => { if (e.status !== 401) toast(e.message); });
}
export function toggleSelect(sym) { S.selected[sym] = !S.selected[sym]; if (!S.selected[sym]) delete S.selected[sym]; renderList(); }
export function syncBulk() {
  const n = Object.keys(S.selected).length;
  $('nq-bulk').hidden = !(S.selectMode && n > 0);
  $('nq-bulk-n').textContent = n + ' đã chọn';
}
export function selectSymbol(sym) {
  if (!D.SYM[sym]) return;
  S.sym = sym; D.acc = 0; D.QCACHE = {};
  loadSeries(true);
  renderList(); D.dirty = true;
  if (window.innerWidth <= 820) $('nq-rail').classList.remove('open');
}
export function addSymbol(sym) {
  if (curRole().rail !== 'rw') { toast('Vai trò ' + curRole().label + ' chỉ xem danh sách, không thêm mã.', { kind: 'warn', ms: 2600 }); return; }
  if (D.watch.indexOf(sym) >= 0) { toast(sym + ' đã có trong danh sách', { kind: 'warn' }); return; }
  apiAddSymbol(sym).then(() => {
    D.watch.push(sym); S.activeView = null; renderList(); renderViews();
    toast('Đã thêm ' + sym + ' vào danh sách', { kind: 'ok' });
  }).catch(e => { if (e.status !== 401) toast(e.message); });
}
export function removeSymbols(syms) {
  if (curRole().rail !== 'rw') { toast('Vai trò ' + curRole().label + ' chỉ xem danh sách, không xoá mã.', { kind: 'warn', ms: 2600 }); return; }
  const before = D.watch.slice(), beforeSel = JSON.parse(JSON.stringify(S.selected));
  const newList = D.watch.filter(s => syms.indexOf(s) < 0);
  Promise.all(syms.map(s => apiRemoveSymbol(s))).then(() => {
    D.watch = newList;
    syms.forEach(s => { delete S.selected[s]; });
    if (syms.indexOf(S.sym) >= 0 && D.watch.length) { S.sym = D.watch[0]; loadSeries(true); }
    S.activeView = null; renderList(); renderViews(); syncBulk();
    toast('Đã xoá ' + syms.length + ' mã: ' + syms.join(', '), {
      kind: 'warn', ms: 6500, action: 'Hoàn tác', onAction: () => {
        replaceWatch(before).then(() => { S.selected = beforeSel; renderList(); renderViews(); syncBulk(); toast('Đã khôi phục danh sách', { kind: 'ok' }); })
          .catch(e => { if (e.status !== 401) toast(e.message); });
      },
    });
  }).catch(e => { if (e.status !== 401) toast(e.message); });
}
export function resetList() {
  if (curRole().rail !== 'rw') { toast('Vai trò ' + curRole().label + ' chỉ xem danh sách.', { kind: 'warn', ms: 2400 }); return; }
  const before = D.watch.slice();
  replaceWatch(D.historical ? D.SYMBOLS.map(x => x.s) : DEFAULT_WATCH.slice()).then(() => {
    S.selected = {}; S.activeView = null; S.query = ''; $('nq-q').value = '';
    if (D.watch.indexOf(S.sym) < 0) { S.sym = D.watch[0]; loadSeries(true); }
    renderList(); renderViews();
    toast('Đã khôi phục danh sách gốc (8 mã)', {
      kind: 'warn', ms: 6000, action: 'Hoàn tác', onAction: () => {
        replaceWatch(before).then(() => { renderList(); renderViews(); }).catch(e => { if (e.status !== 401) toast(e.message); });
      },
    });
  }).catch(e => { if (e.status !== 401) toast(e.message); });
}
export function renderViews() {
  const host = $('nq-views'); host.innerHTML = '';
  const all = document.createElement('button');
  all.className = 'nq-chip'; all.setAttribute('aria-pressed', S.activeView === null ? 'true' : 'false');
  all.textContent = 'Tất cả (' + D.watch.length + ')';
  all.addEventListener('click', () => { S.activeView = null; S.query = ''; $('nq-q').value = ''; renderList(); renderViews(); });
  host.appendChild(all);
  D.views.forEach(v => {
    const b = document.createElement('button'); b.className = 'nq-chip';
    b.setAttribute('aria-pressed', S.activeView === v.id ? 'true' : 'false');
    b.textContent = v.name;
    b.title = v.symbols.join(', ');
    b.addEventListener('click', () => applyView(v));
    b.addEventListener('contextmenu', ev => { ev.preventDefault(); viewMenu(ev, v); });
    host.appendChild(b);
  });
  if (curRole().views) {
    const add = document.createElement('button'); add.className = 'nq-chip'; add.textContent = '+ Lưu';
    add.addEventListener('click', ev => saveViewPop(ev));
    host.appendChild(add);
  }
}
export function applyView(v) {
  const filtered = v.symbols.filter(s => !!D.SYM[s]);
  const final = filtered.length ? filtered : (D.historical ? D.SYMBOLS.map(x => x.s) : DEFAULT_WATCH.slice());
  replaceWatch(final).then(() => {
    S.sort = v.sort || 'manual'; $('nq-sort').value = S.sort;
    if (v.tf && TFS[v.tf] != null && curRole().tfs.indexOf(v.tf) >= 0) { S.tf = v.tf; $('nq-c-tf').value = v.tf; }
    S.activeView = v.id; S.selected = {}; S.query = ''; $('nq-q').value = '';
    if (D.watch.indexOf(S.sym) < 0) S.sym = D.watch[0];
    D.QCACHE = {}; loadSeries(true); persist(); renderList(); renderViews();
    toast('Khung nhìn “' + v.name + '” · ' + D.watch.length + ' mã · ' + S.tf, { kind: 'ok', ms: 2600 });
  }).catch(e => { if (e.status !== 401) toast(e.message); });
}
export function viewMenu(ev, v) {
  if (!curRole().views) { toast('Vai trò ' + curRole().label + ' không quản lý khung nhìn.', { kind: 'warn', ms: 2600 }); return; }
  closePops();
  const m = document.createElement('div'); m.className = 'nq-menu';
  m.innerHTML = '<button data-a="apply">Áp dụng khung nhìn</button><button data-a="rename">Đổi tên</button><hr><button data-a="del" class="dgr">Xoá khung nhìn</button>';
  popAt(m, ev.clientX, ev.clientY);
  m.addEventListener('click', e => {
    const a = e.target.closest('[data-a]'); if (!a) return; closePops();
    if (a.dataset.a === 'apply') applyView(v);
    if (a.dataset.a === 'del') {
      apiDeleteView(v.id).then(() => {
        D.views = D.views.filter(x => x.id !== v.id);
        if (S.activeView === v.id) S.activeView = null;
        renderViews();
        toast('Đã xoá khung nhìn “' + v.name + '”', {
          kind: 'warn', ms: 6000, action: 'Hoàn tác', onAction: () => {
            apiSaveView(v.name, { symbols: v.symbols, sort: v.sort, tf: v.tf }).then(res => {
              D.views.push({ id: res.id, name: res.name, symbols: v.symbols, sort: v.sort, tf: v.tf }); renderViews();
            }).catch(er => { if (er.status !== 401) toast(er.message); });
          },
        });
      }).catch(er => { if (er.status !== 401) toast(er.message); });
    }
    if (a.dataset.a === 'rename') renamePop(ev, v);
  });
}
export function renamePop(ev, v) {
  closePops();
  const p = document.createElement('div'); p.className = 'nq-pop';
  p.innerHTML = '<h4>Đổi tên khung nhìn</h4><input class="nq-inp" id="nq-rn" maxlength="24" value="' + escapeHtml(v.name) + '"><button class="nq-btn pri" id="nq-rn-ok">Lưu tên</button>';
  popAt(p, ev.clientX, ev.clientY);
  const inp = p.querySelector('#nq-rn'); inp.focus(); inp.select();
  function ok() {
    const n = inp.value.trim(); if (!n) { inp.setAttribute('aria-invalid', 'true'); return; }
    apiRenameView(v.id, n).then(() => { v.name = n; renderViews(); closePops(); toast('Đã đổi tên thành “' + n + '”', { kind: 'ok' }); })
      .catch(e => { if (e.status !== 401) toast(e.message); });
  }
  p.querySelector('#nq-rn-ok').addEventListener('click', ok);
  inp.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); ok(); } });
}
export function saveViewPop(ev) {
  if (!curRole().views) { toast('Vai trò ' + curRole().label + ' không lưu khung nhìn.', { kind: 'warn', ms: 2600 }); return; }
  closePops();
  const p = document.createElement('div'); p.className = 'nq-pop';
  p.innerHTML = '<h4>Lưu khung nhìn hiện tại</h4><input class="nq-inp" id="nq-sv" maxlength="24" placeholder="Tên, vd: Theo dõi sáng"><div style="font-size:11.5px;color:var(--dim);line-height:1.5">Lưu ' + D.watch.length + ' mã, cách sắp xếp và khung ' + S.tf + '.</div><button class="nq-btn pri" id="nq-sv-ok">Lưu khung nhìn</button>';
  popAt(p, ev.clientX, ev.clientY);
  const inp = p.querySelector('#nq-sv'); inp.focus();
  function ok() {
    const n = inp.value.trim(); if (!n) { inp.setAttribute('aria-invalid', 'true'); inp.focus(); return; }
    const config = { symbols: D.watch.slice(), sort: S.sort, tf: S.tf };
    apiSaveView(n, config).then(res => {
      D.views.push({ id: res.id, name: res.name, symbols: config.symbols, sort: config.sort, tf: config.tf });
      S.activeView = res.id; renderViews(); closePops();
      toast('Đã lưu khung nhìn “' + n + '”', { kind: 'ok' });
    }).catch(e => { if (e.status !== 401) toast(e.message); });
  }
  p.querySelector('#nq-sv-ok').addEventListener('click', ok);
  inp.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); ok(); } });
}

/* ---------- add-symbol dialog ---------- */
export function addDialog(ev) {
  closePops();
  const p = document.createElement('div'); p.className = 'nq-pop'; p.style.width = '276px';
  let opts = D.SYMBOLS.filter(x => D.watch.indexOf(x.s) < 0);
  p.innerHTML = '<h4>Thêm mã Nasdaq</h4><input class="nq-inp" id="nq-af" placeholder="Lọc theo mã / tên / nhóm ngành" spellcheck="false">' +
    '<div id="nq-al" style="max-height:236px;overflow-y:auto;display:flex;flex-direction:column;gap:3px;margin:0 -3px;padding:0 3px"></div>' +
    (opts.length ? '' : '<div style="font-size:11.5px;color:var(--dim)">Bạn đã thêm cả ' + D.SYMBOLS.length + ' mã.</div>');
  popAt(p, ev.clientX || 200, ev.clientY || 120);
  const inp = p.querySelector('#nq-af'), listEl = p.querySelector('#nq-al');
  function draw() {
    const q = inp.value.trim().toLowerCase();
    const f = opts.filter(x => !q || x.s.toLowerCase().indexOf(q) >= 0 || x.n.toLowerCase().indexOf(q) >= 0 || x.sec.toLowerCase().indexOf(q) >= 0);
    listEl.innerHTML = '';
    if (!f.length) { listEl.innerHTML = '<div style="font-size:11.5px;color:var(--dim);padding:8px 2px">Không khớp.</div>'; return; }
    f.forEach(x => {
      const b = document.createElement('button');
      b.style.cssText = 'display:flex;align-items:center;gap:8px;padding:7px 9px;border-radius:7px;border:1px solid var(--line);background:var(--bg0);text-align:left;width:100%';
      b.innerHTML = '<b style="font-family:var(--mono);font-size:11.5px;color:var(--hi);min-width:46px">' + x.s + '</b><span style="font-size:11.5px;color:var(--dim);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + escapeHtml(x.n) + '</span><span style="font-size:11px;color:var(--dim)">' + escapeHtml(x.sec) + '</span>';
      b.addEventListener('mouseenter', () => { b.style.borderColor = PAL.cy; });
      b.addEventListener('mouseleave', () => { b.style.borderColor = PAL.line; });
      b.addEventListener('click', () => { addSymbol(x.s); opts = opts.filter(o => o.s !== x.s); draw(); });
      listEl.appendChild(b);
    });
  }
  inp.addEventListener('input', draw); draw(); inp.focus();
}
