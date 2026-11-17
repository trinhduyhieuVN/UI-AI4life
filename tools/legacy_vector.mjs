import { readFileSync, writeFileSync } from "node:fs";
import { pbkdf2Sync } from "node:crypto";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const ART =
  process.argv[2] ||
  "C:/Users/Hieu/.qoder/app/chat-session-visualizations/4446aceb-62ce-4331-8e61-9ed8a64a84d3/visualizations/nasdaq-replay-terminal.html";
const txt = readFileSync(ART, "utf8");
const start = txt.indexOf("/* ---------- crypto");
const end = txt.indexOf("/* ---------- local persistence");
const { fallbackHash } = new Function(
  txt.slice(start, end) + "; return {fallbackHash};"
)();

const pw = "probe-pass-1";
const salt = "00112233445566778899aabbccddeeff";
const vectors = [
  { pw, salt, kdf: "pbkdf2-sha256-150k",
    hash: pbkdf2Sync(pw, Buffer.from(salt, "hex"), 150000, 32, "sha256").toString("hex") },
  { pw, salt, kdf: "sha256-iter-fallback", hash: fallbackHash(pw, salt) },
];
writeFileSync(join(ROOT, "tools", "legacy_vector.json"), JSON.stringify(vectors, null, 2));
console.log("vectors", vectors.map((v) => v.kdf));