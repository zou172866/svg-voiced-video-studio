# svg-voiced-video-studio

将口播稿、分镜脚本或选题制作成带本地个人音色配音的 **4K 60fps** 原生几何 SVG 动态视频，并配套四尺寸防裁切高清封面、同步 SRT 字幕与五平台（B站、小红书、抖音、视频号、快手）纯文字过检标题简介及置顶首评。

## 解决的问题与适用边界

- **核心能力**：
  - **口播体检与双轨防吞字配音**：`lint_script.py` 清查公文单字、AI 套话、多音字与中英借词读法（如 `{偷肯=>token}`、`{宕=>档}`）；`synth_voiceover_template.py` 物理拆句、保留英文后逗号气口、结合 `faster-whisper` 中英混合打分多遍择优，并混入避让卡点音效与 `-14.0 LUFS` 动态闪避母带。
  - **动态分幕与原生矢量 4K 60fps 视频**：按「一幕只立一个核心信息点」随内容复杂度自然切分幕数（不锁死固定幕数）；基于 `1080×1920` / `1920×1080` 逻辑画布抽帧体检（`audit_aesthetics.py`），以 `--scale=2 --crf=16` 直出 `2160×3840` / `3840×2160` 真 4K 60fps 成片，并经 `inspect_video.py` 六项程序化硬检。
  - **多视口 `@2x` 高清封面与五平台文案**：一次生成 `9:16`（中央 `3:4` 防宫格裁切）、`3:4`、`4:3`、`16:9` 四张高清封面（按东亚视觉全角字宽 `<= 6.2 em` 校验）及零 Markdown 纯文字发布文案。
- **适用边界**：专注于程序化原生几何 SVG 有声动态视频与多平台包装；**不处理**实景视频素材剪辑、真人抠像或写实人物插画生成。

## 安装

```bash
npx -y skills add zou172866/svg-voiced-video-studio -g --all
```

## 最短使用示例

安装后，在支持 Agent Skills 的客户端中直接调用：

> 使用 `$svg-voiced-video-studio` 将这份实测文稿按信息点动态分幕，制作成个人音色 4K 60fps 瑞士纸媒风 SVG 视频，配套生成四尺寸防裁切封面与五平台纯文字发布文案，并完成成片六项硬检。

## 运行环境依赖

- 支持 Agent Skills 的客户端（如 Google Antigravity、Claude Code、Codex、Cursor 等）
- **Node.js 18+** 与 **Remotion 4.x**（用于 60fps 关键帧抽检与 4K 成片渲染）
- **Python 3.10+**（含 `soundfile`、`numpy`、`scipy`、`librosa`、`pypinyin`、`Pillow`；本地配音需配置 `GPT-SoVITS v2ProPlus` 环境与可选 `faster-whisper`）
- **FFmpeg / FFprobe**（音视频流探针、EBU R128 响度硬检与编码合成）
- **Microsoft Edge / Google Chrome**（Headless `@2x` 四规格封面光栅化）

## 发布内容说明

本仓库仅包含运行该 Skill 所需的指令、参考手册、脚本与 React/TS 模板组件；本地评测样本（`evals/`）、音色权重与运行缓存均已排除。
