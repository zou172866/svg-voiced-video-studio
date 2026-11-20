#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Render 4 high-resolution (@2x Headless Edge/Chrome) anti-crop Swiss-editorial video covers (v6):
- 9:16 (1080x1920, locks all text inside central 3:4 safe zone with >=240px top/bottom margin)
- 3:4  (1080x1440, Xiaohongshu / Kuaishou dual-column / WeChat Channels)
- 4:3  (1440x1080, Bilibili mobile dual-column / Douyin 4:3)
- 16:9 (1920x1080, Bilibili web widescreen / Douyin full-screen horizontal)

v6 Aesthetic invariants:
- Typographic headline hierarchy across all modes: 1 giant focal `hook` (number or proper noun,
  1.6x-2.0x scale) + 1-2 smaller explanatory `sublines` (backward-compatible with legacy `headline_lines`)
- Vermilion focus strictly signals information (numbers / proper nouns), NEVER empty slogans/verbs
- Open hairline 2-column data strip (`open-split`, default): two data groups separated by ONE 1px rule,
  ZERO outer border box, ZERO dark/solid background slabs
- Zero production specs or decorative English chrome (no "4K · 60FPS", "01:25 ▶", "VISUAL ESSAY")
- Brand font unity: Mode C (`editorial`) locks `Source Han Sans CN Heavy`; Mode A/B (`dark`/`vellum`)
  lock matched serif with Latin runs wrapped at `letter-spacing: 0` + optical `pangu_space()`
- Optional `--qa-sheet` renders a real 180px mobile-feed thumbnail check sheet
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw

THEMES = {
    "dark": {
        "bg": "#111110",
        "paper": "#181816",
        "paper_deep": "#1F1F1C",
        "ink": "#F2EFE9",
        "ink_sec": "#D6D2C8",
        "muted": "rgba(242, 239, 233, 0.58)",
        "bar_track": "#2B2A26",
        "bar_muted": "#7E7A72",
        "rule": "rgba(242, 239, 233, 0.22)",
        "rule_strong": "rgba(242, 239, 233, 0.52)",
        "tick": "rgba(242, 239, 233, 0.22)",
        "accent": "#D94E28",
        "grain_opacity": 0.0,
        "default_headline_style": "serif",
    },
    "vellum": {
        "bg": "#F5F0E6",
        "paper": "#FAF7F1",
        "paper_deep": "#ECE5D8",
        "ink": "#191715",
        "ink_sec": "#3D3933",
        "muted": "#6E665B",
        "bar_track": "#DDD4C3",
        "bar_muted": "#8C8373",
        "rule": "rgba(25, 23, 21, 0.22)",
        "rule_strong": "#191715",
        "tick": "rgba(25, 23, 21, 0.20)",
        "accent": "#C83E2B",
        "grain_opacity": 0.030,
        "default_headline_style": "serif",
    },
    # Mode C: Swiss warm-paper editorial (9:16 commercial explainers, matches workspace AGENTS.md palette)
    "editorial": {
        "bg": "#F5F1EA",
        "paper": "#FAF8F3",
        "paper_deep": "#ECE7DD",
        "ink": "#1A1A18",
        "ink_sec": "#3A3833",
        "muted": "#6B665E",
        "bar_track": "#DFD8CA",
        "bar_muted": "#8C867A",
        "rule": "rgba(26, 26, 24, 0.22)",
        "rule_strong": "#1A1A18",
        "tick": "rgba(26, 26, 24, 0.20)",
        "accent": "#D93B22",
        "grain_opacity": 0.026,
        "default_headline_style": "grotesk",
    },
}

LATIN_RUN_RE = re.compile(r"([A-Za-z0-9][A-Za-z0-9._:/+-]*|/[a-z][a-z0-9-]*)")
INFO_TOKEN_RE = re.compile(r"([$¥€£]?\d[\d.,万亿倍个项%]*|/[a-z][a-z0-9-]*|[A-Za-z][A-Za-z0-9_-]{1,})")


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


def strip_accent_markers(s: str) -> str:
    return re.sub(r"\*([^*]+)\*", r"\1", s)


def pangu_space(s: str) -> str:
    """Insert delicate optical thin space (U+2009) at CJK <-> ASCII alphanumeric / slash-command / currency / percent boundaries."""
    thin = "\u2009"
    s = re.sub(r"([\u3400-\u9fff])([A-Za-z0-9$¥€£]|[+-](?=[$¥€£]?\d)|/(?=[a-z]))", rf"\1{thin}\2", s)
    s = re.sub(r"([A-Za-z0-9%])([\u3400-\u9fff])", rf"\1{thin}\2", s)
    return s


def visual_em_width(s: str) -> float:
    """East-Asian mixed-script visual width in full-width CJK em units (W3C CLReq)."""
    plain = strip_accent_markers(s)
    w = 0.0
    for ch in plain:
        if ord(ch) <= 0x7F:
            if ch == " ":
                w += 0.30
            elif ch.isupper():
                w += 0.66
            else:
                w += 0.54
        elif ch in ("\u2009", "\u200A"):
            w += 0.16
        else:
            w += 1.0
    return round(w, 2)


def validate_headline_lines(lines: list[str], max_len: int) -> None:
    """Backward-compatible validator for flat headline_lines (also imported by legacy scripts)."""
    max_em = 7.2 if max_len >= 7 else 6.2
    if not 2 <= len(lines) <= 4:
        raise ValueError(f"Cover headline should have 2 to 4 lines, got {len(lines)}")
    for idx, line in enumerate(lines, 1):
        clean = strip_accent_markers(str(line).strip())
        if not clean:
            raise ValueError(f"Cover line {idx} is empty; every headline line must contain visible text.")
        is_pure_cjk = all(ord(c) > 0x7F for c in clean)
        em = visual_em_width(clean)
        if (is_pure_cjk and len(clean) > max_len) or em > max_em:
            raise ValueError(
                f"Cover line {idx} {clean!r} is {em:.2f} em ({len(clean)} chars), exceeding hard limit <= {max_em:.1f} em ({max_len} CJK chars)."
            )


def validate_hierarchical_headline(hook: str, sublines: list[str], allow_7: bool) -> None:
    clean_hook = strip_accent_markers(hook.strip())
    if not clean_hook:
        raise ValueError("Cover 'hook' must be a non-empty giant focal hook (number or proper noun).")
    hook_limit = 6.8 if allow_7 else 5.8
    hook_em = visual_em_width(clean_hook)
    if hook_em > hook_limit:
        raise ValueError(
            f"Cover hook {clean_hook!r} is {hook_em:.2f} em, exceeding <= {hook_limit:.1f} em (keep hook punchy so it renders huge)."
        )
    if not 1 <= len(sublines) <= 2:
        raise ValueError(f"Cover 'sublines' should have 1 to 2 explanatory lines, got {len(sublines)}.")
    sub_limit = 8.2 if allow_7 else 7.4
    for idx, ln in enumerate(sublines, 1):
        clean = strip_accent_markers(str(ln).strip())
        if not clean:
            raise ValueError(f"Cover subline {idx} is empty.")
        em = visual_em_width(clean)
        if em > sub_limit:
            raise ValueError(
                f"Cover subline {idx} {clean!r} is {em:.2f} em, exceeding <= {sub_limit:.1f} em."
            )


def check_font_environment(headline_style: str) -> None:
    if sys.platform != "win32":
        return
    fdir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    if not fdir.is_dir():
        return
    stems = {p.stem.lower() for p in fdir.iterdir() if p.suffix.lower() in (".ttf", ".otf", ".ttc")}
    has_noto_serif = any(k in s for s in stems for k in ("notoserifsc", "sourcehanserif"))
    has_zhongsong = any("stzhongs" in s for s in stems)
    if headline_style == "serif" and not has_noto_serif:
        if has_zhongsong:
            print("[FONT] 未检测到 Noto Serif SC，封面衬线主标将启用本机 STZhongsong + Cambria 拉丁衬线（字距锁 0）。")
        else:
            print("[FONT] 未检测到思源宋体/华文中宋，封面衬线将用 Cambria（拉丁字距 0）+ STSong；模式 C 商业封面固定用 Source Han Sans CN Heavy。")


def render_one(browser_exe: str, html_text: str, dst_png: Path, w: int, h: int, work_dir: Path, tag: str) -> Path:
    html_file = work_dir / f"{tag}.html"
    tmp_png = work_dir / f"{tag}.png"
    profile_dir = work_dir / "browser_profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    html_file.write_text(html_text, encoding="utf-8")

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
    return dst_png


def render_thumbnail_qa_sheet(cover_paths: list[tuple[str, Path]], out_png: Path, thumb_w: int = 180) -> None:
    """Composite all 4 covers at real 180px mobile-feed width to inspect legibility and crop safety at a glance."""
    pad = 20
    label_h = 26
    thumbs: list[tuple[str, Image.Image]] = []
    for lbl, p in cover_paths:
        im = Image.open(p).convert("RGB")
        th = max(40, int(round(im.height * (thumb_w / im.width))))
        thumbs.append((lbl, im.resize((thumb_w, th), Image.Resampling.LANCZOS)))

    total_w = pad + sum(thumb_w + pad for _ in thumbs)
    total_h = pad * 2 + label_h + max(im.height for _, im in thumbs)
    sheet = Image.new("RGB", (total_w, total_h), (222, 218, 210))
    draw = ImageDraw.Draw(sheet)

    x = pad
    for lbl, im in thumbs:
        draw.text((x, pad), lbl, fill=(26, 26, 24))
        sheet.paste(im, (x, pad + label_h))
        draw.rectangle([x - 1, pad + label_h - 1, x + im.width, pad + label_h + im.height], outline=(140, 134, 124))
        x += thumb_w + pad

    sheet.save(out_png, format="PNG", optimize=True)
    print(f"[OK] {out_png.name} ({sheet.size[0]}x{sheet.size[1]}, 180px mobile feed preview)")


def _needs_pangu_between(left_text: str, right_text: str) -> bool:
    if not left_text or not right_text:
        return False
    probe = left_text[-1] + right_text[:3]
    return pangu_space(probe).startswith(left_text[-1] + "\u2009")


def _wrap_latin_runs_html(text: str, wrap_latin: bool) -> str:
    """Escape text and optionally wrap Latin/number runs with zero letter-spacing for crisp mixed serif."""
    if not wrap_latin:
        return html.escape(text)
    out: list[str] = []
    last = 0
    for m in LATIN_RUN_RE.finditer(text):
        if m.start() > last:
            out.append(html.escape(text[last : m.start()]))
        out.append(f'<span class="latin-run">{html.escape(m.group(0))}</span>')
        last = m.end()
    if last < len(text):
        out.append(html.escape(text[last:]))
    return "".join(out)


def format_marked_line(raw: str, wrap_latin: bool, auto_highlight_info: bool = False) -> tuple[str, list[str]]:
    """
    Format one headline line with single vermilion focus (*info*) and optional Latin zero-tracking spans.
    Returns (html_str, list_of_accented_texts).
    """
    stripped = raw.strip()
    accented: list[str] = []
    if "*" in stripped and re.search(r"\*[^*]+\*", stripped):
        segs = [s for s in re.split(r"(\*[^*]+\*)", stripped) if s]
        tokens: list[tuple[str, bool]] = []
        for seg in segs:
            if seg.startswith("*") and seg.endswith("*") and len(seg) > 2:
                tok = pangu_space(seg[1:-1])
                tokens.append((tok, True))
                accented.append(tok)
            else:
                tokens.append((pangu_space(seg), False))
        buf: list[str] = []
        for i, (txt, is_acc) in enumerate(tokens):
            if i > 0 and _needs_pangu_between(tokens[i - 1][0], txt):
                buf.append("\u2009")
            inner = _wrap_latin_runs_html(txt, wrap_latin)
            buf.append(f'<span class="accent">{inner}</span>' if is_acc else inner)
        return "".join(buf), accented

    spaced = pangu_space(stripped)
    if auto_highlight_info:
        # Automatically highlight the first number or proper noun inside the hook (NEVER a slogan line!)
        m = INFO_TOKEN_RE.search(spaced)
        if m:
            tok = m.group(0)
            accented.append(tok)
            before = _wrap_latin_runs_html(spaced[: m.start()], wrap_latin)
            mid = _wrap_latin_runs_html(tok, wrap_latin)
            after = _wrap_latin_runs_html(spaced[m.end() :], wrap_latin)
            return f'{before}<span class="accent">{mid}</span>{after}', accented
        # If hook has no digits/Latin (e.g. poetic 2-4 char CJK noun hook), highlight the hook itself
        accented.append(spaced)
        return f'<span class="accent">{_wrap_latin_runs_html(spaced, wrap_latin)}</span>', accented

    return _wrap_latin_runs_html(spaced, wrap_latin), accented


def _audit_cover_red_focus(accented_spans: list[str]) -> None:
    if len(accented_spans) > 1:
        print(f"[COVER WARN] 封面出现 {len(accented_spans)} 处红焦点（{accented_spans}），请收束为唯一 1 处数字或专名焦点。")
    for span in accented_spans:
        has_num_or_latin = bool(re.search(r"[\dA-Za-z]", span))
        if not has_num_or_latin and len(span) >= 5:
            print(
                f"[COVER WARN] 红焦点 {span!r} 偏长且不含数字/专名；按 v6 规范红色应优先给数字或专有名词，不给空动词/口号。"
            )


def make_paper_grain_svg(opacity: float) -> str:
    if opacity <= 0:
        return ""
    return (
        f'<svg class="grain" width="100%" height="100%" style="opacity:{opacity:.3f}">'
        '<filter id="cov-grain"><feTurbulence type="fractalNoise" baseFrequency="0.88" numOctaves="2" seed="11" stitchTiles="stitch"/>'
        '<feColorMatrix type="saturate" values="0"/></filter>'
        '<rect width="100%" height="100%" filter="url(#cov-grain)"/></svg>'
    )


def make_common_css(t: dict, headline_style: str) -> str:
    is_grotesk = headline_style == "grotesk"
    h_class_font = (
        "'Source Han Sans CN', 'Noto Sans SC', 'PingFang SC', 'Helvetica Neue', 'Bahnschrift', 'Microsoft YaHei UI', sans-serif"
        if is_grotesk
        else "'Source Serif 4', 'Newsreader', 'Cambria', 'Times New Roman', 'Noto Serif SC', 'Source Han Serif SC', 'Source Han Serif CN', 'Songti SC', 'STZhongsong', 'STSong', serif"
    )
    h_weight = "900" if is_grotesk else "600"
    h_tracking = "-0.025em" if is_grotesk else "0.01em"
    h_leading = "1.06" if is_grotesk else "1.12"

    return f"""
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background-color: {t['bg']}; color: {t['ink']};
  font-family: 'Source Han Sans CN', 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei UI', sans-serif;
  font-variant-numeric: lining-nums tabular-nums;
  overflow: hidden; position: relative;
  -webkit-font-smoothing: antialiased;
}}
.grain {{ position: absolute; inset: 0; pointer-events: none; mix-blend-mode: multiply; z-index: 20; }}
.fig {{
  font-family: 'Bahnschrift', 'DIN Alternate', 'Helvetica Neue', 'Segoe UI', 'Source Han Sans CN', 'Noto Sans SC', sans-serif;
  font-variant-numeric: lining-nums tabular-nums;
}}
.h1-voice {{
  font-family: {h_class_font};
  font-weight: {h_weight};
  letter-spacing: {h_tracking};
  line-height: {h_leading};
  font-synthesis-weight: none;
}}
.latin-run {{
  font-family: 'Source Serif 4', 'Newsreader', 'Cambria', 'Times New Roman', serif;
  letter-spacing: 0 !important;
}}
.muted {{ color: {t['muted']}; }}
.sec {{ color: {t['ink_sec']}; }}
.accent {{ color: {t['accent']}; }}
.eyebrow-row {{
  display: flex; align-items: center; gap: 10px;
  font-size: 13px; font-weight: 700; color: {t['muted']}; letter-spacing: 0.04em;
}}
.eyebrow-bar {{ width: 20px; height: 2px; background: {t['rule_strong']}; flex-shrink: 0; }}
.safe-ticks {{ position: absolute; inset: 124px 30px; pointer-events: none; z-index: 10; }}
.tick {{ position: absolute; width: 12px; height: 12px; }}
.tick.tl {{ top: 0; left: 0; border-top: 1px solid {t['tick']}; border-left: 1px solid {t['tick']}; }}
.tick.tr {{ top: 0; right: 0; border-top: 1px solid {t['tick']}; border-right: 1px solid {t['tick']}; }}
.tick.bl {{ bottom: 0; left: 0; border-bottom: 1px solid {t['tick']}; border-left: 1px solid {t['tick']}; }}
.tick.br {{ bottom: 0; right: 0; border-bottom: 1px solid {t['tick']}; border-right: 1px solid {t['tick']}; }}
"""


def parse_ratio(box: dict, default: float, label: str) -> float:
    raw = box.get("ratio", default)
    if raw is None:
        return default
    if isinstance(raw, bool):
        raise ValueError(f"{label}.ratio must be a finite number in [0, 1], got boolean {raw!r}")
    try:
        val = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}.ratio must be a finite number in [0, 1], got {raw!r}") from exc
    if not math.isfinite(val):
        raise ValueError(f"{label}.ratio must be a finite number in [0, 1], got {raw!r}")
    return max(0.0, min(1.0, val))


def resolve_primary_flags(left_box: dict, right_box: dict, r_l: float, r_r: float) -> tuple[bool, bool]:
    l_has = "primary" in left_box and left_box["primary"] is not None
    r_has = "primary" in right_box and right_box["primary"] is not None
    if l_has and r_has:
        return bool(left_box["primary"]), bool(right_box["primary"])
    if l_has:
        lp = bool(left_box["primary"])
        return lp, not lp
    if r_has:
        rp = bool(right_box["primary"])
        return not rp, rp
    return r_l >= r_r, r_r >= r_l


def render_info_strip_html(
    layout: str,
    left_box: dict,
    right_box: dict,
    orientation: str,
    graphic_svg: str = "",
) -> str:
    """
    Build v6 ZERO-box, ZERO-solid-fill open editorial info strip:
    - `open-split` / `editorial-rows`: two data groups separated ONLY by a single 1px hairline (vertical on 9:16/3:4, horizontal on 4:3/16:9).
    - `metric-bars`: open proportional Swiss zero-origin bars directly on paper.
    - `monument`: open anchor stat or custom graphic_svg.
    """
    lt_tag = html.escape(pangu_space(str(left_box.get("tag", ""))))
    lt_title = html.escape(pangu_space(str(left_box.get("title", ""))))
    lt_sub = html.escape(pangu_space(str(left_box.get("sub", ""))))

    rt_tag = html.escape(pangu_space(str(right_box.get("tag", ""))))
    rt_title = html.escape(pangu_space(str(right_box.get("title", ""))))
    rt_sub = html.escape(pangu_space(str(right_box.get("sub", ""))))

    if layout == "monument":
        if graphic_svg.strip():
            return f'<div class="monument-slot">{graphic_svg}</div>'
        return f"""
<div class="monument-open">
  <div class="tag-lbl">{lt_tag}</div>
  <div class="fig mon-val">{lt_title}</div>
  <div class="sec mon-sub">{lt_sub}</div>
  <div class="open-sep"></div>
  <div class="mon-foot"><span class="tag-lbl">{rt_tag}</span><span class="fig mon-foot-val">{rt_title}</span></div>
</div>"""

    if layout == "metric-bars":
        r_l = parse_ratio(left_box, 1.0, "left_card")
        r_r = parse_ratio(right_box, 0.62, "right_card")
        l_primary, r_primary = resolve_primary_flags(left_box, right_box, r_l, r_r)
        l_fill = "bar-fill-ink" if l_primary else "bar-fill-muted"
        r_fill = "bar-fill-ink" if r_primary else "bar-fill-muted"
        l_tcls = "fig ct" if l_primary else "fig ct sec"
        r_tcls = "fig ct" if r_primary else "fig ct sec"
        if orientation in ("4x3", "16x9"):
            return f"""
<div class="open-stack">
  <div class="bar-item">
    <div class="tag-lbl">{lt_tag}</div>
    <div class="{l_tcls}">{lt_title}</div>
    <div class="bar-rail"><div class="{l_fill}" style="width:{r_l*100:.1f}%"></div></div>
    <div class="cs">{lt_sub}</div>
  </div>
  <div class="open-sep"></div>
  <div class="bar-item">
    <div class="tag-lbl">{rt_tag}</div>
    <div class="{r_tcls}">{rt_title}</div>
    <div class="bar-rail"><div class="{r_fill}" style="width:{r_r*100:.1f}%"></div></div>
    <div class="cs">{rt_sub}</div>
  </div>
</div>"""
        return f"""
<div class="open-2col">
  <div class="open-col">
    <div class="tag-lbl">{lt_tag}</div>
    <div class="{l_tcls}">{lt_title}</div>
    <div class="bar-rail"><div class="{l_fill}" style="width:{r_l*100:.1f}%"></div></div>
    <div class="cs">{lt_sub}</div>
  </div>
  <div class="open-col open-col-r">
    <div class="tag-lbl">{rt_tag}</div>
    <div class="{r_tcls}">{rt_title}</div>
    <div class="bar-rail"><div class="{r_fill}" style="width:{r_r*100:.1f}%"></div></div>
    <div class="cs">{rt_sub}</div>
  </div>
</div>"""

    # Default v6: open-split (pure paper, single hairline divider, zero box, zero solid fill)
    if orientation in ("4x3", "16x9"):
        return f"""
<div class="open-stack">
  <div class="open-row">
    <div class="tag-lbl">{lt_tag}</div>
    <div class="fig ct">{lt_title}</div>
    <div class="cs">{lt_sub}</div>
  </div>
  <div class="open-sep"></div>
  <div class="open-row">
    <div class="tag-lbl">{rt_tag}</div>
    <div class="fig ct sec">{rt_title}</div>
    <div class="cs">{rt_sub}</div>
  </div>
</div>"""
    return f"""
<div class="open-2col">
  <div class="open-col">
    <div class="tag-lbl">{lt_tag}</div>
    <div class="fig ct">{lt_title}</div>
    <div class="cs">{lt_sub}</div>
  </div>
  <div class="open-col open-col-r">
    <div class="tag-lbl">{rt_tag}</div>
    <div class="fig ct sec">{rt_title}</div>
    <div class="cs">{rt_sub}</div>
  </div>
</div>"""


def build_covers_from_spec(
    spec: dict,
    out_dir: Path,
    theme_name: str,
    max_chars: int,
    layout: str | None = None,
    headline_style: str | None = None,
    enable_grain: bool = True,
    qa_sheet: bool = False,
) -> list[Path]:
    allow_7 = max_chars >= 7
    t = THEMES[theme_name]
    resolved_layout = layout or spec.get("layout", "open-split")
    req_style = headline_style or spec.get("headline_style", "auto")
    resolved_style = t["default_headline_style"] if req_style == "auto" else req_style
    wrap_latin = resolved_style == "serif"

    check_font_environment(resolved_style)

    # Resolve hierarchical headline (v6 default: `hook` + `sublines`) or fallback from legacy `headline_lines`
    is_hierarchical = bool(spec.get("hook"))
    accented_all: list[str] = []
    if is_hierarchical:
        hook_raw = str(spec["hook"]).strip()
        sub_raw = [str(x).strip() for x in (spec.get("sublines") or []) if str(x).strip()]
        validate_hierarchical_headline(hook_raw, sub_raw, allow_7)

        any_explicit_star = ("*" in hook_raw and bool(re.search(r"\*[^*]+\*", hook_raw))) or any(
            "*" in s and bool(re.search(r"\*[^*]+\*", s)) for s in sub_raw
        )
        hook_html, acc_h = format_marked_line(hook_raw, wrap_latin, auto_highlight_info=not any_explicit_star)
        accented_all.extend(acc_h)
        sub_html_parts: list[str] = []
        for s in sub_raw:
            sh, acc_s = format_marked_line(s, wrap_latin, auto_highlight_info=False)
            accented_all.extend(acc_s)
            sub_html_parts.append(f'<div class="subline">{sh}</div>')
        sub_html = "".join(sub_html_parts)
        _audit_cover_red_focus(accented_all)

        hook_em = max(1.0, visual_em_width(pangu_space(strip_accent_markers(hook_raw))))
        sub_max_em = max(
            1.0,
            *(visual_em_width(pangu_space(strip_accent_markers(s))) for s in sub_raw),
        )
        # Giant hook (1.6x-2.0x scale) + crisp supporting sublines dynamically fitted per viewport
        hook_v = min(116.0, 448.0 / hook_em)
        sub_v = min(hook_v * 0.54, 448.0 / sub_max_em, 56.0)

        hook_43 = min(98.0, 384.0 / hook_em)
        sub_43 = min(hook_43 * 0.54, 384.0 / sub_max_em, 48.0)

        hook_169 = min(116.0, 476.0 / hook_em)
        sub_169 = min(hook_169 * 0.54, 476.0 / sub_max_em, 54.0)

        headline_block = f'<div class="h1-voice hook-line">{hook_html}</div><div class="h1-voice sub-wrap">{sub_html}</div>'
    else:
        lines: list[str] = spec["headline_lines"]
        validate_headline_lines(lines, max_chars)
        print("[COVER NOTE] 检测到旧版等字号 headline_lines，建议升级为 v6 层级字段 `hook` + `sublines`。")
        any_explicit_star = any("*" in ln and bool(re.search(r"\*[^*]+\*", ln)) for ln in lines)
        html_lines: list[str] = []
        for idx, ln in enumerate(lines):
            lh, acc = format_marked_line(ln, wrap_latin, auto_highlight_info=(not any_explicit_star and idx == 0))
            accented_all.extend(acc)
            html_lines.append(lh)
        _audit_cover_red_focus(accented_all)
        max_line_em = max(visual_em_width(pangu_space(strip_accent_markers(str(ln).strip()))) for ln in lines)
        line_scale = 0.86 if len(lines) == 4 else 1.0
        hook_v = min(68.0 * line_scale, 444.0 / max(1.0, max_line_em))
        sub_v = hook_v * 0.6
        hook_43 = min(60.0 * line_scale, 372.0 / max(1.0, max_line_em))
        sub_43 = hook_43 * 0.6
        hook_169 = min(72.0 * line_scale, 468.0 / max(1.0, max_line_em))
        sub_169 = hook_169 * 0.6
        headline_block = f'<div class="h1-voice hook-line">{"<br>".join(html_lines)}</div>'

    css = make_common_css(t, resolved_style)
    grain_svg = make_paper_grain_svg(t["grain_opacity"] if enable_grain else 0.0)
    browser = find_browser_exe()

    # Optional concise Chinese eyebrow only (NO English tech specs like "4K · 60FPS" or "01:25 ▶")
    eyebrow = html.escape(pangu_space(str(spec.get("eyebrow") or spec.get("kicker") or "").strip()))
    lead = html.escape(pangu_space(str(spec.get("lead", "")).strip()))
    graphic_svg = str(spec.get("graphic_svg", ""))
    left_box = spec.get("left_card") or {}
    right_box = spec.get("right_card") or {}
    if not (resolved_layout == "monument" and graphic_svg.strip()):
        if not left_box or not right_box:
            raise ValueError("Spec must provide both 'left_card' and 'right_card' unless using layout='monument' with 'graphic_svg'.")

    lt_em = max(visual_em_width(pangu_space(str(left_box.get("title", "")))), 1.0)
    rt_em = max(visual_em_width(pangu_space(str(right_box.get("title", "")))), 1.0)
    max_ct_em = max(lt_em, rt_em)

    ct_v = min(30.0, max(16.0, 186.0 / max_ct_em))
    ct_v_wrap = "normal" if (max_ct_em * ct_v > 190.0) else "nowrap"
    ct_43 = min(30.0, max(16.0, 200.0 / max_ct_em))
    ct_43_wrap = "normal" if (max_ct_em * ct_43 > 204.0) else "nowrap"
    ct_169 = min(34.0, max(18.0, 290.0 / max_ct_em))
    ct_169_wrap = "normal" if (max_ct_em * ct_169 > 294.0) else "nowrap"

    mon_v = min(44.0, max(22.0, 380.0 / lt_em))
    mon_v_wrap = "normal" if (lt_em * mon_v > 384.0) else "nowrap"
    mon_43 = min(36.0, max(18.0, 180.0 / lt_em))
    mon_43_wrap = "normal" if (lt_em * mon_43 > 184.0) else "nowrap"
    mon_169 = min(44.0, max(20.0, 276.0 / lt_em))
    mon_169_wrap = "normal" if (lt_em * mon_169 > 280.0) else "nowrap"

    eyebrow_html = (
        f'<div class="eyebrow-row"><span class="eyebrow-bar"></span><span>{eyebrow}</span></div>'
        if eyebrow
        else ""
    )

    # v6 Open Swiss Data Strip CSS: ZERO boxes, ZERO paper_deep slabs — single 1px divider on pure paper!
    shared_strip_css = f"""
.tag-lbl {{
  font-size: 12px; font-weight: 700; color: {t['muted']}; letter-spacing: 0.04em;
}}
.open-2col {{
  border-top: 1.5px solid {t['rule_strong']};
  padding-top: 18px;
  display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
}}
.open-col {{ padding: 2px 18px 2px 0; min-width: 0; display: flex; flex-direction: column; gap: 5px; }}
.open-col-r {{ padding: 2px 0 2px 22px; border-left: 1px solid {t['rule']}; }}
.open-stack {{
  border-left: 1px solid {t['rule']}; padding-left: 26px; min-width: 0;
  display: flex; flex-direction: column; justify-content: center; gap: 22px;
}}
.open-row {{ display: flex; flex-direction: column; gap: 5px; min-width: 0; }}
.open-sep {{ height: 1px; background: {t['rule']}; }}
.bar-item {{ display: flex; flex-direction: column; gap: 6px; min-width: 0; }}
.bar-rail {{
  width: 100%; height: 10px; background: {t['bar_track']};
  border-left: 2px solid {t['rule_strong']}; overflow: hidden;
}}
.bar-fill-ink {{ height: 100%; background: {t['ink']}; }}
.bar-fill-muted {{ height: 100%; background: {t['bar_muted']}; }}
.monument-open {{
  border-top: 1.5px solid {t['rule_strong']};
  padding-top: 16px; display: flex; flex-direction: column; gap: 8px; min-width: 0;
}}
.mon-val {{ font-weight: 900; line-height: 1.06; letter-spacing: -0.025em; overflow-wrap: break-word; text-wrap: balance; }}
.mon-sub {{ font-size: 14px; line-height: 1.42; text-wrap: balance; }}
.mon-foot {{ display: flex; justify-content: space-between; align-items: baseline; gap: 6px 12px; flex-wrap: wrap; }}
.mon-foot-val {{ font-size: 16px; font-weight: 800; text-align: right; min-width: 0; }}
.monument-slot {{ border-top: 1.5px solid {t['rule_strong']}; padding-top: 14px; min-width: 0; overflow: hidden; }}
.monument-slot svg {{ display: block; width: 100%; max-width: 100%; height: auto; max-height: 230px; }}
.sub-wrap {{ margin-top: 16px; display: flex; flex-direction: column; gap: 6px; }}
"""

    info_v = render_info_strip_html(resolved_layout, left_box, right_box, "vertical", graphic_svg)
    info_43 = render_info_strip_html(resolved_layout, left_box, right_box, "4x3", graphic_svg)
    info_169 = render_info_strip_html(resolved_layout, left_box, right_box, "16x9", graphic_svg)

    rendered: list[tuple[str, Path]] = []
    with tempfile.TemporaryDirectory(prefix="svg_covers_") as tmp:
        wdir = Path(tmp)

        # 1) 9:16 (1080x1920): 136px logical padding = 272px physical (>=240px top/bottom central 3:4 safe zone)
        html_9x16 = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><style>
{css}
{shared_strip_css}
body {{ width:540px; height:960px; padding:136px 42px; }}
.safe {{ width:100%; height:100%; display:flex; flex-direction:column; justify-content:space-between; position:relative; z-index:2; }}
.hero {{ display:flex; flex-direction:column; justify-content:center; flex:1; padding:14px 0 22px 0; }}
.hook-line {{ font-size:{hook_v:.1f}px; white-space:nowrap; }}
.subline {{ font-size:{sub_v:.1f}px; line-height:1.18; font-weight:{"800" if resolved_style=="grotesk" else "600"}; white-space:nowrap; }}
.ct {{ font-size:{ct_v:.1f}px; font-weight:900; line-height:1.14; margin:2px 0 2px; white-space:{ct_v_wrap}; overflow-wrap:break-word; text-wrap:balance; letter-spacing:-0.015em; }}
.mon-val {{ font-size:{mon_v:.1f}px; white-space:{mon_v_wrap}; }}
.cs {{ font-size:13.5px; line-height:1.4; color:{t['muted']}; font-weight:500; text-wrap:balance; }}
</style></head><body>
{grain_svg}
<div class="safe-ticks"><div class="tick tl"></div><div class="tick tr"></div><div class="tick bl"></div><div class="tick br"></div></div>
<div class="safe">
  {eyebrow_html}
  <div class="hero">{headline_block}</div>
  {info_v}
</div></body></html>"""
        p1 = render_one(browser, html_9x16, out_dir / "封面_竖屏9比16_抖音视频号版.png", 540, 960, wdir, "c9x16")
        rendered.append(("9:16", p1))

        # 2) 3:4 (1080x1440): Xiaohongshu / Kuaishou dual-column / WeChat Channels
        html_3x4 = html_9x16.replace("height:960px; padding:136px 42px;", "height:720px; padding:44px 42px 42px 42px;").replace(
            '<div class="safe-ticks"><div class="tick tl"></div><div class="tick tr"></div><div class="tick bl"></div><div class="tick br"></div></div>',
            "",
        )
        p2 = render_one(browser, html_3x4, out_dir / "封面_信息流3比4_小红书视频号版.png", 540, 720, wdir, "c3x4")
        rendered.append(("3:4", p2))

        # 3) 4:3 (1440x1080): Bilibili mobile dual-column / Douyin 4:3
        html_4x3 = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><style>
{css}
{shared_strip_css}
body {{ width:720px; height:540px; padding:38px 40px 36px 40px; display:flex; flex-direction:column; justify-content:space-between; }}
.grid {{ display:grid; grid-template-columns:minmax(0, 1.38fr) minmax(0, 0.78fr); gap:26px; align-items:center; flex:1; position:relative; z-index:2; }}
.hook-line {{ font-size:{hook_43:.1f}px; white-space:nowrap; }}
.subline {{ font-size:{sub_43:.1f}px; line-height:1.18; font-weight:{"800" if resolved_style=="grotesk" else "600"}; white-space:nowrap; }}
.ct {{ font-size:{ct_43:.1f}px; font-weight:900; line-height:1.14; margin:2px 0; white-space:{ct_43_wrap}; overflow-wrap:break-word; text-wrap:balance; letter-spacing:-0.015em; }}
.mon-val {{ font-size:{mon_43:.1f}px; white-space:{mon_43_wrap}; }}
.mon-foot-val {{ font-size:15px; }}
.cs {{ font-size:13.5px; line-height:1.42; color:{t['muted']}; font-weight:500; text-wrap:balance; }}
.monument-slot svg {{ max-height:280px; }}
</style></head><body>
{grain_svg}
  {eyebrow_html}
  <div class="grid">
    <div>{headline_block}</div>
    {info_43}
  </div>
</body></html>"""
        p3 = render_one(browser, html_4x3, out_dir / "封面_横版4比3_B站抖音推荐版.png", 720, 540, wdir, "c4x3")
        rendered.append(("4:3", p3))

        # 4) 16:9 (1920x1080): Bilibili widescreen / Douyin horizontal (Swiss 7:5 asymmetric)
        lead_html = f'<div class="lead">{lead}</div>' if lead else ""
        html_16x9 = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><style>
{css}
{shared_strip_css}
body {{ width:960px; height:540px; padding:42px 52px 38px 52px; display:flex; flex-direction:column; justify-content:space-between; }}
.grid {{ display:grid; grid-template-columns:minmax(0, 1.32fr) minmax(0, 0.88fr); gap:42px; align-items:center; flex:1; position:relative; z-index:2; }}
.hook-line {{ font-size:{hook_169:.1f}px; white-space:nowrap; }}
.subline {{ font-size:{sub_169:.1f}px; line-height:1.18; font-weight:{"800" if resolved_style=="grotesk" else "600"}; white-space:nowrap; }}
.lead {{ font-size:16px; color:{t['ink_sec']}; margin-top:18px; line-height:1.5; font-weight:500; text-wrap:balance; }}
.ct {{ font-size:{ct_169:.1f}px; font-weight:900; line-height:1.12; margin:2px 0; white-space:{ct_169_wrap}; overflow-wrap:break-word; text-wrap:balance; letter-spacing:-0.015em; }}
.mon-val {{ font-size:{mon_169:.1f}px; white-space:{mon_169_wrap}; }}
.cs {{ font-size:14px; line-height:1.45; color:{t['muted']}; font-weight:500; text-wrap:balance; }}
.monument-slot svg {{ max-height:280px; }}
</style></head><body>
{grain_svg}
  {eyebrow_html}
  <div class="grid">
    <div>{headline_block}{lead_html}</div>
    {info_169}
  </div>
</body></html>"""
        p4 = render_one(browser, html_16x9, out_dir / "封面_横屏16比9_B站双封面版.png", 960, 540, wdir, "c16x9")
        rendered.append(("16:9", p4))

    if qa_sheet:
        render_thumbnail_qa_sheet(rendered, out_dir / "封面_手机双列180px缩略图检验表.png")

    return [p for _, p in rendered]


def main() -> int:
    parser = argparse.ArgumentParser(description="Render 4 multi-platform Swiss-editorial covers (@2x) from a JSON spec (v6).")
    parser.add_argument("--spec-json", required=True, help="Path to cover specification JSON")
    parser.add_argument("--out-dir", required=True, help="Output directory for the 4 PNG covers")
    parser.add_argument("--theme", choices=sorted(THEMES), default="editorial", help="dark = mode A, vellum = mode B, editorial = mode C")
    parser.add_argument("--layout", choices=["open-split", "editorial-rows", "metric-bars", "monument"], help="Cover info layout (default open-split)")
    parser.add_argument("--headline-style", choices=["auto", "grotesk", "serif"], default="auto", help="auto = grotesk for editorial, serif for dark/vellum")
    parser.add_argument("--no-grain", action="store_true", help="Disable subtle paper fiber micro-grain overlay")
    parser.add_argument("--qa-sheet", action="store_true", help="Also emit a 180px mobile-feed thumbnail check sheet")
    parser.add_argument("--allow-7", action="store_true", help="Allow slightly wider proper nouns in hook/sublines")
    args = parser.parse_args()

    spec_path = Path(args.spec_json).expanduser().resolve()
    if not spec_path.is_file():
        print(f"ERROR: Spec JSON not found: {spec_path}", file=sys.stderr)
        return 1

    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8-sig"))
        build_covers_from_spec(
            spec,
            Path(args.out_dir).expanduser().resolve(),
            args.theme,
            7 if args.allow_7 else 6,
            layout=args.layout,
            headline_style=args.headline_style,
            enable_grain=not args.no_grain,
            qa_sheet=args.qa_sheet,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
