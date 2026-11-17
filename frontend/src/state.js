export const root = document.getElementById('nq-root');
export const $ = id => document.getElementById(id);

export const SPEEDS = [0.5, 1, 2, 4, 8, 16, 32, 64];

/* Trạng thái phiên phát lại — giữ các trường của ART; T11 nối dữ liệu thật. */
export const S = {
  sym: 'AAPL', si: 0, tf: '5m', type: 'hollow', cursor: 0, playing: false, spd: 1, rate: 2,
  follow: true, loop: false, density: .70, volFrac: .26, glow: .30,
  ma1: 9, ma2: 21, ma1On: true, ma2On: true, vwap: true, grid: true, cross: true, future: true, sound: true,
  view: { start: 0, count: 90 }, hover: null, selectMode: false, selected: {}, query: '', sort: 'manual',
  activeView: null, dirty: true, sigFilter: 'all', blind: false,
};

export let USER = null;
export let prefsCache = null;
export let capsCache = null;

export function setSession(me) {
  USER = me ? me.user : null;
  prefsCache = me ? me.prefs : null;
  capsCache = me ? me.caps : null;
}