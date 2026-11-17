import { S } from './state.js';

const DB_NAME = 'nq-offline';
const STORE = 'sessions';

export const OFFLINE_WRITE_MSG = 'Ngoại tuyến — chỉ xem lại, không lưu được thay đổi.';
export const OFFLINE_NODATA_MSG = 'Ngoại tuyến — chưa có dữ liệu mã/khung này trong máy.';

export function isOffline() { return !navigator.onLine; }

function idb() {
  return new Promise((res, rej) => {
    const rq = indexedDB.open(DB_NAME, 1);
    rq.onupgradeneeded = () => rq.result.createObjectStore(STORE);
    rq.onsuccess = () => res(rq.result);
    rq.onerror = () => rej(rq.error);
  });
}
function getRec(db, key) {
  return new Promise((res, rej) => {
    const rq = db.transaction(STORE).objectStore(STORE).get(key);
    rq.onsuccess = () => res(rq.result || null);
    rq.onerror = () => rej(rq.error);
  });
}
function putRec(db, key, rec) {
  return new Promise((res, rej) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).put(rec, key);
    tx.oncomplete = res;
    tx.onerror = () => rej(tx.error);
  });
}

/* bars/signals: truyền null để giữ phần đã lưu trước đó (merge theo sym|si). */
export async function saveSession(sym, si, bars, signals) {
  try {
    const db = await idb();
    const key = sym + '|' + si;
    const rec = Object.assign({}, await getRec(db, key), { sym, si, at: Date.now() });
    if (bars) { rec.bars = bars; rec.tf = S.tf; }
    if (signals) rec.signals = signals;
    await putRec(db, key, rec);
    db.close();
  } catch (e) { /* lưu đệm offline là best-effort */ }
}

export async function loadOffline(sym, si) {
  try {
    const db = await idb();
    const rec = await getRec(db, sym + '|' + si);
    db.close();
    return rec;
  } catch (e) { return null; }
}