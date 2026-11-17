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