import { S } from './state.js';

let AC = null, lastTick = 0;
export function audio() {
  if (!S.sound) return null;
  try {
    if (!AC) { const C = window.AudioContext || window.webkitAudioContext; if (!C) return null; AC = new C(); }
    if (AC.state === 'suspended') AC.resume();
    return AC;
  } catch (e) { return null; }
}
export function blip(freq, dur, gain, type) {
  const ac = audio(); if (!ac) return;
  try {
    const o = ac.createOscillator(), g = ac.createGain(), f = ac.createBiquadFilter();
    f.type = 'lowpass'; f.frequency.value = 2600;
    o.type = type || 'sine'; o.frequency.value = freq;
    const t = ac.currentTime;
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(gain, t + 0.006);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(f); f.connect(g); g.connect(ac.destination); o.start(t); o.stop(t + dur + 0.02);
  } catch (e) { /* audio không khả dụng */ }
}
export function tickSound(up) {
  if (!S.sound || S.spd > 4) return;
  const now = performance.now(); if (now - lastTick < 70) return; lastTick = now;
  blip(up ? 1180 : 760, 0.045, 0.028, 'triangle');
}
export function chime() { blip(660, 0.16, 0.05, 'sine'); setTimeout(() => blip(990, 0.26, 0.045, 'sine'), 110); }