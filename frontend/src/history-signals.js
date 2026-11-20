import { $, D, S, curRole } from './state.js';
import { api } from './api.js';
import { hhmm, nfmt } from './util.js';

const scores = new Map();
const pending = new Map();

function selection() {
  const b = D.bars[S.cursor];
  return b && { key: S.sym + '|' + b.day, day: b.day, symbol: S.sym, minute: b.minute };
}

function loadThrough(sel) {
  const { key, day, symbol, minute } = sel, saved = scores.get(key) || [];
  if (saved.length >= minute || pending.has(key)) return;
  const query = new URLSearchParams({ symbol, day, through: minute, after: saved.length });
  pending.set(key, true);
  api('/historical/points?' + query).then(({ points }) => {
    scores.set(key, saved.concat(points));
    D.sigDirty = true; D.dirty = true;
  }).catch(e => {
    if (selection()?.key === key) $('nq-sig-b').textContent = e.message;
  }).finally(() => pending.delete(key));
}

export function visibleHistoryScores() {
  const sel = selection();
  return sel ? (scores.get(sel.key) || []).slice(0, sel.minute) : [];
}

export function historyMarkers() {
  return visibleHistoryScores().filter(p => p.energy > p.threshold).map(p => ({ endIdx: p.minute - 1 }));
}

export function renderHistorySignals() {
  const sel = selection(), host = $('nq-sig-b'), role = curRole();
  const filter = S.sigFilter === 'alert' ? 'alert' : 'all';
  $('nq-sig-mode').textContent = 'DHGNN + EBM · ' + S.sym;
  $('nq-sig-blind').hidden = !role.blind;
  $('nq-sig-blind').setAttribute('aria-pressed', String(S.blind));
  $('nq-sig-csv').hidden = !role.sigCSV;
  $('nq-sig-csv').disabled = S.blind;
  for (const chip of $('nq-sig-f').querySelectorAll('[data-f]')) {
    chip.hidden = !['all', 'alert'].includes(chip.dataset.f);
    chip.setAttribute('aria-pressed', String(chip.dataset.f === filter));
  }
  const points = visibleHistoryScores();
  const waiting = sel && points.length < sel.minute;
  if (waiting) loadThrough(sel);
  host.setAttribute('aria-busy', String(!!waiting));
  if (!points.length) {
    host.textContent = 'Đang tải điểm tại mốc phát…';
    $('nq-sig-n').textContent = '—';
    return;
  }
  const alerts = points.filter(p => p.energy > p.threshold).reverse();
  $('nq-sig-n').textContent = alerts.length + ' phút vượt ngưỡng';
  const latest = points.at(-1);
  const shown = filter === 'alert' ? alerts : [latest, ...alerts.filter(p => p !== latest)];
  if (!shown.length) {
    host.textContent = 'Chưa có phút vượt ngưỡng đến mốc phát.';
    return;
  }
  if (!host.firstElementChild) host.replaceChildren();
  const count = Math.min(40, shown.length);
  while (host.children.length > count) host.lastElementChild.remove();
  for (let i = 0; i < count; i++) {
    const p = shown[i];
    const alert = p.energy > p.threshold;
    const cells = [
      ['nq-sig-t', hhmm(p.end_ms)], ['nq-sig-sym', sel.symbol],
      ['nq-sig-txt', p === latest ? 'Điểm tại ' + hhmm(p.end_ms) : 'Phút vượt ngưỡng'],
      ['nq-sig-score', S.blind ? '•••' : nfmt(p.energy, 6) + ' / ' + nfmt(p.threshold, 6)],
      ['nq-sig-st ' + (alert ? 'alert' : 'watch'), alert ? 'Cảnh báo' : 'Dưới ngưỡng'],
    ];
    let row = host.children[i];
    if (!row) {
      row = document.createElement('div'); row.className = 'nq-sig-row';
      row.title = 'Điểm năng lượng / ngưỡng cảnh báo';
      for (const _ of cells) row.appendChild(document.createElement('span'));
      host.appendChild(row);
    }
    cells.forEach(([cls, label], index) => {
      const cell = row.children[index];
      if (cell.className !== cls) cell.className = cls;
      if (cell.textContent !== label) cell.textContent = label;
    });
  }
}
