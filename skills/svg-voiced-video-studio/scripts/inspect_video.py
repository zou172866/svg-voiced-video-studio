#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Programmatic final-video technical QA & review-sheet generator for svg-voiced-video-studio.

Hard PASS / FAIL checks (exit code 1 on any FAIL):
  1. Video stream decodable, non-zero frames
  2. Resolution matches --expect-size (e.g. 1080x1920 or 1920x1080)
  3. Frame rate matches --expect-fps (e.g. 60)
  4. Packet/frame count matches duration * fps (within +-2 frames) and --scenes-json / --expect-duration
  5. Stereo audio stream present, EBU R128 integrated loudness within -14.0 +- 1.5 LUFS, true peak <= -1.0 dBTP
  6. Zero accidental pure-black dropout frames (pix_th=0.02 so Mode A #111110 charcoal canvas is not false-flagged)

Unchecked spec rule:
  Omitting --expect-size, --expect-fps, or (--scenes-json / --expect-duration) marks that item NOT_CHECKED
  and exits with code 2 (never claims "ALL PASSED" on partial checks).

Review cues & visual sheets (written to --out-dir, default <video_dir>/qa):
  - qa_report.json : Full structured technical & motion diagnostics
  - qa_sheet.png   : 24-cell contact sheet across the full duration
  - qa_phone.png   : 12-cell mobile-feed thumbnail sheet (180px cell width for 9:16, 320px for 16:9)
  - Freeze classification against scenesData.json intentional pauses/tails & flash-frame spike detection

Usage:
  python scripts/inspect_video.py out/final.mp4 --expect-size 1080x1920 --expect-fps 60 --scenes-json src/data/scenesData.json
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path


def resolve_bin(name: str, ffmpeg_dir: str | None) -> str:
    if ffmpeg_dir:
        cand = Path(ffmpeg_dir).expanduser().resolve() / (f"{name}.exe" if sys.platform == "win32" else name)
        if cand.is_file():
            return str(cand)
    found = shutil.which(name)
    if found:
        return found
    raise FileNotFoundError(f"未在 PATH 中找到 {name}，请安装 ffmpeg 或传入 --ffmpeg-dir")


def probe_media(video_path: Path, ffprobe_bin: str) -> dict:
    r = subprocess.run(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "-count_packets",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe 读取失败：{r.stderr.strip()}")
    info = json.loads(r.stdout)
    streams = info.get("streams", [])
    vs = next((s for s in streams if s.get("codec_type") == "video"), None)
    aus = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not vs:
        raise RuntimeError("文件中未检测到视频流")

    num, den = (vs.get("r_frame_rate", "0/1").split("/") + ["1"])[:2]
    fps = float(num) / float(den) if float(den) else 0.0
    dur = float(info.get("format", {}).get("duration") or vs.get("duration") or 0.0)
    frames = int(vs.get("nb_read_packets") or vs.get("nb_frames") or 0)

    return {
        "width": int(vs.get("width", 0)),
        "height": int(vs.get("height", 0)),
        "fps": round(fps, 4),
        "r_frame_rate": vs.get("r_frame_rate", ""),
        "duration": round(dur, 4),
        "frames": frames,
        "has_audio": aus is not None,
        "audio_channels": int(aus.get("channels", 0)) if aus else 0,
        "audio_sr": int(aus.get("sample_rate", 0)) if aus else 0,
    }


def measure_loudness(video_path: Path, ffmpeg_bin: str) -> dict:
    r = subprocess.run(
        [
            ffmpeg_bin,
            "-hide_banner",
            "-nostats",
            "-loglevel",
            "info",
            "-i",
            str(video_path),
            "-vn",
            "-af",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    txt = r.stderr or ""
    if "Summary:" not in txt:
        raise RuntimeError("ffmpeg ebur128 未返回 Summary 响度块")
    summary = txt[txt.rfind("Summary:") :]
    m_i = re.search(r"I:\s+(-?[\d.]+)\s+LUFS", summary)
    m_lra = re.search(r"LRA:\s+(-?[\d.]+)\s+LU", summary)
    m_tp = re.search(r"Peak:\s+(-?(?:[\d.]+|inf))\s+dBFS", summary)
    if not (m_i and m_tp):
        raise RuntimeError("无法解析 ebur128 综合响度或真峰值")
    tp_str = m_tp.group(1)
    tp = -99.0 if tp_str == "-inf" else float(tp_str)
    return {
        "integrated_lufs": float(m_i.group(1)),
        "lra_lu": float(m_lra.group(1)) if m_lra else 0.0,
        "true_peak_dbtp": tp,
    }


def detect_visual_anomalies(video_path: Path, dur: float, fps: float, ffmpeg_bin: str) -> dict:
    vf = "freezedetect=n=0.0005:d=0.80,blackdetect=d=0.04:pix_th=0.02:pic_th=0.98,select='gt(scene,0.35)',metadata=print:key=lavfi.scene_score:file=-"
    r = subprocess.run(
        [ffmpeg_bin, "-hide_banner", "-nostats", "-i", str(video_path), "-vf", vf, "-an", "-f", "null", "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    txt = (r.stdout or "") + "\n" + (r.stderr or "")
    blacks = [[round(float(m.group(1)), 3), round(float(m.group(2)), 3)] for m in re.finditer(r"black_start:([\d.]+)\s+black_end:([\d.]+)", txt)]

    freezes: list[list[float]] = []
    for m in re.finditer(r"freeze_(start|end):\s*([\d.]+)", txt):
        if m.group(1) == "start":
            freezes.append([round(float(m.group(2)), 3), round(dur, 3)])
        elif freezes:
            freezes[-1][1] = round(float(m.group(2)), 3)

    cuts: list[float] = []
    for block in (r.stdout or "").split("frame:"):
        mt = re.search(r"pts_time:([\d.]+)", block)
        if mt:
            cuts.append(round(float(mt.group(1)), 3))

    # Single/two-frame flash spike: two high scene-score jumps within <= 3 frames
    max_gap = 3.2 / max(1.0, fps)
    flashes = [cuts[i] for i in range(len(cuts) - 1) if (cuts[i + 1] - cuts[i]) <= max_gap]
    return {"black_segments": blacks, "freeze_segments": freezes, "scene_cuts": cuts, "flash_spikes_sec": flashes}


def load_intended_holds(scenes_json: Path | None) -> tuple[float | None, int | None, list[tuple[float, float]]]:
    if not scenes_json or not scenes_json.is_file():
        return None, None, []
    scenes = json.loads(scenes_json.read_text(encoding="utf-8-sig"))
    if not scenes:
        return None, None, []
    fps = float(scenes[0].get("fps", 60))
    total_frames = sum(int(s.get("durationInFrames", 0)) for s in scenes)
    holds: list[tuple[float, float]] = []
    for s in scenes:
        s0 = float(s.get("startSec", 0.0))
        dur = float(s.get("durationInFrames", 0)) / fps
        lead = float(s.get("leadInSec", 0.0))
        tail = float(s.get("tailOutSec", 0.0))
        if lead >= 0.6:
            holds.append((s0, s0 + lead))
        if tail >= 0.6:
            holds.append((s0 + dur - tail, s0 + dur))
        for ln in s.get("lines", []):
            p = float(ln.get("pauseAfterSec", 0.0))
            le = float(ln.get("endSec", 0.0))
            if p >= 0.6:
                holds.append((s0 + le, s0 + le + p))
        # Static Swiss layout holds: scenes explicitly marked holdStill
        if s.get("holdStill"):
            holds.append((s0, s0 + dur))
    return round(total_frames / fps, 4), total_frames, holds


def render_contact_sheet(video_path: Path, dur: float, cells: int, cell_w: int, out_png: Path, ffmpeg_bin: str) -> bool:
    cols = 4 if cells <= 12 else 6
    rows = math.ceil(cells / cols)
    rate = max(0.05, cells / max(0.5, dur))
    vf = f"fps={rate:.5f},scale={cell_w}:-2,tile={cols}x{rows}:padding=4:color=0x1A1A18"
    out_png.unlink(missing_ok=True)
    r = subprocess.run(
        [ffmpeg_bin, "-hide_banner", "-v", "error", "-y", "-i", str(video_path), "-vf", vf, "-frames:v", "1", str(out_png)],
        capture_output=True,
        text=True,
        check=False,
    )
    return r.returncode == 0 and out_png.is_file() and out_png.stat().st_size > 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Programmatic final-video technical QA & review sheet generator.")
    ap.add_argument("video", help="Path to rendered .mp4")
    ap.add_argument("--expect-size", help="Expected WxH, e.g. 1080x1920 or 1920x1080")
    ap.add_argument("--expect-fps", type=float, help="Expected FPS, e.g. 60")
    ap.add_argument("--expect-duration", type=float, help="Expected duration in seconds")
    ap.add_argument("--scenes-json", help="Path to src/data/scenesData.json (auto-derives expected frames/duration & intentional holds)")
    ap.add_argument("--lufs-target", type=float, default=-14.0, help="Target integrated loudness (default -14.0 LUFS, +-1.5 tolerance)")
    ap.add_argument("--out-dir", help="Directory for qa_report.json / qa_sheet.png / qa_phone.png (default <video_dir>/qa)")
    ap.add_argument("--ffmpeg-dir", help="Optional directory containing ffmpeg/ffprobe binaries")
    args = ap.parse_args()

    video_path = Path(args.video).expanduser().resolve()
    if not video_path.is_file():
        print(f"FAIL: 视频文件不存在：{video_path}", file=sys.stderr)
        return 1

    ffmpeg_bin = resolve_bin("ffmpeg", args.ffmpeg_dir)
    ffprobe_bin = resolve_bin("ffprobe", args.ffmpeg_dir)
    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else (video_path.parent / "qa")
    out_dir.mkdir(parents=True, exist_ok=True)

    media = probe_media(video_path, ffprobe_bin)
    scenes_dur, scenes_frames, holds = load_intended_holds(Path(args.scenes_json).expanduser().resolve() if args.scenes_json else None)
    exp_dur = args.expect_duration if args.expect_duration is not None else scenes_dur

    checks: dict[str, dict] = {}
    checks["decode"] = {"status": "PASS" if media["frames"] > 0 else "FAIL", "actual": f"{media['frames']} frames"}

    if args.expect_size:
        m_sz = re.fullmatch(r"(\d+)x(\d+)", args.expect_size.strip().lower())
        if not m_sz:
            print(f"ERROR: --expect-size 格式无效（应为 1080x1920）：{args.expect_size}", file=sys.stderr)
            return 1
        ew, eh = int(m_sz.group(1)), int(m_sz.group(2))
        ok = media["width"] == ew and media["height"] == eh
        checks["size"] = {"status": "PASS" if ok else "FAIL", "expected": f"{ew}x{eh}", "actual": f"{media['width']}x{media['height']}"}
    else:
        checks["size"] = {"status": "NOT_CHECKED", "actual": f"{media['width']}x{media['height']}"}

    if args.expect_fps is not None:
        ok = abs(media["fps"] - args.expect_fps) <= 0.05
        checks["fps"] = {"status": "PASS" if ok else "FAIL", "expected": args.expect_fps, "actual": media["fps"]}
    else:
        checks["fps"] = {"status": "NOT_CHECKED", "actual": media["fps"]}

    calc_frames = round(media["duration"] * media["fps"])
    sync_ok = abs(media["frames"] - calc_frames) <= 2
    if exp_dur is not None:
        exp_frames = scenes_frames if scenes_frames is not None else round(exp_dur * (args.expect_fps or media["fps"]))
        dur_ok = sync_ok and abs(media["frames"] - exp_frames) <= 3
        checks["duration_and_frames"] = {
            "status": "PASS" if dur_ok else "FAIL",
            "expected_frames": exp_frames,
            "actual_frames": media["frames"],
            "actual_duration_sec": media["duration"],
        }
    else:
        checks["duration_and_frames"] = {
            "status": "NOT_CHECKED" if sync_ok else "FAIL",
            "note": "未传 --expect-duration 或 --scenes-json，仅核验内部帧数自洽",
            "actual_frames": media["frames"],
            "duration_x_fps": calc_frames,
        }

    if not media["has_audio"] or media["audio_channels"] < 2:
        checks["audio_loudness"] = {"status": "FAIL", "actual": f"has_audio={media['has_audio']}, channels={media['audio_channels']}"}
        loud = None
    else:
        loud = measure_loudness(video_path, ffmpeg_bin)
        i_ok = abs(loud["integrated_lufs"] - args.lufs_target) <= 1.5
        tp_ok = loud["true_peak_dbtp"] <= -1.0
        checks["audio_loudness"] = {
            "status": "PASS" if (i_ok and tp_ok) else "FAIL",
            "expected": f"{args.lufs_target:.1f} +- 1.5 LUFS, TP <= -1.0 dBTP",
            **loud,
        }

    vis = detect_visual_anomalies(video_path, media["duration"], media["fps"], ffmpeg_bin)
    checks["black_frames"] = {
        "status": "PASS" if len(vis["black_segments"]) == 0 else "FAIL",
        "segments": vis["black_segments"],
    }

    intended_freezes, unexplained_freezes = [], []
    for f0, f1 in vis["freeze_segments"]:
        is_hold = any(f0 >= (h0 - 0.40) and f1 <= (h1 + 0.40) for h0, h1 in holds)
        (intended_freezes if is_hold else unexplained_freezes).append([f0, f1])

    sheet_path = out_dir / "qa_sheet.png"
    phone_path = out_dir / "qa_phone.png"
    is_portrait = media["height"] > media["width"]
    sheet_ok = render_contact_sheet(video_path, media["duration"], 24, 240 if is_portrait else 320, sheet_path, ffmpeg_bin)
    phone_ok = render_contact_sheet(video_path, media["duration"], 12, 180 if is_portrait else 320, phone_path, ffmpeg_bin)

    failed = [k for k, v in checks.items() if v["status"] == "FAIL"]
    unchecked = [k for k, v in checks.items() if v["status"] == "NOT_CHECKED"]
    overall = "FAIL" if failed else ("INCOMPLETE" if unchecked else "PASS")

    report = {
        "video": str(video_path),
        "overall": overall,
        "media": media,
        "checks": checks,
        "review_cues": {
            "unexplained_freezes_sec": unexplained_freezes,
            "intended_holds_sec": intended_freezes,
            "flash_spikes_sec": vis["flash_spikes_sec"],
            "qa_sheet": str(sheet_path) if sheet_ok else None,
            "qa_phone": str(phone_path) if phone_ok else None,
        },
    }
    report_path = out_dir / "qa_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"=== 成片程序化终检报告 [{overall}] ===")
    for name, detail in checks.items():
        print(f"  [{detail['status']:11s}] {name}: {json.dumps({k: v for k, v in detail.items() if k != 'status'}, ensure_ascii=False)}")
    print(f"  [审片线索] 未声明静止段={len(unexplained_freezes)} 处 | 刻意留白静止={len(intended_freezes)} 处 | 单帧突跳={len(vis['flash_spikes_sec'])} 处")
    if sheet_ok and phone_ok:
        print(f"  [抽帧总览] {sheet_path} | 手机尺寸图: {phone_path}")
    if unchecked:
        print(f"  注意：存在未检查规格项 {unchecked}（不算全部通过，请补齐 --expect-size / --expect-fps / --scenes-json）。")

    return 1 if failed else (2 if unchecked else 0)


if __name__ == "__main__":
    raise SystemExit(main())
