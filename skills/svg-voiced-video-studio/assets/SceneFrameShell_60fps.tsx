import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {
  accentAt,
  clampedRange,
  EASE_IN_OUT,
  EASE_OUT_EXPO,
  EmphasisWindow,
  getSceneLifecycle,
  mixHex,
  panguSpace,
} from './motion_60fps';

export type {EmphasisWindow};

export interface StudioTheme {
  bg: string;
  paper: string;
  /** Subtle recessed tonal surface (replaces heavy black slabs on light paper themes). */
  paperDeep?: string;
  ink: string;
  /** Secondary body ink step for comfortable visual hierarchy. */
  inkSecondary?: string;
  muted: string;
  /** Low-emphasis comparison ink (retreated competitor bars / inactive labels). */
  faint?: string;
  /** Structural track / progress bar rail neutral. */
  track?: string;
  rule: string;
  /** Structural 1.5-2px axis/divider ink. */
  ruleStrong?: string;
  accent: string;
  /** Deeper vermilion hitting >= 4.5:1 WCAG AA if small red text is ever needed. */
  accentText?: string;
  /** Delicate tinted highlight wash (<= 10% opacity, never triggers a second red blob). */
  accentSoft?: string;
  /** High-contrast foreground text placed atop compact accent seal stamps. */
  accentInk?: string;
  subtitleBg?: string;
}

export const DARK_NIGHT_THEME: StudioTheme = {
  bg: '#111110',
  paper: '#181816',
  paperDeep: '#1F1F1C',
  ink: '#F2EFE9',
  inkSecondary: '#D6D2C8',
  /** WCAG AA compliant on #111110 (~6.08:1; old 0.32 alpha was only 2.66:1). */
  muted: 'rgba(242, 239, 233, 0.58)',
  faint: 'rgba(242, 239, 233, 0.30)',
  track: 'rgba(242, 239, 233, 0.14)',
  rule: 'rgba(242, 239, 233, 0.18)',
  ruleStrong: 'rgba(242, 239, 233, 0.42)',
  accent: '#D94E28',
  accentText: '#E86A45',
  accentSoft: 'rgba(217, 78, 40, 0.14)',
  accentInk: '#F2EFE9',
};

export const ARCHIVAL_VELLUM_THEME: StudioTheme = {
  bg: '#F5F0E6',
  paper: '#FAF7F1',
  paperDeep: '#ECE5D8',
  ink: '#191715',
  inkSecondary: '#3D3933',
  muted: '#6E665B',
  faint: '#A89F91',
  track: '#DFD7C8',
  rule: 'rgba(25, 23, 21, 0.16)',
  ruleStrong: '#191715',
  accent: '#C83E2B',
  accentText: '#B83321',
  accentSoft: 'rgba(200, 62, 43, 0.08)',
  accentInk: '#FAF7F1',
  subtitleBg: 'rgba(245, 240, 230, 0.92)',
};

export const EDITORIAL_PAPER_THEME: StudioTheme = {
  bg: '#F5F1EA',
  paper: '#FAF8F3',
  paperDeep: '#ECE7DD',
  ink: '#1A1A18',
  inkSecondary: '#3A3833',
  muted: '#6B665E',
  faint: '#A6A094',
  track: '#DDD7CA',
  rule: 'rgba(26, 26, 24, 0.16)',
  ruleStrong: '#1A1A18',
  accent: '#D93B22',
  accentText: '#C9351E',
  accentSoft: 'rgba(217, 59, 34, 0.08)',
  accentInk: '#FAF8F3',
  subtitleBg: 'transparent',
};

/**
 * Cross-platform editorial font stacks (v6).
 * - Mode C (commercial portrait): unified Heavy Grotesk (`sans` / `displayC`) across BOTH cover and video.
 * - Mode A/B (philosophy essays): unified serif (`serifMixed` / `displayAB`) with matched Latin serif first
 *   (Source Serif 4 / Cambria / Times New Roman) and `letter-spacing: 0` on Latin runs via `splitLatinRuns()`.
 */
export const STUDIO_FONTS = {
  serif: "'Noto Serif SC', 'Source Han Serif SC', 'Source Han Serif CN', 'Songti SC', 'STZhongsong', 'STSong', serif",
  serifMixed:
    "'Source Serif 4', 'Newsreader', 'Cambria', 'Times New Roman', 'Noto Serif SC', 'Source Han Serif SC', 'Source Han Serif CN', 'Songti SC', 'STZhongsong', 'STSong', serif",
  latinSerif: "'Source Serif 4', 'Newsreader', 'Cambria', 'Times New Roman', serif",
  sans: "'Source Han Sans CN', 'Noto Sans SC', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei UI', sans-serif",
  displayC: "'Source Han Sans CN', 'Noto Sans SC', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei UI', sans-serif",
  displayAB:
    "'Source Serif 4', 'Newsreader', 'Cambria', 'Times New Roman', 'Noto Serif SC', 'Source Han Serif SC', 'Source Han Serif CN', 'Songti SC', 'STZhongsong', 'STSong', serif",
  figure:
    "'Bahnschrift', 'DIN Alternate', 'Helvetica Neue', 'Segoe UI', 'Source Han Sans CN', 'Noto Sans SC', sans-serif",
  mono: "'JetBrains Mono', 'IBM Plex Mono', 'SF Mono', Consolas, ui-monospace, 'Source Han Sans CN', 'Noto Sans SC', monospace",
} as const;

export interface ShellLineWindow {
  index: number;
  text: string;
  startSec: number;
  endSec: number;
  audioSrc?: string;
}

export interface ShellTimeline {
  id: string;
  chapterLabel: string;
  sceneTitle: string;
  audioSrc?: string;
  durationInFrames: number;
  lineWindows: ShellLineWindow[];
  emphasis?: EmphasisWindow[];
}

export interface ScenesDataItem {
  id: string;
  chapterLabel: string;
  sceneTitle: string;
  fps: number;
  durationInFrames: number;
  startSec: number;
  audioSrc?: string;
  lines: {index: number; text: string; startSec: number; endSec: number; emphasis?: EmphasisWindow[]}[];
}

export const toShellTimeline = (s: ScenesDataItem): ShellTimeline => ({
  id: s.id,
  chapterLabel: s.chapterLabel,
  sceneTitle: s.sceneTitle,
  audioSrc: s.audioSrc,
  durationInFrames: s.durationInFrames,
  lineWindows: s.lines.map((l) => ({index: l.index, text: l.text, startSec: l.startSec, endSec: l.endSec})),
  emphasis: s.lines.flatMap((l) => l.emphasis ?? []),
});

export interface ShellMasthead {
  title: string;
  sceneIndex: number;
  totalScenes: number;
  /** Optional full-film progress bar data; omit to show single-scene progress. */
  allScenes?: {id: string; startSec: number; durationInFrames: number; fps: number}[];
  globalSec?: number;
}

export interface ShellChapterProgress {
  /** 1-based current chapter index (e.g. 3). */
  current: number;
  /** Total chapters in the film (e.g. 6). */
  total: number;
  /** Concise Chinese chapter label (e.g. "对比 Codex"); falls back to parsed timeline.chapterLabel. */
  title?: string;
}

export interface ShellFooter {
  leftTop?: string;
  leftBottom?: string;
  /** Platform compliance 3-line small print (e.g., data source / scope / disclaimer). */
  disclaimerLines?: string[];
  /**
   * Portrait placement: 'bottom' (default, quiet floor bottom=44) or 'underSubtitle'
   * (lifts 3-line compliance print beneath the subtitle rail).
   */
  position?: 'bottom' | 'underSubtitle';
}

export interface SceneRenderProps {
  progress: number;
  tSec: number;
  frame: number;
  durationInFrames: number;
  fps: number;
  breath: number;
  enterFactor: number;
  exitFactor: number;
  safe: {left: number; top: number; right: number; bottom: number; width: number; height: number};
  emphasis: EmphasisWindow[];
  theme: StudioTheme;
}

interface SceneFrameShellProps {
  timeline: ShellTimeline;
  theme?: StudioTheme;
  safeMarginX?: number;
  safeMarginY?: number;
  hideBottomSubtitle?: boolean;
  hideChapterHeader?: boolean;
  playSceneAudio?: boolean;
  paperGrain?: boolean;
  /** Portrait defaults to left-aligned Swiss rail; landscape defaults to centered cinema subtitle. */
  subtitleAlign?: 'auto' | 'left' | 'center';
  /** Keep SVG layer opacity at 1 across boundaries so cross-scene match-cut spines & pans never blink. */
  disableMasterFade?: boolean;
  /** Highlight the currently spoken *keyword* in vermilion directly inside the subtitle rail (default true). */
  subtitleHighlightAccent?: boolean;
  /** Concise Chinese top chapter progress (e.g. "03 / 06  对比 Codex"), replacing decorative English mastheads. */
  chapterProgress?: ShellChapterProgress;
  /** Optional extra episode-specific disyllabic words protected from mid-word subtitle breaks. */
  extraProtectedBigrams?: string[];
  /** Legacy optional masthead (OFF by default in v6; prefer `chapterProgress`). */
  masthead?: ShellMasthead;
  /** Optional bottom compliance 3-line disclaimer (omit leftTop/leftBottom in Mode C to stay noise-free). */
  footer?: ShellFooter;
  children: (props: SceneRenderProps) => React.ReactNode;
}

const SAFE_DEFAULTS = {
  landscape: {
    left: 136,
    right: 136,
    top: 68,
    headerSize: 24,
    subtitleBottom: 64,
    subtitleSize: 34,
    wrapUnits: 24,
    graphicsTop: 148,
    graphicsBottomGap: 232,
  },
  /**
   * Portrait 9:16 (1080x1920) v6 calibrated for ultra-clean Swiss editorial grouping:
   * - Clean pure-paper margins on left (left=72) and top (NO top progress bar / chapter strip, clearing top 200px UI)
   * - Graphics safe band: y=266..1330 (height=1064) -> graphics bottom-anchor right above subtitle (gap <= 72px)
   * - Subtitle rail: 54px large legible pure-text type at bottom=412 (y ~ 1352..1508, clears bottom 400px platform chrome)
   * - Right margin=140px clears right-edge like/comment/share icon column (all content strictly x <= 940)
   */
  portrait: {
    left: 72,
    right: 140,
    top: 204,
    headerSize: 30,
    subtitleBottom: 412,
    subtitleSize: 54,
    wrapUnits: 12.6,
    graphicsTop: 266,
    graphicsBottomGap: 590,
  },
};

function visualUnits(s: string): number {
  let u = 0;
  for (const ch of s) {
    const code = ch.charCodeAt(0);
    if (code <= 0x7f) {
      u += ch === ' ' ? 0.32 : 0.56;
    } else if (code === 0x2009 || code === 0x200a) {
      u += 0.16;
    } else {
      u += 1.0;
    }
  }
  return u;
}

/**
 * Split utterances into crisp phrase cards:
 * 1. ALWAYS split on major sentence/clause stops (。！？；：) so two sentences never share a card.
 * 2. Also split on commas (，) whenever merging would exceed maxMergeUnits (tuned for 54px portrait readability).
 */
function expandSubWindows(lineWindows: ShellLineWindow[], isPortrait: boolean): ShellLineWindow[] {
  if (!isPortrait) return lineWindows;
  const maxMergeUnits = 16.5;
  const out: ShellLineWindow[] = [];

  for (const w of lineWindows) {
    const clean = w.text.trim().replace(/[，。、；：]+$/g, '');
    const rawParts = clean.split(/(?<=[，。！？；：])/g).map((p) => p.trim()).filter(Boolean);
    if (rawParts.length <= 1) {
      out.push({...w, text: clean});
      continue;
    }

    const groups: string[] = [];
    let cur = '';
    for (const p of rawParts) {
      const prevHardStop = /[。！？；：]$/.test(cur);
      if (!cur) {
        cur = p;
      } else if (!prevHardStop && visualUnits(cur + p) <= maxMergeUnits) {
        cur += p;
      } else {
        groups.push(cur.replace(/[，。、；：]+$/g, ''));
        cur = p;
      }
    }
    if (cur) groups.push(cur.replace(/[，。、；：]+$/g, ''));

    const totalU = groups.reduce((s, g) => s + Math.max(1, visualUnits(g)), 0);
    const dur = Math.max(0.2, w.endSec - w.startSec);
    let accU = 0;
    groups.forEach((g, idx) => {
      const u = Math.max(1, visualUnits(g));
      const s0 = w.startSec + (accU / totalU) * dur;
      accU += u;
      const s1 = idx === groups.length - 1 ? w.endSec : w.startSec + (accU / totalU) * dur;
      out.push({
        index: w.index * 100 + idx,
        text: g,
        startSec: s0,
        endSec: s1,
      });
    });
  }
  return out;
}

const GOOD_BREAK_AFTER = new Set(['的', '了', '着', '把', '被', '到', '在', '和', '与', '或', '而', '但', '等', '就', '才']);
const NO_BREAK_BEFORE = new Set(['号', '日', '月', '年', '天', '分', '秒', '倍', '成', '个', '位', '档', '次', '单', '折', '万', '亿', '%']);
const PROTECTED_BIGRAMS = new Set([
  '十一', '十二', '十九', '二十', '三十', '百分', '之一', '之十', '百万', '千万',
  '时候', '因为', '所以', '但是', '不过', '如果', '已经', '其实', '真正', '完全',
  '直接', '自动', '默认', '平时', '日常', '复杂', '核心', '关键', '重要', '实际',
  '时间', '成本', '费用', '价格', '收入', '利润', '数据', '评测', '结果', '原因',
  '问题', '办法', '工具', '系统', '模型', '代码', '任务', '效率', '差距', '选择',
  '免费', '开源', '官方', '公开', '具体', '准确', '简单', '清楚', '明显', '彻底',
  '指令', '路由', '智能', '调用', '开启', '会员', '功能', '方案', '细节', '末尾',
  '输入', '输出', '手动', '实现', '报错', '到底', '跑到', '生效', '回本', '安装',
  '运行', '发送', '识别', '验证', '推演', '追问', '项目', '终端', '仓库', '聊天',
]);

function splitBalancedTwoLines(
  text: string,
  maxLineUnits: number,
  extraProtected?: Set<string>,
): string[] {
  const clean = text.trim();
  if (visualUnits(clean) <= maxLineUnits) return [clean];

  const totalU = visualUnits(clean);
  const halfU = totalU / 2;
  let bestIdx = -1;
  let bestScore = Infinity;
  let acc = 0;

  for (let i = 0; i < clean.length - 2; i++) {
    acc += visualUnits(clean[i]);
    const rem = totalU - acc;
    if (acc < 3.0 || rem < 3.0) continue;

    const ch = clean[i];
    const nextCh = clean[i + 1];
    const bigram = ch + nextCh;
    const isPunct = '，。；：、？！ '.includes(ch);
    const isAsciiBoundary =
      (ch.charCodeAt(0) <= 0x7f && nextCh.charCodeAt(0) > 0x7f) ||
      (ch.charCodeAt(0) > 0x7f && nextCh.charCodeAt(0) <= 0x7f);
    const isAsciiMidWord = ch.charCodeAt(0) <= 0x7f && nextCh.charCodeAt(0) <= 0x7f && ch !== ' ' && nextCh !== ' ';

    let penalty = 4.0;
    if (isPunct) {
      penalty = 0.0;
    } else if (
      isAsciiMidWord ||
      PROTECTED_BIGRAMS.has(bigram) ||
      (extraProtected && extraProtected.has(bigram)) ||
      NO_BREAK_BEFORE.has(nextCh)
    ) {
      penalty = 25.0;
    } else if (isAsciiBoundary || GOOD_BREAK_AFTER.has(ch)) {
      penalty = 1.2;
    }

    const score = Math.abs(acc - halfU) + penalty;
    if (score < bestScore) {
      bestScore = score;
      bestIdx = i + 1;
    }
  }

  if (bestIdx !== -1) {
    const l1 = clean.slice(0, bestIdx).trim().replace(/[，。、；：]+$/g, '');
    const l2 = clean.slice(bestIdx).trim();
    return [l1, l2];
  }
  const cut = Math.ceil(clean.length / 2);
  return [clean.slice(0, cut), clean.slice(cut)];
}

/** Render one subtitle line, smoothly tinting the active spoken *keyword* into vermilion via OKLab. */
function renderHighlightedSubtitleLine(
  line: string,
  targetWord: string | null,
  strength: number,
  inkColor: string,
  accentColor: string,
): React.ReactNode {
  if (!targetWord || strength <= 0.02) {
    return line;
  }
  const cleanWord = targetWord.trim();
  if (!cleanWord) return line;

  // Build flexible matcher ignoring optical thin spaces / spaces inside mixed keywords
  const escapedChars = Array.from(cleanWord.replace(/[\s\u2009\u200a]+/g, '')).map((c) =>
    c.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'),
  );
  if (escapedChars.length === 0) return line;
  const pat = new RegExp(escapedChars.join('[\\s\\u2009\\u200a]*'), 'i');
  const m = pat.exec(line);
  if (!m) return line;

  const before = line.slice(0, m.index);
  const hit = m[0];
  const after = line.slice(m.index + hit.length);
  const hitColor = mixHex(inkColor, accentColor, strength);

  return (
    <>
      {before}
      <span style={{color: hitColor, fontWeight: 800}}>{hit}</span>
      {after}
    </>
  );
}

function isLightHex(hex: string): boolean {
  const clean = hex.trim().replace(/^#/, '');
  const full =
    clean.length === 3
      ? clean
          .split('')
          .map((c) => c + c)
          .join('')
      : clean.slice(0, 6);
  if (full.length !== 6) return true;
  const r = (parseInt(full.slice(0, 2), 16) || 0) / 255;
  const g = (parseInt(full.slice(2, 4), 16) || 0) / 255;
  const b = (parseInt(full.slice(4, 6), 16) || 0) / 255;
  const lin = (c: number) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b) > 0.45;
}

export const PaperGrain: React.FC<{opacity?: number; seed?: number; dark?: boolean}> = ({
  opacity = 0.032,
  seed = 7,
  dark = false,
}) => {
  const uid = React.useId().replace(/[^a-zA-Z0-9_-]/g, '');
  const filterId = `paper-grain-${seed}-${uid}`;
  return (
    <svg
      width="100%"
      height="100%"
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        opacity,
        mixBlendMode: dark ? 'screen' : 'multiply',
      }}
    >
      <filter id={filterId}>
        <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves={2} seed={seed} stitchTiles="stitch" />
        <feColorMatrix type="saturate" values="0" />
      </filter>
      <rect width="100%" height="100%" filter={`url(#${filterId})`} />
    </svg>
  );
};

const FONTS = STUDIO_FONTS;

export const SceneFrameShell: React.FC<SceneFrameShellProps> = ({
  timeline,
  theme = ARCHIVAL_VELLUM_THEME,
  safeMarginX,
  safeMarginY,
  hideBottomSubtitle = false,
  hideChapterHeader,
  playSceneAudio = false,
  paperGrain = false,
  subtitleAlign = 'auto',
  disableMasterFade = false,
  subtitleHighlightAccent = true,
  chapterProgress,
  extraProtectedBigrams,
  masthead,
  footer,
  children,
}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const {durationInFrames, lineWindows} = timeline;
  const isPortrait = height > width;
  const resolvedHideChapterHeader = hideChapterHeader ?? isPortrait;
  const sd = isPortrait ? SAFE_DEFAULTS.portrait : SAFE_DEFAULTS.landscape;
  const marginLeft = safeMarginX ?? sd.left;
  const marginRight = safeMarginX ?? sd.right;
  const defaultHeaderTop = !isPortrait && masthead ? 84 : sd.top;
  const marginTop = safeMarginY ?? defaultHeaderTop;
  const headerShift = Math.max(0, marginTop - sd.top);
  const effectiveGraphicsTop = sd.graphicsTop + headerShift;
  const landscapeLeftLines = (footer?.leftTop ? 1 : 0) + (footer?.leftBottom ? 1 : 0);
  const landscapeFooterInnerW = Math.max(400, width - marginLeft - marginRight);
  const landscapeLeftEstPx = Math.min(
    landscapeFooterInnerW * 0.44,
    Math.max(
      footer?.leftTop ? visualUnits(panguSpace(footer.leftTop)) * 14 * 1.08 : 0,
      footer?.leftBottom ? visualUnits(panguSpace(footer.leftBottom)) * 14 * 1.08 : 0,
    ),
  );
  const landscapeRightAvailPx = Math.max(
    360,
    landscapeFooterInnerW - (landscapeLeftEstPx > 0 ? landscapeLeftEstPx + 40 : 0),
  );
  const landscapeRightLines = (footer?.disclaimerLines ?? []).reduce(
    (sum, line) => sum + Math.max(1, Math.ceil((visualUnits(panguSpace(line)) * 14.4) / landscapeRightAvailPx)),
    0,
  );
  const landscapeLeftHeight =
    landscapeLeftLines > 0 ? landscapeLeftLines * 20 + (landscapeLeftLines > 1 ? 4 : 0) : 0;
  const landscapeRightHeight = landscapeRightLines * 20;
  const landscapeFooterHeight =
    !isPortrait && footer ? 11 + Math.max(landscapeLeftHeight, landscapeRightHeight, 20) : 0;
  const effectiveSubBottom =
    !isPortrait && footer
      ? Math.max(sd.subtitleBottom, 22 + landscapeFooterHeight + 26)
      : sd.subtitleBottom;
  const effectiveGraphicsBottomGap =
    !isPortrait && footer
      ? Math.max(sd.graphicsBottomGap, effectiveSubBottom + 144)
      : sd.graphicsBottomGap;
  const safe = {
    left: marginLeft,
    top: effectiveGraphicsTop,
    right: width - marginRight,
    bottom: height - effectiveGraphicsBottomGap,
    width: width - marginLeft - marginRight,
    height: height - effectiveGraphicsBottomGap - effectiveGraphicsTop,
  };

  const {progress, tSec, enterFactor, exitFactor, masterOpacity, breath} = getSceneLifecycle(
    frame,
    durationInFrames,
    fps,
  );

  const headerOpacity = disableMasterFade ? 1 : clampedRange(tSec, 0, 0.32, 0, 1, EASE_OUT_EXPO) * exitFactor;
  const headerRulePct = disableMasterFade ? 100 : clampedRange(tSec, 0.03, 0.45, 0, 100, EASE_OUT_EXPO) * exitFactor;

  const [parsedNum, parsedTitle] = timeline.chapterLabel.includes('/')
    ? timeline.chapterLabel.split('/').map((s) => s.trim())
    : ['', timeline.chapterLabel];

  const displayChapNum = chapterProgress
    ? `${String(chapterProgress.current).padStart(2, '0')} / ${String(chapterProgress.total).padStart(2, '0')}`
    : parsedNum;
  const displayChapTitle = chapterProgress?.title ?? parsedTitle;

  const subWindows = expandSubWindows(lineWindows, isPortrait);
  const activeLine = subWindows.find(
    (w, i) =>
      tSec >= w.startSec - 0.03 &&
      tSec < (i < subWindows.length - 1 && subWindows[i + 1].startSec - w.endSec < 0.08 ? subWindows[i + 1].startSec - 0.03 : w.endSec + 0.24),
  );

  let subOpacity = 0;
  let subTranslateY = 0;
  if (activeLine) {
    const localInFrames = Math.max(0, (tSec - (activeLine.startSec - 0.03)) * fps);
    const inSpring = spring({
      frame: localInFrames,
      fps,
      config: {damping: 26, stiffness: 220, overshootClamping: true},
    });
    const outFade = clampedRange(
      tSec,
      activeLine.endSec + 0.02,
      activeLine.endSec + 0.24,
      1,
      0,
      EASE_IN_OUT,
    );
    subOpacity = Math.min(1, inSpring) * outFade * (disableMasterFade ? 1 : exitFactor);
    subTranslateY = (1 - inSpring) * 8;
  }

  const activeEmphasis = subtitleHighlightAccent
    ? accentAt(tSec, timeline.emphasis ?? [])
    : {word: null, index: -1, strength: 0};

  const extraSet = extraProtectedBigrams ? new Set(extraProtectedBigrams) : undefined;
  const wrappedLines = activeLine
    ? splitBalancedTwoLines(activeLine.text, sd.wrapUnits, extraSet).map((ln) => panguSpace(ln))
    : [];
  const longestUnits = wrappedLines.reduce((m, l) => Math.max(m, visualUnits(l)), 0);
  const resolvedSubAlign: 'left' | 'center' =
    subtitleAlign === 'auto' ? (isPortrait ? 'left' : 'center') : subtitleAlign;
  const subRight = marginRight;
  const hasSubBg = Boolean(theme.subtitleBg && theme.subtitleBg !== 'transparent');
  const availSubWidth = width - marginLeft - subRight - (hasSubBg ? 44 : 8);
  const minPortraitSub = 46;
  const computedSubSize =
    longestUnits > 0
      ? Math.min(sd.subtitleSize, Math.max(isPortrait ? minPortraitSub : 26, Math.floor(availSubWidth / (longestUnits * 1.03))))
      : sd.subtitleSize;

  const trackColor = theme.track ?? theme.rule;
  const ruleStrongColor = theme.ruleStrong ?? theme.ink;
  const isLightTheme = isLightHex(theme.bg);
  const liftFooterUnderSub = isPortrait && footer?.position === 'underSubtitle';
  const hasFooterLeft = Boolean(footer?.leftTop || footer?.leftBottom);

  return (
    <AbsoluteFill style={{backgroundColor: theme.bg}}>
      {masthead && (
        <div
          style={{
            position: 'absolute',
            top: isPortrait ? 82 : 22,
            left: marginLeft,
            right: marginRight,
            pointerEvents: 'none',
          }}
        >
          <div style={{display: 'flex', gap: 6, marginBottom: 12}}>
            {masthead.allScenes && masthead.allScenes.length > 0 ? (
              masthead.allScenes.map((s) => {
                const endSec = s.startSec + s.durationInFrames / s.fps;
                const p = clampedRange(masthead.globalSec ?? tSec, s.startSec, endSec, 0, 100, (x) => x);
                return (
                  <div key={s.id} style={{flex: 1, height: 3, backgroundColor: trackColor}}>
                    <div style={{width: `${p}%`, height: '100%', backgroundColor: ruleStrongColor}} />
                  </div>
                );
              })
            ) : (
              Array.from({length: Math.max(1, masthead.totalScenes)}).map((_, idx) => {
                const p = idx < masthead.sceneIndex ? 100 : idx === masthead.sceneIndex ? progress * 100 : 0;
                return (
                  <div key={idx} style={{flex: 1, height: 3, backgroundColor: trackColor}}>
                    <div style={{width: `${p}%`, height: '100%', backgroundColor: ruleStrongColor}} />
                  </div>
                );
              })
            )}
          </div>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              fontFamily: FONTS.sans,
              fontSize: isPortrait ? 24 : 16,
              letterSpacing: '0.04em',
              color: theme.muted,
              fontVariantNumeric: 'lining-nums tabular-nums',
            }}
          >
            <span style={{color: theme.ink, fontWeight: 700}}>{panguSpace(masthead.title)}</span>
            <span>
              <strong style={{color: theme.ink}}>{String(masthead.sceneIndex + 1).padStart(2, '0')}</strong> /{' '}
              {String(masthead.totalScenes).padStart(2, '0')}
            </span>
          </div>
        </div>
      )}

      {!resolvedHideChapterHeader && (
        <div
          style={{
            position: 'absolute',
            left: marginLeft,
            right: marginRight,
            top: marginTop,
            opacity: headerOpacity,
            pointerEvents: 'none',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: 16,
              paddingBottom: 10,
            }}
          >
            {displayChapNum && (
              <span
                style={{
                  fontFamily: FONTS.figure,
                  fontSize: Math.round(sd.headerSize * 0.96),
                  fontWeight: 800,
                  letterSpacing: '0.06em',
                  color: theme.muted,
                  fontVariantNumeric: 'lining-nums tabular-nums',
                }}
              >
                {displayChapNum}
              </span>
            )}
            <span
              style={{
                fontFamily: isPortrait ? FONTS.displayC : FONTS.displayAB,
                fontSize: sd.headerSize,
                fontWeight: isPortrait ? 800 : 500,
                fontSynthesisWeight: 'none',
                letterSpacing: isPortrait ? '0.02em' : '0.06em',
                color: theme.ink,
              }}
            >
              {panguSpace(displayChapTitle)}
            </span>
          </div>
          <div style={{width: `${headerRulePct}%`, height: 1, backgroundColor: theme.rule}} />
        </div>
      )}

      {paperGrain && <PaperGrain opacity={isLightTheme ? 0.032 : 0.026} dark={!isLightTheme} />}

      <svg
        viewBox={`0 0 ${width} ${height}`}
        width={width}
        height={height}
        style={{
          position: 'absolute',
          inset: 0,
          opacity: disableMasterFade ? 1 : masterOpacity,
          fontSynthesisWeight: 'none',
        }}
      >
        {children({
          progress,
          tSec,
          frame,
          durationInFrames,
          fps,
          breath,
          enterFactor,
          exitFactor,
          safe,
          emphasis: timeline.emphasis ?? [],
          theme,
        })}
      </svg>

      {!hideBottomSubtitle && activeLine && (
        <div
          style={{
            position: 'absolute',
            left: marginLeft,
            right: subRight,
            bottom: effectiveSubBottom,
            display: 'flex',
            flexDirection: 'column',
            alignItems: resolvedSubAlign === 'left' ? 'flex-start' : 'center',
            opacity: subOpacity,
            transform: `translateY(${subTranslateY}px)`,
            pointerEvents: 'none',
          }}
        >
          <div
            style={{
              backgroundColor: theme.subtitleBg ?? 'transparent',
              padding:
                resolvedSubAlign === 'left'
                  ? hasSubBg
                    ? '10px 22px'
                    : '6px 0'
                  : hasSubBg
                    ? '10px 26px'
                    : '0',
              display: 'flex',
              flexDirection: 'column',
              alignItems: resolvedSubAlign === 'left' ? 'flex-start' : 'center',
            }}
          >
            {wrappedLines.map((ln, idx) => (
              <div
                key={idx}
                style={{
                  fontFamily: FONTS.sans,
                  fontSize: computedSubSize,
                  fontWeight: 700,
                  lineHeight: 1.32,
                  color: theme.ink,
                  textAlign: resolvedSubAlign,
                  whiteSpace: 'nowrap',
                  letterSpacing: '0.01em',
                  fontVariantNumeric: 'lining-nums tabular-nums',
                }}
              >
                {renderHighlightedSubtitleLine(ln, activeEmphasis.word, activeEmphasis.strength, theme.ink, theme.accent)}
              </div>
            ))}
          </div>
        </div>
      )}

      {footer && (
        <div
          style={{
            position: 'absolute',
            left: marginLeft,
            right: liftFooterUnderSub ? marginRight : isPortrait ? 72 : marginRight,
            ...(liftFooterUnderSub
              ? {top: height - effectiveSubBottom + 28}
              : {bottom: isPortrait ? 44 : 22}),
            paddingTop: 10,
            borderTop: hasFooterLeft || !isPortrait ? `1px solid ${theme.rule}` : undefined,
            display: 'flex',
            justifyContent: hasFooterLeft ? 'space-between' : 'flex-end',
            alignItems: 'flex-end',
            gap: isPortrait ? 20 : 36,
            pointerEvents: 'none',
          }}
        >
          {hasFooterLeft && (
            <div
              style={{
                fontFamily: FONTS.sans,
                fontSize: isPortrait ? 18 : 14,
                color: theme.muted,
                letterSpacing: '0.04em',
                flexShrink: 0,
                maxWidth: '44%',
              }}
            >
              {footer.leftTop && <div style={{color: theme.ink, fontWeight: 700}}>{panguSpace(footer.leftTop)}</div>}
              {footer.leftBottom && <div style={{marginTop: 4}}>{panguSpace(footer.leftBottom)}</div>}
            </div>
          )}
          {footer.disclaimerLines && footer.disclaimerLines.length > 0 && (
            <div
              style={{
                textAlign: 'right',
                fontFamily: FONTS.sans,
                fontSize: isPortrait ? 19 : 14,
                lineHeight: 1.4,
                color: theme.muted,
                minWidth: 0,
              }}
            >
              {footer.disclaimerLines.map((line, i) => (
                <div key={i}>{panguSpace(line)}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {playSceneAudio && timeline.audioSrc && <Audio src={staticFile(timeline.audioSrc)} volume={1} />}

      {playSceneAudio &&
        lineWindows.map((w) =>
          w.audioSrc ? (
            <Sequence key={w.index} from={Math.round(w.startSec * fps)}>
              <Audio src={staticFile(w.audioSrc)} volume={1} />
            </Sequence>
          ) : null,
        )}
    </AbsoluteFill>
  );
};
