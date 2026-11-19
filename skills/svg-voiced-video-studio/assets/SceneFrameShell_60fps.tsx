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
  clampedRange,
  EASE_IN_OUT,
  EASE_OUT_EXPO,
  EmphasisWindow,
  getSceneLifecycle,
} from './motion_60fps';

export type {EmphasisWindow};

export interface StudioTheme {
  bg: string;
  paper: string;
  ink: string;
  muted: string;
  rule: string;
  accent: string;
  subtitleBg?: string;
}

export const DARK_NIGHT_THEME: StudioTheme = {
  bg: '#111110',
  paper: '#181816',
  ink: '#F2EFE9',
  muted: 'rgba(242, 239, 233, 0.32)',
  rule: 'rgba(242, 239, 233, 0.22)',
  accent: '#D94E28',
};

export const ARCHIVAL_VELLUM_THEME: StudioTheme = {
  bg: '#F5F0E6',
  paper: '#FAF7F1',
  ink: '#191715',
  muted: '#6E665B',
  rule: 'rgba(25, 23, 21, 0.16)',
  accent: '#C83E2B',
  subtitleBg: 'rgba(245, 240, 230, 0.92)',
};

export const EDITORIAL_PAPER_THEME: StudioTheme = {
  bg: '#F5F1EA',
  paper: '#FAF8F3',
  ink: '#1A1A18',
  muted: '#6B665E',
  rule: 'rgba(26, 26, 24, 0.16)',
  accent: '#D93B22',
  subtitleBg: 'rgba(245, 241, 234, 0.94)',
};

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

export interface SceneRenderProps {
  progress: number;
  tSec: number;
  frame: number;
  durationInFrames: number;
  fps: number;
  breath: number;
  exitFactor: number;
  safe: {left: number; top: number; right: number; bottom: number; width: number; height: number};
  emphasis: EmphasisWindow[];
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
  children: (props: SceneRenderProps) => React.ReactNode;
}

const SAFE_DEFAULTS = {
  landscape: {left: 136, right: 136, top: 72, headerSize: 28, subtitleBottom: 68, subtitleSize: 34, wrapUnits: 24, graphicsTop: 155, graphicsBottomGap: 240},
  portrait: {left: 72, right: 140, top: 196, headerSize: 40, subtitleBottom: 340, subtitleSize: 44, wrapUnits: 15.5, graphicsTop: 292, graphicsBottomGap: 608},
};

function visualUnits(s: string): number {
  let u = 0;
  for (const ch of s) {
    if (ch.charCodeAt(0) <= 0x7f) {
      u += ch === ' ' ? 0.32 : 0.56;
    } else {
      u += 1.0;
    }
  }
  return u;
}

/**
 * Split utterances into clean phrase cards:
 * 1. ALWAYS split on major sentence/clause stops (。！？；：) so two sentences never share a card.
 * 2. Also split on commas (，) whenever merging would exceed ~19 visual units.
 */
function expandSubWindows(lineWindows: ShellLineWindow[], isPortrait: boolean): ShellLineWindow[] {
  if (!isPortrait) return lineWindows;
  const maxMergeUnits = 19.0;
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

// Natural Chinese phrase-break prefixes/suffixes so disyllabic words & date/unit suffixes are never cut in half
const GOOD_BREAK_AFTER = new Set(['的', '了', '着', '把', '被', '到', '在', '和', '与', '或', '而', '但', '等', '高', '号']);
const NO_BREAK_BEFORE = new Set(['号', '日', '月', '年', '天', '分', '秒', '倍', '成', '个', '位', '档', '次', '单', '折', '%']);
const PROTECTED_BIGRAMS = new Set([
  '十一', '十二', '三十', '二十', '八千', '三百', '百分', '之十', '四四',
  '更是', '冲上', '拿到', '追平', '都在', '首发', '开满', '狂吐', '留心', '时候',
  '恢复', '复杂', '读表', '表格', '代码', '模型', '旗舰', '思考', '档位', '默认',
  '程度', '调高', '平时', '均摊', '每单', '智能', '总榜', '评测', '使用', '工程',
  '日常', '划算', '优惠', '优势', '涨回', '正式', '生效',
  '美金', '原价', '五折', '单价', '接口', '刺客', '开销', '准确', '概率',
  '瞎编', '缓存', '费用', '输入', '输出', '口诀', '羊毛', '开源', '财报',
  '图表', '物理', '计算', '权威', '机构', '任务', '时间', '每秒', '飙出',
]);

/** Word-boundary-aware balanced 1-to-2 line splitter with zero mid-word cuts */
function splitBalancedTwoLines(text: string, maxLineUnits: number): string[] {
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
    if (acc < 3.5 || rem < 3.5) continue;

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
    } else if (isAsciiMidWord || PROTECTED_BIGRAMS.has(bigram) || NO_BREAK_BEFORE.has(nextCh)) {
      penalty = 25.0; // Never slice inside protected disyllabic words, ASCII words, or before unit/date suffixes!
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

export const PaperGrain: React.FC<{opacity?: number; seed?: number}> = ({opacity = 0.035, seed = 7}) => (
  <svg width="100%" height="100%" style={{position: 'absolute', inset: 0, pointerEvents: 'none', opacity, mixBlendMode: 'multiply'}}>
    <filter id={`paper-grain-${seed}`}>
      <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves={2} seed={seed} stitchTiles="stitch" />
      <feColorMatrix type="saturate" values="0" />
    </filter>
    <rect width="100%" height="100%" filter={`url(#paper-grain-${seed})`} />
  </svg>
);

const FONTS = {
  serif: "'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', 'STSong', 'SimSun', serif",
  sans: "'Noto Sans SC', 'Source Han Sans SC', 'PingFang SC', 'Microsoft YaHei UI', sans-serif",
  mono: "Consolas, 'SF Mono', ui-monospace, monospace",
};

export const SceneFrameShell: React.FC<SceneFrameShellProps> = ({
  timeline,
  theme = ARCHIVAL_VELLUM_THEME,
  safeMarginX,
  safeMarginY,
  hideBottomSubtitle = false,
  hideChapterHeader = false,
  playSceneAudio = false,
  paperGrain = false,
  children,
}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const {durationInFrames, lineWindows} = timeline;
  const isPortrait = height > width;
  const sd = isPortrait ? SAFE_DEFAULTS.portrait : SAFE_DEFAULTS.landscape;
  const marginLeft = safeMarginX ?? sd.left;
  const marginRight = safeMarginX ?? sd.right;
  const marginTop = safeMarginY ?? sd.top;
  const safe = {
    left: marginLeft,
    top: sd.graphicsTop,
    right: width - marginRight,
    bottom: height - sd.graphicsBottomGap,
    width: width - marginLeft - marginRight,
    height: height - sd.graphicsBottomGap - sd.graphicsTop,
  };

  const {progress, tSec, exitFactor, masterOpacity, breath} = getSceneLifecycle(
    frame,
    durationInFrames,
    fps,
  );

  const headerOpacity = clampedRange(tSec, 0, 0.45, 0, 1, EASE_OUT_EXPO) * exitFactor;
  const headerRulePct = clampedRange(tSec, 0.03, 0.65, 0, 100, EASE_OUT_EXPO) * exitFactor;

  const [chapNum, chapTitle] = timeline.chapterLabel.includes('/')
    ? timeline.chapterLabel.split('/').map((s) => s.trim())
    : ['', timeline.chapterLabel];

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
      config: {damping: 26, stiffness: 210, overshootClamping: true},
    });
    const outFade = clampedRange(
      tSec,
      activeLine.endSec + 0.02,
      activeLine.endSec + 0.24,
      1,
      0,
      EASE_IN_OUT,
    );
    subOpacity = Math.min(1, inSpring) * outFade * exitFactor;
    subTranslateY = (1 - inSpring) * 8;
  }

  const wrappedLines = activeLine ? splitBalancedTwoLines(activeLine.text, sd.wrapUnits) : [];
  const longestUnits = wrappedLines.reduce((m, l) => Math.max(m, visualUnits(l)), 0);
  const availSubWidth = width - marginLeft - 72 - 56;
  const computedSubSize =
    longestUnits > 0
      ? Math.min(sd.subtitleSize, Math.max(34, Math.floor(availSubWidth / (longestUnits * 1.05))))
      : sd.subtitleSize;

  return (
    <AbsoluteFill style={{backgroundColor: theme.bg}}>
      {!hideChapterHeader && (
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
              paddingBottom: 12,
            }}
          >
            {chapNum && (
              <span
                style={{
                  fontFamily: FONTS.mono,
                  fontSize: sd.headerSize,
                  letterSpacing: '0.1em',
                  color: theme.muted,
                  fontVariantNumeric: 'lining-nums tabular-nums',
                }}
              >
                {chapNum}
              </span>
            )}
            <span
              style={{
                fontFamily: FONTS.serif,
                fontSize: sd.headerSize,
                fontWeight: 600,
                letterSpacing: '0.06em',
                color: theme.ink,
              }}
            >
              {chapTitle}
            </span>
          </div>
          <div style={{width: `${headerRulePct}%`, height: 1, backgroundColor: theme.rule}} />
        </div>
      )}

      {paperGrain && <PaperGrain opacity={theme.bg.toLowerCase() === '#111110' ? 0.05 : 0.035} />}

      <svg
        viewBox={`0 0 ${width} ${height}`}
        width={width}
        height={height}
        style={{position: 'absolute', inset: 0, opacity: masterOpacity}}
      >
        {children({
          progress,
          tSec,
          frame,
          durationInFrames,
          fps,
          breath,
          exitFactor,
          safe,
          emphasis: timeline.emphasis ?? [],
        })}
      </svg>

      {!hideBottomSubtitle && activeLine && (
        <div
          style={{
            position: 'absolute',
            left: marginLeft,
            right: isPortrait ? 72 : marginRight,
            bottom: sd.subtitleBottom,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            opacity: subOpacity,
            transform: `translateY(${subTranslateY}px)`,
            pointerEvents: 'none',
          }}
        >
          <div
            style={{
              backgroundColor: theme.subtitleBg ?? 'transparent',
              padding: theme.subtitleBg ? '10px 26px' : '0',
              borderLeft: isPortrait ? `4px solid ${theme.ink}` : undefined,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
            }}
          >
            {wrappedLines.map((ln, idx) => (
              <div
                key={idx}
                style={{
                  fontFamily: FONTS.sans,
                  fontSize: computedSubSize,
                  fontWeight: 600,
                  lineHeight: 1.44,
                  color: theme.ink,
                  textAlign: 'center',
                  whiteSpace: 'nowrap',
                  letterSpacing: '0.01em',
                  fontVariantNumeric: 'lining-nums tabular-nums',
                }}
              >
                {ln}
              </div>
            ))}
          </div>
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
