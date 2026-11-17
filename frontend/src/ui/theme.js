import { root } from '../state.js';

export const THEMES = {
  workbench: { bg0: '#F4F5F7', bg1: '#FFFFFF', bg2: '#EDF1F3', bg3: '#F8FAFC', bg4: '#DFE5E8', line: '#DFE5E8', line2: '#CBD6DB', hi: '#20282D', tx: '#20282D', dim: '#59666E', faint: '#8A99A1', up: '#067A68', upS: '#DCFCE7', dn: '#D01F2F', dnS: '#FEE2E2', cy: '#146F64', am: '#D97706', mg: '#0369A1', vi: '#3730A3', wm: '#8A99A1', grid: '#E2E8F0', scrim: 'rgba(15,23,42,.16)', onCy: '#FFFFFF', light: 1 },
  midnight: { bg0: '#05070D', bg1: '#0A0F1A', bg2: '#101827', bg3: '#182236', bg4: '#22304A', line: '#1B2740', line2: '#2A3B58', hi: '#EAF2FF', tx: '#B9C7DC', dim: '#7186A3', faint: '#465872', up: '#00E08A', upS: '#0C3A2C', dn: '#FF3B5C', dnS: '#3E1220', cy: '#22D3EE', am: '#FFB020', mg: '#FF3DCB', vi: '#8B7BFF', wm: '#F2E4CE', grid: '#152036', scrim: 'rgba(3,6,12,.74)', onCy: '#04070E', light: 0 },
  nasdaq: { bg0: '#03101C', bg1: '#061826', bg2: '#0A2233', bg3: '#0F2E44', bg4: '#164059', line: '#123449', line2: '#1D4E6B', hi: '#E8F6FF', tx: '#AECBDE', dim: '#6E93AC', faint: '#456A82', up: '#00E5A0', upS: '#0A3D31', dn: '#FF4D6D', dnS: '#40152A', cy: '#00A9E0', am: '#FFC24D', mg: '#FF5FD2', vi: '#6FA8FF', wm: '#FFEFD6', grid: '#0E2A3D', scrim: 'rgba(2,10,18,.74)', onCy: '#03101C', light: 0 },
  phosphor: { bg0: '#020805', bg1: '#04120C', bg2: '#071A12', bg3: '#0C2419', bg4: '#123324', line: '#123024', line2: '#1C4534', hi: '#DFFFE9', tx: '#9FD8B4', dim: '#5F9A76', faint: '#3C6B4F', up: '#7CFFB2', upS: '#123D28', dn: '#FF7A7A', dnS: '#3D1A1A', cy: '#4DE8C2', am: '#E8FF7A', mg: '#B6FF4D', vi: '#4DFFA6', wm: '#EAFFF2', grid: '#0D2418', scrim: 'rgba(1,6,3,.76)', onCy: '#02120A', light: 0 },
  daylight: { bg0: '#E7E2D7', bg1: '#F5F2EB', bg2: '#FFFFFF', bg3: '#F0EDE5', bg4: '#E0DACC', line: '#D8D2C4', line2: '#BFB7A5', hi: '#131C28', tx: '#3A4757', dim: '#566374', faint: '#8A93A3', up: '#00674A', upS: '#D6F2E6', dn: '#B01C36', dnS: '#FBDDE3', cy: '#00699E', am: '#7A4800', mg: '#A81F85', vi: '#4A3BC4', wm: '#7A5C2E', grid: '#E2DDD1', scrim: 'rgba(30,26,18,.42)', onCy: '#FFFFFF', light: 1 },
};

export let PAL = THEMES.workbench;

const VAR_MAP = {
  bg0: '--bg0', bg1: '--bg1', bg2: '--bg2', bg3: '--bg3', bg4: '--bg4', line: '--line', line2: '--line2',
  hi: '--hi', tx: '--tx', dim: '--dim', faint: '--faint', up: '--up', upS: '--upS', dn: '--dn', dnS: '--dnS',
  cy: '--cy', am: '--am', mg: '--mg', vi: '--vi', wm: '--wm', grid: '--grid', scrim: '--scrim', onCy: '--onCy',
};

export function applyTheme(name) {
  PAL = THEMES[name] || THEMES.workbench;
  root.setAttribute('data-theme', THEMES[name] ? name : 'workbench');
  for (const k in VAR_MAP) root.style.setProperty(VAR_MAP[k], PAL[k]);
}