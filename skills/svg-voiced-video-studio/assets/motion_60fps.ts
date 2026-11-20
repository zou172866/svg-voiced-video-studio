import {Easing, interpolate, spring} from 'remotion';

export const EASE_OUT_EXPO = Easing.bezier(0.22, 1, 0.36, 1);
export const EASE_IN_OUT = Easing.bezier(0.45, 0, 0.55, 1);
/** Hard start, long glide: Swiss layout jumps, mask wipes, rule extensions. */
export const EASE_SNAP = Easing.bezier(0.7, 0, 0.2, 1);
/** Smooth deceleration (~outExpo): arrivals, camera settles, bar growth. */
export const EASE_GLIDE = Easing.bezier(0.16, 1, 0.3, 1);
/** Fast smash / whip transition and crisp exit. */
export const EASE_WHIP = Easing.bezier(0.85, 0, 0.15, 1);

/**
 * Four named spring tiers. Keep the same element class on one tier across the whole film.
 * Mode C (Swiss editorial) must use 'hero' or 'swissSnap' only — never bouncy springs.
 */
export const SPRING_PRESETS = {
  /** Fast, crisp UI edge / indicator / badge (~0.80 damping ratio). */
  edge: {stiffness: 380, damping: 31, mass: 1},
  /** Default container / card / camera follow (~0.74 damping ratio). */
  card: {stiffness: 220, damping: 22, mass: 1},
  /** Heavy, calm hero type / main object (~0.95 damping ratio, near-zero overshoot). */
  hero: {stiffness: 110, damping: 20, mass: 1},
  /** Overdamped Swiss layout snap: locks cleanly onto the grid with zero bounce. */
  swissSnap: {stiffness: 280, damping: 34, mass: 1, overshootClamping: true},
} as const;

export type SpringPresetName = keyof typeof SPRING_PRESETS;

/**
 * 严格边界钳制区间映射（显式声明 clamp，防止任何图形或透明度越界）
 */
export function clampedRange(
  value: number,
  inMin: number,
  inMax: number,
  outMin: number = 0,
  outMax: number = 1,
  easing: (t: number) => number = EASE_OUT_EXPO,
): number {
  if (inMax <= inMin) {
    return value >= inMax ? outMax : outMin;
  }
  return interpolate(value, [inMin, inMax], [outMin, outMax], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing,
  });
}

/**
 * SVG 描边生长计算：返回 strokeDasharray、strokeDashoffset 与显隐门控
 */
export function drawStroke(
  progress: number,
  startP: number,
  endP: number,
  pathLength: number,
): {strokeDasharray: number; strokeDashoffset: number; opacity: number} {
  const p = clampedRange(progress, startP, endP, 0, 1, EASE_OUT_EXPO);
  return {
    strokeDasharray: pathLength,
    strokeDashoffset: pathLength * (1 - p),
    opacity: p > 0.002 ? 1 : 0,
  };
}

/**
 * 按相对进度百分比触发物理弹簧（随任意配音时长与帧率自动自适应；支持传 SPRING_PRESETS 档名或自定义配置）
 */
export function springAt(
  frame: number,
  durationInFrames: number,
  fps: number,
  startP: number,
  configOrPreset:
    | SpringPresetName
    | {damping?: number; stiffness?: number; mass?: number; overshootClamping?: boolean} = 'card',
): number {
  const triggerFrame = Math.round(startP * durationInFrames);
  if (frame < triggerFrame) return 0;
  const config =
    typeof configOrPreset === 'string' ? SPRING_PRESETS[configOrPreset] : configOrPreset;
  return spring({
    frame: frame - triggerFrame,
    fps,
    config,
  });
}

/**
 * 帧率无关的完整场景生命周期计算（Enter 0.45~0.55s → Hold 微呼吸 → Exit 0.25s 快离场）
 */
export function getSceneLifecycle(
  frame: number,
  durationInFrames: number,
  fps: number,
  exitSec: number = 0.25,
) {
  const exitFrames = Math.max(12, Math.round(exitSec * fps));
  const safeDur = Math.max(durationInFrames, exitFrames + Math.round(0.6 * fps));
  const progress = clampedRange(frame, 0, safeDur - 1, 0, 1, (t) => t);

  const enterSpring = spring({
    frame,
    fps,
    config: SPRING_PRESETS.hero,
  });
  const enterFactor = Math.min(1, enterSpring);

  const exitStart = safeDur - exitFrames;
  const exitFactor =
    frame >= exitStart
      ? clampedRange(frame, exitStart, safeDur - 1, 1, 0, EASE_WHIP)
      : 1;

  const masterOpacity = enterFactor * exitFactor;
  const tSec = frame / fps;
  const breath = Math.sin(tSec * Math.PI * 0.85);

  return {
    progress,
    tSec,
    enterSpring,
    enterFactor,
    exitFactor,
    masterOpacity,
    breath,
  };
}

/**
 * 中文旁白字幕均衡折行（优先在标点处切分，杜绝孤字断行）
 */
export function wrapSubtitleText(text: string, maxCharsPerLine: number = 25): string[] {
  const clean = text.trim();
  if (clean.length <= maxCharsPerLine) {
    return [clean];
  }
  const mid = clean.length / 2;
  let bestIdx = -1;
  let bestDist = Infinity;

  for (let i = 5; i < clean.length - 4; i++) {
    if ('，；：、。？！—'.includes(clean[i])) {
      const dist = Math.abs(i + 1 - mid);
      if (
        dist < bestDist &&
        i + 1 <= maxCharsPerLine + 2 &&
        clean.length - (i + 1) <= maxCharsPerLine + 2
      ) {
        bestDist = dist;
        bestIdx = i + 1;
      }
    }
  }

  if (bestIdx !== -1) {
    return [clean.slice(0, bestIdx), clean.slice(bestIdx)];
  }

  const cut = Math.ceil(clean.length / 2);
  return [clean.slice(0, cut), clean.slice(cut)];
}

// ---------------------------------------------------------------------------
// Aesthetic helpers (see references/svg-motion-aesthetics.md)
// ---------------------------------------------------------------------------

/** Scene-local timing of one *keyword* emphasis mark, written by synth_voiceover_template.py. */
export interface EmphasisWindow {
  word: string;
  startSec: number;
  endSec: number;
}

/**
 * Vermilion follows the voice: returns which emphasis word is "lit" at tSec and how strongly (0..1).
 * Ramps in leadSec before the word is spoken (eye needs ~100-150 ms to land), holds while spoken,
 * fades back to ink over releaseSec. Only one word is ever returned, so the frame keeps a single red focus.
 */
export function accentAt(
  tSec: number,
  emphasis: EmphasisWindow[],
  leadSec: number = 0.12,
  releaseSec: number = 0.45,
): {word: string | null; index: number; strength: number} {
  let best = {word: null as string | null, index: -1, strength: 0};
  emphasis.forEach((e, i) => {
    const rampIn = clampedRange(tSec, e.startSec - leadSec, e.startSec, 0, 1, EASE_OUT_EXPO);
    const rampOut = clampedRange(tSec, e.endSec, e.endSec + releaseSec, 1, 0, EASE_IN_OUT);
    const s = Math.min(rampIn, rampOut);
    if (s > best.strength) best = {word: e.word, index: i, strength: s};
  });
  return best;
}

function parseColorRgba(color: string): [number, number, number, number] {
  const trimmed = color.trim();
  const rgbaMatch = trimmed.match(
    /^rgba?\(\s*(\d+(?:\.\d+)?)\s*[,\s]\s*(\d+(?:\.\d+)?)\s*[,\s]\s*(\d+(?:\.\d+)?)(?:\s*[,/]\s*(\d+(?:\.\d+)?%?))?\s*\)$/i,
  );
  if (rgbaMatch) {
    const r = Math.max(0, Math.min(255, Number(rgbaMatch[1]))) / 255;
    const g = Math.max(0, Math.min(255, Number(rgbaMatch[2]))) / 255;
    const b = Math.max(0, Math.min(255, Number(rgbaMatch[3]))) / 255;
    let a = 1;
    if (rgbaMatch[4] !== undefined) {
      const rawA = rgbaMatch[4].endsWith('%')
        ? parseFloat(rgbaMatch[4]) / 100
        : parseFloat(rgbaMatch[4]);
      a = Number.isFinite(rawA) ? Math.max(0, Math.min(1, rawA)) : 1;
    }
    return [r, g, b, a];
  }

  const hexMatch = trimmed.match(/^#?([0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})$/i);
  if (!hexMatch) {
    return [0, 0, 0, 1];
  }
  const clean = hexMatch[1];
  const full =
    clean.length === 3 || clean.length === 4
      ? clean
          .split('')
          .map((c) => c + c)
          .join('')
      : clean;
  const r = parseInt(full.slice(0, 2), 16) / 255;
  const g = parseInt(full.slice(2, 4), 16) / 255;
  const b = parseInt(full.slice(4, 6), 16) / 255;
  const a = full.length === 8 ? parseInt(full.slice(6, 8), 16) / 255 : 1;
  return [r, g, b, a];
}

function formatRgbOrRgba(r: number, g: number, b: number, a: number): string {
  const ri = Math.round(Math.max(0, Math.min(1, r)) * 255);
  const gi = Math.round(Math.max(0, Math.min(1, g)) * 255);
  const bi = Math.round(Math.max(0, Math.min(1, b)) * 255);
  const ac = Math.max(0, Math.min(1, a));
  if (ac >= 0.999) {
    return `#${[ri, gi, bi].map((v) => v.toString(16).padStart(2, '0')).join('')}`;
  }
  return `rgba(${ri}, ${gi}, ${bi}, ${Number(ac.toFixed(3))})`;
}

function srgbToLinear(c: number): number {
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

function linearToSrgb(c: number): number {
  const clamped = Math.max(0, Math.min(1, c));
  return clamped <= 0.0031308 ? 12.92 * clamped : 1.055 * Math.pow(clamped, 1 / 2.4) - 0.055;
}

function rgbToOklab(r: number, g: number, b: number): [number, number, number] {
  const lr = srgbToLinear(r);
  const lg = srgbToLinear(g);
  const lb = srgbToLinear(b);
  const l = Math.cbrt(0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb);
  const m = Math.cbrt(0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb);
  const s = Math.cbrt(0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

function oklabToRgb(L: number, a: number, b: number): [number, number, number] {
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.291485548 * b;
  const l = l_ * l_ * l_;
  const m = m_ * m_ * m_;
  const s = s_ * s_ * s_;
  return [
    linearToSrgb(+4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
    linearToSrgb(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
    linearToSrgb(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s),
  ];
}

/**
 * Perceptually smooth OKLab color interpolation (ink -> vermilion stays crisp without muddy sRGB midpoints).
 * Accepts #RGB, #RRGGBB, #RRGGBBAA, rgb(...), or rgba(...) (including DARK_NIGHT_THEME translucent tokens).
 * Returns #rrggbb when opaque and rgba(...) when alpha < 1; use with accentAt().strength.
 */
export function mixHex(from: string, to: string, t: number): string {
  const k = Number.isFinite(t) ? Math.max(0, Math.min(1, t)) : 0;
  const [r1, g1, b1, a1] = parseColorRgba(from);
  if (k <= 0) {
    return formatRgbOrRgba(r1, g1, b1, a1);
  }
  const [r2, g2, b2, a2] = parseColorRgba(to);
  if (k >= 1) {
    return formatRgbOrRgba(r2, g2, b2, a2);
  }
  const lab1 = rgbToOklab(r1, g1, b1);
  const lab2 = rgbToOklab(r2, g2, b2);
  const [r, g, b] = oklabToRgb(
    lab1[0] + (lab2[0] - lab1[0]) * k,
    lab1[1] + (lab2[1] - lab1[1]) * k,
    lab1[2] + (lab2[2] - lab1[2]) * k,
  );
  return formatRgbOrRgba(r, g, b, a1 + (a2 - a1) * k);
}

export interface CameraKey {
  /** Scene-local second at which the camera arrives at this framing. */
  atSec: number;
  /** Centre of the framing in world (canvas) coordinates. */
  cx: number;
  cy: number;
  /** Zoom: 1 = whole canvas width visible, 2 = half the width (closer). */
  zoom: number;
}

/**
 * One-canvas camera: interpolate between framings and return an SVG viewBox string.
 * Draw the whole film (or act) on one large world canvas and move the camera instead of cutting cards.
 * Between keys the move uses EASE_IN_OUT so the camera settles like a dolly, never linear.
 */
export function cameraAt(
  tSec: number,
  keys: CameraKey[],
  viewW: number,
  viewH: number,
): string {
  if (keys.length === 0) return `0 0 ${viewW} ${viewH}`;
  const sorted = [...keys].sort((a, b) => a.atSec - b.atSec);
  let a = sorted[0];
  let b = sorted[0];
  for (let i = 0; i < sorted.length; i++) {
    if (sorted[i].atSec <= tSec) a = sorted[i];
    if (sorted[i].atSec >= tSec) {
      b = sorted[i];
      break;
    }
    b = sorted[i];
  }
  const t = a === b ? 1 : clampedRange(tSec, a.atSec, b.atSec, 0, 1, EASE_IN_OUT);
  const cx = a.cx + (b.cx - a.cx) * t;
  const cy = a.cy + (b.cy - a.cy) * t;
  // interpolate zoom in log space so 1 -> 4 feels as even as 1 -> 2 -> 4
  const zA = Math.max(1e-3, a.zoom);
  const zB = Math.max(1e-3, b.zoom);
  const zoom = Math.exp(Math.log(zA) + (Math.log(zB) - Math.log(zA)) * t);
  const w = viewW / zoom;
  const h = viewH / zoom;
  return `${cx - w / 2} ${cy - h / 2} ${w} ${h}`;
}

/** Deterministic hash noise in [-1, 1]; same inputs give the same value on every frame and every render. */
function hashNoise(i: number, seed: number): number {
  const x = Math.sin(i * 127.1 + seed * 311.7) * 43758.5453;
  return (x - Math.floor(x)) * 2 - 1;
}

/**
 * Hand-drawn ink wobble for a polyline: offsets each point perpendicular-ish by a fixed seeded amount.
 * amplitude in px (1.2-2.5 reads as brush, > 4 looks broken). Static per seed: never re-randomise per frame,
 * or the line will shimmer. Returns an SVG path "d" string.
 */
export function inkJitter(points: Array<[number, number]>, amplitude: number = 1.6, seed: number = 1): string {
  return points
    .map(([x, y], i) => {
      const jx = hashNoise(i, seed) * amplitude;
      const jy = hashNoise(i + 1000, seed) * amplitude;
      return `${i === 0 ? 'M' : 'L'}${(x + jx).toFixed(2)} ${(y + jy).toFixed(2)}`;
    })
    .join(' ');
}

/**
 * Brush stroke with entry/exit taper: returns a filled outline path around a polyline whose half-width
 * rises from 0 to maxWidth/2 over the first `taper` fraction and falls back over the last `taper` fraction.
 * Fill it with ink (no stroke). Pair with a clipPath/mask driven by progress for draw-on.
 */
export function taperStroke(points: Array<[number, number]>, maxWidth: number = 6, taper: number = 0.18): string {
  const n = points.length;
  if (n < 2) return '';
  const safeTaper = Math.max(1e-4, Math.min(0.5, taper));
  const left: string[] = [];
  const right: string[] = [];
  for (let i = 0; i < n; i++) {
    const [x, y] = points[i];
    const [px, py] = points[Math.max(0, i - 1)];
    const [nx, ny] = points[Math.min(n - 1, i + 1)];
    let dx = nx - px;
    let dy = ny - py;
    const len = Math.hypot(dx, dy) || 1;
    dx /= len;
    dy /= len;
    const u = i / (n - 1);
    const shape = Math.min(1, u / safeTaper, (1 - u) / safeTaper);
    const hw = (maxWidth / 2) * Math.sin((Math.max(0, shape) * Math.PI) / 2);
    left.push(`${(x - dy * hw).toFixed(2)} ${(y + dx * hw).toFixed(2)}`);
    right.push(`${(x + dy * hw).toFixed(2)} ${(y - dx * hw).toFixed(2)}`);
  }
  return `M${left.join(' L')} L${right.reverse().join(' L')} Z`;
}

/**
 * When to START a transition so the new picture first becomes visible ON the voice/beat hit.
 * revealRatio = fraction into durSec where the new subject first shows (0 = immediate wipe, 0.3 = iris opening).
 */
export function revealOn(hitSec: number, durSec: number, revealRatio: number = 0): number {
  return Math.max(0, hitSec - Math.max(0, Math.min(1, revealRatio)) * Math.max(0, durSec));
}

/**
 * Minimum on-screen hold time (seconds AFTER fully revealed) for Chinese screen text:
 * chars / 4.5 + 1.5s; key commercial numbers hold at least 2.5s.
 */
export function minReadHoldSec(text: string, isKeyNumber: boolean = false): number {
  const units = (text.match(/[A-Za-z0-9]+|[\u3400-\u9fff]/g) ?? []).length;
  const base = units / 4.5 + 1.5;
  return isKeyNumber ? Math.max(2.5, base) : base;
}

export interface SwissGridSpec {
  cols: number;
  gutter: number;
  colWidth: number;
  /** X coordinate of 1-based column (1..cols). */
  colX: (col1Based: number) => number;
  /** Pixel width spanning N columns (including internal gutters). */
  spanW: (colSpan: number) => number;
  /** Baseline Y coordinate for 0-based row (default 24px vertical rhythm). */
  baselineY: (row: number, step?: number) => number;
}

/**
 * Modular Swiss grid inside SceneFrameShell's `safe` content box:
 * defaults to 12 columns (24px gutter) on 16:9 landscape and 6 columns (20px gutter) on 9:16 portrait.
 */
export function swissGrid(
  safe: {left: number; top: number; width: number; height: number},
  cols?: number,
  gutter?: number,
): SwissGridSpec {
  const isLandscape = safe.width >= safe.height;
  const n = cols ?? (isLandscape ? 12 : 6);
  const g = gutter ?? (isLandscape ? 24 : 20);
  const colWidth = (safe.width - g * (n - 1)) / n;
  return {
    cols: n,
    gutter: g,
    colWidth,
    colX: (col1Based: number) => {
      const c = Math.max(1, Math.min(n, col1Based)) - 1;
      return safe.left + c * (colWidth + g);
    },
    spanW: (colSpan: number) => {
      const s = Math.max(1, Math.min(n, colSpan));
      return s * colWidth + (s - 1) * g;
    },
    baselineY: (row: number, step: number = 24) => safe.top + row * step,
  };
}

/**
 * Time-based choreography stagger (default 0.09s cascade step, 0.42s glide).
 * Keeps entrances hierarchical instead of popping every element simultaneously.
 */
export function staggerAt(
  tSec: number,
  index: number,
  baseSec: number = 0.08,
  stepSec: number = 0.09,
  durSec: number = 0.42,
  easing: (t: number) => number = EASE_GLIDE,
): number {
  const start = baseSec + Math.max(0, index) * stepSec;
  return clampedRange(tSec, start, start + Math.max(0.05, durSec), 0, 1, easing);
}

/**
 * Crisp Swiss paper-mask wipe CSS clipPath value for HTML overlay containers.
 * Inside SVG `<g>` stages (e.g. SceneFrameShell children), prefer `wipeRect()` or `<SvgWipe>`
 * using native SVG `<clipPath><rect /></clipPath>` in explicit user-space coordinates.
 */
export function wipeInset(
  progress: number,
  direction: 'left' | 'right' | 'up' | 'down' = 'right',
): string {
  const rem = (1 - Math.max(0, Math.min(1, progress))) * 100;
  const pct = `${rem.toFixed(2)}%`;
  switch (direction) {
    case 'right':
      return `inset(0 ${pct} 0 0)`;
    case 'left':
      return `inset(0 0 0 ${pct})`;
    case 'down':
      return `inset(0 0 ${pct} 0)`;
    case 'up':
      return `inset(${pct} 0 0 0)`;
  }
}

export interface SvgRectBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * Native SVG user-space `<clipPath><rect /></clipPath>` wipe geometry.
 * 100% deterministic inside `<svg>` stages at both 1K (`--scale=1`) and 4K (`--scale=2`),
 * avoiding Chromium CSS `clip-path: inset(...)` objectBoundingBox quirks on `<g>` elements.
 */
export function wipeRect(
  x: number,
  y: number,
  width: number,
  height: number,
  progress: number,
  direction: 'right' | 'left' | 'down' | 'up' = 'right',
): SvgRectBox {
  const p = Number.isFinite(progress) ? Math.max(0, Math.min(1, progress)) : 0;
  const safeW = Math.max(0, width);
  const safeH = Math.max(0, height);
  switch (direction) {
    case 'right':
      return {x, y, width: safeW * p, height: safeH};
    case 'left':
      return {x: x + safeW * (1 - p), y, width: safeW * p, height: safeH};
    case 'down':
      return {x, y, width: safeW, height: safeH * p};
    case 'up':
      return {x, y: y + safeH * (1 - p), width: safeW, height: safeH * p};
  }
}

/**
 * Strictly clamped, eased numeric counter supporting cross-scene continuation.
 * Pass the previous scene's terminal value in `from` so metrics never reset to 0 across cuts.
 */
export function countTo(
  tSec: number,
  startSec: number,
  durSec: number,
  from: number,
  to: number,
  decimals: number = 0,
  easing: (t: number) => number = EASE_GLIDE,
): number {
  const p = clampedRange(tSec, startSec, startSec + Math.max(0.05, durSec), 0, 1, easing);
  const raw = from + (to - from) * p;
  if (decimals <= 0) {
    const rounded = Math.round(raw);
    return rounded === 0 ? 0 : rounded;
  }
  const factor = Math.pow(10, decimals);
  const rounded = Math.round(raw * factor) / factor;
  return rounded === 0 ? 0 : rounded;
}

/**
 * Compute top Y inside `safe` that anchors a visual block around the optical center
 * (default bias 0.47 = slightly above geometric midpoint, eliminating bottom dead voids).
 */
export function opticalCenterY(
  contentHeight: number,
  safe: {top: number; height: number},
  bias: number = 0.47,
): number {
  const clampedBias = Math.max(0.2, Math.min(0.8, bias));
  const free = Math.max(0, safe.height - contentHeight);
  return Math.round(safe.top + free * clampedBias);
}

/**
 * Anchor a visual block cleanly above the bottom edge of `safe` (right above the portrait 54px subtitle rail)
 * so graphic + subtitle read as ONE visual unit and negative space consolidates into a single clean block above.
 */
export function bottomAnchorY(
  contentHeight: number,
  safe: {top: number; height: number},
  bottomPad: number = 28,
): number {
  const pad = Math.max(0, bottomPad);
  const target = safe.top + safe.height - contentHeight - pad;
  return Math.round(Math.max(safe.top, target));
}

export interface TextScriptRun {
  text: string;
  isLatin: boolean;
}

/**
 * Split mixed CJK + Latin strings into script runs so serif typography can apply `letter-spacing: 0`
 * strictly to Latin/number runs (preventing "S k i l l" drift when CJK tracking is non-zero).
 */
export function splitLatinRuns(text: string): TextScriptRun[] {
  const spaced = panguSpace(text);
  const runs: TextScriptRun[] = [];
  const re = /([A-Za-z0-9][A-Za-z0-9._:/+-]*|\/[a-z][a-z0-9-]*)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(spaced)) !== null) {
    if (m.index > last) {
      runs.push({text: spaced.slice(last, m.index), isLatin: false});
    }
    runs.push({text: m[0], isLatin: true});
    last = m.index + m[0].length;
  }
  if (last < spaced.length) {
    runs.push({text: spaced.slice(last), isLatin: false});
  }
  return runs;
}

/**
 * Insert delicate optical thin spaces (U+2009) at CJK <-> ASCII alphanumeric / lowercase slash-command /
 * currency / percent / signed-number or signed-currency boundaries ("盘古之白") so mixed headlines like
 * "月收$12,400", "省下-$100美元", "直降-25%成本", "用/boost多智能体", and "1个Skill解决" breathe cleanly
 * while keeping "$12,400/月" and "效率/ROI" intact. Idempotent.
 */
export function panguSpace(text: string): string {
  const THIN = '\u2009';
  return text
    .replace(/([\u3400-\u9fff])([A-Za-z0-9$¥€£]|[+-](?=[$¥€£]?\d)|\/(?=[a-z]))/g, `$1${THIN}$2`)
    .replace(/([A-Za-z0-9%])([\u3400-\u9fff])/g, `$1${THIN}$2`);
}
