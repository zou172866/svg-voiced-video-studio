#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reusable local GPT-SoVITS v2ProPlus voiceover + 60fps timeline synchronizer
(Upgraded with kaikou acoustic craft: multi-take auto-selection, anti-chop tail envelope,
ITU-R BS.1770 K-weighted loudness leveling, inline {say=>show} dual-track, optional vocal FX,
and automatic sidechain-ducked ambient BGM mix).

Key capabilities:
1. Dual-track pronunciation: supports both line["ttsText"] and inline "{念法=>字幕}" tags.
2. Multi-take synthesis (--takes N, default 3): generates N takes per clause across distinct seeds,
   scoring each take on speech-rate sanity (anti-skip), final-60ms tail decay slope (anti-hard-chop),
   optional faster-whisper pinyin error rate (--asr-verify), and F0 pitch continuity with prior line.
3. Breath-preserving trim & BS.1770 leveling: onset -38dB (40ms cosine fade-in without eating consonants),
   offset -46dB (160ms tail breath + smooth cosine fade-out), leveled to -18.5 LUFS (-1.5 dBFS true peak).
4. Semantic pause micro-stagger & sidechain ducking: exports per-scene S01..SXX.mp3 (voice only, for QA listening),
   ambient_pad.mp3, and mixed_master_ducked.mp3 (voice + ducked pad; the ONLY track the Remotion root composition should play).
5. Number normalization (scripts/zh_textnorm.py): $12,400 / 37% / 3.2万 / 2024年 / 1:1 -> Chinese readings on the TTS track only.
6. Clause splitting at ；：—— (0.18s gap) and 。！？ (0.30s gap); clauses under 4 chars are merged with a neighbour.
7. Presets: --preset long (A/B 16:9 essays, default) | short (C 9:16 75-115s explainers, tighter lead/tail/pauses).
8. Outputs Remotion-ready src/data/scenesData.json (durationInFrames, startSec, per-line startSec/endSec)
   and out/chapters.txt (00:00 chapter list from real 60fps frame totals, for Bilibili descriptions).
9. *keyword* emphasis marks -> per-line "emphasis" [{word, startSec, endSec, source}] (scene-local seconds).
   Estimated from syllable position inside the chosen take; with --asr-verify snapped to faster-whisper word
   timestamps. Drives accentAt() in assets/motion_60fps.ts so vermilion lights exactly what is being said.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from scipy.ndimage import maximum_filter1d, uniform_filter1d

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from sfx_synth import generate_sfx  # noqa: E402
from voice_fx import apply_voice_fx_array, compute_lufs_bs1770  # noqa: E402
from zh_textnorm import normalize_numbers_zh  # noqa: E402

HAN_RE = re.compile(r"[㐀-鿿]")


def split_dual_track(raw_text: str) -> tuple[str, str]:
    say = re.sub(r"\{([^}]*)=>[^}]*\}", r"\1", raw_text).replace("*", "")
    show = re.sub(r"\{[^}]*=>([^}]*)\}", r"\1", raw_text).replace("*", "")
    return say.strip(), show.strip()


# *keyword* emphasis marks survive clause splitting / number normalization as private-use sentinels
EM_OPEN, EM_CLOSE = "\ue000", "\ue001"


def mark_emphasis(raw_text: str) -> tuple[str, list[str]]:
    """Return the say-track with *word* turned into sentinels, plus the display form of each marked word."""
    show = re.sub(r"\{[^}]*=>([^}]*)\}", r"\1", raw_text)
    words = re.findall(r"\*([^*]+)\*", show)
    say = re.sub(r"\{([^}]*)=>[^}]*\}", r"\1", raw_text)
    say = re.sub(r"\*([^*]+)\*", EM_OPEN + r"\1" + EM_CLOSE, say).replace("*", "")
    return say.strip(), words


def _speech_weight(ch: str) -> float:
    if HAN_RE.match(ch):
        return 1.0
    if ch.isascii() and ch.isalnum():
        return 0.45
    if ch in "，、,":
        return 1.2  # a comma inside a clause costs roughly one syllable of time
    return 0.0


def emphasis_fracs(clause: str) -> tuple[str, list[tuple[str, float, float]]]:
    """Strip sentinels from one clause; return (clean_text, [(say_word, start_frac, end_frac), ...])."""
    clean, spans, buf_word = [], [], None
    pos = 0.0
    total = sum(_speech_weight(c) for c in clause if c not in (EM_OPEN, EM_CLOSE)) or 1.0
    start = 0.0
    for c in clause:
        if c == EM_OPEN:
            buf_word, start = "", pos
            continue
        if c == EM_CLOSE:
            if buf_word is not None:
                spans.append((buf_word, start / total, pos / total))
            buf_word = None
            continue
        clean.append(c)
        pos += _speech_weight(c)
        if buf_word is not None:
            buf_word += c
    if buf_word is not None:  # unclosed mark: close at clause end
        spans.append((buf_word, start / total, 1.0))
    return "".join(clean), spans


def voiced_bounds(clip: np.ndarray, sr: int, thresh_db: float = -35.0) -> tuple[float, float]:
    """(first_voiced_sample, voiced_length_samples) using 10 ms RMS frames relative to the clip's 95th percentile."""
    hop = max(1, int(0.01 * sr))
    n = len(clip) // hop
    if n < 3:
        return 0.0, float(max(1, len(clip)))
    rms = np.sqrt(np.mean(clip[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    db = 20.0 * np.log10(rms / (np.percentile(rms, 95) + 1e-9))
    idx = np.where(db > thresh_db)[0]
    if len(idx) == 0:
        return 0.0, float(len(clip))
    return float(idx[0] * hop), float(max(hop, (idx[-1] + 1 - idx[0]) * hop))


def refine_emphasis_with_asr(asr_model, clip: np.ndarray, sr: int, spans: list[dict]) -> int:
    """Snap proportional emphasis estimates to faster-whisper word timestamps (pinyin match). Returns #snapped."""
    try:
        from pypinyin import Style, pinyin
    except Exception:
        return 0
    y16 = librosa.resample(clip, orig_sr=sr, target_sr=16000) if sr != 16000 else clip
    segs, _ = asr_model.transcribe(y16, language="zh", word_timestamps=True, beam_size=2)
    # Whisper splits numbers into fragments ("12" "400", "37" "%"); merge them back before normalizing
    words: list[list] = []
    for seg in segs:
        for w in seg.words or []:
            tok = w.word.strip()
            if words and re.fullmatch(r"[\d,.%％]+", tok) and re.search(r"\d[\d,.]*$", words[-1][0]):
                words[-1][0] += tok
                words[-1][2] = w.end
            else:
                words.append([tok, w.start, w.end])
    chars: list[tuple[str, float, float]] = []
    for tok, w_start, w_end in words:
        # ASR writes numbers as digits ("12400"); read them the same way the TTS track did
        units = HAN_RE.findall(normalize_numbers_zh(tok)) or re.findall(r"[A-Za-z0-9]+", tok)
        if not units:
            continue
        step = (w_end - w_start) / len(units)
        for i, u in enumerate(units):
            chars.append((u, w_start + i * step, w_start + (i + 1) * step))
    if not chars:
        return 0
    rec_py = [pinyin(c, style=Style.NORMAL)[0][0] if HAN_RE.match(c) else c.lower() for c, _, _ in chars]
    snapped = 0
    for sp in spans:
        target = [x[0] for x in pinyin("".join(HAN_RE.findall(sp["sayWord"])), style=Style.NORMAL)]
        if not target or len(target) > len(rec_py):
            continue
        best_i, best_r = -1, 0.0
        for i in range(len(rec_py) - len(target) + 1):
            r = difflib.SequenceMatcher(None, target, rec_py[i : i + len(target)]).ratio()
            if r > best_r:
                best_i, best_r = i, r
        if best_r >= 0.6:
            s, e = chars[best_i][1], chars[best_i + len(target) - 1][2]
            if abs(s - sp["startSec"]) <= 0.6:  # guard against matching a repeated word elsewhere
                sp["startSec"], sp["endSec"], sp["asr"] = s, e, True
                snapped += 1
    return snapped


CLAUSE_GAP_SHORT = 0.18  # after ； ： ——  (same thought continues)
CLAUSE_GAP_LONG = 0.30  # after 。 ！ ？  (sentence boundary inside one line)
MIN_CLAUSE_UNITS = 4  # clauses shorter than this are merged with a neighbour (1-3 char TTS calls babble or drop)

PRESETS = {
    # long: philosophy / humanities 16:9 essays (modes A, B)
    "long": {"lead": 0.95, "tail": 1.45, "pause": 0.52},
    # short: 75-115s vertical commercial explainers (mode C); ~7 scenes lose ~12s of dead air vs long
    "short": {"lead": 0.30, "tail": 0.60, "pause": 0.42},
}


def _units(s: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+|[㐀-鿿]", s))


def to_tts_clauses(text: str, normalize: bool = True) -> list[tuple[str, float]]:
    """
    Split one subtitle line into independent TTS clauses and the silence (sec) to insert after each.
    - ； ： —— -> short gap (0.18s); 。 ！ ？ -> long gap (0.30s)
    - numbers / currency / percent normalized to Chinese readings unless normalize=False
    - every clause ends with 。！？ so the model lands the tail instead of chopping mid-air
    """
    if normalize:
        text = normalize_numbers_zh(text)
    pieces = re.split(r"(——|[；：？。！])", text)
    raw: list[list] = []  # [clause_text, gap]
    buf = ""
    for p in pieces:
        if p == "——" or (p and p in "；："):
            raw.append([buf, CLAUSE_GAP_SHORT])
            buf = ""
        elif p and p in "？。！":
            raw.append([buf + p, CLAUSE_GAP_LONG])
            buf = ""
        else:
            buf += p
    if buf.strip():
        raw.append([buf, CLAUSE_GAP_LONG])

    cleaned: list[list] = []
    for s, gap in raw:
        s = s.replace("《", "").replace("》", "").replace("“", "").replace("”", "").replace("「", "").replace("」", "")
        # Convert full-width CJK comma after Latin letters into ASCII ', ' so LangSegmenter/en cleaner never swallows pauses!
        s = re.sub(r"(?<=[A-Za-z])[，、]", ", ", s.strip())
        # drop whitespace unless it separates two Latin words or follows ASCII ', '
        s = re.sub(r"(?<=[^A-Za-z,])\s+|\s+(?=[^A-Za-z])", "", s)
        if not s or not re.search(r"[A-Za-z0-9㐀-鿿]", s):
            continue
        cleaned.append([s, gap])

    # merge too-short clauses into the following one (or the previous one when last)
    def _join(a: str, b: str) -> str:
        # keep ？！ tone inside the merged clause; replace a bare 。 with a comma
        return (a if a[-1] in "？！" else a.rstrip("。") + "，") + b

    merged: list[list] = []
    i = 0
    while i < len(cleaned):
        s, gap = cleaned[i]
        while _units(s) < MIN_CLAUSE_UNITS and i + 1 < len(cleaned):
            i += 1
            s = _join(s, cleaned[i][0])
            gap = cleaned[i][1]
        if _units(s) < MIN_CLAUSE_UNITS and merged:
            merged[-1][0] = _join(merged[-1][0], s)
            merged[-1][1] = gap
        else:
            merged.append([s, gap])
        i += 1

    out: list[tuple[str, float]] = []
    for s, gap in merged:
        if s[-1] in "，、；：":
            s = s[:-1] + "。"
        elif s[-1] not in "。！？":
            s += "。"
        out.append((s, gap))
    return out


def clean_and_level_clip(audio: np.ndarray, sr: int, target_lufs: float = -18.5) -> tuple[np.ndarray, dict]:
    """
    kaikou-grade vocal trim & BS.1770 leveling:
    - Onset threshold -38 dB below 95th-percentile frame RMS, keep 40ms pre-onset, cosine fade-in (preserves plosives/consonants).
    - Offset threshold -46 dB below 95th-percentile frame RMS, keep 160ms breath tail, cosine fade-out.
    - Detects sudden hard-cut tails (drop from -12 dB to -40 dB in < 38ms or ending > -32 dB) and softens fade-out + flags penalty.
    """
    a = audio.astype(np.float32)
    if np.max(np.abs(a)) > 1.5:
        a = a / 32768.0
    if len(a) < int(0.12 * sr):
        return a, {"hard_cut": True, "f0_med": 0.0}

    hop = max(1, int(0.01 * sr))  # 10ms frame
    n_fr = len(a) // hop
    rms_fr = np.sqrt(np.mean(a[: n_fr * hop].reshape(n_fr, hop) ** 2, axis=1) + 1e-12)
    ref_rms = float(np.percentile(rms_fr, 95)) + 1e-9
    db_fr = 20.0 * np.log10(rms_fr / ref_rms)

    voiced_on = np.where(db_fr > -38.0)[0]
    voiced_off = np.where(db_fr > -46.0)[0]
    if len(voiced_on) == 0 or len(voiced_off) == 0:
        return a, {"hard_cut": True, "f0_med": 0.0}

    on_sample = int(voiced_on[0] * hop)
    off_sample = int((voiced_off[-1] + 1) * hop)

    # Check tail decay slope in the 60ms window around off_sample (kaikou step 6 diagnostics)
    tail_end_fr = min(n_fr - 1, int(voiced_off[-1]))
    tail_win_start = max(0, tail_end_fr - 6)
    tail_slice = db_fr[tail_win_start : tail_end_fr + 1]
    hard_cut = bool(
        (len(tail_slice) >= 2 and float(tail_slice[-1]) > -32.0)
        or (len(tail_slice) >= 4 and (float(np.max(tail_slice)) > -12.0 and float(tail_slice[-1]) < -40.0 and len(tail_slice) <= 4))
    )

    head_pad = int(0.040 * sr)
    tail_pad = int(0.160 * sr)
    s0 = max(0, on_sample - head_pad)
    s1 = min(len(a), off_sample + tail_pad)
    clip = a[s0:s1].copy()

    # Gentle cosine fade-in over first 45ms (40ms pre-pad + 5ms into onset -> zero consonant loss)
    fi_n = min(int(0.045 * sr), len(clip) // 5)
    if fi_n > 4:
        clip[:fi_n] *= 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, fi_n, dtype=np.float32)))

    # Smooth cosine fade-out (if hard_cut detected, start 60ms earlier to round off abrupt end)
    fo_dur = 0.180 if hard_cut else 0.120
    fo_n = min(int(fo_dur * sr), len(clip) // 3)
    if fo_n > 4:
        clip[-fo_n:] *= 0.5 * (1.0 + np.cos(np.linspace(0.0, np.pi, fo_n, dtype=np.float32)))

    # BS.1770 K-weighted loudness normalization (target -18.5 LUFS, max gain +12 dB, peak ceiling -1.5 dBFS)
    cur_lufs = compute_lufs_bs1770(clip, sr)
    if cur_lufs > -65.0:
        gain = min(10.0 ** ((target_lufs - cur_lufs) / 20.0), 4.0)
        clip = clip * float(gain)
    peak = float(np.max(np.abs(clip)))
    max_peak = 10.0 ** (-1.5 / 20.0)
    if peak > max_peak:
        clip = clip / peak * max_peak

    # Median voiced F0 for cross-sentence pitch smoothness scoring
    f0_med = 0.0
    try:
        y16 = librosa.resample(clip, orig_sr=sr, target_sr=16000) if sr != 16000 else clip
        f0 = librosa.yin(y16, fmin=75, fmax=360, sr=16000, frame_length=1024, hop_length=256)
        valid_f0 = f0[(f0 > 78) & (f0 < 340)]
        if len(valid_f0) >= 4:
            f0_med = float(np.median(valid_f0))
    except Exception:
        f0_med = 0.0

    return clip, {"hard_cut": hard_cut, "f0_med": f0_med}


def _mixed_phonetic_tokens(text: str, pinyin_fn, style_normal) -> list[str]:
    """Tokenize mixed Chinese + English text into tone-stripped pinyin + lowercased ASCII words."""
    norm = normalize_numbers_zh(text)
    out: list[str] = []
    for m in re.finditer(r"[㐀-鿿]+|[A-Za-z0-9]+", norm):
        seg = m.group(0)
        if HAN_RE.match(seg[0]):
            out.extend(x[0] for x in pinyin_fn(seg, style=style_normal))
        else:
            out.append(seg.lower())
    return out


def pinyin_similarity(expected_text: str, recognized_text: str) -> float:
    """Compare tone-stripped pinyin + lowercased English word sequences so both CJK & English ASR errors are caught."""
    try:
        from pypinyin import Style, pinyin

        p_exp = _mixed_phonetic_tokens(expected_text, pinyin, Style.NORMAL)
        p_rec = _mixed_phonetic_tokens(recognized_text, pinyin, Style.NORMAL)
        if not p_exp:
            return 1.0
        return difflib.SequenceMatcher(None, p_exp, p_rec).ratio()
    except Exception:
        c_exp = "".join(re.findall(r"[㐀-鿿A-Za-z0-9]+", expected_text)).lower()
        c_rec = "".join(re.findall(r"[㐀-鿿A-Za-z0-9]+", recognized_text)).lower()
        return difflib.SequenceMatcher(None, c_exp, c_rec).ratio() if c_exp else 1.0


def score_take(
    clip: np.ndarray,
    sr: int,
    meta: dict,
    clause_text: str,
    speed: float,
    prev_f0: float,
    asr_model=None,
) -> float:
    """Higher score = better take (0..100 scale)."""
    n_chars = max(1, len(HAN_RE.findall(clause_text)) + 2 * len(re.findall(r"[A-Za-z]+", clause_text)))
    dur = len(clip) / sr
    cps = n_chars / max(0.15, dur)
    ideal_cps = 4.6 * speed

    score = 100.0
    # 1. Penalize abnormal token skipping (too fast > 6.6 cps) or runaway babbling (< 2.7 cps)
    if cps > 6.5 * speed:
        score -= (cps - 6.5 * speed) * 28.0
    elif cps < 2.8 * speed:
        score -= (2.8 * speed - cps) * 22.0
    else:
        score -= abs(cps - ideal_cps) * 3.2

    # 2. Penalize abrupt tail cutoffs
    if meta.get("hard_cut"):
        score -= 18.0

    # 3. Penalize pitch jump > 3.2 semitones vs previous clause/line
    f0 = meta.get("f0_med", 0.0)
    if prev_f0 > 0.0 and f0 > 0.0:
        semitones = abs(12.0 * np.log2(f0 / prev_f0))
        if semitones > 3.2:
            score -= (semitones - 3.2) * 4.0

    # 4. Optional ASR pinyin accuracy check
    if asr_model is not None:
        try:
            y16 = librosa.resample(clip, orig_sr=sr, target_sr=16000) if sr != 16000 else clip
            segs, _ = asr_model.transcribe(y16, language="zh", beam_size=2)
            rec_txt = "".join(s.text for s in segs)
            sim = pinyin_similarity(clause_text, rec_txt)
            score -= (1.0 - sim) * 80.0
        except Exception:
            pass

    return float(score)


def sidechain_duck_bgm(
    voice_track: np.ndarray,
    pad_track: np.ndarray,
    sr: int,
    base_pad_gain: float = 0.085,
    duck_db: float = -9.5,
) -> np.ndarray:
    """
    kaikou-style breathing BGM sidechain ducking:
    - Fast attack (~35ms) when voice enters so music immediately clears 1-4kHz speech band;
    - Slow cosine-smoothed release (~420ms) so music gently floats back up in semantic pauses.
    """
    n = min(len(voice_track), len(pad_track))
    v = voice_track[:n].astype(np.float32)
    p = pad_track[:n].astype(np.float32)

    hop = max(1, int(0.01 * sr))  # 10ms envelope step
    n_fr = n // hop
    if n_fr < 4:
        return np.clip(v + p * base_pad_gain, -0.95, 0.95)

    v_rms = np.sqrt(np.mean(v[: n_fr * hop].reshape(n_fr, hop) ** 2, axis=1) + 1e-12)
    speaking = (v_rms > 0.012).astype(np.float32)

    # Asymmetric attack/release envelope follower (attack=35ms, release=420ms)
    att_coef = np.exp(-0.01 / 0.035)
    rel_coef = np.exp(-0.01 / 0.420)
    env = np.zeros(n_fr, dtype=np.float32)
    cur = 0.0
    for i, spk in enumerate(speaking):
        if spk > cur:
            cur = att_coef * cur + (1.0 - att_coef) * spk
        else:
            cur = rel_coef * cur + (1.0 - rel_coef) * spk
        env[i] = cur

    env_smooth = uniform_filter1d(env, size=5)
    min_ratio = 10.0 ** (duck_db / 20.0)
    gain_fr = base_pad_gain * (1.0 - env_smooth * (1.0 - min_ratio))
    gain_samples = np.interp(np.arange(n), np.arange(n_fr) * hop, gain_fr).astype(np.float32)

    mixed = v + p * gain_samples
    peak = float(np.max(np.abs(mixed)))
    ceil = 10.0 ** (-1.5 / 20.0)
    if peak > ceil:
        mixed = mixed / peak * ceil
    return mixed


def fmt_srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    hrs, ms = divmod(ms, 3600000)
    mins, ms = divmod(ms, 60000)
    secs, ms = divmod(ms, 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{ms:03d}"


def build_ambient_pad_array(total_sec: float, sr: int = 32000, mode: str = "vellum") -> np.ndarray:
    n = int(np.ceil(total_sec * sr))
    t = np.arange(n, dtype=np.float32) / sr
    lfo1 = 0.66 + 0.34 * np.sin(2.0 * np.pi * t / 14.5)
    lfo2 = 0.56 + 0.44 * np.sin(2.0 * np.pi * t / 20.5 + 1.0)

    freqs = (73.42, 110.00, 164.81, 174.61, 220.00) if mode == "dark" else (87.31, 130.81, 196.00, 220.00, 329.63)
    pad = (
        0.41 * np.sin(2.0 * np.pi * freqs[0] * t)
        + 0.31 * np.sin(2.0 * np.pi * freqs[1] * t) * lfo1
        + 0.15 * np.sin(2.0 * np.pi * freqs[2] * t) * lfo2
        + 0.10 * np.sin(2.0 * np.pi * freqs[3] * t) * (1.06 - 0.26 * lfo1)
        + 0.06 * np.sin(2.0 * np.pi * freqs[4] * t) * lfo2
    ).astype(np.float32)

    pad = pad / (float(np.max(np.abs(pad))) + 1e-9) * 0.42
    fi = min(int(3.0 * sr), n // 4)
    fo = min(int(4.2 * sr), n // 4)
    if fi > 4:
        pad[:fi] *= 0.5 * (1.0 - np.cos(np.linspace(0.0, np.pi, fi, dtype=np.float32)))
    if fo > 4:
        pad[-fo:] *= 0.5 * (1.0 + np.cos(np.linspace(0.0, np.pi, fo, dtype=np.float32)))
    return pad


def encode_mp3(audio: np.ndarray, sr: int, out_mp3_path: Path, ffmpeg_bin: str, bitrate: str = "192k") -> None:
    tmp_wav = out_mp3_path.with_suffix(".tmp_enc.wav")
    sf.write(str(tmp_wav), audio, sr, subtype="PCM_16")
    subprocess.run(
        [ffmpeg_bin, "-v", "error", "-y", "-i", str(tmp_wav), "-ar", "48000", "-ac", "2", "-b:a", bitrate, str(out_mp3_path)],
        check=True,
    )
    tmp_wav.unlink(missing_ok=True)


def master_to_target_lufs(
    audio: np.ndarray,
    sr: int,
    target_lufs: float = -14.0,
    ceiling_db: float = -1.8,
) -> tuple[np.ndarray, float, float]:
    """
    ITU-R BS.1770 loudness mastering with smooth lookahead peak limiting.
    Uses -1.8 dBFS PCM ceiling so 192 kbps MP3 encoding stays safely <= -1.0 dBTP.
    Returns (mastered_audio, final_lufs, peak_dbfs).
    """
    out = audio.astype(np.float32, copy=True)
    ceil = float(10.0 ** (ceiling_db / 20.0))
    lookahead = max(1, int(0.008 * sr))
    release = max(1, int(0.055 * sr))

    for _ in range(2):
        cur_lufs = compute_lufs_bs1770(out, sr)
        if cur_lufs <= -65.0:
            break
        gain_db = max(-12.0, min(16.0, target_lufs - cur_lufs))
        out *= float(10.0 ** (gain_db / 20.0))

        # Lookahead soft-envelope limiter (zero hard-clipping distortion)
        env = maximum_filter1d(np.abs(out), size=lookahead * 2 + 1)
        req_gain = np.minimum(1.0, ceil / (env + 1e-9)).astype(np.float32)
        smooth_gain = uniform_filter1d(req_gain, size=release)
        eff_gain = np.minimum(req_gain, smooth_gain)
        out *= eff_gain

    final_lufs = compute_lufs_bs1770(out, sr)
    peak_db = float(20.0 * np.log10(float(np.max(np.abs(out))) + 1e-9))
    return out, round(final_lufs, 2), round(peak_db, 2)


def build_sfx_bus(
    scenes_in: list[dict],
    scenes_out: list[dict],
    voice_master: np.ndarray,
    sr: int,
    sfx_mode: str,
    preset_name: str,
) -> tuple[np.ndarray, list[dict]]:
    """
    Build speech-aware paper-and-ink editorial foley bus aligned to scenesData.json timestamps (v6):
    - Scene/chapter cuts get J-cut page_turn (0.04s early, crest aligned via peak_offset_sec).
    - Key numbers / emphasis get sparse ledger_tick + pause-placed ruler_drop / pen_stroke / stamp_thud.
    - Non-cut cues avoid the first 80ms of spoken lines and duck -6 dB whenever overlapping speech.
    - 'stamp_thud' (alias 'impact') is capped at <= 2 across the entire film and placed strictly in pauses.
    """
    total_n = len(voice_master)
    bus = np.zeros(total_n, dtype=np.float32)
    if sfx_mode == "none" or total_n == 0:
        return bus, []

    tone = "crisp" if preset_name == "short" else "warm"
    hop = max(1, int(0.01 * sr))
    n_fr = total_n // hop
    v_rms = np.sqrt(np.mean(voice_master[: n_fr * hop].reshape(n_fr, hop) ** 2, axis=1) + 1e-12) if n_fr > 0 else np.zeros(1)

    line_starts: list[float] = []
    for sc in scenes_out:
        s0 = float(sc["startSec"])
        for ln in sc["lines"]:
            line_starts.append(s0 + float(ln["startSec"]))

    raw_cues: list[dict] = []
    for idx, (sc_in, sc_out) in enumerate(zip(scenes_in, scenes_out)):
        s0 = float(sc_out["startSec"])
        s_end = s0 + float(sc_out["durationInFrames"]) / float(sc_out["fps"])
        explicit = sc_in.get("sfxCues", [])

        for c in explicit:
            at = c.get("at", "cut")
            kind = c.get("kind", "ruler_drop")
            gain = float(c.get("gain", 0.30))
            t_hit = s0 if at == "cut" else (s_end - 0.35 if at == "end" else s0 + float(at) if isinstance(at, (int, float)) else s0)
            if isinstance(at, str) and at.startswith("emphasis:"):
                k = int(at.split(":", 1)[1])
                ems = [e for ln in sc_out["lines"] for e in ln.get("emphasis", [])]
                if 0 <= k < len(ems):
                    t_hit = s0 + float(ems[k]["endSec"]) + 0.04
            raw_cues.append({"timeSec": t_hit, "kind": kind, "gain": gain, "isCut": at == "cut", "reason": f"{sc_out['id']} explicit"})

        if sfx_mode != "auto":
            continue

        # Auto cues: clean J-cut page_turn on cuts (all cuts in short mode, chapter shifts in long mode)
        if idx >= 1 and sc_in.get("density") != "empty":
            prev_ch = scenes_out[idx - 1].get("chapterLabel")
            if preset_name == "short" or sc_out.get("chapterLabel") != prev_ch:
                raw_cues.append({
                    "timeSec": max(0.05, s0 - 0.04),
                    "kind": "page_turn",
                    "gain": 0.28 if preset_name == "short" else 0.18,
                    "isCut": True,
                    "reason": f"{sc_out['id']} J-cut page_turn",
                })

        # Auto emphasis / numeric payoff placed cleanly in post-line pause (never stepping on spoken syllables)
        if preset_name == "short":
            placed_scene_accent = False
            for ln in sc_out["lines"]:
                ems = ln.get("emphasis", [])
                if not ems or placed_scene_accent:
                    continue
                em0 = ems[0]
                has_num = bool(re.search(r"[\d$¥%％万亿十百千]", em0["word"]))
                pause_anchor = s0 + float(ln["endSec"]) + 0.04
                if has_num:
                    em_abs = s0 + float(em0["startSec"])
                    for ti in range(3):
                        raw_cues.append({
                            "timeSec": max(0.02, em_abs - (3 - ti) * 0.11),
                            "kind": "ledger_tick",
                            "gain": 0.14,
                            "isCut": False,
                            "reason": f"{sc_out['id']} number count-in ({em0['word']})",
                        })
                    raw_cues.append({
                        "timeSec": pause_anchor,
                        "kind": "stamp_thud" if idx in (1, len(scenes_out) - 1) else "ruler_drop",
                        "gain": 0.28 if idx in (1, len(scenes_out) - 1) else 0.22,
                        "isCut": False,
                        "reason": f"{sc_out['id']} post-number foley ({em0['word']})",
                    })
                else:
                    raw_cues.append({
                        "timeSec": pause_anchor,
                        "kind": "pen_stroke" if idx == 0 else "ruler_drop",
                        "gain": 0.20,
                        "isCut": False,
                        "reason": f"{sc_out['id']} post-keyword foley ({em0['word']})",
                    })
                placed_scene_accent = True
        elif idx == max(0, len(scenes_out) - 2) and sc_out["lines"]:
            # Mode A/B long essay: single tactile pen_stroke after penultimate thesis scene
            ln_last = sc_out["lines"][-1]
            raw_cues.append({
                "timeSec": s0 + float(ln_last["endSec"]) + 0.08,
                "kind": "pen_stroke",
                "gain": 0.18,
                "isCut": False,
                "reason": f"{sc_out['id']} thesis payoff pen_stroke",
            })

    applied: list[dict] = []
    impact_count = 0
    for idx_c, cue in enumerate(sorted(raw_cues, key=lambda x: x["timeSec"])):
        kind = cue["kind"]
        if kind in ("impact", "stamp_thud"):
            if impact_count >= 2:
                continue
            impact_count += 1

        t_hit = float(cue["timeSec"])
        # Keep non-cut SFX away from the first 80ms plosive onset of any spoken line
        if not cue["isCut"]:
            for ls in line_starts:
                if -0.03 <= (t_hit - ls) <= 0.08:
                    t_hit = max(0.0, ls - 0.06)
                    break

        wav, peak_off = generate_sfx(kind, sr=sr, tone=tone, seed=17 + idx_c * 7)
        start_sec = max(0.0, t_hit - peak_off)
        i0 = int(round(start_sec * sr))
        if i0 >= total_n:
            continue
        i1 = min(total_n, i0 + len(wav))
        seg_wav = wav[: i1 - i0]

        gain = float(cue["gain"])
        # Attenuate -6 dB if a non-cut SFX overlaps active speech
        f0_idx = min(len(v_rms) - 1, i0 // hop)
        f1_idx = min(len(v_rms), (i1 // hop) + 1)
        overlaps_voice = bool(not cue["isCut"] and f1_idx > f0_idx and float(np.max(v_rms[f0_idx:f1_idx])) > 0.014)
        if overlaps_voice:
            gain *= 0.50

        bus[i0:i1] += seg_wav * gain
        applied.append({
            "timeSec": round(t_hit, 3),
            "startSec": round(start_sec, 3),
            "kind": kind,
            "gain": round(gain, 3),
            "duckedForVoice": overlaps_voice,
            "reason": cue["reason"],
        })

    return np.clip(bus, -0.85, 0.85), applied


def preflight_check(sovits_root: Path, script_path: Path | None, ffmpeg_bin: str) -> list[str]:
    """Validate voice profile, model weights, CUDA availability, ffmpeg, and optional script JSON before synthesis."""
    errors: list[str] = []
    profile_path = sovits_root / "voice_profile.json"
    if not profile_path.is_file():
        errors.append(f"缺少 voice_profile.json：{profile_path}")
        return errors

    try:
        prof = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        errors.append(f"voice_profile.json 解析失败：{exc}")
        return errors

    for key in ("gpt_weight", "sovits_weight", "ref_audio_path"):
        rel = prof.get(key)
        if not rel:
            errors.append(f"voice_profile.json 缺少字段 {key}")
            continue
        p = Path(rel) if Path(rel).is_absolute() else (sovits_root / rel)
        if not p.exists():
            errors.append(f"{key} 文件不存在：{p}")

    for pre in ("GPT_SoVITS/pretrained_models/chinese-hubert-base", "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large"):
        if not (sovits_root / pre).exists():
            errors.append(f"缺少预训练底模目录：{sovits_root / pre}")

    try:
        r = subprocess.run([ffmpeg_bin, "-version"], capture_output=True, text=True, check=False)
        if r.returncode != 0:
            errors.append(f"ffmpeg 无法正常运行：{ffmpeg_bin}")
    except Exception as exc:
        errors.append(f"未找到可执行 ffmpeg（{ffmpeg_bin}）：{exc}")

    try:
        import torch
        import torchaudio  # noqa: F401
        if not torch.cuda.is_available():
            errors.append("PyTorch 未检测到可用 CUDA GPU（GPT-SoVITS 半精度推理需要 CUDA）")
    except Exception as exc:
        venv_py = sovits_root / ".venv" / "Scripts" / "python.exe"
        hint = f"；检测到专属虚拟环境，请改用 {venv_py} 运行" if venv_py.is_file() else ""
        errors.append(f"PyTorch/TorchAudio 环境不兼容（{exc}）{hint}")

    if script_path is not None:
        if not script_path.is_file():
            errors.append(f"台词脚本不存在：{script_path}")
        else:
            try:
                data = json.loads(script_path.read_text(encoding="utf-8-sig"))
                if not isinstance(data, list) or not data:
                    errors.append("script JSON 必须是非空分幕数组")
            except Exception as exc:
                errors.append(f"script JSON 格式错误：{exc}")
    return errors


def clause_cache_key(clause: str, speed: float, n_takes: int, prof: dict, asr_on: bool) -> str:
    payload = json.dumps(
        {
            "v": 4,
            "clause": clause,
            "speed": round(speed, 4),
            "takes": n_takes,
            "gpt": prof.get("gpt_weight", ""),
            "sovits": prof.get("sovits_weight", ""),
            "ref": prof.get("ref_audio_path", ""),
            "prompt": prof.get("prompt_text", ""),
            "ver": prof.get("version", ""),
            "asr": asr_on,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synthesize personal GPT-SoVITS voiceover with preflight check, clause cache, SFX & -14 LUFS master.")
    parser.add_argument("--gpt-sovits-dir", required=True, help="Directory containing GPT_SoVITS and voice_profile.json")
    parser.add_argument("--project-dir", help="Target Remotion project directory (required unless --check-only)")
    parser.add_argument("--script-json", help="Input script JSON array path (required unless --check-only)")
    parser.add_argument("--check-only", action="store_true", help="Run preflight health check (weights, CUDA, ffmpeg) and exit")
    parser.add_argument("--force-resynth", action="store_true", help="Ignore out/.tts_cache and re-synthesize all clauses")
    parser.add_argument("--sfx", choices=["auto", "cues", "none"], default="auto", help="Editorial SFX mode: auto (default) | cues | none")
    parser.add_argument("--target-lufs", type=float, default=-14.0, help="Master loudness target in LUFS (default -14.0)")
    parser.add_argument("--srt-name", default="subtitles_60fps.srt", help="Output SRT filename inside project out/")
    parser.add_argument("--speed", type=float, default=1.00, help="Speech speed factor (0.98-1.08)")
    parser.add_argument("--fps", type=int, default=60, help="Target video FPS (default 60)")
    parser.add_argument("--takes", type=int, default=3, help="Number of candidate takes per clause to synthesize and auto-pick (default 3)")
    parser.add_argument("--asr-verify", action="store_true", help="Enable local faster-whisper pinyin error rate scoring when selecting takes")
    parser.add_argument("--pad-mode", choices=["dark", "vellum"], default="vellum", help="Ambient harmonic pad tone")
    parser.add_argument("--preset", choices=sorted(PRESETS), default="long", help="long = 16:9 essays (default); short = 9:16 75-115s explainers")
    parser.add_argument("--no-num-normalize", action="store_true", help="Send digits/currency/percent to TTS untouched")
    return parser.parse_args()


def fmt_chapter_time(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def main() -> int:
    args = parse_args()
    sovits_root = Path(args.gpt_sovits_dir).expanduser().resolve()
    ffmpeg_bin = str(sovits_root / "ffmpeg.exe") if (sovits_root / "ffmpeg.exe").is_file() else "ffmpeg"
    script_path = Path(args.script_json).expanduser().resolve() if args.script_json else None

    if not args.check_only and (not args.project_dir or not args.script_json):
        print("ERROR: --project-dir and --script-json are required unless --check-only is set.", file=sys.stderr)
        return 1

    pf_errors = preflight_check(sovits_root, script_path, ffmpeg_bin)
    if pf_errors:
        print("=== GPT-SoVITS 配音环境体检未通过 ===", file=sys.stderr)
        for err in pf_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    if args.check_only:
        print(f"[HEALTH OK] GPT-SoVITS voice profile, weights, CUDA, and ffmpeg verified at {sovits_root}")
        return 0

    assert args.project_dir and script_path is not None
    proj_root = Path(args.project_dir).expanduser().resolve()
    profile_path = sovits_root / "voice_profile.json"

    audio_out = proj_root / "public" / "audio"
    data_out = proj_root / "src" / "data"
    out_dir = proj_root / "out"
    cache_dir = out_dir / ".tts_cache"
    for d in (audio_out, data_out, out_dir, cache_dir):
        d.mkdir(parents=True, exist_ok=True)

    os.chdir(sovits_root)
    for sub in [sovits_root, sovits_root / "GPT_SoVITS", sovits_root / "GPT_SoVITS" / "BigVGAN", sovits_root / "tools"]:
        sp = str(sub)
        if sp not in sys.path:
            sys.path.insert(0, sp)

    prof = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    scenes_in = json.loads(script_path.read_text(encoding="utf-8-sig"))

    asr_model = None
    if args.asr_verify:
        try:
            from faster_whisper import WhisperModel
            asr_model = WhisperModel("small", device="cuda", compute_type="float16")
            print("[QA] Loaded faster-whisper for multi-take pinyin verification.")
        except Exception as exc:
            print(f"[QA] faster-whisper unavailable ({exc}), falling back to acoustic/cadence scoring.")

    tts = None

    def get_tts():
        nonlocal tts
        if tts is None:
            from GPT_SoVITS.TTS_infer_pack.TTS import TTS, TTS_Config
            tts = TTS(
                TTS_Config(
                    {
                        "custom": {
                            "device": "cuda",
                            "is_half": True,
                            "version": prof["version"],
                            "t2s_weights_path": prof["gpt_weight"],
                            "vits_weights_path": prof["sovits_weight"],
                            "cnhuhbert_base_path": "GPT_SoVITS/pretrained_models/chinese-hubert-base",
                            "bert_base_path": "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large",
                        }
                    }
                )
            )
        return tts

    sr = 32000
    n_takes = max(1, int(args.takes))
    preset = PRESETS[args.preset]
    scenes_out = []
    srt_entries = []
    chapter_rows: list[str] = []
    full_voice_timeline: list[np.ndarray] = []
    global_offset_sec = 0.0
    line_counter = 0
    prev_f0 = 0.0
    cache_hits = 0
    synth_clauses = 0

    for sc in scenes_in:
        sid = sc["id"]
        lead = float(sc.get("leadInSec", preset["lead"]))
        tail = float(sc.get("tailOutSec", preset["tail"]))
        chunks = [np.zeros(int(round(lead * sr)), dtype=np.float32)]
        local_cursor = lead
        out_lines = []

        for l_idx, ln in enumerate(sc["lines"]):
            line_counter += 1
            raw_display = ln["text"]
            raw_spoken = ln.get("ttsText") or raw_display
            say_marked, em_words = mark_emphasis(raw_spoken)
            say_full = say_marked.replace(EM_OPEN, "").replace(EM_CLOSE, "")
            _, display_clean = split_dual_track(raw_display)
            display_words = mark_emphasis(raw_display)[1]

            clauses = to_tts_clauses(say_marked, normalize=not args.no_num_normalize)
            sub_clips = []
            clip_cursor = 0  # samples
            em_spans: list[dict] = []
            em_k = 0

            for c_idx, (clause_marked, clause_gap) in enumerate(clauses):
                clause, fracs = emphasis_fracs(clause_marked)
                ckey = clause_cache_key(clause, args.speed, n_takes, prof, asr_model is not None)
                c_wav = cache_dir / f"{ckey}.wav"
                c_meta = cache_dir / f"{ckey}.json"

                if not args.force_resynth and c_wav.is_file() and c_meta.is_file():
                    best_clip_raw, _ = sf.read(str(c_wav), dtype="float32")
                    best_clip = np.asarray(best_clip_raw, dtype=np.float32)
                    best_meta = json.loads(c_meta.read_text(encoding="utf-8"))
                    cache_hits += 1
                else:
                    best_clip = None
                    best_meta = {"f0_med": 0.0}
                    best_score = -1e9
                    tts_engine = get_tts()

                    for t_idx in range(n_takes):
                        seed = 200 + line_counter * 31 + c_idx * 11 + t_idx * 97
                        req = {
                            "text": clause,
                            "text_lang": "zh",
                            "ref_audio_path": prof["ref_audio_path"],
                            "aux_ref_audio_paths": prof.get("aux_ref_audio_paths", []),
                            "prompt_text": prof["prompt_text"],
                            "prompt_lang": prof.get("prompt_lang", "zh"),
                            "top_k": 12,
                            "top_p": 0.80,
                            "temperature": 0.72,
                            "text_split_method": "cut2",
                            "batch_size": 1,
                            "speed_factor": args.speed,
                            "fragment_interval": 0.15,
                            "seed": seed,
                            "parallel_infer": False,
                            "repetition_penalty": 1.35,
                        }
                        tts_sr, raw_wav = list(tts_engine.run(req))[-1]
                        raw_wav = np.asarray(raw_wav)
                        if raw_wav.dtype != np.float32:
                            raw_wav = raw_wav.astype(np.float32) / (32768.0 if np.max(np.abs(raw_wav)) > 1.5 else 1.0)
                        if tts_sr != sr:
                            raw_wav = librosa.resample(raw_wav, orig_sr=tts_sr, target_sr=sr)
                        cand_clip, cand_meta = clean_and_level_clip(raw_wav, sr)
                        sc_val = score_take(cand_clip, sr, cand_meta, clause, args.speed, prev_f0, asr_model)
                        if sc_val > best_score:
                            best_score = sc_val
                            best_clip = cand_clip
                            best_meta = cand_meta

                    assert best_clip is not None
                    sf.write(str(c_wav), best_clip, sr, subtype="FLOAT")
                    c_meta.write_text(json.dumps(best_meta, ensure_ascii=False), encoding="utf-8")
                    synth_clauses += 1
                if best_meta.get("f0_med", 0.0) > 0:
                    prev_f0 = best_meta["f0_med"]
                # proportional emphasis timing inside the voiced part of the chosen take (-35 dB speech bounds,
                # so the kept breath tail and fades do not stretch the estimate late)
                head, voiced = voiced_bounds(best_clip, sr)
                for say_word, f0, f1 in fracs:
                    word = display_words[em_k] if em_k < len(display_words) else (em_words[em_k] if em_k < len(em_words) else say_word)
                    em_spans.append(
                        {
                            "word": word,
                            "sayWord": say_word,
                            "startSec": (clip_cursor + head + f0 * voiced) / sr,
                            "endSec": (clip_cursor + head + f1 * voiced) / sr,
                        }
                    )
                    em_k += 1
                sub_clips.append(best_clip)
                clip_cursor += len(best_clip)
                if c_idx < len(clauses) - 1:
                    gap_n = int(clause_gap * sr)
                    sub_clips.append(np.zeros(gap_n, dtype=np.float32))
                    clip_cursor += gap_n

            clip = np.concatenate(sub_clips)
            if not em_spans and display_words:
                # marks only on the display text (ttsText unmarked): spread proportionally over the whole line
                disp_marked, _ = mark_emphasis(raw_display)
                _, dfr = emphasis_fracs(disp_marked)
                dur = len(clip) / sr
                em_spans = [{"word": w, "sayWord": w, "startSec": a * dur, "endSec": b * dur} for w, a, b in dfr]
            if em_spans and asr_model is not None:
                refine_emphasis_with_asr(asr_model, clip, sr, em_spans)
            if ln.get("fx") in ("canyon", "tape", "water"):
                clip, _ = apply_voice_fx_array(clip, sr, ln["fx"])

            spoken_dur = round(len(clip) / sr, 3)
            # Subtle +-0.025s stagger across consecutive lines so pauses never feel mechanical (kaikou step 6)
            base_pause = float(ln.get("pauseAfterSec", preset["pause"]))
            stagger = (-0.025 if l_idx % 2 == 0 else 0.025) if l_idx < len(sc["lines"]) - 1 else 0.0
            pause_after = round(max(0.24, base_pause + stagger), 3)

            chunks.append(clip)
            chunks.append(np.zeros(int(round(pause_after * sr)), dtype=np.float32))

            abs_start = global_offset_sec + local_cursor
            srt_entries.append((line_counter, abs_start, abs_start + spoken_dur, display_clean))
            line_rec = {
                "index": line_counter,
                "text": display_clean,
                "startSec": round(local_cursor, 3),
                "endSec": round(local_cursor + spoken_dur, 3),
                "durationSec": spoken_dur,
                "pauseAfterSec": pause_after,
            }
            if say_full != display_clean:
                line_rec["ttsText"] = say_full
            line_rec["ttsClauses"] = [emphasis_fracs(c)[0] for c, _ in clauses]  # exactly what was sent to TTS
            if em_spans:
                line_rec["emphasis"] = [
                    {
                        "word": sp["word"],
                        "startSec": round(local_cursor + sp["startSec"], 3),
                        "endSec": round(local_cursor + sp["endSec"], 3),
                        "source": "asr" if sp.get("asr") else "estimate",
                    }
                    for sp in em_spans
                ]
            out_lines.append(line_rec)
            local_cursor += spoken_dur + pause_after

        chunks.append(np.zeros(int(round(tail * sr)), dtype=np.float32))
        local_cursor += tail

        scene_wave = np.concatenate(chunks)
        mp3_full = audio_out / f"{sid}.mp3"
        encode_mp3(scene_wave, sr, mp3_full, ffmpeg_bin, bitrate="192k")

        scene_frames = max(120, int(round(local_cursor * args.fps)))
        padded_samples = int(round((scene_frames / args.fps) * sr))
        if len(scene_wave) < padded_samples:
            full_voice_timeline.append(np.pad(scene_wave, (0, padded_samples - len(scene_wave))))
        else:
            full_voice_timeline.append(scene_wave[:padded_samples])

        chapter_rows.append(f"{fmt_chapter_time(global_offset_sec)} {sc['sceneTitle']}")
        scenes_out.append(
            {
                "id": sid,
                "chapterLabel": sc["chapterLabel"],
                "sceneTitle": sc["sceneTitle"],
                "fps": args.fps,
                "durationInFrames": scene_frames,
                "startSec": round(global_offset_sec, 3),
                "leadInSec": lead,
                "tailOutSec": tail,
                "audioSrc": f"audio/{sid}.mp3",  # voice-only per-scene track for QA; do NOT also play it in Remotion
                "lines": out_lines,
            }
        )
        global_offset_sec += scene_frames / args.fps

    pad_wave = build_ambient_pad_array(global_offset_sec, sr=sr, mode=args.pad_mode)
    encode_mp3(pad_wave, sr, audio_out / "ambient_pad.mp3", ffmpeg_bin, bitrate="160k")

    voice_master = np.concatenate(full_voice_timeline) if full_voice_timeline else np.zeros(sr, dtype=np.float32)
    sfx_bus, sfx_cues_applied = build_sfx_bus(scenes_in, scenes_out, voice_master, sr=sr, sfx_mode=args.sfx, preset_name=args.preset)
    if args.sfx != "none":
        encode_mp3(sfx_bus, sr, audio_out / "sfx_bus.mp3", ffmpeg_bin, bitrate="160k")
    (out_dir / "sfx_cues.json").write_text(json.dumps(sfx_cues_applied, ensure_ascii=False, indent=2), encoding="utf-8")

    ducked_voice_pad = sidechain_duck_bgm(voice_master, pad_wave, sr=sr)
    n_mix = min(len(ducked_voice_pad), len(sfx_bus))
    raw_mix = ducked_voice_pad[:n_mix] + sfx_bus[:n_mix]
    mastered_mix, master_lufs, master_peak = master_to_target_lufs(raw_mix, sr=sr, target_lufs=args.target_lufs)
    encode_mp3(mastered_mix, sr, audio_out / "mixed_master_ducked.mp3", ffmpeg_bin, bitrate="192k")

    (data_out / "scenesData.json").write_text(json.dumps(scenes_out, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / args.srt_name).write_text(
        "\n".join(f"{i}\n{fmt_srt_time(st)} --> {fmt_srt_time(et)}\n{tx}\n" for i, st, et, tx in srt_entries),
        encoding="utf-8",
    )
    (out_dir / "chapters.txt").write_text("\n".join(chapter_rows) + "\n", encoding="utf-8")
    total_frames = sum(s["durationInFrames"] for s in scenes_out)
    print(
        f"[OK] Synthesized {len(scenes_out)} scenes ({global_offset_sec:.2f}s = {total_frames} frames @ {args.fps}fps, "
        f"preset={args.preset}, clauses: {synth_clauses} new / {cache_hits} cached, sfx={len(sfx_cues_applied)} cues, "
        f"master={master_lufs:.1f} LUFS / peak={master_peak:.1f} dBFS). Root composition plays audio/mixed_master_ducked.mp3 only."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
