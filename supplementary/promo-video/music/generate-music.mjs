// Generates public/music.wav — an original synthesized score for the APP promo.
// Timed to the composition at 30 fps: scene boundaries and stamp hits are
// hard-coded in seconds below. 120 BPM (0.5 s per beat).
//
//   node music/generate-music.mjs

import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SR = 44100;
// The composition opens with a 2 s title-card hook; all timeline literals
// below are in "story time" (hook = negative time) and get shifted by LEAD.
const LEAD = 1.5;
const DUR = 68.22 + LEAD;
const N = Math.ceil(DUR * SR);
const samp = (t) => Math.floor((t + LEAD) * SR);
const L = new Float32Array(N);
const Rr = new Float32Array(N);
const SEND = new Float32Array(N); // mono delay-send bus

// ---------- deterministic noise ----------
let seed = 123456789;
const rnd = () => {
  seed = (seed * 1103515245 + 12345) & 0x7fffffff;
  return seed / 0x3fffffff - 1;
};
const rnd01 = () => (rnd() + 1) / 2;

// ---------- wavetables ----------
const TS = 4096;
const mkTable = (amps) => {
  const t = new Float32Array(TS);
  for (let k = 1; k <= amps.length; k++) {
    const a = amps[k - 1];
    if (!a) continue;
    for (let i = 0; i < TS; i++) t[i] += a * Math.sin((2 * Math.PI * k * i) / TS);
  }
  let max = 0;
  for (let i = 0; i < TS; i++) max = Math.max(max, Math.abs(t[i]));
  for (let i = 0; i < TS; i++) t[i] /= max;
  return t;
};
const SAW = mkTable(Array.from({ length: 12 }, (_, i) => 1 / (i + 1)));
const TRI = mkTable(
  Array.from({ length: 9 }, (_, i) => {
    const k = i + 1;
    if (k % 2 === 0) return 0;
    const sign = ((k - 1) / 2) % 2 === 0 ? 1 : -1;
    return sign / (k * k);
  }),
);
const SIN = mkTable([1]);

const f = (m) => 440 * Math.pow(2, (m - 69) / 12);

// ---------- building blocks ----------
const tone = ({
  t0,
  dur,
  freq,
  glideTo = null,
  table = SIN,
  amp,
  panL = 0.71,
  panR = 0.71,
  send = 0,
}) => {
  const s0 = samp(t0);
  const n = Math.floor(dur * SR);
  let ph = rnd01() * TS;
  for (let i = 0; i < n; i++) {
    const idx = s0 + i;
    if (idx < 0 || idx >= N) continue;
    const tt = i / SR;
    const fq = glideTo === null ? freq : freq + (glideTo - freq) * (tt / dur);
    ph += (fq * TS) / SR;
    const v = table[ph % TS | 0];
    const a = amp(tt);
    L[idx] += v * a * panL;
    Rr[idx] += v * a * panR;
    if (send) SEND[idx] += v * a * send;
  }
};

const kick = (t0, g = 1) => {
  const s0 = samp(t0);
  const n = Math.floor(0.34 * SR);
  let ph = 0;
  for (let i = 0; i < n; i++) {
    const idx = s0 + i;
    if (idx < 0 || idx >= N) continue;
    const tt = i / SR;
    const fq = 44 + 115 * Math.exp(-tt / 0.028);
    ph += fq / SR;
    const v = Math.sin(2 * Math.PI * ph) * Math.exp(-tt / 0.15) * 0.9 * g;
    L[idx] += v;
    Rr[idx] += v;
  }
};

const boom = (t0, g = 1) => {
  const s0 = samp(t0);
  const n = Math.floor(0.9 * SR);
  let ph = 0;
  let lp = 0;
  for (let i = 0; i < n; i++) {
    const idx = s0 + i;
    if (idx < 0 || idx >= N) continue;
    const tt = i / SR;
    const fq = 72 + 0 - 42 * (1 - Math.exp(-tt / 0.1));
    ph += fq / SR;
    lp += 0.02 * (rnd() - lp);
    const body = Math.sin(2 * Math.PI * ph) * Math.exp(-tt / 0.24);
    const thud = lp * Math.exp(-tt / 0.07) * 2.4;
    const v = (body * 0.85 + thud) * g;
    L[idx] += v;
    Rr[idx] += v;
  }
};

// crisp noise hit: mode "hat" (differentiated) or "thud" (lowpassed)
const noiseHit = ({ t0, dur, decay, g, mode = "hat", panL = 0.71, panR = 0.71, send = 0 }) => {
  const s0 = samp(t0);
  const n = Math.floor(dur * SR);
  let prev = 0;
  let lp = 0;
  for (let i = 0; i < n; i++) {
    const idx = s0 + i;
    if (idx < 0 || idx >= N) continue;
    const tt = i / SR;
    const w = rnd();
    let v;
    if (mode === "hat") {
      v = (w - prev) * 0.8;
      prev = w;
    } else {
      lp += 0.06 * (w - lp);
      v = lp * 2.2;
    }
    v *= Math.exp(-tt / decay) * g;
    L[idx] += v * panL;
    Rr[idx] += v * panR;
    if (send) SEND[idx] += v * send;
  }
};

const clap = (t0, g) => {
  noiseHit({ t0, dur: 0.18, decay: 0.045, g, send: 0.3 });
  noiseHit({ t0: t0 + 0.012, dur: 0.16, decay: 0.04, g: g * 0.8 });
  noiseHit({ t0: t0 + 0.026, dur: 0.22, decay: 0.07, g: g * 0.7, send: 0.3 });
};

const splash = (t0, g) => noiseHit({ t0, dur: 1.1, decay: 0.32, g, send: 0.4 });

// sustained chord pad: detuned saws through a one-pole lowpass, optional pump
const PUMP_START = 17.5;
const PUMP_END = 59.5;
const pumpAt = (t) => {
  if (t < PUMP_START || t >= PUMP_END) return 1;
  const ts = (t - PUMP_START) % 0.5;
  return 1 - 0.5 * Math.exp(-ts / 0.09);
};

const pad = ({
  t0,
  t1,
  notes,
  gain,
  gainEnd = null,
  cutoff,
  cutoffEnd = null,
  attack = 0.25,
  release = 0.3,
  pump = false,
  send = 0.1,
}) => {
  const s0 = samp(t0);
  const len = t1 - t0;
  const n = Math.floor((len + release) * SR);
  const oscs = [];
  for (const note of notes) {
    for (const d of [-1, 1]) {
      oscs.push({
        fL: f(note) * (1 + d * 0.0017),
        fR: f(note) * (1 - d * 0.0014),
        phL: rnd01() * TS,
        phR: rnd01() * TS,
      });
    }
  }
  let lpL = 0;
  let lpR = 0;
  const gEnd = gainEnd === null ? gain : gainEnd;
  const cEnd = cutoffEnd === null ? cutoff : cutoffEnd;
  for (let i = 0; i < n; i++) {
    const idx = s0 + i;
    if (idx < 0 || idx >= N) continue;
    const tt = i / SR;
    const prog = Math.min(tt / len, 1);
    let env = Math.min(tt / attack, 1);
    if (tt > len) env *= Math.max(0, 1 - (tt - len) / release);
    let g = (gain + (gEnd - gain) * prog) * env;
    if (pump) g *= pumpAt(t0 + tt);
    const fc = cutoff + (cEnd - cutoff) * prog;
    const a = 1 - Math.exp((-2 * Math.PI * fc) / SR);
    let sL = 0;
    let sR = 0;
    for (const o of oscs) {
      o.phL += (o.fL * TS) / SR;
      o.phR += (o.fR * TS) / SR;
      sL += SAW[o.phL % TS | 0];
      sR += SAW[o.phR % TS | 0];
    }
    sL /= oscs.length;
    sR /= oscs.length;
    lpL += a * (sL - lpL);
    lpR += a * (sR - lpR);
    L[idx] += lpL * g;
    Rr[idx] += lpR * g;
    if (send) SEND[idx] += lpL * g * send;
  }
};

const bassNote = (t0, note, g = 0.34) => {
  const s0 = samp(t0);
  const dur = 0.23;
  const n = Math.floor(dur * SR);
  const fq = f(note);
  let ph = 0;
  let ph2 = 0;
  let lp = 0;
  const a = 1 - Math.exp((-2 * Math.PI * 300) / SR);
  for (let i = 0; i < n; i++) {
    const idx = s0 + i;
    if (idx < 0 || idx >= N) continue;
    const tt = i / SR;
    ph += (fq * TS) / SR;
    ph2 += fq / SR;
    lp += a * (SAW[ph % TS | 0] - lp);
    let env = Math.min(tt / 0.005, 1) * Math.exp(-tt / 0.3);
    if (tt > dur - 0.02) env *= (dur - tt) / 0.02;
    const v = (lp * 0.55 + Math.sin(2 * Math.PI * ph2) * 0.6) * env * g * pumpAt(t0 + tt);
    L[idx] += v;
    Rr[idx] += v;
  }
};

const arpNote = (t0, note, pan) => {
  tone({
    t0,
    dur: 0.3,
    freq: f(note),
    table: TRI,
    amp: (tt) => Math.min(tt / 0.004, 1) * Math.exp(-tt / 0.12) * 0.12,
    panL: pan < 0 ? 0.85 : 0.45,
    panR: pan < 0 ? 0.45 : 0.85,
    send: 0.35,
  });
};

const pluck = (t0, note, g = 0.15, decay = 0.9) => {
  tone({
    t0,
    dur: decay * 3,
    freq: f(note),
    table: TRI,
    amp: (tt) => Math.min(tt / 0.006, 1) * Math.exp(-tt / decay) * g,
    send: 0.5,
  });
  tone({
    t0,
    dur: decay * 3,
    freq: f(note) * 2.001,
    table: SIN,
    amp: (tt) => Math.min(tt / 0.006, 1) * Math.exp(-tt / (decay * 0.6)) * g * 0.3,
    send: 0.4,
  });
};

// ---------- timeline ----------
// scene boundaries (s): cold open 0, problems 5.5, flip 13.833, title 17.5,
// repo 24.833, workflow 34.833, results 43.5, network 52.833, outro 60.833
const STAMPS = [6.567, 8.1, 9.633, 11.167];

const Am = [57, 60, 64, 69];
const Dm = [50, 53, 57, 62];
const Fc = [53, 57, 60, 65];
const Cc = [55, 60, 64, 67];
const Gc = [55, 59, 62, 67];
const Am9 = [57, 60, 64, 71];

// --- room tone for the "paper" world (covers the hook card too) ---
{
  let lp = 0;
  const n = Math.floor((13.9 + LEAD) * SR);
  for (let i = 0; i < n; i++) {
    lp += 0.015 * (rnd() - lp);
    const g = 0.05 * Math.min(i / (0.5 * SR), 1);
    L[i] += lp * g;
    Rr[i] += lp * g * 0.9;
  }
}

// --- hook title card (negative story time): stamp slam + pad bed ---
boom(-1.43, 0.75);
noiseHit({ t0: -1.43, dur: 0.1, decay: 0.05, g: 0.3, send: 0.3 });
pad({ t0: -1.5, t1: 0, notes: Am, gain: 0.11, cutoff: 900, attack: 0.4, release: 0.3 });
pluck(-1.15, 69, 0.12, 1.2);

// --- intro pads (cold open) ---
pad({ t0: 0, t1: 5.5, notes: Am, gain: 0.13, cutoff: 900, attack: 1.0, release: 0.4 });
pluck(1.0, 76, 0.13, 1.0);
pluck(2.2, 72, 0.13, 1.0);
pluck(3.4, 69, 0.14, 1.2);

// --- problems: darker pads + heartbeat + stamp hits ---
pad({ t0: 5.5, t1: 9.5, notes: Dm, gain: 0.17, cutoff: 1100, attack: 0.3 });
pad({ t0: 9.5, t1: 13.833, notes: Am, gain: 0.18, cutoff: 1200, attack: 0.3, release: 0.2 });
for (let t = 5.5; t < 13.8; t += 2) {
  kick(t, 0.42);
  kick(t + 0.35, 0.28);
}
for (let t = 5.75; t < 13.833; t += 0.5) {
  noiseHit({ t0: t, dur: 0.07, decay: 0.02, g: 0.045 });
}
for (const t of STAMPS) {
  boom(t, 0.7);
  noiseHit({ t0: t, dur: 0.09, decay: 0.05, g: 0.28, send: 0.3 });
}

// --- flip: riser into the drop ---
pad({
  t0: 13.833,
  t1: 17.36,
  notes: Fc,
  gain: 0.19,
  gainEnd: 0.33,
  cutoff: 1300,
  cutoffEnd: 5500,
  attack: 0.2,
  release: 0.1,
});
{
  // noise sweep, brightening as it ramps
  const t0 = 13.93;
  const dur = 3.3;
  const s0 = samp(t0);
  const n = Math.floor(dur * SR);
  let lp = 0;
  let prev = 0;
  for (let i = 0; i < n; i++) {
    const idx = s0 + i;
    if (idx >= N) break;
    const tt = i / SR;
    const prog = tt / dur;
    const w = rnd();
    lp += 0.04 * (w - lp);
    const bright = (w - prev) * 0.8;
    prev = w;
    const v = (lp * 2 * (1 - prog) + bright * prog) * prog * prog * 0.23;
    L[idx] += v;
    Rr[idx] += v;
  }
}
tone({
  t0: 14.1,
  dur: 3.2,
  freq: 90,
  glideTo: 660,
  table: SIN,
  amp: (tt) => Math.pow(tt / 3.2, 1.6) * 0.1,
});

// --- the drop (title) and groove through network ---
boom(17.5, 1.0);
splash(17.5, 0.17);

// pumped pads, one bar each: Am F C G, from the drop until the outro
const CYCLE = [Am, Fc, Cc, Gc];
const ROOTS = [33, 29, 36, 31];
for (let b = 0; b < 21; b++) {
  const t = 17.5 + b * 2;
  pad({
    t0: t,
    t1: t + 2,
    notes: CYCLE[b % 4],
    gain: 0.235,
    cutoff: b >= 17 ? 4200 : 3300, // brighten for the network lift
    attack: 0.04,
    release: 0.22,
    pump: true,
  });
}

// kicks: four-on-the-floor
for (let t = 17.5; t < 59.5; t += 0.5) kick(t, 1);
// offbeat hats; 16ths once the results scene lands
for (let t = 17.75; t < 59.5; t += 0.5) noiseHit({ t0: t, dur: 0.07, decay: 0.022, g: 0.07 });
for (let t = 43.5; t < 59.5; t += 0.25) noiseHit({ t0: t, dur: 0.05, decay: 0.014, g: 0.032 });
// claps on 2 & 4 from the repo scene onward
for (let t = 25.0; t < 59.5; t += 1.0) clap(t, 0.13);
// section splashes
for (const t of [24.833, 34.833, 43.5, 52.833]) splash(t, 0.14);
boom(48.0, 0.55); // the 11/11 reveal
boom(52.9, 0.45); // network scene entry

// bass: eighths following the chord roots, octave kick on the last beat pair
for (let t = 17.5; t < 59.5; t += 0.5) {
  const bar = Math.floor((t - 17.5) / 2) % 4;
  const beatInBar = Math.floor(((t - 17.5) % 2) / 0.5);
  const root = ROOTS[bar];
  bassNote(t, root);
  bassNote(t + 0.25, beatInBar === 3 ? root + 12 : root, 0.3);
}

// arp: 16ths over chord tones; octave up after the network wakes
{
  const pattern = [0, 1, 2, 3, 2, 1];
  let k = 0;
  for (let t = 17.5; t < 60.8; t += 0.125) {
    const bar = Math.floor((t - 17.5) / 2) % 4;
    const chord = CYCLE[bar];
    const up = t >= 52.833 ? 12 : 0;
    arpNote(t, chord[pattern[k % pattern.length]] + up, k % 2 === 0 ? -1 : 1);
    k++;
  }
}

// --- outro: back to paper ---
boom(60.9, 0.5);
pad({
  t0: 59.5,
  t1: 68.0,
  notes: Am9,
  gain: 0.26,
  gainEnd: 0.2,
  cutoff: 1900,
  attack: 0.7,
  release: 1.0,
});
pluck(61.4, 76, 0.14, 1.0);
pluck(62.3, 72, 0.14, 1.0);
pluck(63.2, 71, 0.13, 1.0);
pluck(64.1, 69, 0.15, 2.0);

// ---------- delay send -> stereo ----------
const D = Math.floor(0.375 * SR);
for (let i = D; i < N; i++) SEND[i] += SEND[i - D] * 0.4;
for (let i = 0; i < N; i++) {
  L[i] += SEND[i] * 0.42;
  const j = i - 180;
  Rr[i] += (j >= 0 ? SEND[j] : SEND[i]) * 0.42;
}

// ---------- master: fades + soft clip ----------
let peak = 0;
const FADE_IN = 0.06 * SR;
const FADE_OUT_START = Math.floor((66.0 + LEAD) * SR);
for (let i = 0; i < N; i++) {
  let g = 1;
  if (i < FADE_IN) g *= i / FADE_IN;
  if (i > FADE_OUT_START) g *= Math.max(0, 1 - (i - FADE_OUT_START) / (N - FADE_OUT_START));
  L[i] = Math.tanh(L[i] * 1.35 * g) * 0.88;
  Rr[i] = Math.tanh(Rr[i] * 1.35 * g) * 0.88;
  peak = Math.max(peak, Math.abs(L[i]), Math.abs(Rr[i]));
}

// ---------- write WAV (16-bit PCM stereo) ----------
const bytes = N * 4;
const buf = Buffer.alloc(44 + bytes);
buf.write("RIFF", 0);
buf.writeUInt32LE(36 + bytes, 4);
buf.write("WAVE", 8);
buf.write("fmt ", 12);
buf.writeUInt32LE(16, 16);
buf.writeUInt16LE(1, 20);
buf.writeUInt16LE(2, 22);
buf.writeUInt32LE(SR, 24);
buf.writeUInt32LE(SR * 4, 28);
buf.writeUInt16LE(4, 32);
buf.writeUInt16LE(16, 34);
buf.write("data", 36);
buf.writeUInt32LE(bytes, 40);
for (let i = 0; i < N; i++) {
  buf.writeInt16LE(Math.max(-32767, Math.min(32767, Math.round(L[i] * 32767))), 44 + i * 4);
  buf.writeInt16LE(Math.max(-32767, Math.min(32767, Math.round(Rr[i] * 32767))), 46 + i * 4);
}

const here = dirname(fileURLToPath(import.meta.url));
const outDir = join(here, "..", "public");
mkdirSync(outDir, { recursive: true });
writeFileSync(join(outDir, "music.wav"), buf);
console.log(`wrote public/music.wav — ${DUR}s, peak ${peak.toFixed(3)}`);
