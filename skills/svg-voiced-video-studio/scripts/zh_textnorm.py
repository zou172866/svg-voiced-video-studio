#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generic Chinese TTS text normalization for numbers, currency, percent, years, ratios and ranges.

Only applied to the spoken (TTS) track. Inline {say=>show} tags and line["ttsText"] are resolved
before this runs, so a manual reading always wins over the automatic one.

Covered patterns (in order):
  $12,400 / US$29 / ¥88 / €5   -> 一万两千四百美元 / 二十九美元 / 八十八元 / 五欧元
  $3.2M / $12k                 -> 三百二十万美元 / 一万两千美元
  12,400                       -> 12400 (thousands separator removed, then read as integer)
  37% / 3.5%                   -> 百分之三十七 / 百分之三点五
  2024年                        -> 二零二四年 (digit by digit)
  1:1 / 3:2                    -> 一比一 / 三比二   (clock times like 10:30 are also read as ratios; use {say=>show} for times)
  75～110 / 3-5                -> 七十五到一百一十 / 三到五
  3.2万 / 150万                 -> 三点二万 / 一百五十万
  2个 / 2万                     -> 两个 / 两万
  digit strings longer than 9  -> read digit by digit

Usage:
  python scripts/zh_textnorm.py "他这个月营收 $12,400，利润率 37%。"
"""
from __future__ import annotations

import re
import sys

DIG = "零一二三四五六七八九"
UNITS = ["", "十", "百", "千"]
LIANG_QUANT = "个件种次条名位天周台家款只张本份批套"


def _section(n: int) -> str:
    """Read 0 < n < 10000."""
    s = ""
    zero = False
    for i in range(3, -1, -1):
        d = n // 10**i % 10
        if d == 0:
            if s:
                zero = True
            continue
        if zero:
            s += "零"
            zero = False
        s += DIG[d] + UNITS[i]
    return s


def int_to_zh(n: int) -> str:
    if n == 0:
        return "零"
    if n >= 10**12:
        return "".join(DIG[int(c)] for c in str(n))
    groups = [(n // 10**8, "亿"), (n // 10**4 % 10**4, "万"), (n % 10**4, "")]
    s = ""
    need_zero = False
    for val, unit in groups:
        if val == 0:
            if s:
                need_zero = True
            continue
        if s and (need_zero or val < 1000):
            s += "零"
        s += _section(val) + unit
        need_zero = False
    if s.startswith("一十"):
        s = s[1:]
    # Spoken Chinese: 两千 / 两万 / 两亿 / 两百 (but keep 十二万, 零二万)
    s = re.sub(r"(?<![十零])二(?=[千万亿])", "两", s)
    if s.startswith("二百"):
        s = "两" + s[1:]
    return s


def num_to_zh(num: str) -> str:
    num = num.replace(",", "")
    if "." in num:
        ip, dp = num.split(".", 1)
        head = int_to_zh(int(ip)) if ip else "零"
        return head + "点" + "".join(DIG[int(c)] for c in dp if c.isdigit())
    if len(num) > 9:
        return "".join(DIG[int(c)] for c in num)
    return int_to_zh(int(num))


NUM = r"\d+(?:,\d{3})*(?:\.\d+)?"
CURRENCY = {"$": "美元", "US$": "美元", "＄": "美元", "¥": "元", "￥": "元", "€": "欧元", "£": "英镑"}
SCALE = {"k": 1_000, "K": 1_000, "m": 1_000_000, "M": 1_000_000, "b": 1_000_000_000, "B": 1_000_000_000}


def _money(m: re.Match) -> str:
    sym, raw, scale_unit, cn_unit = m.group(1), m.group(2), m.group(3), m.group(4)
    cur = CURRENCY.get(sym, "美元")
    if scale_unit:
        val = float(raw.replace(",", "")) * SCALE[scale_unit]
        txt = num_to_zh(str(int(val)) if val.is_integer() else f"{val:g}")
        return txt + cur
    return num_to_zh(raw) + (cn_unit or "") + cur


def normalize_numbers_zh(text: str) -> str:
    s = text
    # 0. Remove spaces between digits and CJK units/symbols so "3.2 万" / "2024 年" / "37 %" are recognized
    s = re.sub(r"(?<=\d)\s+(?=[万亿千百年月日号岁个%％美元欧英倍])", "", s)
    s = re.sub(r"(?<=[$¥￥€£＄])\s+(?=\d)", "", s)
    # 1. Currency with symbol prefix (optionally k/M/B scale or 万/亿 unit)
    s = re.sub(r"(US\$|[$¥￥€£＄])(" + NUM + r")(?:([kKmMbB])(?![A-Za-z])|([万亿])?)", _money, s)
    # 2. Percent
    s = re.sub(r"(" + NUM + r")[%％]", lambda m: "百分之" + num_to_zh(m.group(1)), s)
    # 3. Four-digit years
    s = re.sub(r"(?<!\d)(\d{4})(?=年)", lambda m: "".join(DIG[int(c)] for c in m.group(1)), s)
    # 4. Ratios a:b
    s = re.sub(r"(?<![\d.])(\d+)[:：](\d+)(?![\d.])", lambda m: num_to_zh(m.group(1)) + "比" + num_to_zh(m.group(2)), s)
    # 5. Ranges a～b / a~b / a-b / a–b
    s = re.sub(
        r"(" + NUM + r")\s*[~～\-–](?!-)\s*(" + NUM + r")",
        lambda m: num_to_zh(m.group(1)) + "到" + num_to_zh(m.group(2)),
        s,
    )
    # 6. Standalone 2 before quantifiers -> 两
    s = re.sub(r"(?<![\d.,])2(?![\d.,])(?=\s?[" + LIANG_QUANT + r"千万亿])", "两", s)
    # 7. Remaining numbers
    s = re.sub(NUM, lambda m: num_to_zh(m.group(0)), s)
    return s


def find_reading_risks(text: str) -> list[str]:
    """Tokens a human should listen to after synthesis: numbers, currency, percent, Latin words."""
    risks = []
    for m in re.finditer(r"(?:US\$|[$¥￥€£＄])?\s?" + NUM + r"\s?(?:[kKmMbB](?![A-Za-z])|[万亿%％])?", text):
        tok = m.group(0).strip()
        if tok:
            risks.append(tok)
    for m in re.finditer(r"[A-Za-z][A-Za-z0-9.&'\-]*", text):
        risks.append(m.group(0))
    return risks


if __name__ == "__main__":
    for arg in sys.argv[1:] or ["他这个月营收 $12,400，利润率 37%，2024 年做到 3.2 万美元，比例 1:1，时长 75～110 秒，2个人。"]:
        print(normalize_numbers_zh(arg))
