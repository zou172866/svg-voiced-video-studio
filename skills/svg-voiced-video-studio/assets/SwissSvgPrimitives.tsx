import React from 'react';
import {
  bottomAnchorY,
  cameraAt,
  CameraKey,
  clampedRange,
  drawStroke,
  EASE_GLIDE,
  EASE_SNAP,
  EASE_WHIP,
  mixHex,
  panguSpace,
  splitLatinRuns,
  staggerAt,
  wipeRect,
} from './motion_60fps';
import {STUDIO_FONTS, StudioTheme} from './SceneFrameShell_60fps';

const NUM_STYLE: React.CSSProperties = {
  fontVariantNumeric: 'lining-nums tabular-nums',
  fontSynthesisWeight: 'none',
};

const DISPLAY_NUM_STYLE: React.CSSProperties = {
  fontVariantNumeric: 'lining-nums tabular-nums',
  fontSynthesisWeight: 'none',
  wordSpacing: '-0.12em',
};

const NO_SYNTH: React.CSSProperties = {
  fontSynthesisWeight: 'none',
};

function sanitizeId(raw: string): string {
  return raw.replace(/[^a-zA-Z0-9_-]/g, '');
}

/** Collapse manual ASCII spaces at CJK boundaries then apply optical U+2009 pangu spacing so giant figures stay 1 cohesive blob. */
function normalizeDisplayMetric(text: string): string {
  const collapsed = text
    .trim()
    .replace(/([\u3400-\u9fff])[ \t]+([A-Za-z0-9$¥€£+-])/g, '$1$2')
    .replace(/([A-Za-z0-9%])[ \t]+([\u3400-\u9fff])/g, '$1$2');
  return panguSpace(collapsed);
}

function approxVisualUnits(text: string, condensedFigure: boolean = false): number {
  let u = 0;
  for (const ch of text) {
    const code = ch.charCodeAt(0);
    if (code <= 0x7f) {
      if (ch === ' ') u += 0.30;
      else if (condensedFigure && /[0-9$¥€£.,/+-]/.test(ch)) u += 0.50;
      else if (ch >= 'A' && ch <= 'Z') u += 0.66;
      else u += 0.56;
    } else if (code === 0x2009 || code === 0x200a) {
      u += 0.16;
    } else {
      u += 1.0;
    }
  }
  return Math.max(1, u);
}

function fitFontSize(
  text: string,
  maxWidth: number,
  maxSize: number,
  minSize: number,
  condensedFigure: boolean = false,
): number {
  const units = approxVisualUnits(text, condensedFigure);
  const safeMaxW = Math.max(1, maxWidth);
  return Math.round(Math.max(minSize, Math.min(maxSize, safeMaxW / (units * 1.04))));
}

// ---------------------------------------------------------------------------
// Core Native-SVG Motion & Structural Primitives
// ---------------------------------------------------------------------------

export interface SvgWipeProps {
  x: number;
  y: number;
  width: number;
  height: number;
  progress: number;
  direction?: 'right' | 'left' | 'down' | 'up';
  /** Extra bleed padding (px) around the clip box so strokes and descenders never clip. */
  bleed?: number;
  children: React.ReactNode;
}

/**
 * Native SVG `<clipPath><rect /></clipPath>` paper-mask wipe.
 * Use this inside `SceneFrameShell`'s `<svg>` stage instead of CSS `clip-path: inset(...)`
 * so reveals stay vector-exact at both 1K (`--scale=1`) and 4K (`--scale=2`).
 */
export const SvgWipe: React.FC<SvgWipeProps> = ({
  x,
  y,
  width,
  height,
  progress,
  direction = 'right',
  bleed = 6,
  children,
}) => {
  const clipId = `svg-wipe-${sanitizeId(React.useId())}`;
  const rect = wipeRect(
    x - bleed,
    y - bleed,
    Math.max(0, width) + bleed * 2,
    Math.max(0, height) + bleed * 2,
    progress,
    direction,
  );
  if (rect.width <= 0.1 || rect.height <= 0.1) return null;
  return (
    <g>
      <defs>
        <clipPath id={clipId}>
          <rect x={rect.x} y={rect.y} width={rect.width} height={rect.height} />
        </clipPath>
      </defs>
      <g clipPath={`url(#${clipId})`}>{children}</g>
    </g>
  );
};

export interface EditorialRuleProps {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  progress?: number;
  stroke: string;
  strokeWidth?: number;
  opacity?: number;
}

/** Animated Swiss structural hairline drawn cleanly by endpoint interpolation. */
export const EditorialRule: React.FC<EditorialRuleProps> = ({
  x1,
  y1,
  x2,
  y2,
  progress = 1,
  stroke,
  strokeWidth = 1.5,
  opacity = 1,
}) => {
  const p = Number.isFinite(progress) ? Math.max(0, Math.min(1, progress)) : 0;
  if (p <= 0.002) return null;
  return (
    <line
      x1={x1}
      y1={y1}
      x2={x1 + (x2 - x1) * p}
      y2={y1 + (y2 - y1) * p}
      stroke={stroke}
      strokeWidth={strokeWidth}
      opacity={opacity}
    />
  );
};

export interface ShockwaveRingProps {
  tSec: number;
  hitSec: number;
  x: number;
  y: number;
  width: number;
  height: number;
  color: string;
  durationSec?: number;
  maxPad?: number;
  strokeWidth?: number;
}

/** Tight geometric shockwave (< 15px expansion so single-red-focus audit stays 1). */
export const ShockwaveRing: React.FC<ShockwaveRingProps> = ({
  tSec,
  hitSec,
  x,
  y,
  width,
  height,
  color,
  durationSec = 0.46,
  maxPad = 14,
  strokeWidth = 2.5,
}) => {
  if (tSec < hitSec || tSec > hitSec + durationSec) return null;
  const p = clampedRange(tSec, hitSec, hitSec + durationSec, 0, 1, EASE_GLIDE);
  const pad = p * Math.min(15, maxPad);
  const alpha = (1 - p) * 0.85;
  return (
    <rect
      x={x - pad}
      y={y - pad}
      width={width + pad * 2}
      height={height + pad * 2}
      fill="none"
      stroke={color}
      strokeWidth={strokeWidth}
      opacity={alpha}
    />
  );
};

// ---------------------------------------------------------------------------
// G1: Monument Metric / Giant Figure (纪念碑巨数/巨字)
// ---------------------------------------------------------------------------

export interface MonumentMetricProps {
  x: number;
  y: number;
  width: number;
  height: number;
  theme: StudioTheme;
  value: string;
  /** Optional unit or suffix displayed beside/beneath the monument figure at smaller Swiss scale. */
  unit?: string;
  kicker?: string;
  caption?: string;
  /** 0..1 reveal progress for main figure and baseline. */
  progress: number;
  /** 0..1 OKLab vermilion tint strength (pass `accentAt(tSec, emphasis).strength`). */
  accentStrength?: number;
  /** Portrait defaults to 'bottom' anchoring so graphics bond with the 54px subtitle and negative space consolidates above. */
  anchor?: 'bottom' | 'center';
  isPortrait?: boolean;
}

export const MonumentMetric: React.FC<MonumentMetricProps> = ({
  x,
  y,
  width,
  height,
  theme,
  value,
  unit,
  kicker,
  caption,
  progress,
  accentStrength = 0,
  anchor,
  isPortrait = height > width,
}) => {
  const cleanVal = normalizeDisplayMetric(value);
  const cleanUnit = unit ? panguSpace(unit) : '';
  const cleanKicker = kicker ? panguSpace(kicker) : '';
  const cleanCaption = caption ? panguSpace(caption) : '';

  const kickerSize = cleanKicker
    ? fitFontSize(cleanKicker, width, isPortrait ? 44 : 30, isPortrait ? 30 : 22)
    : isPortrait
      ? 44
      : 30;
  const captionSize = cleanCaption
    ? fitFontSize(cleanCaption, width, isPortrait ? 46 : 32, isPortrait ? 30 : 22)
    : isPortrait
      ? 46
      : 32;
  // v6: monumental Swiss scale — 320..460px on 1080px portrait canvas for massive visual contrast
  const valMax = isPortrait ? 460 : 280;
  const valMin = isPortrait ? 120 : 72;
  const valSize = fitFontSize(cleanVal, width * (cleanUnit ? 0.86 : 0.98), valMax, valMin, true);
  const unitSize = cleanUnit ? Math.max(40, Math.round(valSize * 0.16)) : 0;

  const kickerH = cleanKicker ? kickerSize * 1.45 : 0;
  const valH = valSize * 0.96;
  const ruleGap = isPortrait ? 44 : 30;
  const capH = cleanCaption ? captionSize * 1.45 : 0;
  const totalH = kickerH + valH + ruleGap + capH;
  const resolvedAnchor = anchor ?? (isPortrait ? 'bottom' : 'center');
  const topY =
    resolvedAnchor === 'bottom'
      ? bottomAnchorY(totalH, {top: y, height}, isPortrait ? 24 : 18)
      : y + Math.max(0, (height - totalH) * 0.46);

  const kickerP = clampedRange(progress, 0.0, 0.25, 0, 1, EASE_GLIDE);
  const valP = clampedRange(progress, 0.08, 0.56, 0, 1, EASE_SNAP);
  const ruleP = clampedRange(progress, 0.22, 0.7, 0, 1, EASE_GLIDE);
  const capP = clampedRange(progress, 0.35, 0.78, 0, 1, EASE_GLIDE);

  const valBaselineY = topY + kickerH + valSize * 0.84;
  const ruleY = topY + kickerH + valH + Math.round(ruleGap * 0.48);
  const capY = ruleY + Math.round(ruleGap * 0.52) + captionSize * 0.88;
  const valColor = mixHex(theme.ink, theme.accent, accentStrength);
  const ruleStrong = theme.ruleStrong ?? theme.ink;
  const approxValW = Math.min(width * 0.84, approxVisualUnits(cleanVal, true) * valSize * 0.98);

  return (
    <g>
      {cleanKicker && (
        <text
          x={x}
          y={topY + kickerSize * 0.85}
          fontFamily={STUDIO_FONTS.sans}
          fontSize={kickerSize}
          fontWeight={700}
          fill={theme.muted}
          opacity={kickerP}
          style={NO_SYNTH}
        >
          {cleanKicker}
        </text>
      )}
      <SvgWipe
        x={x - 10}
        y={topY + kickerH - 18}
        width={width + 20}
        height={valH + 40}
        progress={valP}
        direction="up"
      >
        <text
          x={x - Math.round(valSize * 0.03)}
          y={valBaselineY}
          fontFamily={STUDIO_FONTS.figure}
          fontSize={valSize}
          fontWeight={900}
          fill={valColor}
          letterSpacing="-0.035em"
          style={DISPLAY_NUM_STYLE}
        >
          {cleanVal}
        </text>
        {cleanUnit && (
          <text
            x={Math.min(x + width - 16, x + approxValW + 14)}
            y={valBaselineY - Math.round(valSize * 0.06)}
            fontFamily={STUDIO_FONTS.sans}
            fontSize={unitSize}
            fontWeight={800}
            fill={theme.inkSecondary ?? theme.ink}
            style={NO_SYNTH}
          >
            {cleanUnit}
          </text>
        )}
      </SvgWipe>
      <EditorialRule
        x1={x}
        y1={ruleY}
        x2={x + width}
        y2={ruleY}
        progress={ruleP}
        stroke={ruleStrong}
        strokeWidth={2.5}
      />
      {cleanCaption && (
        <text
          x={x}
          y={capY}
          fontFamily={STUDIO_FONTS.sans}
          fontSize={captionSize}
          fontWeight={700}
          fill={theme.inkSecondary ?? theme.ink}
          opacity={capP}
          style={NUM_STYLE}
        >
          {cleanCaption}
        </text>
      )}
    </g>
  );
};

// ---------------------------------------------------------------------------
// G2: Asymmetric Editorial Split 65:35 (非对称张力对切，禁止 50/50 双黑框)
// ---------------------------------------------------------------------------

export interface SplitPanelContent {
  tag?: string;
  value: string;
  caption?: string;
}

export interface AsymmetricSplitProps {
  x: number;
  y: number;
  width: number;
  height: number;
  theme: StudioTheme;
  primary: SplitPanelContent;
  secondary: SplitPanelContent;
  progress: number;
  /** Primary proportion clamped to [0.58, 0.72] (default 0.64, never symmetric 0.50). */
  ratio?: number;
  orientation?: 'horizontal' | 'vertical';
  /** 'primaryFirst' (default) reveals primary then secondary; 'secondaryFirst' reveals pain/baseline first then sweeps in primary solution. */
  revealOrder?: 'primaryFirst' | 'secondaryFirst';
  /** 0..1 OKLab highlight applied strictly to primary.value only. */
  accentStrength?: number;
}

export const AsymmetricSplit: React.FC<AsymmetricSplitProps> = ({
  x,
  y,
  width,
  height,
  theme,
  primary,
  secondary,
  progress,
  ratio = 0.64,
  orientation,
  revealOrder = 'primaryFirst',
  accentStrength = 0,
}) => {
  const isVert = orientation ? orientation === 'vertical' : height > width;
  const r = Math.max(0.58, Math.min(0.72, ratio));
  const gap = isVert ? 44 : 48;
  const padX = isVert ? 36 : 40;
  const padY = isVert ? 40 : 38;
  const tagBase = isVert ? 40 : 28;
  const capBase = isVert ? 40 : 30;
  const minVal = isVert ? 54 : 46;
  const paperDeep = theme.paperDeep ?? theme.paper;
  const ruleStrong = theme.ruleStrong ?? theme.ink;

  const pBox = isVert
    ? {x, y, w: width, h: Math.round((height - gap) * r)}
    : {x, y, w: Math.round((width - gap) * r), h: height};
  const sBox = isVert
    ? {x, y: y + pBox.h + gap, w: width, h: height - pBox.h - gap}
    : {x: x + pBox.w + gap, y, w: width - pBox.w - gap, h: height};

  const pInnerW = Math.max(120, pBox.w - padX * 2);
  const sPadX = isVert ? padX : 8;
  const sInnerW = Math.max(120, sBox.w - sPadX - 12);

  const pTagText = primary.tag ? panguSpace(primary.tag) : '';
  const pValText = normalizeDisplayMetric(primary.value);
  const pCapText = primary.caption ? panguSpace(primary.caption) : '';
  const sTagText = secondary.tag ? panguSpace(secondary.tag) : '';
  const sValText = normalizeDisplayMetric(secondary.value);
  const sCapText = secondary.caption ? panguSpace(secondary.caption) : '';

  const pTagSize = pTagText ? fitFontSize(pTagText, pInnerW, tagBase, isVert ? 28 : 22) : tagBase;
  const pValSize = fitFontSize(pValText, pInnerW, isVert ? 148 : 132, minVal);
  const pCapSize = pCapText ? fitFontSize(pCapText, pInnerW, capBase, isVert ? 28 : 22) : capBase;

  const sTagSize = sTagText ? fitFontSize(sTagText, sInnerW, tagBase, isVert ? 28 : 22) : tagBase;
  const sValSize = fitFontSize(sValText, sInnerW, isVert ? 92 : 84, isVert ? 42 : 36);
  const sCapSize = sCapText ? fitFontSize(sCapText, sInnerW, capBase, isVert ? 28 : 22) : capBase;

  const pReveal =
    revealOrder === 'secondaryFirst'
      ? clampedRange(progress, 0.42, 0.88, 0, 1, EASE_SNAP)
      : clampedRange(progress, 0.0, 0.45, 0, 1, EASE_SNAP);
  const sReveal =
    revealOrder === 'secondaryFirst'
      ? clampedRange(progress, 0.0, 0.36, 0, 1, EASE_GLIDE)
      : clampedRange(progress, 0.35, 0.78, 0, 1, EASE_GLIDE);
  const pValColor = mixHex(theme.ink, theme.accent, accentStrength);

  const layoutPanelStack = (
    box: {x: number; y: number; w: number; h: number},
    item: SplitPanelContent,
    tSize: number,
    vSize: number,
    cSize: number,
    padTopBot: number,
  ) => {
    const gap1 = item.tag ? Math.max(14, Math.round(tSize * 0.45)) : 0;
    const gap2 = item.caption ? Math.max(18, Math.round(cSize * 0.55)) : 0;
    const tagH = item.tag ? tSize : 0;
    const valH = Math.round(vSize * 1.02);
    const capH = item.caption ? cSize : 0;
    const stackH = tagH + gap1 + valH + gap2 + capH;
    const effPad = Math.min(padTopBot, Math.max(8, Math.floor((box.h - stackH) * 0.5)));
    const startY = box.y + Math.max(effPad, Math.round((box.h - stackH) * 0.48));
    const tagY = startY + tSize * 0.85;
    const valY = startY + tagH + gap1 + vSize * 0.88;
    const capY = startY + tagH + gap1 + valH + gap2 + cSize * 0.85;
    return {tagY, valY, capY};
  };

  const pStack = layoutPanelStack(pBox, primary, pTagSize, pValSize, pCapSize, padY);
  const sStack = layoutPanelStack(sBox, secondary, sTagSize, sValSize, sCapSize, Math.round(padY * 0.6));

  return (
    <g>
      <SvgWipe
        x={pBox.x}
        y={pBox.y}
        width={pBox.w}
        height={pBox.h}
        progress={pReveal}
        direction={isVert ? 'down' : 'right'}
      >
        <rect x={pBox.x} y={pBox.y} width={pBox.w} height={pBox.h} fill={paperDeep} />
        <line
          x1={pBox.x}
          y1={pBox.y + 1.5}
          x2={pBox.x + pBox.w}
          y2={pBox.y + 1.5}
          stroke={ruleStrong}
          strokeWidth={3}
        />
        {pTagText && (
          <text
            x={pBox.x + padX}
            y={pStack.tagY}
            fontFamily={STUDIO_FONTS.sans}
            fontSize={pTagSize}
            fontWeight={700}
            fill={theme.muted}
            style={NO_SYNTH}
          >
            {pTagText}
          </text>
        )}
        <text
          x={pBox.x + padX}
          y={pStack.valY}
          fontFamily={STUDIO_FONTS.figure}
          fontSize={pValSize}
          fontWeight={900}
          fill={pValColor}
          letterSpacing="-0.02em"
          style={DISPLAY_NUM_STYLE}
        >
          {pValText}
        </text>
        {pCapText && (
          <text
            x={pBox.x + padX}
            y={pStack.capY}
            fontFamily={STUDIO_FONTS.sans}
            fontSize={pCapSize}
            fontWeight={600}
            fill={theme.inkSecondary ?? theme.ink}
            style={NUM_STYLE}
          >
            {pCapText}
          </text>
        )}
      </SvgWipe>

      <g opacity={sReveal}>
        {sTagText && (
          <text
            x={sBox.x + sPadX}
            y={sStack.tagY}
            fontFamily={STUDIO_FONTS.sans}
            fontSize={sTagSize}
            fontWeight={600}
            fill={theme.muted}
            style={NO_SYNTH}
          >
            {sTagText}
          </text>
        )}
        <text
          x={sBox.x + sPadX}
          y={sStack.valY}
          fontFamily={STUDIO_FONTS.figure}
          fontSize={sValSize}
          fontWeight={800}
          fill={theme.muted}
          style={DISPLAY_NUM_STYLE}
        >
          {sValText}
        </text>
        {sCapText && (
          <text
            x={sBox.x + sPadX}
            y={sStack.capY}
            fontFamily={STUDIO_FONTS.sans}
            fontSize={sCapSize}
            fontWeight={500}
            fill={theme.faint ?? theme.muted}
            style={NUM_STYLE}
          >
            {sCapText}
          </text>
        )}
      </g>
    </g>
  );
};

// ---------------------------------------------------------------------------
// G3: Geometric Flow Router (几何拓扑流图 — 脉冲经闸门分流多轨)
// ---------------------------------------------------------------------------

export interface FlowBranch {
  label: string;
  detail?: string;
}

export interface FlowRouterProps {
  x: number;
  y: number;
  width: number;
  height: number;
  theme: StudioTheme;
  sourceLabel: string;
  gateLabel?: string;
  branches: FlowBranch[];
  /** Index of the active routed branch (0..N-1); pass -1 for neutral. */
  activeIndex?: number;
  progress: number;
  /** 0..1 OKLab tint applied ONLY to the active branch label (single red focus). */
  accentStrength?: number;
  orientation?: 'horizontal' | 'vertical';
}

export const FlowRouter: React.FC<FlowRouterProps> = ({
  x,
  y,
  width,
  height,
  theme,
  sourceLabel,
  gateLabel,
  branches,
  activeIndex = 0,
  progress,
  accentStrength = 0,
  orientation,
}) => {
  const safeBranches = branches.slice(0, 4);
  if (safeBranches.length === 0) return null;

  const isVert = orientation ? orientation === 'vertical' : height > width * 1.05;
  const count = safeBranches.length;
  const labelSize = isVert ? 42 : 30;
  const detailSize = isVert ? 40 : 28;
  const paperDeep = theme.paperDeep ?? theme.paper;
  const ruleStrong = theme.ruleStrong ?? theme.ink;
  const trackColor = theme.track ?? theme.rule;
  const activeColor = mixHex(theme.ink, theme.accent, accentStrength);

  const trunkP = clampedRange(progress, 0.0, 0.28, 0, 1, EASE_GLIDE);
  const gateP = clampedRange(progress, 0.18, 0.45, 0, 1, EASE_SNAP);
  const cleanSource = panguSpace(sourceLabel);
  // Render inactive branches first and active branch last so shared trunk segments never get overpainted by faint rails
  const orderedIndices = [
    ...safeBranches.map((_, i) => i).filter((i) => i !== activeIndex),
    ...(activeIndex >= 0 && activeIndex < count ? [activeIndex] : []),
  ];

  if (isVert) {
    const srcSize = fitFontSize(cleanSource, width, labelSize, 30);
    const approxSrcW = Math.min(width, approxVisualUnits(cleanSource) * srcSize * 1.04);
    const railX = x + Math.min(Math.round(width * 0.24), Math.max(28, Math.round(approxSrcW * 0.48)));
    const srcX = railX;
    const srcY = y + 64;
    const gateY = y + Math.round(height * 0.26);
    const branchTop = y + Math.round(height * 0.46);
    const branchSpan = Math.max(160, height - (branchTop - y) - 96);
    const stepY = count > 1 ? branchSpan / (count - 1) : 0;
    const gateR = 26;
    const labelX = Math.max(railX + 96, x + Math.round(width * 0.34));
    const gateTextMaxW = Math.max(160, x + width - (srcX + gateR + 28) - 8);
    const cleanGate = gateLabel ? panguSpace(gateLabel) : '';
    const gateFontSize = cleanGate ? fitFontSize(cleanGate, gateTextMaxW, labelSize, 28) : labelSize;
    const branchTextMaxW = Math.max(180, x + width - (labelX + 6) - 16);

    return (
      <g>
        <text
          x={x}
          y={srcY}
          fontFamily={STUDIO_FONTS.sans}
          fontSize={srcSize}
          fontWeight={700}
          fill={theme.ink}
          opacity={trunkP}
          style={NO_SYNTH}
        >
          {cleanSource}
        </text>

        <EditorialRule
          x1={srcX}
          y1={srcY + 24}
          x2={srcX}
          y2={gateY - gateR}
          progress={trunkP}
          stroke={ruleStrong}
          strokeWidth={3}
        />

        <g opacity={gateP}>
          <polygon
            points={`${srcX},${gateY - gateR} ${srcX + gateR},${gateY} ${srcX},${gateY + gateR} ${srcX - gateR},${gateY}`}
            fill={paperDeep}
            stroke={ruleStrong}
            strokeWidth={2.5}
          />
          {cleanGate && (
            <text
              x={srcX + gateR + 28}
              y={gateY + Math.round(gateFontSize * 0.34)}
              fontFamily={STUDIO_FONTS.sans}
              fontSize={gateFontSize}
              fontWeight={700}
              fill={theme.inkSecondary ?? theme.ink}
              style={NO_SYNTH}
            >
              {cleanGate}
            </text>
          )}
        </g>

        {orderedIndices.map((idx) => {
          const br = safeBranches[idx];
          const cleanLabel = panguSpace(br.label);
          const cleanDetail = br.detail ? panguSpace(br.detail) : '';
          const brLabelSize = fitFontSize(cleanLabel, branchTextMaxW, labelSize, 28);
          const brDetailSize = cleanDetail ? fitFontSize(cleanDetail, branchTextMaxW, detailSize, 26) : detailSize;
          const by = branchTop + idx * stepY;
          const isAct = idx === activeIndex;
          const bStart = 0.28 + idx * 0.08;
          const bEnd = Math.min(0.92, bStart + 0.34);
          const d = `M ${railX} ${gateY + gateR} L ${railX} ${by} L ${labelX - 24} ${by}`;
          const pathLen = Math.abs(by - (gateY + gateR)) + Math.abs(labelX - 24 - railX) + 8;
          const strokeAnim = drawStroke(progress, bStart, bEnd, pathLen);
          const textP = clampedRange(progress, bStart + 0.14, Math.min(1, bEnd + 0.08), 0, 1, EASE_GLIDE);

          return (
            <g key={idx}>
              <path
                d={d}
                fill="none"
                stroke={isAct ? ruleStrong : trackColor}
                strokeWidth={isAct ? 3.5 : 2}
                {...strokeAnim}
              />
              {isAct && textP > 0.05 && (
                <rect
                  x={labelX - 18}
                  y={by - brLabelSize * 0.95}
                  width={Math.max(120, x + width - (labelX - 18))}
                  height={cleanDetail ? brLabelSize * 1.45 + brDetailSize * 1.25 : brLabelSize * 1.55}
                  fill={paperDeep}
                  opacity={textP}
                />
              )}
              <circle
                cx={labelX - 24}
                cy={by}
                r={isAct ? 6 : 4}
                fill={isAct ? ruleStrong : theme.faint ?? theme.muted}
                opacity={textP}
              />
              <text
                x={labelX + 6}
                y={by + Math.round(brLabelSize * 0.32)}
                fontFamily={STUDIO_FONTS.sans}
                fontSize={brLabelSize}
                fontWeight={isAct ? 900 : 600}
                fill={isAct ? activeColor : theme.muted}
                opacity={textP}
                style={NUM_STYLE}
              >
                {cleanLabel}
              </text>
              {cleanDetail && (
                <text
                  x={labelX + 6}
                  y={by + Math.round(brLabelSize * 0.32) + brDetailSize * 1.28}
                  fontFamily={STUDIO_FONTS.sans}
                  fontSize={brDetailSize}
                  fontWeight={500}
                  fill={isAct ? theme.inkSecondary ?? theme.ink : theme.faint ?? theme.muted}
                  opacity={textP}
                  style={NUM_STYLE}
                >
                  {cleanDetail}
                </text>
              )}
            </g>
          );
        })}
      </g>
    );
  }

  // Landscape horizontal topology: source (left) -> diamond gate (center-left) -> fanned horizontal rails (right)
  const cy = y + Math.round(height * 0.5);
  const srcX = x;
  const gateX = x + Math.round(width * 0.34);
  const gateR = 22;
  const srcMaxW = Math.max(160, gateX - gateR - 56 - srcX);
  const srcFontSize = fitFontSize(cleanSource, srcMaxW, labelSize + 4, 22);
  const approxSrcEnd = srcX + Math.round(approxVisualUnits(cleanSource) * srcFontSize * 1.04);
  const trunkStartX = Math.min(gateX - gateR - 24, approxSrcEnd + 20);
  const elbowX = x + Math.round(width * 0.45);
  const targetX = x + Math.round(width * 0.55);
  const branchTextMaxW = Math.max(200, x + width - (targetX + 8) - 14);
  const cleanGate = gateLabel ? panguSpace(gateLabel) : '';
  const gateFontSize = cleanGate ? fitFontSize(cleanGate, Math.max(160, (elbowX - srcX) * 0.6), detailSize, 22) : detailSize;
  const topY = y + Math.round(height * 0.16);
  const spanY = Math.max(120, height * 0.68);
  const stepY = count > 1 ? spanY / (count - 1) : 0;

  return (
    <g>
      <text
        x={srcX}
        y={cy + Math.round(srcFontSize * 0.35)}
        fontFamily={STUDIO_FONTS.sans}
        fontSize={srcFontSize}
        fontWeight={700}
        fill={theme.ink}
        opacity={trunkP}
        style={NO_SYNTH}
      >
        {cleanSource}
      </text>

      <EditorialRule
        x1={trunkStartX}
        y1={cy}
        x2={gateX - gateR}
        y2={cy}
        progress={trunkP}
        stroke={ruleStrong}
        strokeWidth={3}
      />

      <g opacity={gateP}>
        <polygon
          points={`${gateX},${cy - gateR} ${gateX + gateR},${cy} ${gateX},${cy + gateR} ${gateX - gateR},${cy}`}
          fill={paperDeep}
          stroke={ruleStrong}
          strokeWidth={2.5}
        />
        {cleanGate && (
          <text
            x={gateX}
            y={cy - gateR - 18}
            textAnchor="middle"
            fontFamily={STUDIO_FONTS.sans}
            fontSize={gateFontSize}
            fontWeight={700}
            fill={theme.muted}
            style={NO_SYNTH}
          >
            {cleanGate}
          </text>
        )}
      </g>

      {orderedIndices.map((idx) => {
        const br = safeBranches[idx];
        const cleanLabel = panguSpace(br.label);
        const cleanDetail = br.detail ? panguSpace(br.detail) : '';
        const brLabelSize = fitFontSize(cleanLabel, branchTextMaxW, labelSize, 22);
        const brDetailSize = cleanDetail ? fitFontSize(cleanDetail, branchTextMaxW, detailSize, 20) : detailSize;
        const by = count > 1 ? topY + idx * stepY : cy;
        const isAct = idx === activeIndex;
        const bStart = 0.25 + idx * 0.08;
        const bEnd = Math.min(0.92, bStart + 0.34);
        const d = `M ${gateX + gateR} ${cy} L ${elbowX} ${cy} L ${elbowX} ${by} L ${targetX - 18} ${by}`;
        const pathLen = Math.abs(elbowX - (gateX + gateR)) + Math.abs(by - cy) + Math.abs(targetX - 18 - elbowX) + 8;
        const strokeAnim = drawStroke(progress, bStart, bEnd, pathLen);
        const textP = clampedRange(progress, bStart + 0.14, Math.min(1, bEnd + 0.08), 0, 1, EASE_GLIDE);

        return (
          <g key={idx}>
            <path
              d={d}
              fill="none"
              stroke={isAct ? ruleStrong : trackColor}
              strokeWidth={isAct ? 3.5 : 2}
              {...strokeAnim}
            />
            {isAct && textP > 0.05 && (
              <rect
                x={targetX - 14}
                y={by - brLabelSize * 0.95}
                width={Math.max(140, x + width - (targetX - 14))}
                height={cleanDetail ? brLabelSize * 1.4 + brDetailSize * 1.25 : brLabelSize * 1.5}
                fill={paperDeep}
                opacity={textP}
              />
            )}
            <circle
              cx={targetX - 18}
              cy={by}
              r={isAct ? 5.5 : 4}
              fill={isAct ? ruleStrong : theme.faint ?? theme.muted}
              opacity={textP}
            />
            <text
              x={targetX + 8}
              y={by + Math.round(brLabelSize * 0.32)}
              fontFamily={STUDIO_FONTS.sans}
              fontSize={brLabelSize}
              fontWeight={isAct ? 900 : 600}
              fill={isAct ? activeColor : theme.muted}
              opacity={textP}
              style={NUM_STYLE}
            >
              {cleanLabel}
            </text>
            {cleanDetail && (
              <text
                x={targetX + 8}
                y={by + Math.round(brLabelSize * 0.32) + brDetailSize * 1.25}
                fontFamily={STUDIO_FONTS.sans}
                fontSize={brDetailSize}
                fontWeight={500}
                fill={isAct ? theme.inkSecondary ?? theme.ink : theme.faint ?? theme.muted}
                opacity={textP}
                style={NUM_STYLE}
              >
                {cleanDetail}
              </text>
            )}
          </g>
        );
      })}
    </g>
  );
};

// ---------------------------------------------------------------------------
// G4: Swiss Bar Axis (瑞士精密数据轴 — 0 起点诚实比例对比，单红主角，竞品退灰)
// ---------------------------------------------------------------------------

export interface SwissBarDatum {
  label: string;
  value: number;
  valueText: string;
  isPrimary?: boolean;
}

export interface SwissBarAxisProps {
  x: number;
  y: number;
  width: number;
  height: number;
  theme: StudioTheme;
  items: SwissBarDatum[];
  tSec: number;
  /** Optional explicit upper domain (defaults to max item value; axis always starts at 0). */
  maxValue?: number;
  axisStartSec?: number;
  barsStartSec?: number;
  /** 0..1 OKLab tint applied ONLY to the single primary bar (never splits red focus). */
  accentStrength?: number;
  sourceNote?: string;
  isPortrait?: boolean;
}

export const SwissBarAxis: React.FC<SwissBarAxisProps> = ({
  x,
  y,
  width,
  height,
  theme,
  items,
  tSec,
  maxValue,
  axisStartSec = 0.05,
  barsStartSec = 0.32,
  accentStrength = 0,
  sourceNote,
  isPortrait = height > width,
}) => {
  if (items.length === 0) return null;

  const hasExplicitPrimary = items.some((it) => it.isPrimary);
  const maxItemVal = Math.max(0.0001, ...items.map((it) => Math.max(0, it.value)));
  const domainMax = Math.max(maxItemVal, maxValue ?? maxItemVal);
  const fallbackPrimaryIdx = items.reduce(
    (best, it, idx) => (it.value > items[best].value ? idx : best),
    0,
  );

  let labelSize = isPortrait ? 44 : 30;
  let valSize = isPortrait ? 52 : 34;
  const cleanNote = sourceNote ? panguSpace(sourceNote) : '';
  const noteSize = cleanNote
    ? fitFontSize(cleanNote, width, isPortrait ? 38 : 26, isPortrait ? 26 : 20)
    : isPortrait
      ? 38
      : 26;
  let barH = isPortrait ? 52 : 34;
  let rowGap = isPortrait ? 54 : 34;
  let labelBarGap = 16;
  const noteBlock = cleanNote ? noteSize + 28 : 0;
  const rawContentH = items.length * (labelSize + labelBarGap + barH + rowGap) - rowGap + noteBlock;
  if (rawContentH > height) {
    const availForRows = Math.max(items.length * 56, height - noteBlock);
    const perRow = (availForRows + 12) / items.length;
    labelSize = Math.max(isPortrait ? 32 : 24, Math.min(labelSize, Math.floor(perRow * 0.30)));
    valSize = Math.max(isPortrait ? 34 : 26, Math.min(valSize, Math.floor(perRow * 0.32)));
    barH = Math.max(18, Math.min(barH, Math.floor(perRow * 0.27)));
    labelBarGap = Math.max(6, Math.min(labelBarGap, Math.floor(perRow * 0.10)));
    rowGap = Math.max(12, Math.floor(perRow - labelSize - labelBarGap - barH));
  }
  const rowH = labelSize + labelBarGap + barH + rowGap;
  const contentH = items.length * rowH - rowGap + noteBlock;
  const topY = isPortrait
    ? bottomAnchorY(contentH, {top: y, height}, 28)
    : y + Math.max(0, (height - contentH) * 0.47);
  const firstBarY = topY + labelSize + labelBarGap;
  const axisBottomY = topY + items.length * rowH - rowGap + 10;

  const axisP = clampedRange(tSec, axisStartSec, axisStartSec + 0.34, 0, 1, EASE_GLIDE);
  const ruleStrong = theme.ruleStrong ?? theme.ink;
  const trackColor = theme.track ?? theme.rule;
  const faintColor = theme.faint ?? theme.muted;
  const primaryBarColor = mixHex(theme.ink, theme.accent, accentStrength);

  return (
    <g>
      {/* 50% and 100% subtle reference hairlines spanning the bar band */}
      {[0.5, 1.0].map((frac) => (
        <EditorialRule
          key={frac}
          x1={x + Math.round(width * frac)}
          y1={firstBarY - 6}
          x2={x + Math.round(width * frac)}
          y2={axisBottomY}
          progress={axisP}
          stroke={theme.rule}
          strokeWidth={1}
        />
      ))}

      {items.map((it, idx) => {
        const isPrimary = hasExplicitPrimary ? Boolean(it.isPrimary) : idx === fallbackPrimaryIdx;
        const cleanLabel = panguSpace(it.label);
        const cleanVal = panguSpace(it.valueText);
        const approxValW = approxVisualUnits(cleanVal) * valSize * 1.05;
        const maxLabelW = Math.max(140, width - approxValW - 28);
        const itemLabelSize = fitFontSize(cleanLabel, maxLabelW, labelSize, isPortrait ? 24 : 20);
        const rowY = topY + idx * rowH;
        const barY = rowY + labelSize + labelBarGap;
        const frac = Math.max(0, Math.min(1, Math.max(0, it.value) / domainMax));
        const p = staggerAt(tSec, idx, barsStartSec, 0.11, 0.46, EASE_GLIDE);
        const fillW = Math.round(width * frac * p);

        return (
          <g key={idx}>
            <text
              x={x}
              y={rowY + labelSize * 0.85}
              fontFamily={STUDIO_FONTS.sans}
              fontSize={itemLabelSize}
              fontWeight={isPrimary ? 700 : 500}
              fill={isPrimary ? theme.ink : theme.muted}
              opacity={axisP}
              style={NO_SYNTH}
            >
              {cleanLabel}
            </text>
            <text
              x={x + width}
              y={rowY + labelSize * 0.85}
              textAnchor="end"
              fontFamily={STUDIO_FONTS.figure}
              fontSize={valSize}
              fontWeight={isPrimary ? 900 : 700}
              fill={isPrimary ? theme.ink : theme.muted}
              opacity={clampedRange(p, 0.15, 0.85, 0, 1, EASE_GLIDE)}
              style={NUM_STYLE}
            >
              {cleanVal}
            </text>
            <rect x={x} y={barY} width={width} height={barH} fill={trackColor} opacity={axisP} />
            {fillW > 0 && (
              <rect
                x={x}
                y={barY}
                width={fillW}
                height={barH}
                fill={isPrimary ? primaryBarColor : faintColor}
              />
            )}
            {/* Crisp zero-origin baseline anchor on each bar track (keeps labels above clean & flush-left) */}
            <EditorialRule
              x1={x}
              y1={barY - 4}
              x2={x}
              y2={barY + barH + 4}
              progress={axisP}
              stroke={ruleStrong}
              strokeWidth={3}
            />
          </g>
        );
      })}

      {cleanNote && (
        <text
          x={x}
          y={axisBottomY + noteSize + 10}
          fontFamily={STUDIO_FONTS.sans}
          fontSize={noteSize}
          fontWeight={500}
          fill={theme.muted}
          opacity={axisP}
          style={NO_SYNTH}
        >
          {cleanNote}
        </text>
      )}
    </g>
  );
};

// ---------------------------------------------------------------------------
// G5: Editorial Strike & Paper-Wipe Reveal (划除旧认知 + 纸面掀幕揭示真相)
// ---------------------------------------------------------------------------

export interface EditorialStrikeRevealProps {
  x: number;
  y: number;
  width: number;
  height: number;
  theme: StudioTheme;
  mythLabel?: string;
  mythText: string;
  truthLabel?: string;
  truthText: string;
  truthSub?: string;
  /** 0..1 progress of ink strike line crossing out mythText. */
  strikeProgress: number;
  /** 0..1 progress of native SVG wipe revealing truth panel. */
  revealProgress: number;
  /** 0..1 OKLab highlight applied strictly to truthText (strike remains crisp ink -> single focus). */
  accentStrength?: number;
  isPortrait?: boolean;
}

export const EditorialStrikeReveal: React.FC<EditorialStrikeRevealProps> = ({
  x,
  y,
  width,
  height,
  theme,
  mythLabel,
  mythText,
  truthLabel,
  truthText,
  truthSub,
  strikeProgress,
  revealProgress,
  accentStrength = 1,
  isPortrait = height > width,
}) => {
  const cleanMythLabel = mythLabel ? panguSpace(mythLabel) : '';
  const cleanMyth = normalizeDisplayMetric(mythText);
  const cleanTruthLabel = truthLabel ? panguSpace(truthLabel) : '';
  const cleanTruth = normalizeDisplayMetric(truthText);
  const cleanTruthSub = truthSub ? panguSpace(truthSub) : '';

  const panelPad = isPortrait ? 38 : 34;
  const panelInnerW = Math.max(160, width - panelPad * 2);
  const labelBase = isPortrait ? 40 : 28;
  const mythLabelSize = cleanMythLabel ? fitFontSize(cleanMythLabel, width, labelBase, isPortrait ? 28 : 22) : labelBase;
  const truthLabelSize = cleanTruthLabel ? fitFontSize(cleanTruthLabel, panelInnerW, labelBase, isPortrait ? 28 : 22) : labelBase;
  const subSize = cleanTruthSub
    ? fitFontSize(cleanTruthSub, panelInnerW, isPortrait ? 42 : 30, isPortrait ? 26 : 20)
    : isPortrait
      ? 42
      : 30;
  const mythSize = fitFontSize(cleanMyth, width - 16, isPortrait ? 110 : 76, isPortrait ? 48 : 34);
  const truthSize = fitFontSize(cleanTruth, panelInnerW, isPortrait ? 156 : 96, isPortrait ? 56 : 38);

  const paperDeep = theme.paperDeep ?? theme.paper;
  const ruleStrong = theme.ruleStrong ?? theme.ink;
  const strikeP = Math.max(0, Math.min(1, strikeProgress));
  const mythColor = mixHex(theme.ink, theme.faint ?? theme.muted, strikeP * 0.85);
  const truthColor = mixHex(theme.ink, theme.accent, accentStrength);

  const mythBlockH = (cleanMythLabel ? mythLabelSize + 18 : 0) + mythSize * 1.25;
  const panelH =
    panelPad * 2 +
    (cleanTruthLabel ? truthLabelSize + 18 : 0) +
    truthSize * 1.15 +
    (cleanTruthSub ? subSize + 24 : 0);
  const gapY = isPortrait ? 72 : 44;
  const totalH = mythBlockH + gapY + panelH;
  const topY = isPortrait
    ? bottomAnchorY(totalH, {top: y, height}, 24)
    : y + Math.max(0, (height - totalH) * 0.46);

  const mythBaselineY = topY + (cleanMythLabel ? mythLabelSize + 18 : 0) + mythSize * 0.92;
  const strikeY = mythBaselineY - Math.round(mythSize * 0.34);
  const approxMythW = Math.min(width, approxVisualUnits(cleanMyth) * mythSize * 1.02);
  const strikeEndX = Math.min(x + width, x + approxMythW + 8);
  const panelY = topY + mythBlockH + gapY;

  return (
    <g>
      {cleanMythLabel && (
        <text
          x={x}
          y={topY + mythLabelSize * 0.85}
          fontFamily={STUDIO_FONTS.sans}
          fontSize={mythLabelSize}
          fontWeight={600}
          fill={theme.muted}
          style={NO_SYNTH}
        >
          {cleanMythLabel}
        </text>
      )}
      <text
        x={x}
        y={mythBaselineY}
        fontFamily={STUDIO_FONTS.sans}
        fontSize={mythSize}
        fontWeight={700}
        fill={mythColor}
        style={NUM_STYLE}
      >
        {cleanMyth}
      </text>
      <EditorialRule
        x1={x - 8}
        y1={strikeY}
        x2={strikeEndX}
        y2={strikeY}
        progress={strikeP}
        stroke={ruleStrong}
        strokeWidth={5}
      />

      <SvgWipe
        x={x}
        y={panelY}
        width={width}
        height={panelH}
        progress={revealProgress}
        direction="right"
      >
        <rect x={x} y={panelY} width={width} height={panelH} fill={paperDeep} />
        <line x1={x} y1={panelY + 1.5} x2={x + width} y2={panelY + 1.5} stroke={ruleStrong} strokeWidth={3} />
        {cleanTruthLabel && (
          <text
            x={x + panelPad}
            y={panelY + panelPad + truthLabelSize * 0.82}
            fontFamily={STUDIO_FONTS.sans}
            fontSize={truthLabelSize}
            fontWeight={700}
            fill={theme.muted}
            style={NO_SYNTH}
          >
            {cleanTruthLabel}
          </text>
        )}
        <text
          x={x + panelPad}
          y={panelY + panelPad + (cleanTruthLabel ? truthLabelSize + 18 : 0) + truthSize * 0.92}
          fontFamily={STUDIO_FONTS.sans}
          fontSize={truthSize}
          fontWeight={900}
          fill={truthColor}
          letterSpacing="-0.02em"
          style={truthSize >= 84 ? DISPLAY_NUM_STYLE : NUM_STYLE}
        >
          {cleanTruth}
        </text>
        {cleanTruthSub && (
          <text
            x={x + panelPad}
            y={panelY + panelH - panelPad - Math.round(subSize * 0.12)}
            fontFamily={STUDIO_FONTS.sans}
            fontSize={subSize}
            fontWeight={600}
            fill={theme.inkSecondary ?? theme.ink}
            style={NUM_STYLE}
          >
            {cleanTruthSub}
          </text>
        )}
      </SvgWipe>
    </g>
  );
};

// ---------------------------------------------------------------------------
// G6: Silent Epigraph / Breathing Room (极简空镜定音 — 高留白稳住节奏 CV)
// ---------------------------------------------------------------------------

export interface SilentEpigraphProps {
  x: number;
  y: number;
  width: number;
  height: number;
  theme: StudioTheme;
  /** 1 to 2 concise display lines (<= 12 chars each). */
  lines: string[];
  caption?: string;
  progress: number;
  /** Optional single line index to tint with vermilion (defaults to -1 = pure quiet ink). */
  accentLineIndex?: number;
  accentStrength?: number;
  /** Defaults to editorial serif locked at weight 500 (never faux-bold 800/900). */
  useSerif?: boolean;
  isPortrait?: boolean;
}

export const SilentEpigraph: React.FC<SilentEpigraphProps> = ({
  x,
  y,
  width,
  height,
  theme,
  lines,
  caption,
  progress,
  accentLineIndex = -1,
  accentStrength = 0,
  useSerif,
  isPortrait = height > width,
}) => {
  // v6: Mode C portrait unifies on Heavy Grotesk; Mode A/B landscape keeps serif.
  const resolvedUseSerif = useSerif ?? !isPortrait;
  const cleanLines = lines.slice(0, 2).map((ln) => panguSpace(ln.trim())).filter(Boolean);
  if (cleanLines.length === 0) return null;

  const cleanCaption = caption ? panguSpace(caption) : '';
  const maxLine = cleanLines.reduce((a, b) => (approxVisualUnits(b) > approxVisualUnits(a) ? b : a), cleanLines[0]);
  const fontSize = fitFontSize(maxLine, width * 0.94, isPortrait ? 112 : 76, isPortrait ? 48 : 34);
  const lineH = Math.round(fontSize * 1.38);
  const capSize = cleanCaption
    ? fitFontSize(cleanCaption, width, isPortrait ? 42 : 28, isPortrait ? 28 : 20)
    : isPortrait
      ? 42
      : 28;
  const totalH = 28 + cleanLines.length * lineH + (cleanCaption ? capSize + 40 : 0);
  const topY = isPortrait
    ? bottomAnchorY(totalH, {top: y, height}, 36)
    : y + Math.max(0, (height - totalH) * 0.48);

  const ruleP = clampedRange(progress, 0.0, 0.35, 0, 1, EASE_GLIDE);
  const textP = clampedRange(progress, 0.14, 0.65, 0, 1, EASE_GLIDE);
  const capP = clampedRange(progress, 0.45, 0.85, 0, 1, EASE_GLIDE);
  const ruleStrong = theme.ruleStrong ?? theme.ink;

  return (
    <g>
      <EditorialRule
        x1={x}
        y1={topY}
        x2={x + 84}
        y2={topY}
        progress={ruleP}
        stroke={ruleStrong}
        strokeWidth={2.5}
      />
      <SvgWipe
        x={x - 6}
        y={topY + 14}
        width={width + 12}
        height={cleanLines.length * lineH + 24}
        progress={textP}
        direction="up"
      >
        {cleanLines.map((ln, idx) => {
          const fill =
            idx === accentLineIndex ? mixHex(theme.ink, theme.accent, accentStrength) : theme.ink;
          if (resolvedUseSerif) {
            return (
              <MixedSerifText
                key={idx}
                x={x}
                y={topY + 34 + idx * lineH + fontSize * 0.85}
                text={ln}
                fontSize={fontSize}
                fontWeight={500}
                fill={fill}
                cjkLetterSpacing="0.04em"
              />
            );
          }
          return (
            <text
              key={idx}
              x={x}
              y={topY + 34 + idx * lineH + fontSize * 0.85}
              fontFamily={STUDIO_FONTS.displayC}
              fontSize={fontSize}
              fontWeight={900}
              fill={fill}
              letterSpacing="-0.02em"
              style={NUM_STYLE}
            >
              {ln}
            </text>
          );
        })}
      </SvgWipe>
      {cleanCaption && (
        <text
          x={x}
          y={topY + 34 + cleanLines.length * lineH + capSize + 18}
          fontFamily={STUDIO_FONTS.sans}
          fontSize={capSize}
          fontWeight={500}
          fill={theme.muted}
          opacity={capP}
          style={NO_SYNTH}
        >
          {cleanCaption}
        </text>
      )}
    </g>
  );
};

// ---------------------------------------------------------------------------
// v6 Mixed-Script Zero-Drift Serif Text (Mode A/B: Latin runs locked to letter-spacing: 0)
// ---------------------------------------------------------------------------

export interface MixedSerifTextProps {
  x: number;
  y: number;
  text: string;
  fontSize: number;
  fontWeight?: number;
  fill: string;
  cjkLetterSpacing?: string;
  textAnchor?: 'start' | 'middle' | 'end';
  opacity?: number;
}

export const MixedSerifText: React.FC<MixedSerifTextProps> = ({
  x,
  y,
  text,
  fontSize,
  fontWeight = 500,
  fill,
  cjkLetterSpacing = '0.03em',
  textAnchor = 'start',
  opacity = 1,
}) => {
  const runs = splitLatinRuns(text);
  return (
    <text
      x={x}
      y={y}
      textAnchor={textAnchor}
      fontFamily={STUDIO_FONTS.serifMixed}
      fontSize={fontSize}
      fontWeight={fontWeight}
      fill={fill}
      opacity={opacity}
      style={NUM_STYLE}
    >
      {runs.map((r, i) => (
        <tspan
          key={i}
          fontFamily={r.isLatin ? STUDIO_FONTS.latinSerif : STUDIO_FONTS.serifMixed}
          letterSpacing={r.isLatin ? '0' : cjkLetterSpacing}
        >
          {r.text}
        </tspan>
      ))}
    </text>
  );
};

// ---------------------------------------------------------------------------
// v6 Mode C Series Signature: Editorial Vermilion Square Seal Stamp (朱砂方印)
// Compact chop seal (never a wide App CTA button), decisive EASE_WHIP stamp-down.
// ---------------------------------------------------------------------------

export interface EditorialSealStampProps {
  /** Center X of the square seal. */
  cx: number;
  /** Center Y of the square seal. */
  cy: number;
  /** 2 or 4 concise Chinese chars (e.g. "开源", "核验", "实盘", "回本"). */
  text: string;
  tSec: number;
  hitSec: number;
  theme: StudioTheme;
  /** Square side length in px (clamped 58..92px so it stays unmistakably a chop seal, never a red button). */
  size?: number;
  /** 'yang' = vermilion frame + red ink text on paper (default, zero solid red slab); 'yin' = compact solid square chop. */
  variant?: 'yang' | 'yin';
  /** Subtle authentic hand-stamped tilt in degrees (default -3.5). */
  angleDeg?: number;
}

export const EditorialSealStamp: React.FC<EditorialSealStampProps> = ({
  cx,
  cy,
  text,
  tSec,
  hitSec,
  theme,
  size = 82,
  variant = 'yang',
  angleDeg = -3.5,
}) => {
  if (tSec < hitSec - 0.01) return null;
  const s = Math.max(58, Math.min(92, size));
  const dur = 0.16;
  const p = clampedRange(tSec, hitSec, hitSec + dur, 0, 1, EASE_WHIP);
  const scale = 1.44 - 0.44 * p;
  const alpha = clampedRange(tSec, hitSec, hitSec + 0.07, 0, 1, EASE_GLIDE);
  const chars = Array.from(text.trim()).slice(0, 4);
  const isTwo = chars.length <= 2;
  const fg = variant === 'yin' ? theme.accentInk ?? theme.paper : theme.accent;
  const bgFill = variant === 'yin' ? theme.accent : theme.bg;
  const half = s / 2;
  const fontSz = isTwo ? Math.round(s * 0.37) : Math.round(s * 0.34);

  return (
    <g
      transform={`translate(${cx}, ${cy}) rotate(${angleDeg}) scale(${scale.toFixed(4)})`}
      opacity={alpha}
    >
      <rect
        x={-half}
        y={-half}
        width={s}
        height={s}
        fill={bgFill}
        stroke={theme.accent}
        strokeWidth={variant === 'yin' ? 0 : 3}
      />
      {variant === 'yang' && (
        <rect
          x={-half + 5}
          y={-half + 5}
          width={s - 10}
          height={s - 10}
          fill="none"
          stroke={theme.accent}
          strokeWidth={1}
          opacity={0.55}
        />
      )}
      {isTwo ? (
        chars.map((ch, i) => (
          <text
            key={i}
            x={0}
            y={chars.length === 1 ? fontSz * 0.36 : i === 0 ? -s * 0.08 : s * 0.33}
            textAnchor="middle"
            fontFamily={STUDIO_FONTS.sans}
            fontSize={fontSz}
            fontWeight={900}
            fill={fg}
            style={NO_SYNTH}
          >
            {ch}
          </text>
        ))
      ) : (
        /* 2x2 traditional chop layout (right column top->bottom, left column top->bottom) */
        [
          {ch: chars[0], dx: s * 0.19, dy: -s * 0.07},
          {ch: chars[1], dx: s * 0.19, dy: s * 0.31},
          {ch: chars[2], dx: -s * 0.19, dy: -s * 0.07},
          {ch: chars[3], dx: -s * 0.19, dy: s * 0.31},
        ].map(
          (slot, i) =>
            slot.ch && (
              <text
                key={i}
                x={slot.dx}
                y={slot.dy}
                textAnchor="middle"
                fontFamily={STUDIO_FONTS.sans}
                fontSize={fontSz}
                fontWeight={900}
                fill={fg}
                style={NO_SYNTH}
              >
                {slot.ch}
              </text>
            ),
        )
      )}
    </g>
  );
};

// ---------------------------------------------------------------------------
// v6 Paper-Native Command Line & Keycaps (Zero Black Terminal Cards!)
// ---------------------------------------------------------------------------

export interface PaperCommandItem {
  command: string;
  /** Optional prompt prefix (defaults to '$' for cursor/underline shell lines; pass '' for chat commands). */
  prompt?: string;
  label?: string;
  note?: string;
}

export interface PaperCommandLineProps {
  x: number;
  y: number;
  width: number;
  theme: StudioTheme;
  items: PaperCommandItem[];
  tSec: number;
  startSec?: number;
  /** 'cursor' = monospace directly on paper + vermilion block cursor; 'underline' = vermilion hairline rule; 'keycap' = crisp ink-outlined rectangular keycap. */
  variant?: 'cursor' | 'underline' | 'keycap';
  /** Index of the active command highlighted with vermilion cursor/underline/text (-1 for neutral). */
  activeIndex?: number;
  accentStrength?: number;
  isPortrait?: boolean;
}

export const PaperCommandLine: React.FC<PaperCommandLineProps> = ({
  x,
  y,
  width,
  theme,
  items,
  tSec,
  startSec = 0.15,
  variant = 'cursor',
  activeIndex = 0,
  accentStrength = 1,
  isPortrait = true,
}) => {
  if (items.length === 0) return null;
  const ruleStrong = theme.ruleStrong ?? theme.ink;
  const activeColor = mixHex(theme.ink, theme.accent, accentStrength);
  const rowPitch = variant === 'keycap' ? (isPortrait ? 136 : 96) : (isPortrait ? 156 : 108);

  return (
    <g>
      {items.map((item, idx) => {
        const p = staggerAt(tSec, idx, startSec, 0.18, 0.45, EASE_SNAP);
        const ry = y + idx * rowPitch;
        const isAct = idx === activeIndex;
        const cleanLabel = item.label ? panguSpace(item.label) : '';
        const cleanNote = item.note ? panguSpace(item.note) : '';
        const cmdText = item.command.trim();

        if (variant === 'keycap') {
          const capFont = fitFontSize(cmdText, width * 0.46, isPortrait ? 44 : 32, isPortrait ? 32 : 24);
          const capW = Math.min(width * 0.48, Math.max(180, Math.round(approxVisualUnits(cmdText) * capFont * 1.12 + 44)));
          const capH = Math.round(capFont * 1.72);
          const noteX = x + capW + 28;
          const noteMaxW = Math.max(180, width - capW - 32);
          const noteFont = cleanNote ? fitFontSize(cleanNote, noteMaxW, isPortrait ? 42 : 30, isPortrait ? 30 : 22) : 40;

          return (
            <SvgWipe key={idx} x={x - 6} y={ry - 8} width={width + 12} height={capH + 20} progress={p} direction="right">
              <rect
                x={x}
                y={ry}
                width={capW}
                height={capH}
                fill={theme.paper}
                stroke={isAct ? activeColor : ruleStrong}
                strokeWidth={isAct ? 2.5 : 1.5}
              />
              {/* Subtle tactile bottom keycap edge hairline (no black shadow block) */}
              <line
                x1={x}
                y1={ry + capH + 3}
                x2={x + capW}
                y2={ry + capH + 3}
                stroke={isAct ? activeColor : theme.rule}
                strokeWidth={2}
              />
              <text
                x={x + 22}
                y={ry + Math.round(capH * 0.67)}
                fontFamily={STUDIO_FONTS.mono}
                fontSize={capFont}
                fontWeight={700}
                fill={isAct ? activeColor : theme.ink}
                style={NO_SYNTH}
              >
                {cmdText}
              </text>
              {cleanNote && (
                <text
                  x={noteX}
                  y={ry + Math.round(capH * 0.67)}
                  fontFamily={STUDIO_FONTS.sans}
                  fontSize={noteFont}
                  fontWeight={isAct ? 700 : 500}
                  fill={isAct ? theme.ink : theme.muted}
                  style={NO_SYNTH}
                >
                  {cleanNote}
                </text>
              )}
            </SvgWipe>
          );
        }

        // 'cursor' or 'underline' variant: raw monospace printed cleanly on warm paper (strictly within `width`, auto-wraps long CLI lines)
        const promptGlyph = item.prompt !== undefined ? item.prompt : '$';
        const hasPrompt = promptGlyph.length > 0;
        const rawLines = cmdText.includes('\n')
          ? cmdText.split('\n').map((s) => s.trim()).filter(Boolean)
          : [cmdText];
        // Monospace glyphs are ~0.64em wide (wider than proportional 0.56em); fit strictly inside width with 28px cursor clearance
        const monoUnits = (s: string) =>
          Array.from(s).reduce((acc, ch) => acc + (ch.charCodeAt(0) <= 0x7f ? 0.64 : 1.02), 0);
        const maxLineMonoU = Math.max(1, ...rawLines.map((ln) => monoUnits(ln)));
        const availCmdW = Math.max(160, width - (hasPrompt ? 48 : 8) - (variant === 'cursor' ? 28 : 8));
        const cmdFont = Math.round(
          Math.max(isPortrait ? 32 : 22, Math.min(isPortrait ? 46 : 32, availCmdW / (maxLineMonoU * 1.02))),
        );
        const promptOffset = hasPrompt ? Math.round(cmdFont * 0.88) : 0;
        const labelFont = isPortrait ? 40 : 26;
        const cmdLineH = Math.round(cmdFont * 1.38);
        const firstCmdY = ry + (cleanLabel ? labelFont + 24 : 0) + cmdFont;
        const lastCmdY = firstCmdY + (rawLines.length - 1) * cmdLineH;
        const lastLineW = Math.min(availCmdW - 12, Math.round(monoUnits(rawLines[rawLines.length - 1]) * cmdFont));
        const blink = Math.sin(tSec * Math.PI * 3.2) > -0.25 ? 1 : 0.25;

        return (
          <g key={idx}>
            {cleanLabel && (
              <text
                x={x}
                y={ry + labelFont * 0.85}
                fontFamily={STUDIO_FONTS.sans}
                fontSize={labelFont}
                fontWeight={700}
                fill={theme.muted}
                opacity={p}
                style={NO_SYNTH}
              >
                {cleanLabel}
              </text>
            )}
            <SvgWipe
              x={x - 6}
              y={firstCmdY - cmdFont - 8}
              width={width + 12}
              height={rawLines.length * cmdLineH + 28}
              progress={p}
              direction="right"
            >
              {hasPrompt && (
                <text
                  x={x}
                  y={firstCmdY}
                  fontFamily={STUDIO_FONTS.mono}
                  fontSize={cmdFont}
                  fontWeight={700}
                  fill={theme.muted}
                  style={NO_SYNTH}
                >
                  {promptGlyph}
                </text>
              )}
              {rawLines.map((ln, li) => (
                <text
                  key={li}
                  x={x + promptOffset}
                  y={firstCmdY + li * cmdLineH}
                  fontFamily={STUDIO_FONTS.mono}
                  fontSize={cmdFont}
                  fontWeight={700}
                  fill={theme.ink}
                  style={NO_SYNTH}
                >
                  {ln}
                </text>
              ))}
              {variant === 'cursor' && isAct && (
                <rect
                  x={Math.min(x + width - 16, x + promptOffset + lastLineW + 10)}
                  y={lastCmdY - Math.round(cmdFont * 0.82)}
                  width={Math.max(10, Math.round(cmdFont * 0.26))}
                  height={Math.round(cmdFont * 0.96)}
                  fill={activeColor}
                  opacity={blink}
                />
              )}
            </SvgWipe>
            <EditorialRule
              x1={x}
              y1={lastCmdY + 18}
              x2={x + width}
              y2={lastCmdY + 18}
              progress={p}
              stroke={variant === 'underline' && isAct ? activeColor : theme.rule}
              strokeWidth={variant === 'underline' && isAct ? 3 : 1.5}
            />
            {cleanNote && (
              <text
                x={x}
                y={lastCmdY + 18 + (isPortrait ? 44 : 30)}
                fontFamily={STUDIO_FONTS.sans}
                fontSize={isPortrait ? 40 : 26}
                fontWeight={500}
                fill={theme.muted}
                opacity={p}
                style={NO_SYNTH}
              >
                {cleanNote}
              </text>
            )}
          </g>
        );
      })}
    </g>
  );
};

// ---------------------------------------------------------------------------
// v6 Single-Canvas Camera Stage (整幕/整章一张画布推拉推移)
// ---------------------------------------------------------------------------

export interface SingleCanvasActProps {
  tSec: number;
  keys: CameraKey[];
  width: number;
  height: number;
  children: React.ReactNode;
}

export const SingleCanvasAct: React.FC<SingleCanvasActProps> = ({
  tSec,
  keys,
  width,
  height,
  children,
}) => {
  const vb = cameraAt(tSec, keys, width, height);
  return (
    <svg x={0} y={0} width={width} height={height} viewBox={vb} overflow="visible">
      {children}
    </svg>
  );
};
