#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spoken-Chinese script linter & polyphone pre-flight checker (adapted from kaikou).
Supports:
  1. JSON scene array (e.g., [{"id": "S01", "lines": [{"text": "...", "ttsText": "..."}]}])
  2. Plain text script ([Section] headers, one line per utterance, optional '| 0.5' pause & '{say=>show}' dual-track tags)

Checks:
  - Banned binary templates ('不是X，而是Y' / '不是X，是Y' / '并非X而是Y' / '不X而Y') & AI summary clichés
  - Premature closing signals ('最后', '总之' appearing outside the final scene/section)
  - Breath-span overflow (> 24 chars between punctuation marks) & subtitle line-width overflow
  - Sentence-length uniformity (Coefficient of Variation < 0.25 warns about robotic parallel cadence)
  - Formal monosyllabic bureaucracy words ('已/需/仅/均/若/则/其/该/即可') & disyllabic verb ratio (target 70%-85%, judged only with >= 6 verbs)
  - High-risk Chinese polyphone & classical-character pronunciation audit (using pypinyin when available)
  - Numbers / currency / percent / Latin words: prints the automatic TTS reading so you can lock wrong ones with {say=>show}
  - Whitelists creator signature closing motto ('以不休止的追问，找到鲜活的自我；在有限的共识里，达成无限的可能。')

Usage:
  python scripts/lint_script.py path/to/script.json
  python scripts/lint_script.py path/to/script.txt --max-breath 22 --max-line 25
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zh_textnorm import find_reading_risks, normalize_numbers_zh  # noqa: E402

SIGNATURE_MOTTO = "以不休止的追问，找到鲜活的自我；在有限的共识里，达成无限的可能"

# Binary-reversal templates. '不是X，是Y' only counts when Y does not open a cause/purpose clause.
BINARY_PATTERNS = [
    re.compile(r"(?<!是)不是[^，。？！；]{1,16}[，,]?\s*而是"),
    re.compile(r"并非[^，。？！；]{0,16}[，,]?\s*而是"),
    re.compile(r"(?<!是)不是[^，。？！；]{1,16}[，,]\s*是(?!因为|由于|为了|不是|否|吗)"),
    re.compile(r"不(?!是)[^，。？！；不]{1,10}[，,]\s*而是"),
    re.compile(r"不(?!是)[^，。？！；不而]{1,8}而(?![且已言是今后外])[^，。？！；]{1,8}"),
]
# Fixed idioms that contain 不…而… but are not the banned template
BUER_IDIOMS = [
    "不得而知", "不约而同", "不期而遇", "不翼而飞", "不劳而获", "不谋而合", "不寒而栗", "不言而喻",
    "不战而胜", "不辞而别", "不欢而散", "不胫而走", "不攻自破", "不由自主", "不了了之", "不宣而战",
]

UNIT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-']*|[㐀-鿿]")
HAN_RE = re.compile(r"[㐀-鿿]")
BREAK_CHARS = "，。？！；：、,.?!;:"

BANNED_WORDS = ["最强", "颠覆", "一键", "零门槛", "赋能", "干货满满", "保姆级", "底层逻辑", "爆款密码"]
END_ONLY_WORDS = ["最后", "总之", "总结一下"]

COLD_OPEN_PATTERNS = [
    (r"^(大家好|哈喽大家好|各位好)", "冷开场禁区（前3秒直抛冲突或事实，勿自我介绍）"),
    (r"^(今天我们来讲|本期视频|这期视频|今天和大家聊)", "冷开场禁区（PPT报幕感，直接进钩子）"),
    (r"^在开始之前[，,]?(先|我们|让我们)", "冷开场禁区（禁止先铺垫背景）"),
]

CLICHE_PATTERNS = [
    # 原有总结与公文套话
    (r"(有|分为|就)(两|三|四)(个|点|条|种)", "AI总结框架"),
    (r"只有一个", "AI总结框架"),
    (r"在[^，。]{2,14}的今天", "公文套话"),
    (r"随着[^，。]{2,14}的(快速)?发展", "公文套话"),
    (r"日益|不断提升|至关重要|值得注意的是|归根结底|总而言之", "机械连接词"),
    (r"(?<![A-Za-z])(首先|其次)[，,]", "PPT结构词（口播建议改『先看/再说』自然过渡）"),
    # 1. 假共情（开口演“我懂你”）
    (r"我知道你(最近|现在)?(肯定|一定)?很", "AI假共情（勿开口装熟，改具体踩坑事实）"),
    (r"你是不是也有这种(感觉|困扰|焦虑|时候)", "AI假共情"),
    (r"今天这条视频[，,]?是给那些", "AI假共情"),
    (r"你的(感受|情绪|痛苦)是被看见的|我(非常|能)理解你的心情", "AI假共情"),
    # 2. 假深刻（用转折词包装普通观点）
    (r"恰恰相反|恰恰在于|恰恰说明|恰恰是", "AI假深刻包装（试删『恰恰』看意思是否改变）"),
    (r"这反而是[^，。？！]{1,14}(地方|原因|关键|秘密)", "AI假深刻包装（删去『反而』直说结论）"),
    (r"正是因为[^，。？！]{1,18}[，,]\s*(所以)?才", "AI假深刻包装（『正是因为…才』，建议直说因果）"),
    # 3. 自我加权（说重点前清嗓子）
    (r"我必须(很)?认真地说|这件事我得展开(讲|说)", "AI自我加权（好观点无需预告，直接说）"),
    (r"接下来我说的[，,]?可能会|这(一)?段(话)?你一定要(听完|记住)", "AI自我加权（靠节奏留人，勿强行加权）"),
    (r"今天就把[^，。？！]{1,12}(一次|彻底)?(说透|讲透|扒光)", "AI自我加权"),
    # 4. 口播万能模板与生硬收尾
    (r"说白了|换句话说|一句话总结|本质上(来说|讲|就是)?|从某种程度上(来讲|看|说)?|在某种意义上", "AI口播万能模板（删去口头预告，直给事实）"),
    (r"以上就是本期(视频|内容)|希望对你有(所)?帮助|感谢(你的|大家)?观看", "AI生硬收尾套话（改用具体提问或固定结束语）"),
]

PAREN_RE = re.compile(r"（[^）]{1,40}）|\([^)]{2,40}\)")


def find_parallel_triplets(masked_say: str) -> str | None:
    """Detect >=3 consecutive short clauses sharing an identical syntactic starter or fixed frame."""
    for sent in re.split(r"[。？！]", masked_say):
        clauses = [c.strip() for c in re.split(r"[，；]", sent) if c.strip()]
        if len(clauses) < 3:
            continue
        for i in range(len(clauses) - 2):
            tri = clauses[i : i + 3]
            hans = ["".join(HAN_RE.findall(c)) for c in tri]
            if not all(2 <= len(h) <= 9 for h in hans):
                continue
            # Same leading prefix (e.g. 不躲，不藏，不绕 / 会画图，会写字，会做表 / 你的X，你的Y，你的Z)
            if hans[0][0] == hans[1][0] == hans[2][0] and hans[0][0] not in "□一二三四五六七八九十":
                return "，".join(tri)
            # 3-4 char rigid frame with identical 2nd character (e.g. 看得见，摸得着，算得清)
            if len(hans[0]) == len(hans[1]) == len(hans[2]) and len(hans[0]) in (3, 4) and hans[0][1] == hans[1][1] == hans[2][1] and hans[0][1] != "□":
                return "，".join(tri)
    return None

# Formal monosyllabic words that sound stiff/clipped when spoken aloud (excluding quoted classical prose)
BOOK_MONO = [
    (r"(?<!而)已(?!经)", "已经"),
    (r"(?<![必急所无刚])需(?![要求求])", "需要"),
    (r"仅(?!仅)", "只、只有"),
    (r"(?<![平人日年])均(?![匀衡值摊价分速])", "都"),
    (r"亦", "也"),
    (r"皆", "都"),
    (r"因此", "所以"),
    (r"此外", "另外"),
    (r"此时", "这时候"),
    (r"该(?=[模方工功步项视文问版句段款套种人产公平店])", "这个"),
    (r"(?<![将从尚])未(?![来知曾必])", "没、没有"),
    (r"无(?=[需须法])", "不用、没办法"),
    (r"若(?!干)", "如果"),
    (r"虽(?!然)", "虽然"),
    (r"并非", "不是（且避免不是…而是…）"),
    (r"即可", "就行、就可以"),
    (r"(?<![规原否准法])则", "就"),
    (r"乃(?=[是至])", "就是、甚至"),
]

VERB_MONO = [
    (r"(?<![实检预推观监探评自烟])测(?![试量评算验])", "测试"),
    (r"(?<![评预高低])估(?![计算值])", "估计、估算"),
    (r"(?<![检调审排])查(?![看找询验])", "检查、查看"),
    (r"(?<![保储生温])存(?![在储档款活])", "保存"),
    (r"删(?![除掉减])", "删掉"),
    (r"剪(?![辑掉切刀])", "剪掉、剪辑"),
    (r"(?<![记收纪目语回])录(?![音制像入取])", "录音、录制"),
    (r"挑(?![选出战剔衅担])", "挑选、挑出"),
    (r"(?<![挑精筛候首])选(?![择项手题出举])", "选择"),
]
VERB_DI_RE = re.compile(r"生成|删减|测试|估计|估算|检查|查看|保存|删掉|删除|剪掉|剪辑|录音|录制|配音|挑选|挑出|选择|选出")

# High-frequency polyphones & classical traps from kaikou + studio experience
POLYPHONE_MAP = {
    "长": "chang2/zhang3", "行": "xing2/hang2", "重": "zhong4/chong2", "还": "hai2/huan2",
    "得": "de2/dei3/de5", "差": "cha4/cha1/chai1", "数": "shu4/shu3/shuo4", "只": "zhi3/zhi1",
    "量": "liang2/liang4", "调": "diao4/tiao2", "降": "jiang4/xiang2", "当": "dang1/dang4",
    "空": "kong1/kong4", "处": "chu4/chu3", "种": "zhong3/zhong4", "为": "wei4/wei2",
    "发": "fa1/fa4", "卡": "ka3/qia3", "率": "lv4/shuai4", "落": "luo4/la4/lao4",
    "没": "mei2/mo4", "背": "bei4/bei1", "弹": "tan2/dan4", "转": "zhuan3/zhuan4",
    "看": "kan4/kan1", "相": "xiang1/xiang4", "好": "hao3/hao4", "少": "shao3/shao4",
    "教": "jiao4/jiao1", "觉": "jue2/jiao4", "乐": "yue4/le4", "应": "ying1/ying4",
    "分": "fen1/fen4", "间": "jian1/jian4", "几": "ji3/ji1", "模": "mo2/mu2",
    "便": "bian4/pian2", "倒": "dao3/dao4", "都": "dou1/du1", "更": "geng4/geng1",
    "中": "zhong1/zhong4", "正": "zheng4/zheng1", "拗": "ao4/niu4", "屏": "ping2/bing3",
    "省": "sheng3/xing3", "似": "si4/shi4", "系": "xi4/ji4", "载": "zai3/zai4",
    "曾": "ceng2/zeng1", "朝": "chao2/zhao1", "称": "cheng1/chen4", "藏": "cang2/zang4",
    "薄": "bo2/bao2", "奇": "qi2/ji1", "供": "gong1/gong4", "给": "gei3/ji3",
    "露": "lu4/lou4", "强": "qiang2/qiang3/jiang4", "切": "qie1/qie4", "传": "chuan2/zhuan4",
    "解": "jie3/xie4", "参": "can1/shen1/cen1", "校": "xiao4/jiao4", "尽": "jin4/jin3",
    "劲": "jin4/jing4", "兴": "xing1/xing4", "难": "nan2/nan4", "担": "dan1/dan4",
    "假": "jia3/jia4", "散": "san4/san3", "塞": "sai1/se4/sai4", "识": "shi2/zhi4",
    "铺": "pu1/pu4", "观": "guan1/guan4", "折": "zhe2/she2", "混": "hun4/hun2",
    "横": "heng2/heng4", "划": "hua2/hua4", "创": "chuang4/chuang1", "恶": "e4/wu4/e3",
    "宿": "su4/xiu3", "冠": "guan1/guan4", "号": "hao4/hao2", "喝": "he1/he4",
    "盛": "sheng4/cheng2", "档": "dang4/dang3", "拏": "na2", "毳": "cui4", "凇": "song1", "沆": "hang4", "砀": "dang4",
}

CLASSICAL_TRAPS = [
    ("焉得", "建议配音写 {焉德=>焉得} 锁定 yan1 de2，防误读轻声 de5"),
    ("痴似", "建议配音写 {痴四=>痴似} 锁定 chi1 si4，防误读 shi4"),
    ("强饮", "建议配音写 {抢饮=>强饮} 锁定三声连读变调 qiang2 yin3"),
    ("更定", "古文打更时间读 geng1 ding4，建议核听防误读 geng4"),
    ("档位", "GPT-SoVITS 常误读台音 dang3，大陆统读 dang4 建议写 {宕=>档}位"),
    ("默认档", "建议配音写 默认{宕=>档} 锁定大陆统读 dang4"),
    ("最高档", "建议配音写 最高{宕=>档} 锁定大陆统读 dang4"),
    ("思考档", "建议配音写 思考{宕=>档} 锁定大陆统读 dang4"),
    ("调高", "程度/档位调高读 tiao2 gao1，建议写 {条=>调}高 防误读 diao4"),
    ("调低", "程度/档位调低读 tiao2 di1，建议写 {条=>调}低 防误读 diao4"),
]

EN_TRAPS = [
    (re.compile(r"(?<![A-Za-z])tokens?(?![A-Za-z])", re.IGNORECASE), "token", "纯中文微调模型直读英文 token 易发成『抽坑』，建议写 {偷肯=>token} 锁定清音，字幕仍显示 token"),
    (re.compile(r"(?<![A-Za-z])PDF(?![A-Za-z])"), "PDF", "建议写 {P D F=>PDF} 逐字母清晰播报，防连读糊音"),
]


def split_dual_track(raw_text: str) -> tuple[str, str]:
    """Parse '{say=>show}' inline dual-track tags and strip '*keyword*' emphasis markers."""
    say = re.sub(r"\{([^}]*)=>[^}]*\}", r"\1", raw_text).replace("*", "")
    show = re.sub(r"\{[^}]*=>([^}]*)\}", r"\1", raw_text).replace("*", "")
    return say.strip(), show.strip()


def load_entries(path: Path) -> list[dict]:
    """Load script entries from either JSON scene config or plain-text script."""
    content = path.read_text(encoding="utf-8-sig")
    entries: list[dict] = []

    stripped = content.lstrip()
    if path.suffix.lower() == ".json" or stripped.startswith("[{"):
        try:
            data = json.loads(content)
            for sc in data:
                sid = sc.get("id", "Scene")
                for idx, ln in enumerate(sc.get("lines", []), 1):
                    raw_show = ln.get("text", "")
                    raw_say = ln.get("ttsText") or raw_show
                    say, show = split_dual_track(raw_say)
                    if "ttsText" in ln:
                        _, show = split_dual_track(raw_show)
                    entries.append(
                        {
                            "loc": f"{sid}-L{idx}",
                            "sec": sid,
                            "say": say,
                            "show": show,
                            "pause": float(ln.get("pauseAfterSec", 0.8)),
                        }
                    )
            return entries
        except json.JSONDecodeError:
            entries.clear()

    cur_sec = "S01"
    for line_no, raw in enumerate(content.splitlines(), 1):
        l = raw.strip()
        if not l or l.startswith("#") or l.startswith("@gap"):
            continue
        if l.startswith("[") and l.endswith("]"):
            cur_sec = l[1:-1].strip() or cur_sec
            continue
        pause = 0.45
        if "|" in l:
            l, p_str = l.rsplit("|", 1)
            try:
                pause = float(p_str.strip())
            except ValueError:
                pause = 0.45
            l = l.strip()
        say, show = split_dual_track(l)
        entries.append({"loc": f"行{line_no}[{cur_sec}]", "sec": cur_sec, "say": say, "show": show, "pause": pause})
    return entries


def mask_quotes(s: str) -> str:
    return re.sub(r"[\"“「『《][^\"”」』》]*[\"”」』》]", lambda m: "□" * len(m.group(0)), s)


def audit_polyphones(entries: list[dict]) -> list[str]:
    try:
        from pypinyin import Style, pinyin
        has_pyp = True
    except Exception:
        has_pyp = False

    alerts: list[str] = []
    for item in entries:
        say = item["say"]
        show = item["show"]
        if SIGNATURE_MOTTO in say or SIGNATURE_MOTTO in show:
            continue
        for phrase, advice in CLASSICAL_TRAPS:
            if phrase in say:
                alerts.append(f"  [{item['loc']}] 正音高危词 {phrase}：{advice}")
        for en_pat, label, advice in EN_TRAPS:
            if en_pat.search(say):
                alerts.append(f"  [{item['loc']}] 英文借词正音提示 {label}：{advice}")

        flagged_chars = []
        for idx, ch in enumerate(say):
            if ch in {"得", "地", "了", "着", "的", "和", "只", "中", "为", "好", "少", "更", "正", "看", "没", "都", "分", "间", "大"}:
                continue
            if ch in POLYPHONE_MAP:
                ctx = say[max(0, idx - 3) : min(len(say), idx + 4)]
                if has_pyp:
                    ctx_py = "".join(x[0] for x in pinyin(ctx, style=Style.TONE3, neutral_tone_with_five=True))
                    flagged_chars.append(f"{ch}({ctx} -> {ctx_py} | 备选:{POLYPHONE_MAP[ch]})")
                else:
                    flagged_chars.append(f"{ch}({ctx} | 备选:{POLYPHONE_MAP[ch]})")
        if flagged_chars:
            # Show if already overridden via dual-track
            note = " [已设正音轨]" if say != show else ""
            alerts.append(f"  [{item['loc']}]{note} 含重点多音/生僻字：{'；'.join(flagged_chars[:4])}")
    return alerts


def audit_readings(entries: list[dict]) -> list[str]:
    """List numbers / currency / percent / Latin tokens with the reading the synth script will send to TTS."""
    alerts: list[str] = []
    for item in entries:
        say = item["say"]
        risks = find_reading_risks(say)
        if not risks:
            continue
        shown = []
        for tok in dict.fromkeys(risks):
            reading = normalize_numbers_zh(tok)
            shown.append(f"{tok} -> {reading}" if reading != tok else f"{tok}（英文原样送入，请核听）")
        alerts.append(f"  [{item['loc']}] {'；'.join(shown[:5])}")
    return alerts


def main() -> int:
    ap = argparse.ArgumentParser(description="Lint voiceover script for natural spoken cadence and polyphone traps.")
    ap.add_argument("script", help="Path to .json scene script or .txt script")
    ap.add_argument("--cps", type=float, default=4.8, help="Estimated speech rate in chars/sec (default 4.8)")
    ap.add_argument("--max-line", type=int, default=25, help="Max characters per single subtitle line (default 25)")
    ap.add_argument("--max-breath", type=int, default=24, help="Max characters between two punctuation marks (default 24)")
    ap.add_argument("--tics", default="然后,的话,就是", help="Comma-separated filler tics to count")
    a = ap.parse_args()

    entries = load_entries(Path(a.script))
    if not entries:
        print("未读取到有效台词条目。")
        return 1

    sections = []
    for e in entries:
        if e["sec"] not in sections:
            sections.append(e["sec"])
    last_sec = sections[-1]

    problems: list[str] = []
    total_sec = 0.0
    sec_totals: dict[str, float] = {}
    book_hits = 0

    for e_idx, item in enumerate(entries):
        loc, sec, say, show, pause = item["loc"], item["sec"], item["say"], item["show"], item["pause"]
        dur = len(UNIT_RE.findall(say)) / a.cps + pause
        total_sec += dur
        sec_totals[sec] = sec_totals.get(sec, 0.0) + dur

        if SIGNATURE_MOTTO in show or SIGNATURE_MOTTO in say:
            continue

        masked = mask_quotes(say)
        if e_idx == 0:
            for pat, why in COLD_OPEN_PATTERNS:
                m = re.search(pat, masked)
                if m:
                    problems.append(f"{loc} {why}（{m.group(0)}）：{say[:30]}")

        pm = PAREN_RE.search(masked)
        if pm:
            problems.append(f"{loc} 口播含括号补充（{pm.group(0)} 无法自然念出，请并入短句或删掉）")

        triplet = find_parallel_triplets(masked)
        if triplet:
            problems.append(f"{loc} 连续三句同构排比（{triplet}），建议留最具体的一句其余砍掉")

        binary_src = say
        for idiom in BUER_IDIOMS:
            binary_src = binary_src.replace(idiom, "□" * len(idiom))
        binary_src = mask_quotes(binary_src)
        for pat in BINARY_PATTERNS:
            m = pat.search(binary_src)
            if m:
                problems.append(f"{loc} 触发禁用二元反转句式（{m.group(0)}）：{say[:32]}")
                break

        for w in BANNED_WORDS:
            if w in say:
                problems.append(f"{loc} 含禁用营销/抽象词 {w}：{say[:30]}")

        for w in END_ONLY_WORDS:
            if w in say and sec != last_sec:
                problems.append(f"{loc} 非结尾段提前出现 {w}（易导致观众误判结束划走）")

        for ph in re.split(f"[{BREAK_CHARS}]", say):
            u_cnt = len(UNIT_RE.findall(ph))
            if u_cnt > a.max_breath:
                problems.append(f"{loc} 单气口过长（{u_cnt} 字 > {a.max_breath} 字，易抢气吞字）：{ph}")

        if len(HAN_RE.findall(show)) > a.max_line * 2:
            problems.append(f"{loc} 单条双行字幕总字数过长（{len(HAN_RE.findall(show))} 字 > {a.max_line * 2} 字）：{show[:28]}...")

        masked = mask_quotes(say)
        for pat, why in CLICHE_PATTERNS:
            for m in re.finditer(pat, masked):
                problems.append(f"{loc} {why}（{m.group(0)}）：{say[:28]}")

        for pat, sug in BOOK_MONO:
            for m in re.finditer(pat, masked):
                book_hits += 1
                ctx = say[max(0, m.start() - 7) : m.end() + 7]
                problems.append(f"{loc} 书面单字（{m.group(0)}）建议改口语双字（{sug}）：{ctx}")

    # Sentence-length variation per chapter/group
    by_sec: dict[str, list[int]] = {}
    for item in entries:
        for sent in re.split(r"[。？！]", item["say"]):
            n_han = len(HAN_RE.findall(sent))
            if n_han >= 3:
                by_sec.setdefault(item["sec"], []).append(n_han)
    for sec, lengths in by_sec.items():
        if len(lengths) >= 4:
            cv = statistics.pstdev(lengths) / max(1e-6, statistics.mean(lengths))
            if cv < 0.25:
                problems.append(f"[{sec}] 句子长短过于整齐（变异系数 {cv:.2f} < 0.25），建议穿插一两句短句打破机械感")

    all_say = "".join(e["say"] for e in entries)
    all_masked = mask_quotes(all_say)
    total_han = max(1, len(HAN_RE.findall(all_say)))
    particles = re.findall(r"[吧呢嘛啊呀啦](?=[，。？！；]|$)", "。".join(e["say"] for e in entries))
    tics_cnt = sum(all_say.count(w) for w in a.tics.split(",") if w)

    v1_hits = [(m.group(0), sug, e["loc"]) for e in entries for pat, sug in VERB_MONO for m in re.finditer(pat, mask_quotes(e["say"]))]
    v2_cnt = len(VERB_DI_RE.findall(all_masked))
    nv = len(v1_hits) + v2_cnt

    has_motto = any(SIGNATURE_MOTTO in e["show"] for e in entries)

    print("=== 口播人话与韵律体检报告 ===")
    if problems:
        for p in problems:
            print(f"- {p}")
    else:
        print("未发现句式、单字公文腔或气口超长问题。")

    print(f"\n总汉字数：{total_han} 字 | 预估配音总时长：{total_sec / 60:.2f} 分钟（{total_sec:.1f} 秒）")
    print(f"书面公文单字：{book_hits} 处（理想为 0） | 句尾语气词：{len(particles)} 个（{len(particles) / total_han * 1000:.1f} 个/千字） | 口头禅：{tics_cnt} 次")
    if nv >= 6:
        ratio = v2_cnt / nv
        status = "比例舒适" if 0.65 <= ratio <= 0.90 else ("单字动词偏多，建议多换双字词" if ratio < 0.65 else "几乎全双字词，可自然留一两处单字")
        print(f"双音节动词占比：{v2_cnt}/{nv} = {ratio:.0%}（{status}）")
    elif nv > 0:
        print(f"双音节动词占比：{v2_cnt}/{nv}（样本少于 6 个，不下结论）")
    print(f"创作者固定结束语检查：{'已原字保留' if has_motto else '当前稿件未包含固定结束语（若为哲思人文视频请确认补入终幕）'}")

    poly_alerts = audit_polyphones(entries)
    print(f"\n=== 重点多音字与古音核听清单（共 {len(poly_alerts)} 处）===")
    if poly_alerts:
        for pa in poly_alerts[:25]:
            print(pa)
        if len(poly_alerts) > 25:
            print(f"  ... 其余 {len(poly_alerts) - 25} 处略")
    else:
        print("  未检出高风险易读错多音字。")

    num_alerts = audit_readings(entries)
    print(f"\n=== 数字、货币与英文读法核听清单（共 {len(num_alerts)} 处）===")
    if num_alerts:
        print("  合成脚本会按右侧读法自动转换；读法不对就在稿件里写 {想要的读法=>原文} 锁定。")
        for na in num_alerts[:30]:
            print(na)
        if len(num_alerts) > 30:
            print(f"  ... 其余 {len(num_alerts) - 30} 处略")
    else:
        print("  未检出数字、货币或英文词。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
