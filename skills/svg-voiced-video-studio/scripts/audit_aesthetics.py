#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Keyframe aesthetic audit for 60fps SVG explainer videos (advisory, run after extract_keyframes_template.mjs).

Checks each scene's climax frame (SXX_B_climax.png, falls back to any SXX_*.png) inside the content band
(header strip and subtitle band excluded):
  1. accent focus   - number of separate vermilion/accent blobs; > 1 means red is decorating, not signalling
  2. elements       - number of separate visual elements (words merge into text blocks); high = labels and boxes
  3. box edges      - long horizontal ink runs; high = framed boxes and tables (PPT diagram)
  4. hero height    - vertical extent of the largest object; low = no protagonist, everything small
  5. rhythm         - coefficient of variation of ink coverage across scenes; low = every scene equally dense
Plus a source scan (--src) for font sizes below the readability floor (28px landscape / 40px portrait).

Usage:
  python scripts/audit_aesthetics.py out/keyframes --theme vellum
  python scripts/audit_aesthetics.py out/keyframes --theme editorial --src src/scenes
  python scripts/audit_aesthetics.py out/keyframes --accent "#D93B22" --bg "#F5F1EA" --strict
"""
from __future__ import annotations

import argparse
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

# Thresholds calibrated on 17 hand-labelled frames from three 12-scene films (6 good / 11 PPT-style);
# see evals/results/v3_aesthetics_calibration.json. Rhythm threshold has no positive example yet (provisional).
MAX_ACCENT_BLOBS = 1
MAX_ELEMENTS = 8
MAX_BOX_EDGES = 6
MIN_HERO_HEIGHT = 0.25
MIN_RHYTHM_CV = 0.45


def hex_rgb(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i : i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def content_band(h: int, w: int) -> tuple[slice, slice]:
    if h > w:  # 9:16 portrait: skip status/header and the bottom caption/platform UI band
        return slice(int(h * 200 / 1920), int(h * (1920 - 400) / 1920)), slice(0, int(w * (1080 - 140) / 1080))
    # 16:9 landscape: skip chapter header (top 9%) and subtitle band (bottom 24%), and right-edge side text (4%)
    return slice(int(h * 0.09), int(h * 0.76)), slice(0, int(w * 0.96))


def analyse(png: Path, bg: np.ndarray, accent: np.ndarray) -> dict:
    im = np.asarray(Image.open(png).convert("RGB"), dtype=np.float32)
    h, w, _ = im.shape
    ys, xs = content_band(h, w)
    region = im[ys, xs]
    scale = w / 1920.0 if w > h else w / 1080.0

    ink = np.linalg.norm(region - bg, axis=2) > 38.0
    # tight tolerance: dark-text anti-aliasing fringes (e.g. 155,85,48) must not count as accent
    acc = np.linalg.norm(region - accent, axis=2) < 45.0

    # 1. Accent blobs: merge glyphs of one phrase / one object
    lab, n = ndimage.label(ndimage.binary_dilation(acc, iterations=max(1, int(14 * scale))))
    acc_sizes = ndimage.sum(acc, lab, range(1, n + 1)) if n else np.array([])
    accent_blobs = int(np.sum(acc_sizes >= 260 * scale * scale))

    # 2. Visual elements: words merge into text blocks, separate boxes / labels / icons stay separate
    lab_e, n_e = ndimage.label(ndimage.binary_dilation(ink, iterations=max(1, int(10 * scale))))
    el_sizes = ndimage.sum(ink, lab_e, range(1, n_e + 1)) if n_e else np.array([])
    elements = int(np.sum(el_sizes >= 120 * scale * scale))

    # 3. Protagonist height: tallest extent of the largest merged object relative to the content band
    lab_o, n_o = ndimage.label(ndimage.binary_dilation(ink, iterations=max(1, int(20 * scale))))
    hero_h = 0.0
    if n_o:
        sizes = ndimage.sum(ink, lab_o, range(1, n_o + 1))
        sl = ndimage.find_objects(lab_o)[int(np.argmax(sizes))]
        hero_h = (sl[0].stop - sl[0].start) / ink.shape[0]

    # 4. Box edges: long horizontal ink runs (>= 6% of width) = frame/box borders and table rules
    step = max(1, int(round(2 * scale)))
    edges = 0
    min_run = ink.shape[1] * 0.06
    for y in range(0, ink.shape[0], step):
        d = np.diff(np.concatenate([[0], ink[y].astype(np.int8), [0]]))
        starts, ends = np.where(d == 1)[0], np.where(d == -1)[0]
        edges += int(np.sum((ends - starts) >= min_run))

    return {
        "accent_blobs": accent_blobs,
        "elements": elements,
        "hero_h": hero_h,
        "edges": edges,
        "coverage": float(np.mean(ink)),
    }


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


def scan_fonts(src: Path, floor: float) -> list[str]:
    hits = []
    pat = re.compile(r"fontSize\s*[:=]\s*\{?\s*(\d+(?:\.\d+)?)|font-size\s*:\s*(\d+(?:\.\d+)?)px")
    files = [src] if src.is_file() else [p for p in src.rglob("*") if p.suffix in (".tsx", ".ts", ".jsx", ".css")]
    for f in files:
        if "node_modules" in f.parts:
            continue
        for ln_no, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            for m in pat.finditer(line):
                val = float(m.group(1) or m.group(2))
                if val < floor:
                    hits.append(f"  {f.name}:{ln_no} 字号 {val:g}px < {floor:g}px：{line.strip()[:70]}")
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="Advisory aesthetic audit of extracted keyframes.")
    ap.add_argument("keyframes", help="Directory with SXX_A_enter.png / SXX_B_climax.png")
    ap.add_argument("--theme", choices=sorted(THEMES), default="vellum")
    ap.add_argument("--bg", help="Override background hex")
    ap.add_argument("--accent", help="Override accent hex")
    ap.add_argument("--src", help="Scene source file/dir to scan for undersized fontSize")
    ap.add_argument("--min-font", type=float, help="Font floor in px (default 28 landscape / 40 portrait)")
    ap.add_argument("--strict", action="store_true", help="Exit 1 when any warning is raised")
    a = ap.parse_args()

    kdir = Path(a.keyframes)
    frames = pick_frames(kdir)
    if not frames:
        print(f"未在 {kdir} 找到 SXX_*.png 关键帧。")
        return 1
    bg = hex_rgb(a.bg or THEMES[a.theme]["bg"])
    accent = hex_rgb(a.accent or THEMES[a.theme]["accent"])

    print("=== 关键帧审美体检（只看内容区，已排除眉批与字幕带）===")
    print("幕     红色焦点  元素数  方框线  主角高度  墨色覆盖  提示")
    warns = 0
    coverages = []
    portrait = False
    for sid, png in frames:
        r = analyse(png, bg, accent)
        with Image.open(png) as im:
            portrait = im.height > im.width
        coverages.append(r["coverage"])
        notes = []
        if r["accent_blobs"] > MAX_ACCENT_BLOBS:
            notes.append(f"红色焦点 {r['accent_blobs']} 处，只留正在念的那一处")
        if r["elements"] > MAX_ELEMENTS:
            notes.append("元素过碎，删掉标签与小框")
        if r["edges"] > MAX_BOX_EDGES:
            notes.append("方框与表格线过多，换成一个主物体")
        if r["hero_h"] < MIN_HERO_HEIGHT:
            notes.append("主角太小，放大到内容区高度的一半以上")
        warns += len(notes)
        print(
            f"{sid:<6} {r['accent_blobs']:^8}  {r['elements']:^6}  {r['edges']:^6}  {r['hero_h']:>6.0%}   "
            f"{r['coverage']:>6.1%}   {'；'.join(notes) or '通过'}"
        )

    if len(coverages) >= 4:
        cv = statistics.pstdev(coverages) / max(1e-6, statistics.mean(coverages))
        status = "通过" if cv >= MIN_RHYTHM_CV else "各幕密度太接近，插入空镜或放大一幕做高潮"
        if cv < MIN_RHYTHM_CV:
            warns += 1
        print(f"\n全片密度起伏（墨色覆盖变异系数）：{cv:.2f}（暂定目标 ≥ {MIN_RHYTHM_CV}，阈值尚无正例校准）{status}")

    if a.src:
        floor = a.min_font or (40.0 if portrait else 28.0)
        hits = scan_fonts(Path(a.src), floor)
        print(f"\n=== 源码字号下限扫描（< {floor:g}px，共 {len(hits)} 处）===")
        for h_ in hits[:40]:
            print(h_)
        warns += len(hits)

    print(f"\n共 {warns} 条提示。数值只是信号，最终以目视为准；明确的设计例外（如数据对照幕需要两个红点）在交付说明里写明理由。")
    return 1 if (a.strict and warns) else 0


if __name__ == "__main__":
    raise SystemExit(main())
