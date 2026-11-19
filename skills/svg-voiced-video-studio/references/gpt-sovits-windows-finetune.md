# GPT-SoVITS v2ProPlus Windows 单卡微调与零吞字合成排坑手册

仅在以下场景读取本文件：① 用户提供了新的个人干声录音，要求克隆/微调专属音色；② 零样本 TTS 听感不像本人（口音被抹平、基频偏移）；③ Windows 本机运行 `GPT-SoVITS` 切片、训练或长句推理出现报错与吞字。

---

## 一、为什么优先用微调 `GPT-SoVITS v2ProPlus`（对比零样本 TTS）

实测对比表明：零样本语音克隆（如 `IndexTTS` 直接喂参考音频）容易将南方温和口音洗成北方播音腔，且平均基频（`f0`）易上飘 `+8Hz` 以上；使用 `12～20` 句干净近讲干声微调 `GPT-SoVITS v2ProPlus`（`SoVITS 12 epochs + GPT 15 epochs`），合成基频与本人原声误差可控制在 `±1.5Hz` 内，咬字习惯高度还原。

---

## 二、干声预处理与防吞辅音切片铁律

1. **切片前必须先做峰值预归一化（核心避坑）**：
   - 手机或声卡直录干声峰值常在 `-10 dBFS ～ -16 dBFS`；若直接用默认 `-34 dBFS` 门限运行 `slice_audio.py`，轻声辅音与句尾余音会被拦腰切断，导致训出的模型句尾发虚或吞字。
   - **标准动作**：先将原始录音转为 `48kHz` 单声道 WAV 并峰值归一化至 **`-1.5 dBFS`**，再以 `threshold=-42, min_length=4200, min_interval=320` 沿自然气口切分。
2. **人工/听感精选黄金训练集**：
   - 宁缺毋滥：从切出的片段中剔除卡壳、咽口水、重复词片段，保留 **`12～20` 条（总计约 `90～150 秒`）零口误完整陈述句** 写入 `clean.list`；
   - 选择其中 1 条字正腔圆、`5～8 秒` 的句子作为主参考音频 `ref_audio_path`，另选 `3～4` 条不同语调的干净句作为 `aux_ref_audio_paths` 写入 `voice_profile.json`。

---

## 三、Windows + 单卡 GPU 环境四大常见报错与根治补丁

### 1. 安装依赖时 `jieba-fast` 或 `pyopenjtalk` 缺少 C++ 编译环境失败
- **修法**：直接安装预编译包 `pyopenjtalk-plus` 与纯 Python `jieba`；在虚拟环境 `site-packages/jieba_fast/__init__.py` 写入 3 行兼容导出：
  ```python
  from jieba import *
  import jieba as _jieba
  __all__ = dir(_jieba)
  ```

### 2. `s2_train.py` 报 `RuntimeError: bad allocation` 或页面文件耗尽崩溃
- **原因**：Windows `spawn` 模式下，`DataLoader(num_workers=4, pin_memory=True)` 会复制 4 份大型 CUDA 进程虚拟内存提交量，在桌面同时开着浏览器或剪辑软件时极易触发虚拟内存上限。
- **修法**：Windows 单机微调统一设 `num_workers=0, pin_memory=False`，配合 `batch_size=2, grad_ckpt=True`。

### 3. `s1_train.py` 或 `DistributedBucketSampler` 在 Windows 单卡下报 `ProcessGroupGloo` 错误
- **修法**：
  - 当 `torch.cuda.device_count() <= 1` 时，PyTorch Lightning `Trainer` 的 `strategy` 设为 `"auto"`（不要强制走 `ddp`）；
  - 在 `bucket_sampler.py` 中先判断 `torch.distributed.is_initialized()`，未初始化时默认 `num_replicas=1, rank=0`；
  - 在 `data_module.py` 中将 `persistent_workers` 设为 `self.num_workers > 0`。

### 4. 长复合句推理中途跳过 `2～4` 个汉字
- **原因**：超过 `35～40` 字且带分号 `；`、冒号 `：` 或破折号 `——` 的长句，若仅把标点替换成逗号交给 `cut2` 一次性自回归生成，注意力容易在中后段漂移跳词。
- **修法**：推理前把长句在 `；：——。！？` 处物理拆成独立短分句，逐条调用 `tts.run()`（`top_k=12, top_p=0.80, temperature=0.72, repetition_penalty=1.35`）。拆句规则、分句气口、淡入淡出与响度参数以 [口播人话与防切尾音工艺手册](kaikou-voice-and-script-craft.md) 第三节和 `scripts/synth_voiceover_template.py` 为准，本手册不再另列数值。

---

## 四、`voice_profile.json` 标准结构示例

将训练好的权重与参考音频统一保存在本地 `gpt-sovits-studio/voice_profile.json` 中供所有视频工程自动读取：

```json
{
  "version": "v2ProPlus",
  "gpt_weight": "<GPT_SOVITS_DIR>/GPT_weights_v2ProPlus/creator_voice_v1-e15.ckpt",
  "sovits_weight": "<GPT_SOVITS_DIR>/SoVITS_weights_v2ProPlus/creator_voice_v1_e12_s600.pth",
  "ref_audio_path": "<GPT_SOVITS_DIR>/dataset_me/sliced_v2/ref_main.wav",
  "prompt_text": "主参考音频对应的逐字准确中文文本。",
  "prompt_lang": "zh",
  "aux_ref_audio_paths": [
    "<GPT_SOVITS_DIR>/dataset_me/sliced_v2/aux_01.wav",
    "<GPT_SOVITS_DIR>/dataset_me/sliced_v2/aux_02.wav"
  ]
}
```
- **语速档位建议**：深度哲思/散文长视频用 `speed_factor=0.98～1.00`；高密度商业拆解竖屏短视频用 `speed_factor=1.06～1.08`。
