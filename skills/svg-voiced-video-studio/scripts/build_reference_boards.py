#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build annotated visual reference contact boards (good vs bad examples) for blind review.

Usage:
  python scripts/build_reference_boards.py --spec board_spec.json --out assets/reference_board_bad.png
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        [
            r"C:\Windows\Fonts\SourceHanSansCN-Bold.otf",
            r"C:\Windows\Fonts\msyhbd.ttc",
            r"C:\Windows\Fonts\arialbd.ttf",
        ]
        if bold
        else [
            r"C:\Windows\Fonts\SourceHanSansCN-Regular.otf",
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\arial.ttf",
        ]
    )
    for c in candidates:
        if Path(c).is_file():
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()


def build_board(spec: dict, out_path: Path) -> Path:
    title = str(spec.get("title", "Reference Board"))
    subtitle = str(spec.get("subtitle", ""))
    tone = spec.get("tone", "good")  # 'good' | 'bad'
    items = spec.get("items", [])
    if not items:
        raise ValueError("Board spec has no items.")

    cols = int(spec.get("cols", 3 if len(items) <= 6 else 4))
    rows = math.ceil(len(items) / cols)
    cell_w = int(spec.get("cell_w", 320))
    cell_h = int(spec.get("cell_h", 568))
    pad = 24
    hdr_h = 88
    cap_h = 68

    board_w = pad + cols * (cell_w + pad)
    board_h = hdr_h + pad + rows * (cell_h + cap_h + pad)

    bg_col = (245, 241, 234)
    ink_col = (26, 26, 24)
    muted_col = (107, 102, 94)
    accent_col = (217, 59, 34) if tone == "bad" else (26, 26, 24)
    border_col = (217, 59, 34) if tone == "bad" else (180, 174, 164)

    canvas = Image.new("RGB", (board_w, board_h), bg_col)
    draw = ImageDraw.Draw(canvas)

    f_title = load_font(30, bold=True)
    f_sub = load_font(17, bold=False)
    f_lbl = load_font(17, bold=True)
    f_note = load_font(14, bold=False)

    draw.text((pad, 20), title, fill=accent_col, font=f_title)
    if subtitle:
        draw.text((pad, 58), subtitle, fill=muted_col, font=f_sub)
    draw.line([(pad, hdr_h - 4), (board_w - pad, hdr_h - 4)], fill=ink_col, width=2)

    for idx, it in enumerate(items):
        r = idx // cols
        c = idx % cols
        x0 = pad + c * (cell_w + pad)
        y0 = hdr_h + pad + r * (cell_h + cap_h + pad)

        p = Path(it["path"])
        if not p.is_file():
            raise FileNotFoundError(f"Missing board frame: {p}")
        im = Image.open(p).convert("RGB")
        # Fit preserving aspect ratio inside cell_w x cell_h (letterboxed gently on neutral tone if mixed 16:9/9:16)
        scale = min(cell_w / im.width, cell_h / im.height)
        nw, nh = max(1, int(round(im.width * scale))), max(1, int(round(im.height * scale)))
        resized = im.resize((nw, nh), Image.Resampling.LANCZOS)

        draw.rectangle([x0, y0, x0 + cell_w, y0 + cell_h], fill=(232, 227, 217), outline=border_col, width=2)
        ox = x0 + (cell_w - nw) // 2
        oy = y0 + (cell_h - nh) // 2
        canvas.paste(resized, (ox, oy))

        lbl = str(it.get("label", p.stem))
        note = str(it.get("note", ""))
        draw.text((x0, y0 + cell_h + 8), lbl, fill=accent_col if tone == "bad" else ink_col, font=f_lbl)
        if note:
            draw.text((x0, y0 + cell_h + 33), note, fill=muted_col, font=f_note)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format="PNG", optimize=True)
    print(f"[OK] Reference board -> {out_path} ({canvas.size[0]}x{canvas.size[1]}, {len(items)} items)")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Build annotated good/bad visual reference board PNG.")
    ap.add_argument("--spec", required=True, help="JSON spec file")
    ap.add_argument("--out", required=True, help="Output PNG path")
    a = ap.parse_args()
    spec = json.loads(Path(a.spec).read_text(encoding="utf-8-sig"))
    build_board(spec, Path(a.out).expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
