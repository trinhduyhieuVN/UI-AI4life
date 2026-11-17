/* Sinh icon PWA từ brand mark (.nq-mark-g trong index.html): tile tối #20282D +
   polyline trắng M3 17l5-6 4 3 5-8 4 5. PNG encoder thuần Node (zlib), không dependency. */
import { deflateSync } from 'node:zlib';
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const OUT = join(ROOT, 'frontend', 'icons');

const T = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
  return t;
})();
function crc(buf) { let c = 0xFFFFFFFF; for (const b of buf) c = T[(c ^ b) & 0xFF] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; }
function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const cr = Buffer.alloc(4); cr.writeUInt32BE(crc(td));
  return Buffer.concat([len, td, cr]);
}
function png(w, h, rgba) {
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 6;
  const stride = w * 4 + 1;
  const raw = Buffer.alloc(stride * h);
  for (let y = 0; y < h; y++) { raw[y * stride] = 0; rgba.copy(raw, y * stride + 1, y * w * 4, (y + 1) * w * 4); }
  return Buffer.concat([sig, chunk('IHDR', ihdr), chunk('IDAT', deflateSync(raw, { level: 9 })), chunk('IEND', Buffer.alloc(0))]);
}

const PTS = [[3, 17], [8, 11], [12, 14], [17, 6], [21, 11]];
const TILE = [0x20, 0x28, 0x2D], INK = [255, 255, 255];
const clamp01 = x => Math.max(0, Math.min(1, x));
function segDist(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay;
  const t = clamp01(((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}
function draw(size, maskable) {
  const rgba = Buffer.alloc(size * size * 4);
  const glyphScale = maskable ? 0.62 : 0.78;
  const gs = (size / 24) * glyphScale;
  const off = (size - 24 * gs) / 2;
  const rad = maskable ? 0 : size * 0.22;
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const px = x + 0.5, py = y + 0.5;
      let tileA = 1;
      if (!maskable) {
        const cx = Math.abs(px - size / 2) - (size / 2 - rad);
        const cy = Math.abs(py - size / 2) - (size / 2 - rad);
        const d = Math.hypot(Math.max(cx, 0), Math.max(cy, 0)) + Math.min(Math.max(cx, cy), 0) - rad;
        tileA = clamp01(0.5 - d);
      }
      const gx = (px - off) / gs, gy = (py - off) / gs;
      let d = Infinity;
      for (let i = 0; i < PTS.length - 1; i++) d = Math.min(d, segDist(gx, gy, PTS[i][0], PTS[i][1], PTS[i + 1][0], PTS[i + 1][1]));
      const inkA = clamp01((1.2 - d) * gs + 0.5);
      const o = (y * size + x) * 4;
      rgba[o] = Math.round(TILE[0] * (1 - inkA) + INK[0] * inkA);
      rgba[o + 1] = Math.round(TILE[1] * (1 - inkA) + INK[1] * inkA);
      rgba[o + 2] = Math.round(TILE[2] * (1 - inkA) + INK[2] * inkA);
      rgba[o + 3] = Math.round(tileA * 255);
    }
  }
  return png(size, size, rgba);
}

mkdirSync(OUT, { recursive: true });
writeFileSync(join(OUT, '192.png'), draw(192, false));
writeFileSync(join(OUT, '512.png'), draw(512, false));
writeFileSync(join(OUT, 'maskable-512.png'), draw(512, true));
console.log('icons written →', OUT);