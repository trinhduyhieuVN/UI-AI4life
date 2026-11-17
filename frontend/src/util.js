import { ET_OFFSET } from './state.js';

export function fmtDate(d) { const p = d.split('-'); return p[2] + '/' + p[1] + '/' + p[0]; }
export function fmtDateShort(d) { const p = d.split('-'); return p[2] + '/' + p[1]; }
export function hhmm(ms) { const d = new Date(ms - ET_OFFSET); return String(d.getUTCHours()).padStart(2, '0') + ':' + String(d.getUTCMinutes()).padStart(2, '0'); }
export function hhmmss(ms) { return hhmm(ms) + ':' + String(new Date(ms - ET_OFFSET).getUTCSeconds()).padStart(2, '0'); }
export function nfmt(v, dp) { if (v == null || !isFinite(v)) return '—'; return v.toLocaleString('en-US', { minimumFractionDigits: dp == null ? 2 : dp, maximumFractionDigits: dp == null ? 2 : dp }); }
export function vfmt(v) { if (v == null || !isFinite(v)) return '—'; if (v >= 1e9) return (v / 1e9).toFixed(2) + 'B'; if (v >= 1e6) return (v / 1e6).toFixed(2) + 'M'; if (v >= 1e3) return (v / 1e3).toFixed(1) + 'K'; return String(Math.round(v)); }
export function rgba(hex, a) {
  let h = hex.replace('#', '');
  if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
  const n = parseInt(h, 16);
  return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
}
export function escapeHtml(s) { return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }