#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pure-math vocal sound-effect presets adapted from kaikou (canyon / tape / water).
- Zero external audio assets required (100% reproducible numpy + scipy synthesis).
- Built-in pure-scipy ITU-R BS.1770-4 K-weighted loudness matching (no pyloudnorm needed).
- Supports .wav and .mp3 output.

Usage:
  python scripts/voice_fx.py canyon input.wav output_canyon.wav
  python scripts/voice_fx.py tape   input.wav output_tape.wav [--seed 3]
  python scripts/voice_fx.py water  input.wav output_water.wav
  python scripts/voice_fx.py all    input.wav output_dir/
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import butter, fftconvolve, sosfilt

SR = 48000

PRESETS = {
    # 空谷回响：长混响打底 + 4 次左右交替、逐次变暗的远山回声（适合古文原句引述、旷野哲思发问）
    "canyon": dict(
        rt60=3.2,
        predelay=0.045,
        wet=0.22,
        tail_lp=3500,
        echoes=4,
        gap=0.55,
        decay_db=6.5,
        echo_lp=(5200, 3600, 2500, 1700),
    ),
    # 老式磁带录音机：窄频带 + 轻微磁饱和 + 转速慢晃快抖 + 极轻底噪（适合年代回忆、旧信独白）
    "tape": dict(
        band=(320, 3600),
        drive=2.2,
        wow_hz=0.55,
        wow_ms=1.6,
        flutter_hz=7.5,
        flutter_ms=0.12,
        hiss_db=-54,
        hum_db=-58,
    ),
    # 水下说话：700Hz 低通包裹感 + 缓慢摇晃 + 偶发上滑气泡音（适合潜意识深处、沉没比喻句）
    "water": dict(
        lp=700,
        lp_order=4,
        sway_hz=0.7,
        sway_ms=2.2,
        bubbles=10,
        rumble_db=-50,
        wet_body=0.25,
    ),
}


def compute_lufs_bs1770(y: np.ndarray, sr: int = SR) -> float:
    """Pure-scipy ITU-R BS.1770-4 K-weighted integrated loudness approximation (48kHz native)."""
    x = np.asarray(y, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    if sr != 48000:
        chans = [librosa.resample(x[:, c].astype(np.float32), orig_sr=sr, target_sr=48000) for c in range(x.shape[1])]
        x = np.stack(chans, axis=1).astype(np.float64)
        sr = 48000

    # Stage 1: ITU-R BS.1770-4 48kHz high-shelf pre-filter (+4dB above 1.5kHz)
    b1 = np.array([1.53512485958697, -2.69169618940638, 1.19839281085285], dtype=np.float64)
    a1 = np.array([1.0, -1.69065929318241, 0.73248077421585], dtype=np.float64)
    # Stage 2: RLB high-pass weighting filter (~38Hz)
    b2 = np.array([1.0, -2.0, 1.0], dtype=np.float64)
    a2 = np.array([1.0, -1.99004745483398, 0.99007225036621], dtype=np.float64)
    sos_k = np.vstack([np.hstack([b1, a1]), np.hstack([b2, a2])])

    kw = sosfilt(sos_k, x, axis=0)
    block = int(0.4 * sr)
    step = int(0.1 * sr)
    if len(kw) < block:
        ms = float(np.mean(np.sum(kw**2, axis=1)))
        return float(-0.691 + 10.0 * np.log10(max(ms, 1e-12)))

    energies = []
    for start in range(0, len(kw) - block + 1, step):
        seg = kw[start : start + block]
        energies.append(float(np.mean(np.sum(seg**2, axis=1))))
    e_arr = np.array(energies, dtype=np.float64)
    l_blocks = -0.691 + 10.0 * np.log10(np.maximum(e_arr, 1e-12))

    # Absolute gate (-70 LUFS) & relative gate (-10 LU)
    keep_abs = e_arr[l_blocks > -70.0]
    if len(keep_abs) == 0:
        return -70.0
    rel_thr = -0.691 + 10.0 * np.log10(float(np.mean(keep_abs))) - 10.0
    keep_rel = e_arr[l_blocks > rel_thr]
    mean_e = float(np.mean(keep_rel)) if len(keep_rel) > 0 else float(np.mean(keep_abs))
    return float(-0.691 + 10.0 * np.log10(max(mean_e, 1e-12)))


def load_mono_48k(path: str | Path) -> np.ndarray:
    y, sr = sf.read(str(path), dtype="float32", always_2d=True)
    mono = y.mean(axis=1)
    if sr != SR:
        mono = librosa.resample(mono, orig_sr=sr, target_sr=SR)
    return mono.astype(np.float64)


def match_loudness(y: np.ndarray, ref: np.ndarray) -> np.ndarray:
    ref_lufs = compute_lufs_bs1770(ref, SR)
    cur_lufs = compute_lufs_bs1770(y, SR)
    gain = 10.0 ** ((ref_lufs - cur_lufs) / 20.0)
    out = y * min(gain, 6.0)
    peak = float(np.max(np.abs(out)))
    return out / peak * 0.891 if peak > 0.891 else out


def _sos(kind: str, f, order: int = 4) -> np.ndarray:
    return butter(order, f, kind, fs=SR, output="sos")


def _mod_delay(x: np.ndarray, base_ms: float, depth_ms: float, hz: float, phase: float = 0.0, extra=None) -> np.ndarray:
    n = np.arange(len(x))
    d = base_ms + depth_ms * np.sin(2.0 * np.pi * hz * n / SR + phase)
    if extra is not None:
        d = d + extra
    pos = n - d * SR / 1000.0
    i = np.clip(np.floor(pos).astype(int), 0, len(x) - 2)
    f = np.clip(pos - i, 0.0, 1.0)
    return x[i] * (1.0 - f) + x[i + 1] * f


def _synth_ir(rt60: float, predelay: float, lp: float, rng: np.random.Generator, stereo: bool = True) -> np.ndarray:
    n = int((rt60 * 1.2 + predelay) * SR)
    t = np.arange(n) / SR
    env = np.exp(-6.91 * t / rt60)
    chans = []
    for _ in range(2 if stereo else 1):
        noise = rng.standard_normal(n) * env
        noise = sosfilt(_sos("lowpass", lp, 2), noise)
        noise[: int(predelay * SR)] = 0.0
        chans.append(noise / (np.sqrt(np.sum(noise**2)) + 1e-12))
    return np.stack(chans, axis=1)


def fx_canyon(x: np.ndarray, p: dict, rng: np.random.Generator) -> np.ndarray:
    pad = np.concatenate([x, np.zeros(int(SR * (p["rt60"] + p["gap"] * p["echoes"] + 0.5)))])
    ir = _synth_ir(p["rt60"], p["predelay"], p["tail_lp"], rng)
    wet = np.stack([fftconvolve(pad, ir[:, c])[: len(pad)] for c in (0, 1)], axis=1)
    out = np.stack([pad, pad], axis=1) * (1.0 - p["wet"]) + wet * p["wet"] * 1.4
    for k in range(1, p["echoes"] + 1):
        sh = int(p["gap"] * k * SR)
        lp_hz = p["echo_lp"][min(k - 1, len(p["echo_lp"]) - 1)]
        e = sosfilt(_sos("lowpass", lp_hz, 2), pad)
        e = np.concatenate([np.zeros(sh), e])[: len(pad)] * (10.0 ** (-p["decay_db"] * k / 20.0))
        pan = 0.5 + (0.22 if k % 2 else -0.22)
        e_wet = np.stack([fftconvolve(e, ir[:, c])[: len(pad)] for c in (0, 1)], axis=1)
        out += np.stack([e * (1.0 - pan), e * pan], axis=1) * 1.1 + e_wet * 0.22
    return out


def fx_tape(x: np.ndarray, p: dict, rng: np.random.Generator) -> np.ndarray:
    n = len(x)
    y = sosfilt(_sos("bandpass", p["band"], 4), x)
    y = np.tanh(y / (np.max(np.abs(y)) + 1e-9) * p["drive"]) / np.tanh(p["drive"])
    drift = np.cumsum(rng.standard_normal(n)) / SR
    drift = sosfilt(_sos("lowpass", 0.3, 1), drift)
    drift = drift / (np.max(np.abs(drift)) + 1e-9) * 0.6
    flutter = p["flutter_ms"] * np.sin(2.0 * np.pi * p["flutter_hz"] * np.arange(n) / SR)
    y = _mod_delay(y, 4.0, p["wow_ms"], p["wow_hz"], extra=flutter + drift)
    hiss = sosfilt(_sos("bandpass", (1500, 7000), 2), rng.standard_normal(n))
    hiss *= (10.0 ** (p["hiss_db"] / 20.0)) / (np.sqrt(np.mean(hiss**2)) + 1e-9)
    hum = (10.0 ** (p["hum_db"] / 20.0)) * np.sin(2.0 * np.pi * 50.0 * np.arange(n) / SR)
    y = y * 0.6 + hiss + hum
    return np.stack([y, y], axis=1)


def _bubble(rng: np.random.Generator, dur: float = 0.09) -> np.ndarray:
    t = np.arange(int(dur * SR)) / SR
    f0 = rng.uniform(380, 900)
    f = f0 * (1.0 + 1.6 * t / dur)
    ph = 2.0 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t / (dur / 4.0)) * rng.uniform(0.3, 1.0)


def fx_water(x: np.ndarray, p: dict, rng: np.random.Generator) -> np.ndarray:
    n = len(x)
    y = _mod_delay(x, 6.0, p["sway_ms"], p["sway_hz"])
    y = sosfilt(_sos("lowpass", p["lp"], p["lp_order"]), y)
    y = sosfilt(_sos("highpass", 90, 2), y)
    ir = _synth_ir(0.35, 0.008, 900, rng, stereo=False)[:, 0]
    y = y * (1.0 - p["wet_body"]) + fftconvolve(y, ir)[:n] * p["wet_body"] * 3.0
    bub = np.zeros(n)
    for _ in range(max(1, int(p["bubbles"] * n / SR / 10.0))):
        b = _bubble(rng)
        s = int(rng.integers(0, max(1, n - len(b))))
        bub[s : s + len(b)] += b
        if rng.random() < 0.5:
            for k in range(int(rng.integers(2, 5))):
                b2 = _bubble(rng, float(rng.uniform(0.05, 0.08)))
                s2 = s + int(rng.uniform(0.04, 0.12) * SR * (k + 1))
                if s2 + len(b2) < n:
                    bub[s2 : s2 + len(b2)] += b2 * 0.7
    bub = bub / (np.max(np.abs(bub)) + 1e-9) * 0.06
    rum = sosfilt(_sos("lowpass", 140, 2), rng.standard_normal(n))
    rum *= (10.0 ** (p["rumble_db"] / 20.0)) / (np.sqrt(np.mean(rum**2)) + 1e-9)
    return np.stack([y + bub * 0.9 + rum, y + bub * 0.6 + rum], axis=1)


FX_MAP = {"canyon": fx_canyon, "tape": fx_tape, "water": fx_water}


def apply_voice_fx_array(audio: np.ndarray, orig_sr: int, kind: str, seed: int = 3) -> tuple[np.ndarray, int]:
    """In-memory helper callable directly from synth_voiceover_template.py."""
    mono = audio.mean(axis=1) if audio.ndim > 1 else audio
    x48 = librosa.resample(mono.astype(np.float32), orig_sr=orig_sr, target_sr=SR).astype(np.float64) if orig_sr != SR else mono.astype(np.float64)
    rng = np.random.default_rng(seed)
    y = FX_MAP[kind](x48, PRESETS[kind], rng)
    y = match_loudness(y, x48)
    env = np.max(np.abs(y), axis=1)
    keep = np.where(env > 10.0 ** (-70.0 / 20.0))[0]
    y = y[: keep[-1] + int(0.05 * SR)] if len(keep) else y
    f = min(int(0.008 * SR), len(y) // 4)
    if f > 2:
        r = np.linspace(0.0, 1.0, f)[:, None]
        y[:f] *= r
        y[-f:] *= r[::-1]
    mono_out = y.mean(axis=1).astype(np.float32)
    if orig_sr != SR:
        mono_out = librosa.resample(mono_out, orig_sr=SR, target_sr=orig_sr)
    return mono_out, orig_sr


def run_fx(kind: str, src: str | Path, dst: str | Path, seed: int = 3, ffmpeg_bin: str = "ffmpeg") -> str:
    x = load_mono_48k(src)
    rng = np.random.default_rng(seed)
    y = FX_MAP[kind](x, PRESETS[kind], rng)
    y = match_loudness(y, x)
    env = np.max(np.abs(y), axis=1)
    keep = np.where(env > 10.0 ** (-70.0 / 20.0))[0]
    y = y[: keep[-1] + int(0.05 * SR)] if len(keep) else y
    f = min(int(0.008 * SR), len(y) // 4)
    if f > 2:
        r = np.linspace(0.0, 1.0, f)[:, None]
        y[:f] *= r
        y[-f:] *= r[::-1]

    dst_p = Path(dst)
    dst_p.parent.mkdir(parents=True, exist_ok=True)
    if dst_p.suffix.lower() == ".mp3" and shutil.which(ffmpeg_bin):
        tmp_wav = dst_p.with_suffix(".tmp_fx.wav")
        sf.write(str(tmp_wav), y.astype(np.float32), SR, subtype="PCM_24")
        subprocess.run([ffmpeg_bin, "-v", "error", "-y", "-i", str(tmp_wav), "-ar", "44100", "-ac", "2", "-b:a", "192k", str(dst_p)], check=True)
        tmp_wav.unlink(missing_ok=True)
    else:
        sf.write(str(dst_p), y.astype(np.float32), SR, subtype="PCM_24")
    return str(dst_p)


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply canyon / tape / water vocal sound effects with BS.1770 loudness matching.")
    ap.add_argument("kind", choices=[*FX_MAP, "all"])
    ap.add_argument("src", help="Input audio file (.wav or .mp3)")
    ap.add_argument("dst", help="Output audio file or output directory (when kind=all)")
    ap.add_argument("--seed", type=int, default=3)
    a = ap.parse_args()
    if a.kind == "all":
        out_dir = Path(a.dst)
        for k in FX_MAP:
            out_file = out_dir / f"{Path(a.src).stem}_{k}.wav"
            print(run_fx(k, a.src, out_file, a.seed))
    else:
        print(run_fx(a.kind, a.src, a.dst, a.seed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
