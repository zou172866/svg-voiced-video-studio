---
name: svg-voiced-video-studio
description: 将口播稿、分镜脚本或选题按信息点动态分幕，制作成带本地个人音色配音的 4K 60fps 原生几何 SVG 动态视频，并配套四尺寸防裁切高清封面、同步 SRT 字幕与五平台（B站、小红书、抖音、视频号、快手）过检标题简介及置顶首评。当用户要求制作哲思、商业拆解或产品横评 SVG 有声视频、排查 GPT-SoVITS 中英混读与吞字或微调新音色、批量生成防宫格切字四规格封面时使用；不处理实拍素材剪辑或写实人物插画生成。
---

# svg-voiced-video-studio：60帧有声 SVG 视频与多平台交付工作坊（v6）

把文稿、分镜或核实过的案例转化为 **本地个人音色零吞字配音 + 纸墨拟音 + `4K 60fps` 杂志内页级原生几何 SVG 动态视频 + `@2x` 四尺寸防裁切层级封面 + 五平台纯文字标题简介与置顶首评**。

> **动工前必读两层文档**：先读 1 页 [美术方向](references/art-direction.md)（核心拷问：这一帧印成杂志内页能不能用？），再按需查 [SVG 动态画面审美手册](references/svg-motion-aesthetics.md) 的网格坐标、质检阈值与组件用法。

## 关键不变量

1. **先体检稿件与配音环境，再拆句缓存合成与纸墨拟音混音。** 依据：汉语双音节韵律词、Grice 会话准则与视听材质一致性。合成前必跑 [lint_script.py](scripts/lint_script.py) 清查书面公文单字、二元反转、五类口播 AI 指纹与多音字读法（读错词用 `{念法=>字幕}` 双轨锁定）；[synth_voiceover_template.py](scripts/synth_voiceover_template.py) 支持 `--check-only`、`out/.tts_cache/` 续合、`--asr-verify` 与纸墨物理建模拟音（[sfx_synth.py](scripts/sfx_synth.py)：`page_turn` 翻纸、`stamp_thud` 盖章闷响、`pen_stroke` 笔尖划纸、`ruler_drop` 尺子落桌、`ledger_tick` 刻度轻叩，支持 `assets/sfx/<kind>.wav` 优先覆盖）。工艺参数见 [口播人话与防切尾音工艺手册](references/kaikou-voice-and-script-craft.md)。
2. **实测秒数驱动 `60fps` 贯通画布，动作改变空间且快离场。** 依据：归一化时间参数化与视听同步感知窗。组件严禁写死帧号；模式 C 保持纯宣纸左/顶极简留白（无左侧竖线、无字幕左竖杠、无顶部进度条），以 `disableMasterFade` 推镜/匹配剪辑连贯衔接不清场，核心数字落定盖一枚朱砂方印（`<EditorialSealStamp>`）；每幕至少 1 个结构性空间主动作（推镜、纸面擦除、柱条生长、墨线划断、路由分流），禁用纯透明度淡入 PPT；模式 C 锁零回弹弹簧 `hero / swissSnap`，离场 `0.25s`，中文画面字停满 `minReadHoldSec()`。
3. **巨尺主角、留白成块、纸面排印与硬门禁构图轮换。** 依据：瑞士国际主义尺幅对比与格式塔图底分离。竖屏 G1 巨数达 `320～480px`，主角高度 `≥ 40%`；图形与 `54px` 跟声标红字幕下沉贴近成组（间距 `≤ 72px`），整块留白推向画幅上方或右侧；严禁大黑底终端卡片（改用 `<PaperCommandLine>` 排在纸面上）与大面积红底白字按钮（红只用于字、≤3px 细线或紧凑方印）；全片至少 `1` 幕 G1 + `1` 幕 G3/G4，相邻幕 Dice 超限直接判 `FAIL`。
4. **四尺寸封面用层级主标与开放双栏，封面与正片同字体零制作参数。** 依据：180px 缩略图信息层级与品牌一致性。主标采用「`1` 个超大钩子（数字/专名，朱砂红只给信息不给口号）+ `1～2` 行中号说明」，双栏数据仅用 1 根细线隔开（零外框、零实心底），彻底删除 `4K 60FPS / 01:25` 制作参数与英文装饰页眉；模式 C 全程统一 `Source Han Sans CN Heavy`，模式 A/B 统一衬线且混排拉丁锁零字距；`9:16` 严锁中央 `3:4` 安全区（上下留白 `≥ 240px`）。细则见 [五平台文案与四尺寸封面规范](references/five-platform-copy-and-cover-spec.md)。
5. **发布文案守住语言与事实边界，哲思片保留专属结束语。** 纯文字零格式、去引号、快手最多 `4` 个话题、禁用二元反转与假设变事实；哲思人文片终幕原字保留「以不休止的追问，找到鲜活的自我；在有限的共识里，达成无限的可能。」（分号拆两句合成，句末留白 `4.5s～5.5s`）。
6. **分幕随信息点动态伸缩，严禁凑固定幕数。** 按「一幕只立一个核心信息点」自然切分（短快评 `3～5` 幕、常规拆解 `5～9` 幕、深度长片 `10～16+` 幕），数据口径严守零起点与统计诚实度。
7. **两段式动效与静态审美硬检 + 正反参考板独立盲审双过关才交付。** 依据：缺陷前移与客观对照防确认偏误。编码前跑 [audit_aesthetics.py](scripts/audit_aesthetics.py) 查静态 10 项像素 + 7 项源码（含纯淡入告警与 G1/G3-G4 配额）；1K 样片渲染后跑 [inspect_video.py](scripts/inspect_video.py) 核查 6 项硬指标 + 第 7 项 `motion_dynamics`（每幕 `10fps` 帧差与结构位移峰值曲线，零主动作 `FAIL`），再由不看代码的独立盲审子 Agent 对照 `assets/reference_board_good.png` 与 `assets/reference_board_bad.png` 逐条验真。

---

## 视觉母版与画布模式选择

| 模式 | 逻辑画布（先 `1K` 样片 `--scale=1` → 审定后超采 `4K` `--scale=2`） | 核心色板（零渐变、`0px` 直角） | 全程唯一展示字体（封面 = 正片） | 招牌骨架与合成预设 | 适用题材 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A. 深炭黑夜车哲思风** | `1920×1080` → **`3840×2160`** | 底 `#111110` · 主墨 `#F2EFE9` · 焦点 `#D94E28` | `STUDIO_FONTS.serifMixed`（500～600 无伪粗，拉丁字距 `0`） | 单画布推镜 · `--preset long --speed 1.00` · `--theme dark` | 内省剖析、存在主义长片 |
| **B. 瑞士典藏暖宣账本风** | `1920×1080` → **`3840×2160`** | 底 `#F5F0E6` · 纸面 `#FAF7F1` · 炭墨 `#191715` · 火漆印 `#C83E2B` | `STUDIO_FONTS.serifMixed`（500～600 无伪粗，拉丁字距 `0`） | 暖宣手卷推镜 · `--preset long --speed 1.00` · `--theme vellum` | 时间与金钱账本、古典哲学长片 |
| **C. 瑞士暖纸媒竖屏快解说** | `1080×1920` → **`2160×3840`** | 底 `#F5F1EA` · 纸页 `#FAF8F3` · 墨黑 `#1A1A18` · 朱砂红 `#D93B22` | `Source Han Sans CN Heavy`（800～900，禁混用衬线主标） | 纯宣纸极简留白（零左竖线/零顶栏进度条）+ 核心落点朱砂方印 · `--preset short --speed 1.07` · `--theme editorial` | 竖屏商业拆解、产品横评与实盘数据短片 |

数字统一 `lining-nums tabular-nums`（禁 `Georgia`），中西/数字/斜杠命令统一过 `panguSpace()`。

---

## 标准五步工作流

若工作区 `AGENTS.md` 设有人工审阅闸门（选题、文稿终审），先在对应闸门停下，严禁未获放行提前渲染；定稿包确认后立即写入工程目录 `out/定稿决策.md` 作为唯一事实源。

### 第 1 步：稿件体检与零吞字缓存配音 + 纸墨拟音混音
1. 运行 `python scripts/lint_script.py 稿件路径`，修净 AI 腔与多音字，写好 `*关键词*` 与 `{念法=>原文}`。
2. 定位 `gpt-sovits-studio/voice_profile.json`（优先用专属 `.venv\Scripts\python.exe`，首次 `--check-only` 预检；训练或报错读 [GPT-SoVITS Windows 单卡微调排坑手册](references/gpt-sovits-windows-finetune.md)）。
3. 运行 [synth_voiceover_template.py](scripts/synth_voiceover_template.py)（选 `--preset`、`--speed`、`--sfx auto`，含英文专名加 `--asr-verify`），产出 `public/audio/S01..SXX.mp3`、`sfx_bus.mp3`（纸墨拟音）、`mixed_master_ducked.mp3`（`-14.0 LUFS` 唯一总母带）、`src/data/scenesData.json`、`out/` 下 `.srt` 与 `chapters.txt`。
4. **编码前必须用多模态 `read_file` 逐幕真耳听检 `public/audio/S01..SXX.mp3`**（确认英文与多音字零糊音、零跳词）。

### 第 2 步：搭建贯通式 Remotion `60fps` 原生 SVG 工程
1. 有可复用 `node_modules` 时用 Windows Junction 挂载；复制 [motion_60fps.ts](assets/motion_60fps.ts)、[SceneFrameShell_60fps.tsx](assets/SceneFrameShell_60fps.tsx) 与 [SwissSvgPrimitives.tsx](assets/SwissSvgPrimitives.tsx)。
2. 合成 ID：整片 `MainEssay`，分幕 `Scene-S01`…`Scene-SXX`；总母带只在 `MainEssay` 挂一次；模式 C 保持纯宣纸极简画幅（无左侧竖线、无字幕左竖杠、无顶部章节进度条与一切英文装饰页眉/制作参数）。
3. 优先复用 G1～G6 原语（`MonumentMetric` / `AsymmetricSplit` / `FlowRouter` / `SwissBarAxis` / `EditorialStrikeReveal` / `SilentEpigraph`）与纸面扩展原语（`PaperCommandLine` / `EditorialSealStamp` / `SingleCanvasAct` / `MixedSerifText`），竖屏默认下沉贴近 `54px` 跟声标红字幕（`bottomAnchorY()`），全片保证 `≥ 1` 幕 G1 + `≥ 1` 幕 G3/G4 且每幕至少 1 个空间主动作。

### 第 3 步：两段式动效与审美硬检 → 先出 `1K` 样片交审 → 确认后超采 `4K`
1. `npx tsc --noEmit` 零报错。
2. 运行 [extract_keyframes_template.mjs](scripts/extract_keyframes_template.mjs)（端口 `18123` 避 Hyper-V 保留段），再跑 [audit_aesthetics.py](scripts/audit_aesthetics.py)（`--theme` + `--src`）确认 10 项像素指标与 7 项源码规则无硬 `FAIL`、无纯淡入 PPT。
3. **阶段 A（先出 `1K` 样片交审）**：`npx remotion render … --scale=1 --codec=h264 --crf=18 --pixel-format=yuv420p --port=18123`。
4. 跑 [inspect_video.py](scripts/inspect_video.py)（传齐 `--expect-size`、`--expect-fps 60`、`--scenes-json`）确认 7 项硬检（含 `motion_dynamics` 帧差主动作曲线）全部 `PASS`；派**不看代码**的独立盲审子 Agent 拿 `qa_sheet.png`、`qa_phone.png`、封面 `180px` 检验表与 `assets/reference_board_good.png` / `reference_board_bad.png` 逐条盲审修净。
5. 完成第 4～5 步后把 **1K 样片 + 四尺寸封面 + 发布文案** 交用户审阅并**停下等待确认**；任何返修全程在 `--scale=1` 极速完成。
6. **阶段 B（用户确认后超采真 `4K` 终版）**：零改代码执行 `--scale=2 --codec=h264 --crf=16 --pixel-format=yuv420p --port=18123`（仅允许整数/半整数合法倍率 `2` 或 `1.5`），复跑 `inspect_video.py --expect-size 2160x3840`［横屏 `3840x2160`］终检全 `PASS`。

### 第 4 步：渲染 `@2x` 四尺寸开放式层级封面组
按 [五平台文案与四尺寸封面规范](references/five-platform-copy-and-cover-spec.md) 编写 `hook` + `sublines` + 开放双栏 JSON，运行 [render_4covers_template.py](scripts/render_4covers_template.py)（传 `--theme`、`--qa-sheet`），核查 `180px` 缩略图、单红信息焦点、`9:16` 中央 `3:4` 安全框与零制作参数。

### 第 5 步：交付纯文字五平台文案与结构化验收单
按规范第二节输出纯文字零格式文案（B 站时间轴取 `out/chapters.txt`），给出所有交付物可点击链接、预览/重渲命令及精简**交付验收单**（已验证项、未验证项、设计例外理由）。

---

## 边界、授权与停止条件

- **适用边界**：实景剪辑、真人抠像、3D 写实渲染需求，直接说明本 Skill 专注程序化原生 SVG 有声动态视频与多平台包装，不强套模板。
- **外部动作授权**：默认只在本地生成文件；未经用户明确指令，不调用浏览器或接口自动上传发布。
- **完成验收标准**：`audit_aesthetics.py` 与 `inspect_video.py`（含 `motion_dynamics`）全部硬检项 `PASS`，正反参考板盲审通过，四尺寸封面与纯文字五平台文案齐全，验收单如实写明验证范围与例外说明。
