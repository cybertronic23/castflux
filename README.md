# CastFlux

> 直播内容切片流水线 —— 自动提取粉丝提问→博主回答的精华片段，加速出片。

从直播视频中自动定位问答闭环，裁剪为独立短视频，1.3x 加速并叠加上头的前情提要，生成可直接发布的爆款内容。

---

## 目录

- [核心逻辑与架构](#核心逻辑与架构)
- [工程目录解析](#工程目录解析)
- [安装部署](#安装部署)
- [使用说明](#使用说明)
- [输出说明](#输出说明)
- [注意事项与常见问题](#注意事项与常见问题)

---

## 核心逻辑与架构

### 处理流水线

```
输入 MP4
  │
  ├─[1] 提取音频 (ffmpeg)
  │      └─ pcm_s16le, 16kHz, 单声道 → temp_audio.wav
  │
  ├─[2] 语音转文字 (faster-whisper)
  │      └─ 词级时间戳 + VAD 过滤静音 → words[]
  │
  ├─[3] 说话人分离 (pyannote.audio 3.1)
  │      └─ 声纹嵌入 + 聚类 → speaker_turns[]
  │
  ├─[4] 合并对齐
  │      └─ 词级时间戳与声纹段匹配 → segments[](speaker + text)
  │
  ├─[5] 提取 QA 对
  │      ├─ 出现最多的说话人 = 博主
  │      ├─ 非博主 → 博主 的相邻段 = 一个 QA 对
  │      ├─ 合并连续博主回答段
  │      └─ 按回答长度取 Top-N
  │
  ├─[6] LLM 批量生成元信息 (OpenAI GPT-4o-mini)
  │      ├─ 并发 5 路
  │      └─ 每路输出: 前情提要 + 标题 + 人群/问题/解法
  │
  └─[7] 切片输出 (ffmpeg)
         ├─ 截取 QA 段时间范围
         ├─ setpts + atempo 实现 1.3x 倍速
         ├─ drawtext 叠加前情提要 (前 5s)
         └─ → part_01.mp4 ~ part_N.mp4
```

### 关键技术决策

| 决策 | 方案 | 理由 |
|------|------|------|
| **说话人识别粒度** | 词级 (word-level) 而非段级 | whisper segment 可能跨越说话人边界，用词级时间戳精确到词 |
| **drawtext 转义** | `textfile` 参数 + 临时文件 | 直接传字符串遇 `:{}%=` 等会崩，写文件最安全 |
| **QA 排序策略** | 按回答文字长度降序取 Top-N | 长回答通常信息量更大 |
| **LLM 并发** | `ThreadPoolExecutor(max_workers=5)` | GPT-4o-mini I/O 密集型，并行近乎线性加速 |
| **临时文件清理** | `try/finally` 保证清理 | 避免长时间运行残留大量临时文件 |
| **前置检查** | 启动时一次性校验 | 避免跑到一半才发现缺依赖 |

### 模块职责

| 模块 | 职责 | 暴露的函数 |
|------|------|-------------|
| `audio.py` | ffmpeg 音频提取 | `extract_audio` |
| `transcribe.py` | faster-whisper 语音转文字 | `transcribe_audio` |
| `diarize.py` | pyannote 说话人分离 + 词级对齐 | `diarize_audio`, `assign_speakers_to_words`, `build_speaker_segments` |
| `qa.py` | QA 对识别与排序 | `find_qa_blocks` |
| `llm.py` | LLM 批量生成标题/前情提要 | `batch_generate` |
| `slice.py` | ffmpeg 切片 + 加速 + 叠加 + 清单保存 | `slice_all_blocks`, `save_manifest` |
| `cli.py` | 参数解析 + 前置检查 + 字体检测 | `build_parser`, `check_prerequisites`, `resolve_font_path` |
| `pipeline.py` | 主流程编排 | `main` (CLI 入口) |

---

## 工程目录解析

```
castflux/
├── src/
│   └── castflux/             # 核心包
│       ├── __init__.py       # 版本信息 (__version__)
│       ├── __main__.py       # python -m castflux 入口
│       ├── cli.py            # CLI 参数解析 + 前置检查 + 字体检测
│       ├── audio.py          # 步骤1: ffmpeg 音频提取
│       ├── transcribe.py     # 步骤2: faster-whisper 语音转文字
│       ├── diarize.py        # 步骤3: pyannote 说话人分离 + 词级对齐
│       ├── qa.py             # 步骤4: QA 对识别与排序
│       ├── llm.py            # 步骤5: LLM 批量生成标题/前情提要
│       ├── slice.py          # 步骤6: ffmpeg 切片 + 加速 + 叠加文字
│       └── pipeline.py       # 主流程编排 (CLI 入口)
│
├── tests/                    # 单元测试
│   ├── __init__.py
│   └── test_qa.py
│
├── pyproject.toml            # 项目配置 + CLI 入口声明
├── README.md                 # 本文档
├── uv.lock                   # 依赖锁文件
└── .venv/                    # 虚拟环境 (自动生成)
```

---

## 安装部署

### 前置环境要求

| 组件 | 版本要求 | 用途 |
|------|---------|------|
| Python | >= 3.10 | 运行环境 |
| UV | >= 0.4.0 | 依赖管理 |
| ffmpeg | >= 4.x | 音视频处理 |
| HuggingFace Token | 需接受 pyannote 协议 | 下载说话人分离模型 |
| OpenAI API Key | 有效 | 调用 GPT-4o-mini 生成标题 |

### 安装步骤

```bash
# 1. 安装 ffmpeg
brew install ffmpeg              # macOS
sudo apt install ffmpeg          # Ubuntu/Debian

# 2. 进入项目目录
cd castflux

# 3. 用 UV 创建虚拟环境并安装依赖 (~5-15 min)
uv sync

# 4. 安装 CastFlux 到当前环境 (开发模式)
uv run pip install -e .

# 5. 验证安装
castflux --help

# 6. 设置环境变量
export OPENAI_API_KEY="sk-..."
export HF_TOKEN="hf_..."
```

### HuggingFace Token 配置

1. 在 https://huggingface.co/settings/tokens 创建 token
2. 登录后接受模型协议:
   - https://huggingface.co/pyannote/speaker-diarization-3.1
   - https://huggingface.co/pyannote/segmentation-3.0
3. `export HF_TOKEN="hf_xxxx"`

---

## 使用说明

### 基本用法

提供两种运行方式:

```bash
# 方式一: 命令行工具 (推荐)
castflux input_video.mp4 -o slices

# 方式二: 模块直接运行
uv run python3 -m castflux input_video.mp4 -o slices
```

### 完整参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `video` | (必填) | 输入 MP4 文件路径 |
| `-o, --output` | `output_slices` | 输出目录 |
| `--model` | `large-v3` | Whisper 模型大小 |
| `--num-slices` | `10` | 输出切片数量 |
| `--speed` | `1.3` | 视频加速倍率 |
| `--llm-workers` | `5` | LLM 并发数 |
| `--keep-audio` | — | 保留临时音频文件 |
| `--verbose` | — | DEBUG 级别日志 |

### 示例

```bash
# 基本用法
castflux live_2025_01_15.mp4

# 快速试验: tiny 模型 + 3 个切片
castflux test_clip.mp4 --model tiny --num-slices 3

# 自定义: 5 切片, 1.5x 倍速
castflux live.mp4 -o output --num-slices 5 --speed 1.5

# 详细日志
castflux live.mp4 --verbose
```

### 运行日志示例

```
14:30:01 [INFO] ================================================
14:30:01 [INFO] CastFlux 启动
14:30:01 [INFO] 字体: /System/Library/Fonts/PingFang.ttc
14:30:01 [INFO] 目标: 10 切片 @ 1.3x 倍速
14:30:01 [INFO] 步骤1/6: 提取音频...
14:30:15 [INFO] 步骤2/6: 语音转文字 (模型: large-v3)...
14:45:00 [INFO]   转录完成: 9000.0s 音频 → 125430 词
14:45:00 [INFO] 步骤3/6: 说话人分离 (pyannote.audio)...
15:00:00 [INFO]   说话人分离完成: 856 段
15:00:05 [INFO]   博主 speaker: SPEAKER_00 (共 623 段)
15:00:05 [INFO]   检测到 47 个 QA 对, 选取 10 个
15:00:05 [INFO] 步骤5/6: 生成标题和提要 (并发 5)...
15:00:25 [INFO] 步骤6/6: 切片 + 1.3x 加速 + 叠加文字 (并发 2)...
15:05:00 [INFO] ✅ 完成！10 个切片 → /Users/.../output_slices
15:05:00 [INFO] 📄 清单: /Users/.../output_slices/titles.txt
```

---

## 输出说明

```
slices/
├── part_01.mp4 ~ part_10.mp4    # 问答切片 (1.3x 加速 + 前情提要)
├── titles.json                   # 结构化标题数据
├── titles.txt                    # 可读标题清单
└── transcript.json               # 完整转写 (调试用)
```

### titles.json 格式

```json
[
  {
    "index": 1,
    "title": "打工人必看！社保断缴怎么补救",
    "crowd": "打工人",
    "problem": "社保断缴",
    "solution": "60天内补缴不影响待遇",
    "file": "slices/part_01.mp4",
    "start_time": 1234.56,
    "end_time": 1300.78,
    "duration": 66.22
  }
]
```

---

## 注意事项与常见问题

### 模型下载

- Whisper large-v3: ~3GB
- pyannote diarization 3.1: ~200MB
- pyannote segmentation 3.0: ~200MB

缓存至 `~/.cache/huggingface/` 和 `~/.cache/whisper/`。

### GPU 加速

- large-v3 推荐 ≥6GB VRAM；CPU 可跑但慢 (2.5h 视频约需 1-2h 转写)
- 降级使用 `--model medium` 或 `--model small` 可显著降低资源

### 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `ffmpeg 未安装` | 系统缺 ffmpeg | `brew install ffmpeg` |
| `OPENAI_API_KEY 未设置` | 缺 API key | `export OPENAI_API_KEY=sk-...` |
| `HF_TOKEN 未设置` | 缺 HuggingFace token | 见配置说明 |
| `说话人分离失败` | token 未授权 | 检查是否已接受模型协议 |
| `无 QA 对` | 无双人对话 / 声纹不准确 | 检查视频内容 |
| `LLM 调用全部失败` | 网络 / key 问题 | 检查网络和 key |

### 本地 LLM 替代

```bash
export OPENAI_BASE_URL="http://localhost:11434/v1"
export OPENAI_API_KEY="ollama"
```

### 缓存清理

```bash
rm -rf ~/.cache/whisper/ ~/.cache/huggingface/hub/
```
