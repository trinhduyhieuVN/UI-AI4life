import { S, D } from '../state.js';

/* Chỉ báo nhân quả — chỉ tính trên các nến đã hiện (≤ cursor). */
export function maArr(p) {
  const out = new Array(D.total).fill(null); let sum = 0;
  for (let i = 0; i <= S.cursor && i < D.total; i++) { sum += D.bars[i].c; if (i >= p) sum -= D.bars[i - p].c; if (i >= p - 1) out[i] = sum / p; }
  return out;
}
export function vwapArr() {
  const out = new Array(D.total).fill(null); let pv = 0, vv = 0;
  for (let i = 0; i <= S.cursor && i < D.total; i++) { const b = D.bars[i], tp = (b.h + b.l + b.c) / 3; pv += tp * b.v; vv += b.v; out[i] = vv ? pv / vv : null; }
  return out;
}