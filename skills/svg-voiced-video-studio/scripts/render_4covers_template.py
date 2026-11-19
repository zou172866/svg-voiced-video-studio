#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Render 4 high-resolution (@2x Headless Edge/Chrome) anti-crop video covers:
- 9:16 (1080x1920, locks all text inside central 3:4 safe zone with >=240px top/bottom margin)
- 3:4  (1080x1440, Xiaohongshu / Kuaishou dual-column / WeChat Channels)
- 4:3  (1440x1080, Bilibili mobile dual-column / Douyin 4:3)
- 16:9 (1920x1080, Bilibili web widescreen / Douyin full-screen horizontal)

Enforces <=6 characters per headline line (or <=7 with --allow-7 flag, which also shrinks the headline 8%).
Themes: dark (mode A), vellum (mode B), editorial (mode C, warm paper + vermilion #D93B22).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from PIL import Image


THEMES = {
    "dark": {
        "bg": "#111110",
        "paper": "#161614",
        "ink": "#F2EFE9",
        "muted": "rgba(242, 239, 233, 0.36)",
        "rule": "rgba(242, 239, 233, 0.24)",
        "accent": "#D94E28",
    },
    "vellum": {
        "bg": "#F5F0E6",
        "paper": "#FAF7F1",
        "ink": "#191715",
        "muted": "#6E665B",
        "rule": "rgba(25, 23, 21, 0.16)",
        "accent": "#C83E2B",
    },
    # Mode C: Swiss warm-paper editorial (9:16 commercial explainers, matches workspace AGENTS.md palette)
    "editorial": {
        "bg": "#F5F1EA",
        "paper": "#FAF8F3",
        "ink": "#1A1A18",
        "muted": "#6B665E",
        "rule": "rgba(26, 26, 24, 0.16)",
        "accent": "#D93B22",
    },
}


def find_browser_exe() -> str:
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        shutil.which("msedge"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
    ]
    for c in candidates:
        if c and Path(c).is_file():
            return str(c)
    raise FileNotFoundError("Could not locate headless Edge or Chrome executable.")


def visual_em_width(s: str) -> float:
    """East-Asian mixed-script visual width in full-width CJK em units (W3C CLReq)."""
    w = 0.0
    for ch in s:
        if ord(ch) <= 0x7F:
            if ch == " ":
                w += 0.32
            elif ch.isupper():
                w += 0.68
            else:
                w += 0.55
        else:
            w += 1.0
    return round(w, 2)


def validate_headline_lines(lines: list[str], max_len: int) -> None:
    max_em = 7.2 if max_len >= 7 else 6.2
    if not 2 <= len(lines) <= 4:
        raise ValueError(f"Cover headline should have 2 to 4 lines, got {len(lines)}")
    for idx, line in enumerate(lines, 1):
        clean = line.strip()
        is_pure_cjk = all(ord(c) > 0x7F for c in clean)
        em = visual_em_width(clean)
        if (is_pure_cjk and len(clean) > max_len) or em > max_em:
            raise ValueError(
                f"Cover line {idx} {clean!r} is {em:.2f} em ({len(clean)} chars), exceeding hard limit <= {max_em:.1f} em ({max_len} CJK chars)."
            )


def render_one(browser_exe: str, html: str, dst_png: Path, w: int, h: int, work_dir: Path, tag: str) -> None:
    html_file = work_dir / f"{tag}.html"
    tmp_png = work_dir / f"{tag}.png"
    profile_dir = work_dir / "browser_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    html_file.write_text(html, encoding="utf-8")

    subprocess.run(
        [
            browser_exe,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            f"--user-data-dir={profile_dir}",
            f"--window-size={w},{h}",
            "--force-device-scale-factor=2",
            f"--screenshot={tmp_png}",
            html_file.as_uri(),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )

    im = Image.open(tmp_png).convert("RGB")
    target = (w * 2, h * 2)
    if im.size != target:
        im = im.resize(target, Image.Resampling.LANCZOS)
    dst_png.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst_png, format="PNG", optimize=True)
    print(f"[OK] {dst_png.name} ({im.size[0]}x{im.size[1]})")


def make_common_css(t: dict[str, str]) -> str:
    return f"""
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background-color: {t['bg']}; color: {t['ink']};
  font-family: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei UI', sans-serif;
  font-variant-numeric: lining-nums tabular-nums;
  overflow: hidden; position: relative;
}}
.mono {{ font-family: Consolas, 'SF Mono', ui-monospace, 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei UI', sans-serif; font-weight: 700; letter-spacing: 0.08em; }}
/* Latin serif first so digits and ASCII punctuation use proportional lining glyphs (CJK serif fonts render "1.2" / "12,400" with full-width gaps) */
.serif {{ font-family: 'Source Serif 4', 'Noto Serif', 'Times New Roman', 'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', serif; }}
.muted {{ color: {t['muted']}; }}
.accent {{ color: {t['accent']}; }}
"""


def format_h1(lines: list[str]) -> str:
    parts = [ln if idx < len(lines) - 1 else f'<span class="accent">{ln}</span>' for idx, ln in enumerate(lines)]
    return "<br>".join(parts)


def build_covers_from_spec(spec: dict, out_dir: Path, theme_name: str, max_chars: int) -> None:
    lines: list[str] = spec["headline_lines"]
    validate_headline_lines(lines, max_chars)
    # Scale headline cleanly for >6.2em --allow-7 exemptions or 4-line layouts so vertical safe zones never clip
    wide_scale = 0.92 if any(visual_em_width(ln.strip()) > 6.2 for ln in lines) else 1.0
    line_scale = 0.86 if len(lines) == 4 else 1.0
    h1_scale = wide_scale * line_scale
    t = THEMES[theme_name]
    css = make_common_css(t)
    h1_html = format_h1(lines)
    browser = find_browser_exe()

    sc_cnt = spec.get("scene_count")
    default_mast = f"VISUAL ESSAY // 01—{int(sc_cnt):02d}" if sc_cnt else "VISUAL ESSAY"
    mast_left = spec.get("masthead_left", default_mast)
    kicker = spec.get("kicker", "60FPS VECTOR MOTION")
    duration = spec.get("duration_mmss", "04:00")
    lead = spec.get("lead", "")
    left_box = spec["left_card"]
    right_box = spec["right_card"]
    footer = spec.get("footer", "")

    with tempfile.TemporaryDirectory(prefix="svg_covers_") as tmp:
        wdir = Path(tmp)

        html_9x16 = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><style>
{css}
body {{ width:540px; height:960px; padding:136px 42px; }}
.safe {{ width:100%; height:100%; display:flex; flex-direction:column; justify-content:space-between; }}
.mast {{ display:flex; justify-content:space-between; padding-bottom:12px; border-bottom:1.5px solid {t['ink']}; font-size:11px; }}
.h1 {{ font-size:{68 * h1_scale:.1f}px; font-weight:800; line-height:1.14; margin-top:12px; }}
.card {{ background:{t['paper']}; border:1.5px solid {t['ink']}; border-left:6px solid {t['accent']}; display:grid; grid-template-columns:1fr 1fr; }}
.c1 {{ padding:16px; border-right:1px solid {t['rule']}; }}
.c2 {{ padding:16px; }}
.ct {{ font-size:22px; font-weight:800; margin:5px 0; white-space:nowrap; }}
.cs {{ font-size:12px; line-height:1.42; color:{t['muted']}; }}
.ft {{ padding-top:12px; border-top:1.5px solid {t['ink']}; display:flex; justify-content:space-between; font-size:13px; font-weight:700; }}
</style></head><body><div class="safe">
  <div class="mast mono"><span>{mast_left}</span><span class="muted">60FPS</span></div>
  <div><div class="mono accent" style="font-size:12.5px;font-weight:700;">{kicker}</div><div class="serif h1">{h1_html}</div></div>
  <div class="card">
    <div class="c1"><div class="mono muted" style="font-size:10px;">{left_box['tag']}</div><div class="serif ct">{left_box['title']}</div><div class="cs">{left_box['sub']}</div></div>
    <div class="c2"><div class="mono accent" style="font-size:10px;font-weight:700;">{right_box['tag']}</div><div class="serif ct accent">{right_box['title']}</div><div class="cs">{right_box['sub']}</div></div>
  </div>
  <div class="ft"><span class="serif">{footer}</span><span class="mono accent">{duration} ▶</span></div>
</div></body></html>"""
        render_one(browser, html_9x16, out_dir / "封面_竖屏9比16_抖音视频号版.png", 540, 960, wdir, "c9x16")

        html_3x4 = html_9x16.replace("height:960px; padding:136px 42px;", "height:720px; padding:38px 42px 34px 42px;")
        render_one(browser, html_3x4, out_dir / "封面_信息流3比4_小红书视频号版.png", 540, 720, wdir, "c3x4")

        html_4x3 = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><style>
{css}
body {{ width:720px; height:540px; padding:30px 38px 26px 38px; display:flex; flex-direction:column; justify-content:space-between; }}
.mast {{ display:flex; justify-content:space-between; padding-bottom:10px; border-bottom:1.5px solid {t['ink']}; font-size:11px; }}
.grid {{ display:grid; grid-template-columns:1.28fr 0.85fr; gap:28px; align-items:center; flex:1; }}
.h1 {{ font-size:{60 * h1_scale:.1f}px; font-weight:800; line-height:1.15; white-space:nowrap; margin-top:10px; }}
.card {{ background:{t['paper']}; border:1.5px solid {t['ink']}; border-top:6px solid {t['accent']}; padding:18px 20px; display:flex; flex-direction:column; gap:14px; }}
.ct {{ font-size:23px; font-weight:800; margin:4px 0; white-space:nowrap; }}
.cs {{ font-size:12px; line-height:1.4; color:{t['muted']}; }}
.ft {{ padding-top:10px; border-top:1.5px solid {t['ink']}; display:flex; justify-content:space-between; font-size:13.5px; font-weight:700; }}
</style></head><body>
  <div class="mast mono"><span>{mast_left}</span><span class="muted">4:3 FEED · 60FPS</span></div>
  <div class="grid">
    <div><div class="mono accent" style="font-size:12px;font-weight:700;">{kicker}</div><div class="serif h1">{h1_html}</div></div>
    <div class="card">
      <div style="padding-bottom:14px;border-bottom:1px solid {t['rule']};"><div class="mono muted" style="font-size:10px;">{left_box['tag']}</div><div class="serif ct">{left_box['title']}</div><div class="cs">{left_box['sub']}</div></div>
      <div><div class="mono accent" style="font-size:10px;font-weight:700;">{right_box['tag']}</div><div class="serif ct accent">{right_box['title']}</div><div class="cs">{right_box['sub']}</div></div>
    </div>
  </div>
  <div class="ft"><span class="serif">{footer}</span><span class="mono accent">{duration} ▶</span></div>
</body></html>"""
        render_one(browser, html_4x3, out_dir / "封面_横版4比3_B站抖音推荐版.png", 720, 540, wdir, "c4x3")

        html_16x9 = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><style>
{css}
body {{ width:960px; height:540px; padding:34px 48px 28px 48px; display:flex; flex-direction:column; justify-content:space-between; }}
.mast {{ display:flex; justify-content:space-between; padding-bottom:11px; border-bottom:1.5px solid {t['ink']}; font-size:11.5px; }}
.grid {{ display:grid; grid-template-columns:1.24fr 0.96fr; gap:38px; align-items:center; flex:1; }}
.h1 {{ font-size:{72 * h1_scale:.1f}px; font-weight:800; line-height:1.12; margin-top:12px; }}
.lead {{ font-size:15.5px; color:{t['muted']}; margin-top:16px; line-height:1.5; }}
.panel {{ background:{t['paper']}; border:1.5px solid {t['ink']}; border-top:6px solid {t['accent']}; padding:22px 24px; display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
.ct {{ font-size:20px; font-weight:800; margin:5px 0; white-space:nowrap; }}
.cs {{ font-size:12px; line-height:1.45; color:{t['muted']}; }}
.ft {{ padding-top:10px; border-top:1.5px solid {t['ink']}; display:flex; justify-content:space-between; font-size:12px; }}
</style></head><body>
  <div class="mast mono"><span>{mast_left}</span><span class="muted">1920×1080 · 60FPS</span></div>
  <div class="grid">
    <div><div class="mono accent" style="font-size:12.5px;font-weight:700;">{kicker}</div><div class="serif h1">{h1_html}</div><div class="serif lead">{lead}</div></div>
    <div class="panel">
      <div><div class="mono muted" style="font-size:10px;">{left_box['tag']}</div><div class="serif ct">{left_box['title']}</div><div class="cs">{left_box['sub']}</div></div>
      <div style="border-left:1px solid {t['rule']};padding-left:16px;"><div class="mono accent" style="font-size:10px;font-weight:700;">{right_box['tag']}</div><div class="serif ct accent">{right_box['title']}</div><div class="cs">{right_box['sub']}</div></div>
    </div>
  </div>
  <div class="ft mono muted"><span>{footer}</span><span class="accent" style="font-weight:700;">{duration} ▶</span></div>
</body></html>"""
        render_one(browser, html_16x9, out_dir / "封面_横屏16比9_B站双封面版.png", 960, 540, wdir, "c16x9")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render 4 multi-platform covers (@2x) from a JSON spec.")
    parser.add_argument("--spec-json", required=True, help="Path to cover specification JSON")
    parser.add_argument("--out-dir", required=True, help="Output directory for the 4 PNG covers")
    parser.add_argument("--theme", choices=sorted(THEMES), default="vellum", help="dark = mode A, vellum = mode B, editorial = mode C")
    parser.add_argument("--allow-7", action="store_true", help="Allow up to 7 chars per line for indivisible proper nouns (headline shrinks 8%%)")
    args = parser.parse_args()

    spec_path = Path(args.spec_json).expanduser().resolve()
    if not spec_path.is_file():
        print(f"ERROR: Spec JSON not found: {spec_path}", file=sys.stderr)
        return 1

    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8-sig"))
        build_covers_from_spec(spec, Path(args.out_dir).expanduser().resolve(), args.theme, 7 if args.allow_7 else 6)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
