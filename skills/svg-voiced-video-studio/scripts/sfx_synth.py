#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zero-dependency procedural editorial SFX synthesizer (32 kHz float32, zero leading silence).

Provides five clean, warm, paper/acoustic-grade sound effects tailored for Swiss editorial
and philosophical SVG essays:
  - whoosh : Asymmetric air/paper sweep; returns peak_offset_sec = 0.70 * dur so placing at
             (cut_sec - peak_offset_sec) lands the crest right on the visual cut.
  - pop    : Tactile wooden/paper pop (~75 ms) for badge/keyword arrival.
  - tick   : Crisp mechanical ledger tick (~28 ms) for rolling counters.
  - chime  : Warm fifth harmonic bell (~0.85 s) for key insight / chapter payoff.
  - impact : Editorial seal stamp with phone-audible 2nd/3rd harmonics (~0.52 s; <=2 per film).

CLI usage:
  python scripts/sfx_synth.py --demo-dir path/to/out_sfx
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

DEFAULT_SR = 32000


def _fade_edges(w: np.ndarray, sr: int, head_ms: float = 1.5, tail_ms: float = 12.0) -> np.ndarray:
    out = w.astype(np.float32, copy=True)
    n = len(out)
    nh = min(max(2, int(sr * head_ms / 1000.0)), n // 4)
    nt = min(max(4, int(sr * tail_ms / 1000.0)), n // 2)
    out[:nh] *= 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, nh, dtype=np.float32)))
    out[-nt:] *= 0.5 * (1.0 + np.cos(np.linspace(0.0, np.pi, nt, dtype=np.float32)))
    peak = float(np.max(np.abs(out))) + 1e-9
    return (out / peak * 0.85).astype(np.float32)


def synth_whoosh(sr: int = DEFAULT_SR, dur_sec: float = 0.28, tone: str = "crisp", seed: int = 17) -> tuple[np.ndarray, float]:
    """Swept bandpass air/paper whoosh. Peak sits at 0.70 * dur_sec."""
    n = max(64, int(round(dur_sec * sr)))
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(n).astype(np.float32)

    # Time-varying sweep approximated via 6 overlapping bandpass slices for deterministic speed
    f_lo, f_mid, f_hi = (240.0, 1750.0, 520.0) if tone == "crisp" else (160.0, 920.0, 260.0)
    u = np.linspace(0.0, 1.0, n, dtype=np.float32)
    peak_u = 0.70
    env = np.where(
        u <= peak_u,
        np.power(u / peak_u, 2.1),
        np.power(np.maximum(0.0, (1.0 - u) / (1.0 - peak_u)), 1.7),
    ).astype(np.float32)

    swept = np.zeros(n, dtype=np.float32)
    bands = 6
    for k in range(bands):
        u_c = (k + 0.5) / bands
        fc = f_lo + (f_mid - f_lo) * (u_c / peak_u) if u_c <= peak_u else f_mid + (f_hi - f_mid) * ((u_c - peak_u) / (1.0 - peak_u))
        lo = max(60.0, fc * 0.58)
        hi = min(sr * 0.45, fc * 1.65)
        sos = butter(2, [lo / (0.5 * sr), hi / (0.5 * sr)], btype="bandpass", output="sos")
        band_sig = sosfilt(sos, noise).astype(np.float32)
        w_k = np.exp(-0.5 * ((u - u_c) / (0.85 / bands)) ** 2).astype(np.float32)
        swept += band_sig * w_k

    out = _fade_edges(swept * env, sr, head_ms=3.0, tail_ms=18.0)
    return out, round(peak_u * dur_sec, 4)


def synth_pop(sr: int = DEFAULT_SR, pitch_hz: float = 520.0) -> tuple[np.ndarray, float]:
    """Zero-latency tactile paper/wood pop (~75 ms)."""
    dur = 0.075
    n = int(round(dur * sr))
    t = np.arange(n, dtype=np.float32) / sr
    freq = pitch_hz * (1.0 + 0.70 * np.exp(-t / 0.011))
    phase = 2.0 * np.pi * np.cumsum(freq) / sr
    body = np.sin(phase) * np.exp(-t / 0.019) + 0.28 * np.sin(2.0 * phase) * np.exp(-t / 0.010)
    return _fade_edges(body, sr, head_ms=1.0, tail_ms=10.0), 0.0


def synth_tick(sr: int = DEFAULT_SR, pitch_hz: float = 1480.0) -> tuple[np.ndarray, float]:
    """Crisp mechanical Swiss ledger tick (~28 ms) for rolling number counters."""
    dur = 0.028
    n = int(round(dur * sr))
    t = np.arange(n, dtype=np.float32) / sr
    click = (
        np.sin(2.0 * np.pi * pitch_hz * t) * np.exp(-t / 0.0045)
        + 0.45 * np.sin(2.0 * np.pi * (pitch_hz * 2.15) * t) * np.exp(-t / 0.0022)
    )
    return _fade_edges(click, sr, head_ms=0.6, tail_ms=5.0), 0.0


def synth_chime(sr: int = DEFAULT_SR, root_hz: float = 587.33) -> tuple[np.ndarray, float]:
    """Warm acoustic bell fifth (D5 + A5) with fast-decaying overtone (~0.85 s)."""
    dur = 0.85
    n = int(round(dur * sr))
    t = np.arange(n, dtype=np.float32) / sr
    fifth = root_hz * 1.4983
    tone = (
        0.62 * np.sin(2.0 * np.pi * root_hz * t) * np.exp(-t / 0.34)
        + 0.32 * np.sin(2.0 * np.pi * fifth * t) * np.exp(-t / 0.26)
        + 0.14 * np.sin(2.0 * np.pi * (root_hz * 2.756) * t) * np.exp(-t / 0.075)
    )
    return _fade_edges(tone, sr, head_ms=2.0, tail_ms=45.0), 0.0


def synth_impact(sr: int = DEFAULT_SR) -> tuple[np.ndarray, float]:
    """Editorial seal stamp (~0.52 s) with 2nd/3rd harmonics audible on mobile speakers."""
    dur = 0.52
    n = int(round(dur * sr))
    t = np.arange(n, dtype=np.float32) / sr
    f_sweep = 48.0 + 96.0 * np.exp(-t / 0.032)
    phase = 2.0 * np.pi * np.cumsum(f_sweep) / sr
    sub = (
        0.65 * np.sin(phase) * np.exp(-t / 0.16)
        + 0.38 * np.sin(2.0 * phase) * np.exp(-t / 0.11)
        + 0.20 * np.sin(3.0 * phase) * np.exp(-t / 0.07)
    )
    rng = np.random.default_rng(29)
    snap_noise = rng.standard_normal(n).astype(np.float32)
    sos = butter(2, [350.0 / (0.5 * sr), 2600.0 / (0.5 * sr)], btype="bandpass", output="sos")
    transient = sosfilt(sos, snap_noise).astype(np.float32) * np.exp(-t / 0.012) * 0.35
    return _fade_edges(sub + transient, sr, head_ms=1.2, tail_ms=35.0), 0.0


def generate_sfx(kind: str, sr: int = DEFAULT_SR, tone: str = "crisp", seed: int = 17) -> tuple[np.ndarray, float]:
    """Dispatch helper returning (mono_float32_wave, peak_offset_sec)."""
    if kind == "whoosh":
        return synth_whoosh(sr=sr, dur_sec=0.26 if tone == "crisp" else 0.34, tone=tone, seed=seed)
    if kind == "pop":
        return synth_pop(sr=sr, pitch_hz=540.0 if tone == "crisp" else 440.0)
    if kind == "tick":
        return synth_tick(sr=sr)
    if kind == "chime":
        return synth_chime(sr=sr, root_hz=587.33 if tone == "crisp" else 523.25)
    if kind == "impact":
        return synth_impact(sr=sr)
    raise ValueError(f"Unknown SFX kind: {kind!r} (expected whoosh|pop|tick|chime|impact)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate procedural 32kHz editorial SFX WAVs.")
    ap.add_argument("--demo-dir", required=True, help="Directory to write sample WAV files")
    ap.add_argument("--tone", choices=["crisp", "warm"], default="crisp")
    args = ap.parse_args()

    out_dir = Path(args.demo_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    for kind in ("whoosh", "pop", "tick", "chime", "impact"):
        wav, peak_off = generate_sfx(kind, sr=DEFAULT_SR, tone=args.tone)
        out_path = out_dir / f"{kind}.wav"
        sf.write(str(out_path), wav, DEFAULT_SR, subtype="PCM_16")
        print(f"[SFX] {kind:7s} -> {out_path.name} ({len(wav)/DEFAULT_SR*1000:.0f} ms, peak_offset={peak_off*1000:.0f} ms)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
