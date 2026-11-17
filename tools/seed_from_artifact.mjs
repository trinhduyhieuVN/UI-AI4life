import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const ART =
  process.argv[2] ||
  "C:/Users/Hieu/.qoder/app/chat-session-visualizations/4446aceb-62ce-4331-8e61-9ed8a64a84d3/visualizations/nasdaq-replay-terminal.html";

const txt = readFileSync(ART, "utf8");
const start = txt.indexOf("/* ---------- deterministic RNG");
const end = txt.indexOf("function sigCursorMinute");
if (start < 0 || end < 0 || end <= start) throw new Error("extraction window not found");
const code = txt.slice(start, end);
const { SYMBOLS, SESSIONS, genSymbol, genSignals } = new Function(
  code + "; return {SYMBOLS, SESSIONS, genSymbol, genSignals};"
)();

const bars = {};
const stats = {};
const signals = {};
for (const meta of SYMBOLS) {
  const all = genSymbol(meta.s);
  bars[meta.s] = {};
  stats[meta.s] = {};
  for (let si = 0; si < SESSIONS.length; si++) {
    const d = all[si];
    bars[meta.s][d.date] = d.m1;
    stats[meta.s][d.date] = {
      open: d.open, close: d.close, high: d.high, low: d.low,
      vol: d.vol, vwap: d.vwap, prev: d.prev, shock: d.shock,
    };
    signals[meta.s + "|" + d.date] = genSignals(meta.s, si);
  }
}

const sha = (o) => createHash("sha256").update(JSON.stringify(o)).digest("hex");
const manifest = {
  symbols: SYMBOLS.map(({ s, n, sec }) => ({ s, n, sec })),
  sessions: SESSIONS,
  bars,
  stats,
  signals,
  checksums: { bars: sha(bars), signals: sha(signals) },
};
writeFileSync(join(ROOT, "tools", "seed_manifest.json"), JSON.stringify(manifest));
console.log("checksums", manifest.checksums);