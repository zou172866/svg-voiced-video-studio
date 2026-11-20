#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Keyframe & source aesthetic + static-motion audit for 60fps SVG explainer videos (v6).

Hard FAIL checks (exit code 1 unconditionally):
  1. accent focus      - >1 separate vermilion/accent blobs in content band
  2. red button ban    - wide filled solid vermilion button/banner rectangle (App CTA language, not print)
  3. large black slab  - on light paper themes, any single solid dark block >12% of content band (terminal card ban)
  4. adjacent rotation - 24x24 silhouette Dice >=0.72 on any adjacent pair, or >=2 pairs >=0.65 (no repeated skeleton)
  5. hero scale        - non-empty scene hero vertical extent < 40% of content band (raised from 25% -> 40%)
  6. film archetypes   - (--src with >=4 scenes) must contain >=1 G1 Monument AND >=1 G3/G4 real diagram

Advisory WARN checks (exit code 1 with --strict):
  7. elements          - >8 separate visual elements
  8. thin box rules    - >6 thin horizontal borders/rules
  9. light ink ceiling - total ink coverage >28% on light paper themes
 10. middle hole & neg - portrait dead hole >24% between graphic bottom and subtitle top, or fragmented whitespace (<55% cohesion)
 11. rhythm CV         - ink coverage CV across scenes <0.45
 12. source craft      - font floor, Georgia ban, SimSun faux-bold, >14 <text> nodes, Mode C serif headline mix,
                         opacity-only PPT entrances lacking spatial/structural motion primitives

Usage:
  python scripts/audit_aesthetics.py out/keyframes --theme editorial --src src/scenes
  python scripts/audit_aesthetics.py out/keyframes --theme vellum --strict
"""
from __future__ import annotations

import argparse
import os
import re
import statistics
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

THEMES = {
    "dark": {"bg": "#111110", "accent": "#D94E28"},
    "vellum": {"bg": "#F5F0E6", "accent": "#C83E2B"},
    "editorial": {"bg": "#F5F1EA", "accent": "#D93B22"},
}

# v6 calibrated thresholds (recalibrated on real Mode C v6 positive frames + Mode B hx good/bad corpus;
# see evals/results/v6_aesthetics_calibration.json)
MAX_ACCENT_BLOBS = 1
MAX_ELEMENTS = 8
MAX_BOX_EDGES = 6
MIN_HERO_HEIGHT = 0.40
EMPTY_SCENE_COV = 0.040
MIN_RHYTHM_CV = 0.30
MAX_LIGHT_COVERAGE = 0.28
MAX_DARK_SLAB_SHARE = 0.12
MAX_MIDDLE_HOLE = 0.24
MIN_NEG_COHESION = 0.55
MAX_ADJACENT_DICE = 0.65
HARD_ADJACENT_DICE = 0.72
MAX_TEXT_NODES_PER_SCENE = 14

SPATIAL_MOTION_TOKENS = (
    "SvgWipe",
    "wipeRect",
    "clipPath",
    "cameraAt",
    "SingleCanvasAct",
    "drawStroke",
    "EditorialRule",
    "SwissBarAxis",
    "FlowRouter",
    "MonumentMetric",
    "EditorialStrikeReveal",
    "AsymmetricSplit",
    "PaperCommandLine",
    "EditorialSealStamp",
    "countTo",
    "SilentEpigraph",
    "x2={",
    "y2={",
    "width={",
    "height={",
    "scale(",
)


def hex_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return np.array([int(h[i : i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def relative_luminance(rgb: np.ndarray) -> float:
    c = rgb / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, np.power((c + 0.055) / 1.055, 2.4))
    return float(0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2])


def content_band(h: int, w: int) -> tuple[slice, slice]:
    if h > w:
        # 9:16 portrait v6: pure-paper left/top margins (excludes outer left bleed x<48, top platform UI y<266,
        # bottom 54px subtitle rail y>=1330, and right platform UI column x>940)
        return slice(int(h * 266 / 1920), int(h * 1330 / 1920)), slice(int(w * 48 / 1080), int(w * 940 / 1080))
    # 16:9 landscape: excludes top header & bottom subtitle/footer
    return slice(int(h * 140 / 1080), int(h * 0.76)), slice(0, int(w * 0.96))


def count_thin_h_lines(ink: np.ndarray, scale: float) -> int:
    """Count thin horizontal rules/box borders while ignoring solid filled bars, stamps, and panels."""
    thick_k = max(3, int(round(10 * scale)))
    thick_body = ndimage.binary_opening(ink, structure=np.ones((thick_k, 1), dtype=bool))
    thin_ink = ink & ~thick_body
    min_run_w = max(8, int(round(ink.shape[1] * 0.06)))
    horiz_open = ndimage.binary_opening(thin_ink, structure=np.ones((1, min_run_w), dtype=bool))
    lab_h, nh = ndimage.label(ndimage.binary_dilation(horiz_open, structure=np.ones((3, 3), dtype=bool)))
    if not nh:
        return 0
    max_h = max(14, int(round(14 * scale)))
    count = 0
    for sl in ndimage.find_objects(lab_h):
        if sl is None:
            continue
        bw = sl[1].stop - sl[1].start
        bh = sl[0].stop - sl[0].start
        if bw >= min_run_w and bh <= max_h:
            count += 1
    return count


def strip_thin_v_spines(ink: np.ndarray, scale: float) -> np.ndarray:
    """Remove thin tall vertical guide lines (>=18% band height, <=10px wide) before element counting."""
    thick_w = max(3, int(round(10 * scale)))
    wide_body = ndimage.binary_opening(ink, structure=np.ones((1, thick_w), dtype=bool))
    thin_v = ink & ~wide_body
    min_h = max(40, int(round(ink.shape[0] * 0.18)))
    v_spines = ndimage.binary_opening(thin_v, structure=np.ones((min_h, 1), dtype=bool))
    return ink & ~v_spines


def dilate_rect(mask: np.ndarray, ry: int, rx: int) -> np.ndarray:
    out = ndimage.binary_dilation(mask, structure=np.ones((1, 2 * max(1, rx) + 1), dtype=bool))
    return ndimage.binary_dilation(out, structure=np.ones((2 * max(1, ry) + 1, 1), dtype=bool))


def detect_red_buttons(acc: np.ndarray, scale: float) -> int:
    """
    Detect solid filled vermilion CTA button / banner rectangles (App UI language) while allowing:
    - red typography (separated glyphs / hollow counters),
    - thin red lines (<=3px),
    - compact square vermilion chop seals (area < 1.2% of band and near-square aspect ratio),
    - slim solid G4 Swiss data bars (height <= 64px with zero interior cutout text holes).
    """
    if not np.any(acc):
        return 0
    band_area = float(acc.shape[0] * acc.shape[1])
    closed = ndimage.binary_closing(acc, structure=np.ones((max(3, int(round(4 * scale))), max(3, int(round(4 * scale)))), dtype=bool))
    filled = ndimage.binary_fill_holes(closed)
    lab, n = ndimage.label(filled)
    if not n:
        return 0
    buttons = 0
    for idx, sl in enumerate(ndimage.find_objects(lab), 1):
        if sl is None:
            continue
        bh = sl[0].stop - sl[0].start
        bw = sl[1].stop - sl[1].start
        if bh < 32 * scale or bw < 96 * scale:
            continue
        comp_acc = acc[sl] & (lab[sl] == idx)
        comp_filled = filled[sl] & (lab[sl] == idx)
        raw_px = float(np.sum(comp_acc))
        filled_px = float(np.sum(comp_filled))
        raw_share = raw_px / band_area
        filled_share = filled_px / band_area
        fill_ratio = raw_px / max(1.0, float(bh * bw))
        interior_cutout = max(0.0, filled_px - raw_px) / max(1.0, filled_px)
        aspect = bw / max(1.0, float(bh))
        # Red App CTA button with white text punched out inside (e.g. "1个Skill解决", "自动识别任务")
        if filled_share >= 0.015 and 0.42 <= fill_ratio <= 0.92 and interior_cutout >= 0.05 and aspect >= 1.45:
            buttons += 1
        # Oversized thick red block/banner far taller than a slim data bar (bh >= 80px)
        elif bh >= 80 * scale and raw_share >= 0.025 and fill_ratio >= 0.55 and aspect >= 1.15:
            buttons += 1
    return buttons


def detect_max_dark_slab(region: np.ndarray, scale: float) -> float:
    """
    On light paper themes, measure the largest single solid dark slab (e.g. black terminal card)
    as a fraction of the content band, after filling interior white text cutouts.
    """
    lum = (0.2126 * region[:, :, 0] + 0.7152 * region[:, :, 1] + 0.0722 * region[:, :, 2]) / 255.0
    dark = lum < 0.14
    if not np.any(dark):
        return 0.0
    k = max(3, int(round(5 * scale)))
    closed = ndimage.binary_closing(dark, structure=np.ones((k, k), dtype=bool))
    filled = ndimage.binary_fill_holes(closed)
    lab, n = ndimage.label(filled)
    if not n:
        return 0.0
    band_area = float(dark.shape[0] * dark.shape[1])
    best = 0.0
    for idx, sl in enumerate(ndimage.find_objects(lab), 1):
        if sl is None:
            continue
        bh = sl[0].stop - sl[0].start
        bw = sl[1].stop - sl[1].start
        if bh < 60 * scale or bw < 120 * scale:
            continue
        sub_dark = dark[sl] & (lab[sl] == idx)
        sub_filled = filled[sl] & (lab[sl] == idx)
        raw_fill_ratio = float(np.sum(sub_dark)) / max(1.0, float(bh * bw))
        filled_ratio = float(np.sum(sub_filled)) / max(1.0, float(bh * bw))
        share = float(np.sum(sub_filled)) / band_area
        # True dark card/slab: dense rectangular dark mass enclosing text or background
        if raw_fill_ratio >= 0.48 and filled_ratio >= 0.72 and share > best:
            best = share
    return best


def analyse(png: Path, bg: np.ndarray, accent: np.ndarray, is_light_bg: bool) -> dict:
    im = np.asarray(Image.open(png).convert("RGB"), dtype=np.float32)
    h, w, _ = im.shape
    portrait = h > w
    ys, xs = content_band(h, w)
    region = im[ys, xs]
    scale = w / 1920.0 if w > h else w / 1080.0

    ink = np.linalg.norm(region - bg, axis=2) > 38.0
    acc = np.linalg.norm(region - accent, axis=2) < 45.0

    # 1. Accent blobs: horizontal-aware merge (rx=34 keeps spaced 150px+ mixed headlines like "1 个 Skill" as 1 focus)
    lab, n = ndimage.label(dilate_rect(acc, int(round(16 * scale)), int(round(34 * scale))))
    acc_sizes = ndimage.sum(acc, lab, range(1, n + 1)) if n else np.array([])
    accent_blobs = int(np.sum(acc_sizes >= 260 * scale * scale))

    # 1b. Solid red CTA buttons
    red_buttons = detect_red_buttons(acc, scale)

    # 2. Visual elements
    ink_no_spine = strip_thin_v_spines(ink, scale)
    lab_e, n_e = ndimage.label(dilate_rect(ink_no_spine, int(round(9 * scale)), int(round(16 * scale))))
    el_sizes = ndimage.sum(ink_no_spine, lab_e, range(1, n_e + 1)) if n_e else np.array([])
    elements = int(np.sum(el_sizes >= 120 * scale * scale))

    # 3. Protagonist scale (vertical extent of dominant object / cohesive group)
    lab_o, n_o = ndimage.label(dilate_rect(ink_no_spine, int(round(24 * scale)), int(round(36 * scale))))
    hero_h = 0.0
    if n_o:
        sizes = ndimage.sum(ink_no_spine, lab_o, range(1, n_o + 1))
        sl = ndimage.find_objects(lab_o)[int(np.argmax(sizes))]
        raw_h = (sl[0].stop - sl[0].start) / ink.shape[0]
        raw_w = (sl[1].stop - sl[1].start) / ink.shape[1]
        hero_h = max(raw_h, raw_w * (0.48 if portrait else 0.45))

    # 4. Thin horizontal rules
    edges = count_thin_h_lines(ink, scale)

    # 5. Coverage, dark slab share, true middle-hole gap (graphic body -> subtitle) & whitespace cohesion
    coverage = float(np.mean(ink))
    dark_slab_share = detect_max_dark_slab(region, scale) if is_light_bg else 0.0

    ys_idx = np.where(ink)[0]
    if len(ys_idx) > 0:
        v_center = float(np.mean(ys_idx)) / max(1, ink.shape[0])
    else:
        v_center = 0.5

    # Substantial graphic rows (>= 2% row ink density, ignoring stray 1px bottom dividers or vertical spines)
    row_density = np.mean(ink_no_spine, axis=1)
    # Exclude thin horizontal rules (thickness <= 4px) so a lone decorative rule near the bottom cannot hide a dead hole
    thick_ink_rows = ndimage.binary_opening(ink_no_spine, structure=np.ones((max(3, int(round(6 * scale))), 1), dtype=bool))
    body_rows = np.where(np.mean(thick_ink_rows, axis=1) >= 0.015)[0]
    if len(body_rows) == 0:
        body_rows = np.where(row_density >= 0.018)[0]

    if len(body_rows) > 0:
        last_body_y_abs = ys.start + int(body_rows[-1])
        if portrait:
            # Find actual top of subtitle band in y=1330..1620 (or fallback to 1360 if frame has no active subtitle)
            sub_band_top = int(h * 1330 / 1920)
            sub_band_bot = int(h * 1620 / 1920)
            sub_region = im[sub_band_top:sub_band_bot, xs]
            sub_ink = np.linalg.norm(sub_region - bg, axis=2) > 38.0
            sub_rows = np.where(np.mean(sub_ink, axis=1) >= 0.015)[0]
            sub_top_abs = (sub_band_top + int(sub_rows[0])) if len(sub_rows) > 0 else int(h * 1360 / 1920)
            gap_px = max(0, sub_top_abs - last_body_y_abs)
            middle_hole = float(gap_px) / max(1.0, float(ink.shape[0]))
        else:
            middle_hole = 1.0 - (float(body_rows[-1]) / max(1, ink.shape[0]))
    else:
        middle_hole = 1.0

    # Whitespace cohesion: ignore ultra-thin <=4px hairlines (which don't box in paper air) when checking fragmented negative space
    bg_mass = (~thick_ink_rows)[::4, ::4]
    bg_total = int(np.sum(bg_mass))
    if bg_total > 0:
        lab_bg, n_bg = ndimage.label(bg_mass)
        bg_sizes = ndimage.sum(bg_mass, lab_bg, range(1, n_bg + 1)) if n_bg else np.array([0])
        neg_cohesion = float(np.max(bg_sizes)) / float(bg_total)
    else:
        neg_cohesion = 0.0

    # 6. 24x24 silhouette for adjacent layout rotation check
    sil = np.asarray(
        Image.fromarray((ink.astype(np.uint8) * 255)).resize((24, 24), Image.Resampling.BILINEAR)
    ) > 20

    return {
        "portrait": portrait,
        "accent_blobs": accent_blobs,
        "red_buttons": red_buttons,
        "elements": elements,
        "hero_h": hero_h,
        "edges": edges,
        "coverage": coverage,
        "dark_slab_share": dark_slab_share,
        "v_center": v_center,
        "middle_hole": middle_hole,
        "neg_cohesion": neg_cohesion,
        "silhouette": sil,
    }


def dice_similarity(a: np.ndarray, b: np.ndarray) -> float:
    tot = int(np.sum(a)) + int(np.sum(b))
    if tot == 0:
        return 0.0
    return float(2 * int(np.sum(a & b))) / float(tot)


def pick_frames(kdir: Path) -> list[tuple[str, Path]]:
    by_scene: dict[str, list[Path]] = {}
    for p in sorted(kdir.glob("*.png")):
        m = re.match(r"(S\d+)_", p.name)
        if m:
            by_scene.setdefault(m.group(1), []).append(p)
    out = []
    for sid, files in sorted(by_scene.items()):
        climax = [f for f in files if "B_climax" in f.name]
        out.append((sid, climax[0] if climax else files[-1]))
    return out


def check_local_editorial_fonts() -> list[str]:
    font_dirs: list[Path] = []
    if sys.platform == "win32":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        font_dirs.append(windir / "Fonts")
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            font_dirs.append(Path(local_app) / "Microsoft" / "Windows" / "Fonts")
    elif sys.platform == "darwin":
        font_dirs.extend([Path("/System/Library/Fonts"), Path("/Library/Fonts"), Path.home() / "Library/Fonts"])
    else:
        font_dirs.extend([Path("/usr/share/fonts"), Path.home() / ".local/share/fonts"])

    names: set[str] = set()
    for d in font_dirs:
        if d.is_dir():
            for p in d.rglob("*"):
                if p.suffix.lower() in (".ttf", ".otf", ".ttc"):
                    names.add(p.stem.lower())
    if not names:
        return []

    has_cjk_serif = any(k in n for n in names for k in ("notoserifsc", "sourcehanserif", "songti"))
    has_cjk_sans = any(k in n for n in names for k in ("sourcehansans", "notosanssc", "pingfang"))
    notes = []
    if not has_cjk_serif:
        notes.append("本机未装 Noto Serif SC / Source Han Serif；模式 A/B 衬线自动启用 Cambria（拉丁字距 0）+ 本机宋体，模式 C 固定统一 Source Han Sans CN Heavy。")
    if not has_cjk_sans:
        notes.append("本机未检测到 Source Han Sans / Noto Sans SC，黑体将回退至系统默认字体。")
    return notes


def iter_jsx_opening_tags(text: str, tag_name: str = "text") -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    start_pat = re.compile(rf"<{tag_name}(?=[\s/>])")
    n = len(text)
    for m in start_pat.finditer(text):
        i = m.start()
        brace_depth = 0
        quote: str | None = None
        escaped = False
        j = m.end()
        while j < n:
            ch = text[j]
            if quote:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote:
                    quote = None
            else:
                if ch in ("'", '"', "`"):
                    quote = ch
                elif ch == "{":
                    brace_depth += 1
                elif ch == "}":
                    brace_depth = max(0, brace_depth - 1)
                elif ch == ">" and brace_depth == 0:
                    out.append((i, text[i : j + 1]))
                    break
            j += 1
    return out


def scan_source_aesthetics(src: Path, floor: float, theme_name: str) -> tuple[list[str], list[str]]:
    """Return (hard_fails, warnings) from TSX/CSS source audit."""
    hard_fails: list[str] = []
    warns: list[str] = []
    size_pat = re.compile(r"fontSize\s*[:=]\s*\{?\s*(\d+(?:\.\d+)?)|font-size\s*:\s*(\d+(?:\.\d+)?)px")
    georgia_pat = re.compile(r"['\"]Georgia['\"]", re.IGNORECASE)
    cjk_serif_stack_pat = re.compile(r"(?:Noto Serif SC|Source Han Serif|Songti SC|STSong|SimSun)", re.IGNORECASE)
    serif_prop_pat = re.compile(
        r"fontFamily\s*[:=]\s*\{?\s*(?:SERIF|STUDIO_FONTS\.serif(?:Mixed)?|STUDIO_FONTS\.displayAB|FONTS\.serif|['\"][^'\"]*(?:Serif|Song|SimSun)[^'\"]*['\"])"
    )
    heavy_wt_pat = re.compile(r"fontWeight\s*[:=]\s*\{?\s*['\"]?(?:800|900)['\"]?\b")
    scene_export_pat = re.compile(r"export\s+(?:const|function)\s+(Scene[A-Za-z0-9_]+)")

    is_dir = src.is_dir()
    files = [src] if src.is_file() else [p for p in sorted(src.rglob("*")) if p.suffix in (".tsx", ".ts", ".jsx", ".css")]

    total_scenes = 0
    has_g1 = False
    has_g3_or_g4 = False

    for f in files:
        if "node_modules" in f.parts:
            continue
        if is_dir and (
            f.name.startswith("SceneFrameShell")
            or f.name.startswith("motion_60fps")
            or f.name.startswith("SwissSvgPrimitives")
        ):
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        for ln_no, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            for m in size_pat.finditer(line):
                val = float(m.group(1) or m.group(2))
                if val < floor:
                    warns.append(f"  {f.name}:{ln_no} 字号 {val:g}px < {floor:g}px：{stripped[:70]}")
            if georgia_pat.search(line):
                warns.append(f"  {f.name}:{ln_no} 禁用旧式不等高数字字体 Georgia：{stripped[:70]}")
            if cjk_serif_stack_pat.search(line) and "STZhongsong" not in line and "STUDIO_FONTS" not in line:
                warns.append(f"  {f.name}:{ln_no} 衬线栈请改用 STUDIO_FONTS.serifMixed 防 SimSun 伪粗与拉丁散开：{stripped[:70]}")

        for start_pos, tag in iter_jsx_opening_tags(text, "text"):
            if serif_prop_pat.search(tag):
                ln_no = text.count("\n", 0, start_pos) + 1
                preview = " ".join(tag.split())[:72]
                if heavy_wt_pat.search(tag):
                    warns.append(f"  {f.name}:{ln_no} 衬线体使用 800/900 易触发伪粗膨胀：{preview}")
                if theme_name == "editorial":
                    warns.append(f"  {f.name}:{ln_no} [品牌字体统一] 模式 C 应统一用 Source Han Sans CN Heavy，勿混用衬线主标：{preview}")

        matches = list(scene_export_pat.finditer(text))
        for i, m in enumerate(matches):
            total_scenes += 1
            seg = text[m.start() : matches[i + 1].start() if i + 1 < len(matches) else len(text)]
            # Include 4 comment lines immediately above the export for @archetype annotations
            prefix_start = max(0, m.start() - 260)
            seg_with_hdr = text[prefix_start : matches[i + 1].start() if i + 1 < len(matches) else len(text)]

            if re.search(r"<MonumentMetric\b|@archetype\s+G1\b|原型[：:]\s*G1\b", seg_with_hdr):
                has_g1 = True
            if re.search(r"<(?:FlowRouter|SwissBarAxis)\b|@archetype\s+G[34]\b|原型[：:]\s*G[34]\b", seg_with_hdr):
                has_g3_or_g4 = True

            text_nodes = len(re.findall(r"<text\b", seg))
            if text_nodes > MAX_TEXT_NODES_PER_SCENE:
                warns.append(
                    f"  {f.name}::{m.group(1)} 含 {text_nodes} 个 <text> 节点（> {MAX_TEXT_NODES_PER_SCENE}），疑似 PPT 文字堆砌"
                )

            # Static motion check: flag scenes that only animate opacity without spatial/structural motion
            has_opacity_anim = bool(re.search(r"opacity\s*=\s*\{", seg))
            has_spatial_motion = any(tok in seg for tok in SPATIAL_MOTION_TOKENS)
            if has_opacity_anim and not has_spatial_motion:
                warns.append(
                    f"  {f.name}::{m.group(1)} [MOTION WARN] 检测到仅靠 opacity 变化的入场，缺少推镜/纸面擦除/描边或柱条生长等空间主动作"
                )

    if total_scenes >= 4:
        if not has_g1:
            hard_fails.append(f"  [配额不足] 全片共 {total_scenes} 幕但缺少至少 1 幕 G1 纪念碑巨数（MonumentMetric / @archetype G1）")
        if not has_g3_or_g4:
            hard_fails.append(f"  [配额不足] 全片共 {total_scenes} 幕但缺少至少 1 幕 G3 拓扑流图或 G4 数据轴（FlowRouter / SwissBarAxis）")

    return hard_fails, warns


def main() -> int:
    ap = argparse.ArgumentParser(description="v6 aesthetic & static-motion audit of extracted keyframes and TSX scenes.")
    ap.add_argument("keyframes", help="Directory with SXX_A_enter.png / SXX_B_climax.png")
    ap.add_argument("--theme", choices=sorted(THEMES), default="editorial")
    ap.add_argument("--bg", help="Override background hex")
    ap.add_argument("--accent", help="Override accent hex")
    ap.add_argument("--src", help="Scene source file/dir to scan for typography, archetype quota & PPT fade-in issues")
    ap.add_argument("--min-font", type=float, help="Font floor in px (default 28 landscape / 40 portrait)")
    ap.add_argument("--strict", action="store_true", help="Exit 1 on advisory warnings as well as hard FAILs")
    a = ap.parse_args()

    kdir = Path(a.keyframes)
    frames = pick_frames(kdir)
    if not frames:
        print(f"未在 {kdir} 找到 SXX_*.png 关键帧。")
        return 1
    bg = hex_rgb(a.bg or THEMES[a.theme]["bg"])
    accent = hex_rgb(a.accent or THEMES[a.theme]["accent"])
    is_light_bg = relative_luminance(bg) > 0.45

    print("=== 关键帧审美与版式硬检 v6（已排除平台安全边与字幕带）===")
    print("幕     红焦点 红按钮 元素 框线  主角高  墨覆  黑块  中洞  留白聚  邻似   结论")
    hard_fails: list[str] = []
    warns = 0
    coverages: list[float] = []
    high_sim_pairs: list[str] = []
    prev_sil: np.ndarray | None = None
    prev_sid: str = ""
    portrait = False

    for sid, png in frames:
        r = analyse(png, bg, accent, is_light_bg)
        portrait = r["portrait"]
        coverages.append(r["coverage"])
        is_empty_epigraph = r["coverage"] < EMPTY_SCENE_COV

        adj_dice = dice_similarity(prev_sil, r["silhouette"]) if prev_sil is not None else 0.0
        if prev_sil is not None and adj_dice >= MAX_ADJACENT_DICE:
            high_sim_pairs.append(f"{prev_sid}->{sid}({adj_dice:.2f})")

        scene_fails: list[str] = []
        scene_warns: list[str] = []

        # HARD FAILS
        if r["accent_blobs"] > MAX_ACCENT_BLOBS:
            scene_fails.append(f"红焦点={r['accent_blobs']}")
        if r["red_buttons"] > 0:
            scene_fails.append(f"禁红底按钮({r['red_buttons']}处)")
        if is_light_bg and r["dark_slab_share"] > MAX_DARK_SLAB_SHARE:
            scene_fails.append(f"禁黑底大块({r['dark_slab_share']:.0%}>12%)")
        if not is_empty_epigraph and r["hero_h"] < MIN_HERO_HEIGHT:
            scene_fails.append(f"主角过小({r['hero_h']:.0%}<40%)")
        if prev_sil is not None and adj_dice >= HARD_ADJACENT_DICE:
            scene_fails.append(f"与{prev_sid}撞骨架(Dice {adj_dice:.2f})")

        # ADVISORY WARNS
        if r["elements"] > MAX_ELEMENTS:
            scene_warns.append("元素碎")
        if r["edges"] > MAX_BOX_EDGES:
            scene_warns.append("细框多")
        if is_light_bg and r["coverage"] > MAX_LIGHT_COVERAGE:
            scene_warns.append(f"重墨{r['coverage']:.0%}>28%")
        if portrait and not is_empty_epigraph and r["middle_hole"] > MAX_MIDDLE_HOLE:
            scene_warns.append(f"中洞{r['middle_hole']:.0%}>24%")
        if not is_empty_epigraph and r["neg_cohesion"] < MIN_NEG_COHESION:
            scene_warns.append(f"留白碎({r['neg_cohesion']:.0%})")

        for sf_ in scene_fails:
            hard_fails.append(f"{sid}: {sf_}")
        warns += len(scene_warns)

        sim_str = f"{adj_dice:4.2f}" if prev_sil is not None else "  - "
        status_parts = ([f"FAIL({','.join(scene_fails)})"] if scene_fails else []) + (
            [f"WARN({','.join(scene_warns)})"] if scene_warns else []
        )
        print(
            f"{sid:<6} {r['accent_blobs']:^6} {r['red_buttons']:^6} {r['elements']:^4} {r['edges']:^4}  "
            f"{r['hero_h']:>5.0%}  {r['coverage']:>4.0%}  {r['dark_slab_share']:>4.0%}  "
            f"{r['middle_hole']:>4.0%}   {r['neg_cohesion']:>4.0%}   {sim_str}   {' | '.join(status_parts) or 'PASS'}"
        )
        prev_sil = r["silhouette"]
        prev_sid = sid

    if len(coverages) >= 4:
        cv = statistics.pstdev(coverages) / max(1e-6, statistics.mean(coverages))
        status = "PASS" if cv >= MIN_RHYTHM_CV else "WARN(各幕密度太接近，增加尺度起伏或留白)"
        if cv < MIN_RHYTHM_CV:
            warns += 1
        print(f"\n全片密度起伏 CV：{cv:.2f}（目标 ≥ {MIN_RHYTHM_CV}）{status}")

    if len(high_sim_pairs) >= 2:
        msg = f"连续构图雷同超限（{len(high_sim_pairs)} 组：{', '.join(high_sim_pairs)}），必须轮换 G1～G6 原型"
        hard_fails.append(msg)
        print(f"[FAIL] {msg}")

    if a.src:
        floor = a.min_font or (40.0 if portrait else 28.0)
        src_fails, src_warns = scan_source_aesthetics(Path(a.src), floor, a.theme)
        print(f"\n=== 源码排版、构图配额与动效静态扫描（字号下限 {floor:g}px：硬失败 {len(src_fails)}，警告 {len(src_warns)}）===")
        for sf_ in src_fails:
            print(f"[FAIL]{sf_}")
            hard_fails.append(sf_.strip())
        for sw_ in src_warns[:40]:
            print(f"[WARN]{sw_}")
        warns += len(src_warns)

        font_notes = check_local_editorial_fonts()
        if font_notes:
            print("\n=== 本机字体环境提示 ===")
            for fn in font_notes:
                print(f"  [FONT] {fn}")

    verdict = "FAIL" if hard_fails else ("WARN" if warns else "PASS")
    print(f"\n=== 审美硬检总结 [{verdict}]：硬失败 {len(hard_fails)} 项 | 警告 {warns} 项 ===")
    if hard_fails:
        return 1
    return 1 if (a.strict and warns) else 0


if __name__ == "__main__":
    raise SystemExit(main())
