# svg-voiced-video-studio

[![Clones](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/zou172866/repo-traffic-archive/main/badges/svg-voiced-video-studio.json)](https://github.com/zou172866/repo-traffic-archive)

将口播稿、分镜脚本或选题按信息点动态分幕，制作成带本地个人音色配音与纸墨拟音的 **4K 60fps** 杂志内页级原生几何 SVG 动态视频，并配套四尺寸开放式层级高清封面、同步 SRT 字幕与五平台（B站、小红书、抖音、视频号、快手）纯文字过检标题简介及置顶首评。

## 解决的问题与适用边界

- **核心能力**：
  - **口播体检、双轨防吞字配音与纸墨拟音**：`lint_script.py` 清查公文单字、二元反转、五类口播 AI 指纹与多音字读法（如 `{偷肯=>token}`、`{宕=>档}`）；`synth_voiceover_template.py` 支持断点缓存续合、`faster-whisper` 中英混合打分择优、纸墨物理建模拟音（`sfx_synth.py`：翻纸 `page_turn`、盖章 `stamp_thud`、划纸 `pen_stroke`、直尺落桌 `ruler_drop`、刻度轻叩 `ledger_tick`，支持 `assets/sfx/<kind>.wav` 实录优先）与 `-14.0 LUFS` 动态闪避总母带。
  - **杂志内页级原生 SVG 60fps 动态视频（先 1K 样片审定 → 超采真 4K）**：双层美术体系（1 页 [美术方向](skills/svg-voiced-video-studio/references/art-direction.md) + 技术细则 [SVG 动态画面审美手册](skills/svg-voiced-video-studio/references/svg-motion-aesthetics.md)），内置 `SwissSvgPrimitives.tsx` 六大构图原型（G1 纪念碑巨数 / G2 非对称对切 / G3 几何拓扑流图 / G4 零起点精密数据轴 / G5 划除与纸面掀幕 / G6 极简空镜）及纸面命令行（`PaperCommandLine`）、朱砂方印（`EditorialSealStamp`）、单画布推镜（`SingleCanvasAct`）与针对抖音 `19.5:9 / 20:9` 全面屏防裁切优化的纯宣纸竖屏外壳（`SceneFrameShell_60fps.tsx`，`left=140 / right=200` 安全内框）。
  - **两段式动效与静态审美硬检 + 抖音真机裁切模拟 + 正反参考板独立盲审**：渲染前跑 `audit_aesthetics.py` 核查 11 项像素指标（主角高度 `>= 40%`、中洞与留白连通聚合、禁黑底终端大块、禁宽条红底按钮、相邻幕 Dice 硬拦截、竖屏抖音 `19.5:9/20:9` 左右贴边裁切硬拦截）与 7 项源码规则（含纯淡入 PPT 告警与全片 G1 / G3-G4 配额）；先出 `1K` 样片经 `inspect_video.py` 跑 7 项硬检（含 `10fps` 帧差与结构位移 `motion_dynamics` 曲线）并自动生成 `qa_douyin_preview.png`（iPhone `19.5:9` 全屏裁切与右侧交互图标模拟预览），对照 `assets/reference_board_good.png` 与 `assets/reference_board_bad.png` 独立盲审通过后再 `--scale=2 --crf=16` 超采出 `2160×3840` / `3840×2160` 真 4K 60fps 成片。
  - **开放式层级四尺寸 `@2x` 封面与五平台纯文字文案**：`render_4covers_template.py` 一次生成 `9:16`（上下 `280px` 中央 `3:4` 安全区 + 左右 `140px` 防抖音全面屏裁切）、`3:4`（左右 `104px`）、`4:3`、`16:9` 四张封面及 `180px` 缩略图检验表（超大钩子 + 说明层级、唯一红信息焦点、开放单细线双栏、零制作参数，封面与正片同品牌字体）及零 Markdown 纯文字发布文案。
- **适用边界**：专注于程序化原生几何 SVG 有声动态视频与多平台包装；**不处理**实景视频素材剪辑、真人抠像或写实人物插画生成。

## 安装

```bash
npx -y skills add zou172866/svg-voiced-video-studio -g --all
```

## 最短使用示例

安装后，在支持 Agent Skills 的客户端中直接调用：

> 使用 `$svg-voiced-video-studio` 将这份实测文稿按信息点动态分幕，制作成个人音色与纸墨拟音的 60fps 瑞士纸媒风 SVG 视频（先出 1K 样片交审，审定后超采 4K），配套生成四尺寸开放式层级封面与五平台纯文字发布文案，并完成两段式动效与七项硬检。

## 运行环境依赖

- 支持 Agent Skills 的客户端（如 Google Antigravity、Claude Code、Codex、Cursor 等）
- **Node.js 18+** 与 **Remotion 4.x**（用于 60fps 关键帧抽检、1K 样片与 4K 成片渲染）
- **Python 3.10+**（含 `soundfile`、`numpy`、`scipy`、`librosa`、`pypinyin`、`Pillow`；本地配音需配置 `GPT-SoVITS v2ProPlus` 环境与可选 `faster-whisper`）
- **FFmpeg / FFprobe**（音视频流探针、EBU R128 响度硬检、10fps 动效曲线分析与编码合成）
- **Microsoft Edge / Google Chrome**（Headless `@2x` 四规格封面光栅化）

## 发布内容说明

本仓库仅包含运行该 Skill 所需的指令、参考手册、视觉正反参考板、脚本与 React/TS 模板组件；本地评测样本（`evals/`）、音色权重与运行缓存均已排除。
