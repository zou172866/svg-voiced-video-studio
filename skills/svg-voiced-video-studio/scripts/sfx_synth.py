#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Physical-modeling Paper & Ink Editorial Foley Synthesizer (v6, 32 kHz float32, zero leading silence)
with automatic real-recording WAV override slot (`assets/sfx/<kind>.wav`).

Replaces generic MG synth sounds (`whoosh/pop/chime`) with tactile archival paper, seal stamp,
nib-on-paper, and drafting ruler foley matching Swiss warm-paper visuals:
  - page_turn   (alias: whoosh) : Dry archival sheet lift -> arched crease flick -> soft paper settle
                                  (peak_offset_sec = 0.62 * dur for J-cut alignment).
  - stamp_thud  (alias: impact) : Heavy stone/rubber vermilion seal stamp pressed onto thick paper stack
                                  on a wooden desk (dry damped thud, phone-audible mid body, <= 2 per film).
  - pen_stroke  (alias: chime)  : Fountain pen / reed nib gliding across textured cotton paper grain.
  - ruler_drop  (alias: pop)    : Wooden/brass straightedge settling onto drafting desk (crisp tactile double-tap).
  - ledger_tick (alias: tick)   : Dry mechanical brass/wood vernier detent click for rolling counters.

Drop recorded or CC0 WAVs into `<skill>/assets/sfx/<kind>.wav` (e.g. `page_turn.wav`, `stamp_thud.wav`)
to seamlessly override the procedural synthesis with zero code changes.

CLI usage:
  python scripts/sfx_synth.py --demo-dir path/to/out_sfx
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, resample_poly, sosfilt

DEFAULT_SR = 32000
SKILL_SFX_DIR = Path(__file__).resolve().parent.parent / "assets" / "sfx"

CANONICAL_ALIASES = {
    "page_turn": "page_turn",
    "whoosh": "page_turn",
    "stamp_thud": "stamp_thud",
    "impact": "stamp_thud",
    "pen_stroke": "pen_stroke",
    "chime": "pen_stroke",
    "ruler_drop": "ruler_drop",
    "pop": "ruler_drop",
    "ledger_tick": "ledger_tick",
    "tick": "ledger_tick",
}

DEFAULT_PEAK_OFFSET = {
    "page_turn": 0.20,
    "stamp_thud": 0.012,
    "pen_stroke": 0.055,
    "ruler_drop": 0.004,
    "ledger_tick": 0.002,
}


def _fade_edges(w: np.ndarray, sr: int, head_ms: float = 1.5, tail_ms: float = 14.0, peak_gain: float = 0.85) -> np.ndarray:
    out = w.astype(np.float32, copy=True)
    n = len(out)
    if n < 8:
        return out
    nh = min(max(2, int(sr * head_ms / 1000.0)), n // 4)
    nt = min(max(4, int(sr * tail_ms / 1000.0)), n // 2)
    out[:nh] *= 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, nh, dtype=np.float32)))
    out[-nt:] *= 0.5 * (1.0 + np.cos(np.linspace(0.0, np.pi, nt, dtype=np.float32)))
    peak = float(np.max(np.abs(out))) + 1e-9
    return (out / peak * peak_gain).astype(np.float32)


def _bp(sig: np.ndarray, sr: int, lo: float, hi: float, order: int = 2) -> np.ndarray:
    nyq = 0.5 * sr
    lo_n = max(1e-4, min(0.95, lo / nyq))
    hi_n = max(lo_n + 1e-3, min(0.98, hi / nyq))
    sos = butter(order, [lo_n, hi_n], btype="bandpass", output="sos")
    return sosfilt(sos, sig).astype(np.float32)


def _lp(sig: np.ndarray, sr: int, cutoff: float, order: int = 2) -> np.ndarray:
    nyq = 0.5 * sr
    c = max(1e-4, min(0.96, cutoff / nyq))
    sos = butter(order, c, btype="lowpass", output="sos")
    return sosfilt(sos, sig).astype(np.float32)


def _try_load_override_wav(canonical: str, sr: int) -> tuple[np.ndarray, float] | None:
    wav_path = SKILL_SFX_DIR / f"{canonical}.wav"
    if not wav_path.is_file():
        return None
    data, file_sr = sf.read(str(wav_path), dtype="float32", always_2d=False)
    if data.ndim == 2:
        data = np.mean(data, axis=1).astype(np.float32)
    if file_sr != sr and file_sr > 0:
        g = int(np.gcd(sr, file_sr))
        data = resample_poly(data, sr // g, file_sr // g).astype(np.float32)
    peak_idx = int(np.argmax(np.abs(data))) if len(data) else 0
    peak_off = round(peak_idx / float(sr), 4)
    return _fade_edges(data, sr, head_ms=1.5, tail_ms=12.0), peak_off


def synth_page_turn(sr: int = DEFAULT_SR, dur_sec: float = 0.34, tone: str = "crisp", seed: int = 17) -> tuple[np.ndarray, float]:
    """
    Physical paper page-turn foley:
    1. Dry finger-edge slide (light papery fiber rustle)
    2. Arched sheet flip crest (broader crisp paper bend + delicate crease crackle)
    3. Soft flat paper settle onto stack (muffled low-mid air cushion)
    """
    n = max(64, int(round(dur_sec * sr)))
    t = np.arange(n, dtype=np.float32) / sr
    u = t / max(1e-6, dur_sec)
    rng = np.random.default_rng(seed)

    # White + subtle pink-ish fiber noise
    raw = rng.standard_normal(n).astype(np.float32)
    # Granular paper micro-modulation (irregular crinkle texture, never smooth synth noise)
    mod_noise = np.abs(_lp(rng.standard_normal(n).astype(np.float32), sr, 42.0, order=2))
    mod_noise = 0.45 + 0.55 * (mod_noise / (np.max(mod_noise) + 1e-6))

    # Layer 1: High dry paper fiber friction (peaking at u=0.62)
    peak_u = 0.62
    fiber_env = np.where(
        u <= peak_u,
        np.power(u / peak_u, 1.8),
        np.power(np.maximum(0.0, (1.0 - u) / (1.0 - peak_u)), 2.2),
    ).astype(np.float32)
    hi_lo, hi_hi = (1600.0, 6800.0) if tone == "crisp" else (1200.0, 4800.0)
    fiber = _bp(raw, sr, hi_lo, hi_hi, order=2) * fiber_env * mod_noise * 0.72

    # Layer 2: Mid-band sheet body rustle (flexing heavy matte stock 520-1850 Hz)
    body_env = np.exp(-0.5 * ((u - 0.58) / 0.16) ** 2).astype(np.float32)
    body = _bp(rng.standard_normal(n).astype(np.float32), sr, 520.0, 1850.0, order=2) * body_env * 0.58

    # Layer 3: Crisp tiny paper-bend snap near peak_u
    snap_t = np.maximum(0.0, t - peak_u * dur_sec)
    snap_mask = (t >= peak_u * dur_sec).astype(np.float32)
    snap = _bp(rng.standard_normal(n).astype(np.float32), sr, 2400.0, 7200.0, order=2) * np.exp(-snap_t / 0.014) * snap_mask * 0.55

    # Layer 4: Soft flat landing puff (u=0.80)
    puff_env = np.exp(-0.5 * ((u - 0.80) / 0.08) ** 2).astype(np.float32)
    puff = _bp(rng.standard_normal(n).astype(np.float32), sr, 190.0, 560.0, order=2) * puff_env * 0.36

    out = _fade_edges(fiber + body + snap + puff, sr, head_ms=4.0, tail_ms=22.0, peak_gain=0.82)
    return out, round(peak_u * dur_sec, 4)


def synth_stamp_thud(sr: int = DEFAULT_SR, seed: int = 29) -> tuple[np.ndarray, float]:
    """
    Physical vermilion seal stamp thud (~0.24s):
    Stone/hardwood chop pressing solidly onto a paper pad over a wooden desk —
    dry damped contact thump + warm woody resonance + subtle micro paper release.
    """
    dur = 0.24
    n = int(round(dur * sr))
    t = np.arange(n, dtype=np.float32) / sr
    rng = np.random.default_rng(seed)

    # Damped woody desk / paper stack body (tight decay, zero electronic sine boom)
    f0 = 104.0 + 38.0 * np.exp(-t / 0.014)
    ph = 2.0 * np.pi * np.cumsum(f0) / sr
    wood_body = (
        0.72 * np.sin(ph) * np.exp(-t / 0.044)
        + 0.44 * np.sin(1.72 * ph + 0.4) * np.exp(-t / 0.028)
        + 0.26 * np.sin(2.85 * ph + 1.1) * np.exp(-t / 0.016)
    )

    # Tactile rubber/stone-on-paper press impulse (crisp damped noise transient)
    press_noise = rng.standard_normal(n).astype(np.float32)
    press = (
        _bp(press_noise, sr, 260.0, 1450.0, order=2) * np.exp(-t / 0.011) * 0.85
        + _bp(rng.standard_normal(n).astype(np.float32), sr, 1400.0, 3800.0, order=2) * np.exp(-t / 0.005) * 0.32
    )

    # Tiny dry ink-pad peel/release 95ms later (subtle tactile realism)
    peel_start = 0.095
    peel_t = np.maximum(0.0, t - peel_start)
    peel_mask = (t >= peel_start).astype(np.float32)
    peel = (
        _bp(rng.standard_normal(n).astype(np.float32), sr, 1800.0, 5200.0, order=2)
        * np.exp(-peel_t / 0.018)
        * peel_mask
        * 0.09
    )

    out = _fade_edges(wood_body + press + peel, sr, head_ms=1.2, tail_ms=26.0, peak_gain=0.86)
    return out, 0.010


def synth_pen_stroke(sr: int = DEFAULT_SR, dur_sec: float = 0.26, tone: str = "crisp", seed: int = 43) -> tuple[np.ndarray, float]:
    """
    Physical fountain-pen / nib stroke across textured cotton rag paper (~0.26s):
    Granular high-frequency paper-tooth micro-friction with natural press-and-lift pressure contour.
    """
    n = max(64, int(round(dur_sec * sr)))
    t = np.arange(n, dtype=np.float32) / sr
    u = t / max(1e-6, dur_sec)
    rng = np.random.default_rng(seed)

    # Rapid asymmetric pressure contour: firm nib touch -> steady glide -> crisp lift
    pressure = np.power(np.sin(np.pi * np.clip(u, 0.0, 1.0)), 0.75) * np.exp(-u * 0.85)

    # Paper tooth micro-grain: bursty pulse train modeling fiber roughness under a moving metal nib
    grain = np.abs(_bp(rng.standard_normal(n).astype(np.float32), sr, 35.0, 140.0, order=2))
    grain = 0.30 + 0.70 * (grain / (np.max(grain) + 1e-6))

    lo, hi = (2000.0, 7400.0) if tone == "crisp" else (1500.0, 5600.0)
    nib_scratch = _bp(rng.standard_normal(n).astype(np.float32), sr, lo, hi, order=2) * grain * pressure * 0.78
    # Subtle resonant body of wooden/metal pen barrel on paper (~900-1900 Hz)
    barrel = _bp(rng.standard_normal(n).astype(np.float32), sr, 880.0, 1950.0, order=2) * pressure * 0.36
    # Initial nib touch click
    touch = _bp(rng.standard_normal(n).astype(np.float32), sr, 2600.0, 6200.0, order=2) * np.exp(-t / 0.004) * 0.32

    out = _fade_edges(nib_scratch + barrel + touch, sr, head_ms=2.0, tail_ms=24.0, peak_gain=0.76)
    return out, 0.045


def synth_ruler_drop(sr: int = DEFAULT_SR, tone: str = "crisp", seed: int = 61) -> tuple[np.ndarray, float]:
    """
    Physical drafting ruler settling onto a wooden desk (~0.16s):
    Two crisp, tightly damped wooden/brass contact taps ~36ms apart (primary edge + settling end).
    """
    dur = 0.16
    n = int(round(dur * sr))
    t = np.arange(n, dtype=np.float32) / sr
    rng = np.random.default_rng(seed)

    def _wood_tap(t_rel: np.ndarray, mask: np.ndarray, gain: float, bright: float = 1.0) -> np.ndarray:
        f1 = 580.0 * bright if tone == "crisp" else 460.0 * bright
        f2 = 1280.0 * bright if tone == "crisp" else 1020.0 * bright
        f3 = 2360.0 * bright
        modes = (
            0.55 * np.sin(2.0 * np.pi * f1 * t_rel) * np.exp(-t_rel / 0.015)
            + 0.38 * np.sin(2.0 * np.pi * f2 * t_rel + 0.6) * np.exp(-t_rel / 0.009)
            + 0.22 * np.sin(2.0 * np.pi * f3 * t_rel + 1.2) * np.exp(-t_rel / 0.005)
        )
        imp = _bp(rng.standard_normal(n).astype(np.float32), sr, 900.0, 4600.0, order=2) * np.exp(-t_rel / 0.0045) * 0.65
        return (modes + imp) * mask * gain

    hit1 = _wood_tap(t, np.ones_like(t), gain=1.0, bright=1.0)
    t2 = np.maximum(0.0, t - 0.036)
    m2 = (t >= 0.036).astype(np.float32)
    hit2 = _wood_tap(t2, m2, gain=0.42, bright=1.14)

    out = _fade_edges(hit1 + hit2, sr, head_ms=0.8, tail_ms=16.0, peak_gain=0.84)
    return out, 0.004


def synth_ledger_tick(sr: int = DEFAULT_SR, seed: int = 73) -> tuple[np.ndarray, float]:
    """Ultra-dry mechanical brass/wood vernier detent tick (~32ms) for rolling counters."""
    dur = 0.032
    n = int(round(dur * sr))
    t = np.arange(n, dtype=np.float32) / sr
    rng = np.random.default_rng(seed)

    detent = (
        0.55 * np.sin(2.0 * np.pi * 1380.0 * t) * np.exp(-t / 0.0038)
        + 0.35 * np.sin(2.0 * np.pi * 2940.0 * t + 0.5) * np.exp(-t / 0.0020)
    )
    click = _bp(rng.standard_normal(n).astype(np.float32), sr, 1800.0, 6400.0, order=2) * np.exp(-t / 0.0028) * 0.72
    out = _fade_edges(detent + click, sr, head_ms=0.5, tail_ms=6.0, peak_gain=0.80)
    return out, 0.002


def generate_sfx(kind: str, sr: int = DEFAULT_SR, tone: str = "crisp", seed: int = 17) -> tuple[np.ndarray, float]:
    """Dispatch helper returning (mono_float32_wave, peak_offset_sec). Prefers assets/sfx/<kind>.wav if present."""
    canonical = CANONICAL_ALIASES.get(kind)
    if not canonical:
        raise ValueError(
            f"Unknown SFX kind: {kind!r} (expected page_turn|stamp_thud|pen_stroke|ruler_drop|ledger_tick or legacy aliases)"
        )

    override = _try_load_override_wav(canonical, sr)
    if override is not None:
        return override

    if canonical == "page_turn":
        return synth_page_turn(sr=sr, dur_sec=0.32 if tone == "crisp" else 0.40, tone=tone, seed=seed)
    if canonical == "stamp_thud":
        return synth_stamp_thud(sr=sr, seed=seed)
    if canonical == "pen_stroke":
        return synth_pen_stroke(sr=sr, dur_sec=0.25 if tone == "crisp" else 0.32, tone=tone, seed=seed)
    if canonical == "ruler_drop":
        return synth_ruler_drop(sr=sr, tone=tone, seed=seed)
    if canonical == "ledger_tick":
        return synth_ledger_tick(sr=sr, seed=seed)
    raise AssertionError(canonical)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate physical-modeling 32kHz paper-and-ink editorial foley WAVs.")
    ap.add_argument("--demo-dir", required=True, help="Directory to write sample WAV files")
    ap.add_argument("--tone", choices=["crisp", "warm"], default="crisp")
    args = ap.parse_args()

    out_dir = Path(args.demo_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    for kind in ("page_turn", "stamp_thud", "pen_stroke", "ruler_drop", "ledger_tick"):
        wav, peak_off = generate_sfx(kind, sr=DEFAULT_SR, tone=args.tone)
        out_path = out_dir / f"{kind}.wav"
        sf.write(str(out_path), wav, DEFAULT_SR, subtype="PCM_16")
        print(f"[FOLEY] {kind:12s} -> {out_path.name} ({len(wav)/DEFAULT_SR*1000:.0f} ms, peak_offset={peak_off*1000:.0f} ms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
