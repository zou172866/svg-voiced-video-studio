---
name: svg-voiced-video-studio
description: 将口播稿、分镜脚本或选题制作成带本地个人音色配音的 60fps 原生几何 SVG 动态视频，并配套四尺寸防裁切高清封面、同步 SRT 字幕与五平台（B站、小红书、抖音、视频号、快手）过检标题简介及置顶首评。当用户要求制作哲思或商业解说 SVG 有声视频、排查 GPT-SoVITS 长句吞字或微调新音色、批量生成防宫格切字四规格封面时使用；不处理实拍素材剪辑或写实人物插画生成。
---

# svg-voiced-video-studio：60帧有声 SVG 视频与多平台交付工作坊

把文稿、分镜或核实过的案例转化为 **本地个人音色零吞字配音 + `4K 60fps` 原生几何 SVG 动态视频 + `@2x` 四尺寸防裁切封面 + 五平台标题简介与置顶首评**。

## 关键不变量

1. **先体检稿件与配音环境，再拆句多遍缓存合成。** 依据：汉语双音节韵律词理论、受众共同基础理论、Grice 会话准则与内容寻址幂等构建。合成前必跑 [lint_script.py](scripts/lint_script.py)：清查书面公文单字、二元反转、五类口播 AI 指纹（假共情、假深刻、自我加权、万能模板、三连排比）、冷开场报幕、括号补充、气口超长、句长变异系数（`≥ 0.25`）、多音字与数字英文读法；实测拆解类保留受众通用计量词（如 `token`）并全片统一、直呼对象与信源真名、按时间先后收束选型；读错的词用 `{念法=>字幕}` 或 `ttsText` 双轨锁定。合成脚本支持 `--check-only` 预检与 `out/.tts_cache/` 分句哈希续合，在 `；：——`（气口 `0.18s`）和 `。！？`（气口 `0.30s`）处物理拆句多遍择优（唯一参数出处见 [口播人话与防切尾音工艺手册](references/kaikou-voice-and-script-craft.md)）。
2. **实测秒数反向驱动 `60fps` 时间轴，快离场且露出帧对准命中点。** 依据：归一化时间参数化与视听同步感知窗。合成脚本写出 `scenesData.json`；组件严禁写死帧号，弹簧按 `SPRING_PRESETS` 四档统一同类元素（模式 C 锁无回弹档），离场 `0.25s` 快于进场，遮罩转场用 `revealOn()` 让露出帧对准强调词或切点，中文画面字停满 `minReadHoldSec()`（`字数÷4.5+1.5s`，关键数字 `≥ 2.5s`）。
3. **先抽双态静态帧目视排雷，再跑全片编码。** 依据：缺陷检测前移与格式塔图底分离。每镜抽 `25%`（进场态）与 `76%`（文字满载态），含裂片或轨迹交叉的分镜加抽 `48%`；确认线条不穿字、路径闭合、字框净距 `≥ 8px`、同屏至多 1 处强调色焦点。
4. **四尺寸封面一次配齐，`9:16` 严锁中央 `3:4` 安全区。** 依据：多视口安全框与中西混排视觉字宽规范。封面主标题纯汉字每行 `≤ 6 字`、中西混排视觉字宽 `≤ 6.2 em`（超长不可拆专名用 `--allow-7` 特批至 `7.2 em` 并自动缩字号 `8%`），`9:16` 版上下留白 `≥ 240px`。
5. **发布文案守住语言与事实边界。** 依据：期望违背检查与知识的诅咒。纯文字零格式、去引号、快手最多 `4` 个话题、禁用二元反转句式、禁止把假设推演写成作者既成事实、创作者固定结束语原字保留——细则统一见 [五平台文案与四尺寸封面规范](references/five-platform-copy-and-cover-spec.md) 第二节第 0 条，旁白与封面同样适用。
6. **哲思人文片终幕原字保留创作者固定结束语。** `以不休止的追问，找到鲜活的自我；在有限的共识里，达成无限的可能。` 来稿已有就一字不改；从选题生成脚本时默认作为终幕收尾，分号处拆两句合成，句末留白 `4.5s～5.5s`。纯商业快解说按工作区规则或用户指令执行。
7. **分幕随信息点动态伸缩，画面审美、数据口径与瑞士版式按手册执行。** 依据：Mayer 多媒体学习原则、Tufte 图形诚实度与瑞士模块网格。**严禁硬套或凑满固定幕数**：按「一幕只立一个核心信息点」随内容复杂度自然切分（短快评 `3～5` 幕、常规拆解 `5～9` 幕、深度长片 `10～16+` 幕均可自由伸缩）；数据图表（未核实数字禁上屏、先坐标后数据、柱从 0 起算、倍数验算、来源小字）、横 12 / 竖 6 栏网格与每期 `2～3` 个防同质化风格信号，均以 [SVG 动态画面审美手册](references/svg-motion-aesthetics.md) 为准。
8. **成片经 `-14 LUFS` 技术终检与独立盲审双过关才交付。** 依据：ITU-R BS.1770 响度标准与独立验证防确认偏误。总混音合入避让人声的卡点音效（[sfx_synth.py](scripts/sfx_synth.py)）并拉齐至 `-14.0 LUFS`（真峰值 `≤ -1.2 dBTP`）；渲染后必跑 [inspect_video.py](scripts/inspect_video.py) 硬检帧数、零黑帧、响度与真峰值（未检规格标 `NOT_CHECKED` 不算通过），并执行独立盲审。

---

## 视觉母版与画布模式选择

根据文稿气质与发布主阵地选择（工作区 `AGENTS.md` 或用户已指定配色时以其为准）：

| 模式 | 逻辑画布 → 4K 成片输出（`--scale=2`） | 核心色板（零渐变、`0px` 直角） | 合成预设 | 封面主题 | 适用题材 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A. 深炭黑夜车哲思风** | `1920×1080` → **`3840×2160`** | 底 `#111110` · 主墨 `#F2EFE9` · 焦点 `#D94E28` | `--preset long --speed 1.00` | `--theme dark` | 内省剖析、存在主义长片 |
| **B. 瑞士典藏暖宣账本风** | `1920×1080` → **`3840×2160`** | 底 `#F5F0E6` · 纸面 `#FAF7F1` · 炭墨 `#191715` · 火漆印 `#C83E2B` | `--preset long --speed 1.00` | `--theme vellum` | 时间与金钱账本、古典哲学长片 |
| **C. 瑞士暖纸媒竖屏快解说** | `1080×1920` → **`2160×3840`** | 底 `#F5F1EA` · 纸页 `#FAF8F3` · 墨黑 `#1A1A18` · 朱砂红 `#D93B22` | `--preset short --speed 1.07` | `--theme editorial` | 竖屏商业拆解、产品横评与实盘数据短片（幕数随信息点自然伸缩） |

数字统一 `font-variant-numeric: lining-nums tabular-nums`，严禁默认旧式数字字体（如 `Georgia`）。

**模式 C 额外注意**：外壳传 `theme={EDITORIAL_PAPER_THEME}`；竖屏画布自动切换平台遮挡安全区（上 `≥ 200px`、下 `≥ 400px`、右 `≥ 140px`，字幕单行 `≤ 16` 字）；图形只画在 `safe` 矩形内并用 `swissGrid(safe)` 贴 6 栏网格；逐条核对 lint 输出的数字读法清单。

---

## 标准五步工作流

若工作区 `AGENTS.md` 设有人工审阅闸门（选题、文稿终审），先在对应闸门停下，严禁未获放行提前渲染：
- **定稿前内部盲审与决策落盘**：提交文稿终审包前，若宿主支持子 Agent，先派未参与写稿的子 Agent 对照去 AI 味五类与事实边界审一遍并改净。定稿包将「核心主张一句话、模式及挑中的 2～3 个风格信号（至少 1 个跳出最俗版）、音色与语速、标好 `*关键词*` 的逐幕口播与九栏分镜自检、四尺寸封面大字、五平台标题」逐项编号；用户拍板后立即写入工程目录 `out/定稿决策.md`，后续渲染与跨会话接手均以该文件为唯一事实源。

### 第 1 步：稿件体检与零吞字缓存配音混音
1. 运行 `python scripts/lint_script.py 稿件路径`，修净句式、五类 AI 腔与公文单字；核对多音字与数字英文读法清单，读法不对写 `{念法=>原文}`。
2. 定位 `gpt-sovits-studio/voice_profile.json`（存在 `.venv\Scripts\python.exe` 专属环境时优先用其运行，首次加 `--check-only` 秒级预检权重、CUDA 与 `ffmpeg`）。训练新音色或遇 Windows 内存报错先读 [GPT-SoVITS Windows 单卡微调排坑手册](references/gpt-sovits-windows-finetune.md)。
3. 运行 [synth_voiceover_template.py](scripts/synth_voiceover_template.py)（选 `--preset`、`--speed`、`--sfx auto`，含英文专名或技术词时加 `--asr-verify`；已合分句自动走 `out/.tts_cache/` 复用，全量重算加 `--force-resynth`）。产出：`public/audio/S01..SXX.mp3`（纯人声质检用）、`ambient_pad.mp3`、`sfx_bus.mp3`、`mixed_master_ducked.mp3`（`48kHz` `-14.0 LUFS` 人声+闪避底乐+避让音效总母带，成片唯一音轨）、`src/data/scenesData.json`、`out/` 下 `.srt`、`chapters.txt` 与 `sfx_cues.json`。
4. 点睛的 1～2 句可加 `"fx": "canyon" | "tape" | "water"`（见 [voice_fx.py](scripts/voice_fx.py)）；**编码视频前必须用多模态 `read_file` 逐幕真耳听检 `public/audio/S01..SXX.mp3`**（重点核听英文专名与多音字无糊音、无跳词；纯中文微调音色遇 `token` 用 `{偷肯=>token}`、`PDF` 用 `{P D F=>PDF}` 双轨锁定）。

### 第 2 步：搭建解耦 Remotion `60fps` 原生 SVG 工程
1. 有可复用的 `node_modules` 时用 Windows 目录 Junction 挂载。
2. 复制 [motion_60fps.ts](assets/motion_60fps.ts) 与 [SceneFrameShell_60fps.tsx](assets/SceneFrameShell_60fps.tsx)，遵守工程约定：
   - 合成 ID：整片 `MainEssay`，分幕 `Scene-S01`…`Scene-SXX`；用 `toShellTimeline()` 转换时间轴；
   - 音轨：只在 `MainEssay` 根合成挂一次 `audio/mixed_master_ducked.mp3`，外壳 `playSceneAudio` 保持关闭；
   - 所有 `interpolate()` 显式 `clamp`；统一用 `SPRING_PRESETS`、`EASE_SNAP / EASE_GLIDE / EASE_WHIP`、默认 `0.25s` 快离场、`revealOn()` 露出对齐、`minReadHoldSec()` 停留时长与 `swissGrid(safe)` 模块网格；
   - 审美与数据实现用 `accentAt()` + `mixHex()`（红随声走）、`cameraAt()`（单画布推移）、`taperStroke()` / `inkJitter()`（模式 A、B 墨线），商业图表严守审美手册第二节数据口径。

### 第 3 步：双态抽检、`-14 LUFS` 程序化终检与独立盲审
1. `npx tsc --noEmit` 零类型错误。
2. 运行 [extract_keyframes_template.mjs](scripts/extract_keyframes_template.mjs) 导出关键帧（默认绑定 `18123` 端口避开 Windows Hyper-V/WinNAT `3000–3100` 保留端口段），目视排查穿字、缺口、孤行与平台遮挡，再跑 [audit_aesthetics.py](scripts/audit_aesthetics.py) 处理红色焦点、元素数、方框线、主角高度、密度起伏与字号提示。
3. 执行 `npx remotion render … --scale=2 --codec=h264 --crf=16 --pixel-format=yuv420p --port=18123` 默认直出原生真矢量 **4K `60fps`** 成片（竖屏 `2160×3840`、横屏 `3840×2160`，彻底消除 `yuv420p` 4:2:0 色度减半导致的朱砂红边缘发虚；`studio` 预览附带 `--port=18123` 防 `No available ports found`）。
4. 必跑 [inspect_video.py](scripts/inspect_video.py)（传齐 `--expect-size 2160x3840`［横屏 `3840x2160`］、`--expect-fps 60`、`--scenes-json src/data/scenesData.json`），确认 4K 分辨率、帧数、零黑帧、`-14.0 ± 1.5 LUFS` 响度与 `≤ -1.0 dBTP` 真峰值全部 `PASS`。
5. 若宿主支持子 Agent，把生成的 `qa_sheet.png`、`qa_phone.png` 与「观众该记住的一句话」交给**不看代码**的独立审片子 Agent，交回最严重的 `≤ 3` 个带时间码问题；修净复验后再进入下一步。

### 第 4 步：渲染 `@2x` 四尺寸防裁切高清封面组
1. 按 [五平台文案与四尺寸封面规范](references/five-platform-copy-and-cover-spec.md) 拟定封面大字并过三道硬检。
2. 运行 [render_4covers_template.py](scripts/render_4covers_template.py)（`--theme` 按模式表选择）输出四规格 `.png`，逐张核查无单字孤行且 `9:16` 文字完全落在中央 `3:4` 安全框内。

### 第 5 步：交付纯文字五平台文案与结构化验收单
按规范第二节输出纯文字零格式文案（B 站时间轴直接取 `out/chapters.txt`；工程记录留在 `out/`，不混入交付目录）。最终回复给出 `.mp4`、`.srt`、四张 `.png`、文案 `.md` 的可点击链接、`npm run studio` 预览与重渲命令，并固定附精简**交付验收单**（已验证项、未验证项、设计例外理由）。

---

## 边界、授权与停止条件

- **适用边界**：实景剪辑、真人抠像、3D 写实渲染需求，直接说明本 Skill 专注程序化原生 SVG 有声动态视频与多平台包装，不强套模板。
- **外部动作授权**：默认只在本地生成文件；未经用户明确指令，不调用浏览器或接口自动上传发布。
- **完成验收标准**：`inspect_video.py` 全部硬检项为 `PASS`（无 `FAIL` 或 `NOT_CHECKED`），四尺寸封面与纯文字五平台文案齐全，验收单如实写明已验证范围与例外说明。
