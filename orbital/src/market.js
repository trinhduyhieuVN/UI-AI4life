import { useEffect, useRef, useState } from 'react';
import { Platform } from 'react-native';

export const worlds = [
  { s:'AAPL', name:'Apple Inc.', sector:'Công nghệ', tile:2, r:.33, a:-2.55, size:57 },
  { s:'MSFT', name:'Microsoft Corporation', sector:'Phần mềm', tile:3, r:.40, a:2.03, size:72 },
  { s:'INTC', name:'Intel Corporation', sector:'Bán dẫn', tile:0, r:.18, a:-.89, size:39 },
  { s:'CSCO', name:'Cisco Systems', sector:'Thiết bị mạng', tile:8, r:.24, a:.65, size:45 },
  { s:'CMCSA', name:'Comcast Corporation', sector:'Viễn thông', tile:1, r:.42, a:2.96, size:64 },
  { s:'FOXA', name:'Fox Corporation', sector:'Truyền thông', tile:5, r:.42, a:-.47, size:61 },
  { s:'DISCA', name:'Discovery, Inc.', sector:'Truyền thông', tile:6, r:.38, a:-1.62, size:48 },
  { s:'VIAC', name:'ViacomCBS Inc.', sector:'Truyền thông', tile:7, r:.44, a:1.03, size:58 },
];

export const apiOrigin = (process.env.EXPO_PUBLIC_API_URL || (Platform.OS === 'android' ? 'http://10.0.2.2:8000' : Platform.OS === 'ios' ? 'http://127.0.0.1:8000' : '')).replace(/\/$/, '');
async function api(path, options) {
  const response = await fetch(apiOrigin + '/api/v1' + path, { credentials:'include', ...options });
  if (!response.ok) throw Object.assign(new Error('Không thể tải dữ liệu (' + response.status + ').'), { status:response.status });
  return response.json();
}
async function sessions() {
  try { return await api('/historical/sessions'); }
  catch (error) {
    if (error.status !== 401) throw error;
    await api('/auth/login', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({username:'demo',password:'demo1234'}) });
    return api('/historical/sessions');
  }
}

// The importer verifies every minute before publishing a session. Intersect
// its per-symbol catalog and require the same opening time and session length.
export function completeSessions(rows) {
  const days = new Map();
  for (const item of rows) {
    if (!days.has(item.day)) days.set(item.day, new Map());
    days.get(item.day).set(item.symbol, item);
  }
  return [...days.keys()].sort().reverse().flatMap(day => {
    const entries = worlds.map(w => days.get(day).get(w.s));
    const first = entries[0];
    if (!first?.minutes || !entries.every(e => e?.minutes === first.minutes && e.open_ms === first.open_ms)) return [];
    return entries;
  });
}
export const speeds = [30, 60, 120, 240];
export function useMarket() {
  const [catalog,setCatalog] = useState([]), [day,setDay] = useState('');
  const [minute,setMinute] = useState(0), [frame,setFrame] = useState(null);
  const [playing,setPlaying] = useState(true), [error,setError] = useState(''), [retry,setRetry] = useState(0);
  const [speed,setSpeed] = useState(60);
  const cache = useRef(new Map());
  useEffect(() => {
    let alive = true;
    sessions().then(({sessions:rows}) => {
      if (!alive) return;
      const complete = completeSessions(rows);
      if (!complete.length) throw Error('Chưa có phiên đủ dữ liệu cho cả 8 mã.');
      setCatalog(complete);
      setDay(d => complete.some(x => x.day === d) ? d : complete[0].day);
    }).catch(e => { if (alive) setError(e.message); });
    return () => { alive = false; };
  },[retry]);
  const active = catalog.filter(x => x.day === day);
  const total = Math.max(1,...active.map(x => x.minutes));
  const target = Math.min(total,minute);
  useEffect(() => {
    if (!active.length) return;
    const controller = new AbortController();
    async function read() {
      const entries = await Promise.all(active.map(async session => {
        const through = Math.min(target,session.minutes), key = day + session.symbol;
        let rows = cache.current.get(key) || [];
        if (rows.length < through) {
          const {points} = await api('/historical/points?symbol=' + session.symbol + '&day=' + day + '&after=' + rows.length + '&through=' + through, {signal:controller.signal});
          if (controller.signal.aborted) return [];
          if (points.length !== through-rows.length || points.some((p,i) => p.minute !== rows.length+i+1 || !Number.isFinite(p.energy) || !Number.isFinite(p.threshold))) {
            throw Error('Điểm mô hình chưa đầy đủ cho ' + session.symbol + ' trong phiên này.');
          }
          rows = [...rows,...points]; cache.current.set(key,rows);
        }
        return [session.symbol,rows.slice(0,through)];
      }));
      if (!controller.signal.aborted) { setFrame({day,minute:target,bySymbol:Object.fromEntries(entries)}); setError(''); }
    }
    read().catch(e => { if (!controller.signal.aborted) {setError(e.message);setPlaying(false);} });
    return () => controller.abort();
  },[catalog,day,target,retry]);
  useEffect(() => {
    if (!playing || frame?.day !== day || frame?.minute !== target) return;
    if (target >= total) { setPlaying(false); return; }
    const timer = setTimeout(() => setMinute(target+1),60000/speed);
    return () => clearTimeout(timer);
  },[playing,day,frame,target,total,speed]);
  return { catalog,day,total,minute:target,open:active[0]?.open_ms,playing,error,speed,
    cycleSpeed() {setSpeed(s => speeds[(speeds.indexOf(s)+1)%speeds.length]);},
    frame:frame?.day === day && frame.minute <= target ? frame : null,
    changeDay(d) { setDay(d);setMinute(0);setPlaying(true); },
    toggle() {
      if (!playing && target === total) setMinute(0);
      setPlaying(v=>!v);
    },
    retry() {setError('');setRetry(i=>i+1);} };
}

const etTime = new Intl.DateTimeFormat('en-GB',{timeZone:'America/New_York',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
export function clock(open,minute) {
  if (!open) return '—';
  return etTime.format(open+minute*60000);
}
export const dateLabel = d => d.split('-').reverse().join('/');
export const number = (n,d=2) => Number.isFinite(n) ? n.toLocaleString('en-US',{minimumFractionDigits:d,maximumFractionDigits:d}) : '—';
export function snapshot(rows=[]) {
  const last = rows[rows.length-1];
  const prices = rows.filter(p => Number.isFinite(p.close));
  const close = prices[prices.length-1]?.close, open = prices[0]?.open;
  const change = open && Number.isFinite(close) ? (close/open-1)*100 : null;
  const alert = Number.isFinite(last?.energy) && Number.isFinite(last?.threshold) ? last.energy > last.threshold : null;
  return {last,close,open,change,alert,prices,volume:rows.reduce((sum,p)=>sum+p.volume,0)};
}
