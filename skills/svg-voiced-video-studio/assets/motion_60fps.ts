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

  const exitStart = safeDur - exitFrames;
  const exitFactor =
    frame >= exitStart
      ? clampedRange(frame, exitStart, safeDur - 1, 1, 0, EASE_WHIP)
      : 1;

  const masterOpacity = Math.min(1, enterSpring) * exitFactor;
  const tSec = frame / fps;
  const breath = Math.sin(tSec * Math.PI * 0.85);

  return {
    progress,
    tSec,
    enterSpring,
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

/** Mix two hex colours (ink -> accent) by t in [0,1]; use with accentAt().strength. */
export function mixHex(from: string, to: string, t: number): string {
  const p = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const a = p(from);
  const b = p(to);
  const k = Math.max(0, Math.min(1, t));
  return `#${a.map((v, i) => Math.round(v + (b[i] - v) * k).toString(16).padStart(2, '0')).join('')}`;
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
  const zoom = Math.exp(Math.log(a.zoom) + (Math.log(b.zoom) - Math.log(a.zoom)) * t);
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
    const shape = Math.min(1, u / taper, (1 - u) / taper);
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
