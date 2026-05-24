# CastFlux

> 直播内容切片流水线 —— 自动提取粉丝提问→博主回答的精华片段，加速出片。

从直播视频中自动定位问答闭环，裁剪为独立短视频，1.3x 加速并叠加上头的前情提要，生成可直接发布的爆款内容。

---

## Windows 用户：下载 EXE 一键安装

> 不用装 Python、不用装 ffmpeg、不用敲任何命令。下载 → 双击 → 填入 API Key → 开用。

**👇 下载 CastFlux 安装程序**
<p align="left">
  <a href="https://github.com/cybertronic23/castflux/releases/latest">
    <img src="https://img.shields.io/github/v/release/cybertronic23/castflux?label=最新版本&color=blue">
  </a>
  <a href="https://github.com/cybertronic23/castflux/releases/latest/download/CastFlux_Setup_1.0.0.exe">
    <img src="https://img.shields.io/badge/下载-Windows_安装程序-brightgreen?logo=windows">
  </a>
</p>

```text
① 下载 CastFlux_Setup_1.0.0.exe
② 双击运行，一路"下一步"
③ 安装程序自动下载 Python / ffmpeg / 全部依赖
④ 安装完成自动打开界面
⑤ 点右上角"设置"，填入 HF_TOKEN 和 DEEPSEEK_API_KEY
⑥ 选择视频文件，开始切片！
```

> 需要 GitHub Token？→ [HuggingFace Token 配置](#huggingface-token-配置)  
> 需要 API Key？→ [LLM 提供商](#llm-提供商)

---

## 目录

- [Windows 用户：下载 EXE 一键安装](#windows-用户下载-exe-一键安装)
- [核心逻辑与架构](#核心逻辑与架构)
- [工程目录解析](#工程目录解析)
- [安装部署](#安装部署)
- [使用说明](#使用说明)
- [输出说明](#输出说明)
- [测试指南](#测试指南)
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
         ├─ drawtext 叠加前情提要 (前 5s) / Pillow PNG 降级
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
├── src/castflux/             # 核心包 (9 个模块)
├── tests/                    # 单元测试
├── scripts/
│   ├── setup_gui.bat         # Windows 一键安装（自动装 Python/UV/ffmpeg）
│   ├── run_gui.bat           # Windows 双击启动 GUI
│   ├── installer.iss         # Inno Setup 安装程序脚本
│   ├── build_installer.ps1   # 安装程序构建脚本（Windows）
│   ├── setup.sh              # macOS/Linux 一键安装脚本
│   └── castflux.bat          # Windows CLI 快捷运行脚本
├── test_data/                # 测试数据 (已 .gitignore)
│   ├── test_guide.md         # 完整测试流程文档
│   ├── scripts/              # 测试生成脚本
│   ├── input_file/           # 输入测试视频
│   └── output_slices/        # 测试输出结果
├── .github/workflows/        # GitHub Actions 构建工作流
├── Dockerfile                # 容器化部署
├── docker-compose.yml        # Docker Compose 配置
├── pyproject.toml             # 项目配置 + CLI 入口
├── README.md
├── .env.example              # 环境变量模板
├── .gitignore
├── uv.lock
└── .venv/
```

---

## 安装部署

### Windows 用户: 傻瓜式一键安装（什么都不用管）

> 无需任何命令行操作，双击即可。

有两种方式，任选其一：

**方式 A：下载 EXE 安装程序（推荐）**

从 [Releases 页面](https://github.com/cybertronic23/castflux/releases/latest) 下载 `CastFlux_Setup_x.x.x.exe`，双击运行，一路"下一步"即可。

```text
下载 → 双击 → 下一步 → 完成 → 开用！
```

**方式 B：双击 setup_gui.bat（从源码安装）**

适用于已通过 Git 克隆了本仓库的用户：

```text
步骤 1:  双击 scripts/setup_gui.bat （只需运行一次）
          ↓
     自动检测/安装 Python 3.13
     自动安装 UV 包管理器
     自动下载 ffmpeg 并解压
     自动安装 CastFlux 所有依赖
     自动在桌面创建 CastFlux 快捷方式
          ↓
步骤 2:  双击桌面 "CastFlux" 图标 （以后每次都双击这个）
```

**两种方式都不需要你手动安装任何东西**。如果提示防火墙/杀毒，选择"允许"即可。

> ⚠ 第一次启动后，点界面右上角"设置"按钮，填入 `HF_TOKEN` 和 `DEEPSEEK_API_KEY`。
> 不知道怎么获取？详见 [HuggingFace Token 配置](#huggingface-token-配置) 和 [LLM 提供商](#llm-提供商)。

---

### 其他安装方式（供参考）

| 平台 | 推荐方式 | 特点 |
|------|----------|------|
| **macOS / Linux** | 一键脚本或手动安装 | 原生性能 |
| **任何平台** | Docker | 零环境配置 |

### 前置环境要求

| 组件 | 版本要求 | 用途 |
|------|---------|------|
| Python | >= 3.10 | 运行环境 |
| UV | >= 0.4.0 | 依赖管理 |
| ffmpeg | >= 4.x | 音视频处理 |
| HuggingFace Token | 需接受 pyannote 协议 | 下载说话人分离模型 |
| LLM API Key | 有效 | 调用 AI 生成标题 (DeepSeek/Qwen/GLM 等) |

### macOS / Linux 一键脚本

```bash
curl -fsSL https://raw.githubusercontent.com/cybertronic23/castflux/main/scripts/setup.sh | bash
```

脚本会自动: 安装 ffmpeg → 安装 uv → 克隆仓库 → 安装依赖。

### 方式二: Docker 容器 (零环境配置)

适合 Windows 用户不想折腾 Python 环境, 或需要隔离运行:

```bash
# 1. 创建 .env 文件 (只需填下面两个)
cat > .env << EOF
HF_TOKEN=hf_...
DEEPSEEK_API_KEY=sk-...
EOF

# 2. 把视频放 input/ 目录
mkdir -p input output
cp your_video.mp4 input/

# 3. 运行 (模型首次下载会自动缓存)
docker compose run --rm -e VIDEO=your_video.mp4 castflux

# 4. 查看结果
ls output/
```

首次运行会下载模型 (~200MB-3GB 取决于模型), 缓存到 Docker volume 中, 下次复用。

### 方式三: 手动安装

```bash
# 1. 安装 ffmpeg + Tcl/Tk（GUI 需要）
brew install ffmpeg tcl-tk       # macOS (推荐 ffmpeg-full)
brew install python-tk           # macOS (Tkinter 支持)
sudo apt install ffmpeg python3-tk  # Ubuntu/Debian
winget install Gyan.FFmpeg       # Windows (需管理员)

# 2. 进入项目目录
cd castflux

# 3. 用 UV 创建虚拟环境并安装依赖
uv sync

# 4. 验证安装 (uv sync 已自动注册 CLI)
uv run castflux --help

# 5. 设置环境变量
export DEEPSEEK_API_KEY="sk-..."     # DeepSeek (默认)
# export QWEN_API_KEY="sk-..."       # 阿里通义千问
# export GLM_API_KEY="sk-..."        # 智谱 GLM
# export MINIMAX_API_KEY="sk-..."   # MiniMax
# export OPENAI_API_KEY="sk-..."    # OpenAI

export HF_TOKEN="hf_..."
```

### HuggingFace Token 配置

1. 在 https://huggingface.co/settings/tokens 创建 token
2. 登录后接受模型协议:
   - https://huggingface.co/pyannote/speaker-diarization-3.1
   - https://huggingface.co/pyannote/segmentation-3.0
   - https://huggingface.co/pyannote/speaker-diarization-community-1
3. `export HF_TOKEN="hf_xxxx"`（或写入项目 `.env` 文件）

---

## 使用说明

### 基本用法

提供三种运行方式:

```bash
# 方式一: 命令行工具 (推荐)
castflux input_video.mp4 -o slices

# 方式二: 模块直接运行
uv run python3 -m castflux input_video.mp4 -o slices

# 方式三: 图形界面 (推荐 Windows 用户)
uv run castflux-gui                           # macOS/Linux
uv run python -m castflux.gui                 # 通用
```

> **Windows 用户**:  
> 1. 第一次使用，双击 **`scripts/setup_gui.bat`**（自动装好全部环境）  
> 2. 以后每次双击桌面 "CastFlux" 快捷方式，或 **`scripts/run_gui.bat`** 启动
>
> macOS/Linux 需先安装 Tcl/Tk: `brew install tcl-tk python-tk`

### 完整参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `video` | (必填) | 输入 MP4 文件路径 |
| `-o, --output` | `output_slices` | 输出目录 |
| `--model` | `large-v3` | Whisper 模型大小 |
| `--num-slices` | `10` | 输出切片数量 |
| `--speed` | `1.3` | 视频加速倍率 |
| `--llm-provider` | `deepseek` | LLM 提供商: `deepseek` / `qwen` / `glm` / `minimax` / `openai` |
| `--llm-model` | (各提供商默认) | LLM 模型名, 如 `deepseek-chat` / `qwen-plus` / `glm-4-plus` |
| `--llm-workers` | `5` | LLM 并发数 |
| `--keep-audio` | — | 保留临时音频文件 |
| `--verbose` | — | DEBUG 级别日志 |

> GUI 模式下无需记忆参数，界面可直接设置。`--model` 默认 `tiny` 适合快速测试。`--verbose` 在 GUI 日志窗口始终启用。

### LLM 提供商

支持多厂商 OpenAI 兼容 API, 可通过环境变量或 `--llm-provider` 切换:

| 提供商 | 环境变量 | 默认模型 | 备注 |
|--------|----------|----------|------|
| **DeepSeek** (默认) | `DEEPSEEK_API_KEY` | `deepseek-chat` | 推荐 DeepSeek V4 |
| 阿里 Qwen | `QWEN_API_KEY` | `qwen-plus` | 通义千问 |
| 智谱 GLM | `GLM_API_KEY` | `glm-4-plus` | ChatGLM |
| MiniMax | `MINIMAX_API_KEY` | `minimax-text-01` | 小米 MiMo |
| OpenAI | `OPENAI_API_KEY` | `gpt-4o-mini` | 回退方案 |

如需自定义模型名, 设置 `--llm-model` 或 `LLM_MODEL` 环境变量。

### 示例

```bash
# 基本用法 (默认 DeepSeek)
castflux live_2025_01_15.mp4

# 使用通义千问
castflux live.mp4 --llm-provider qwen

# 使用 DeepSeek 指定模型
castflux live.mp4 --llm-provider deepseek --llm-model deepseek-chat

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

### GPU 加速 / CPU 优化

- **有 GPU**: 自动使用 large-v3 模型 (推荐 ≥6GB VRAM)
- **无 GPU** (Windows 笔记本常见): 自动回退到 base 模型, 约 200MB 下载量, 速度可接受
- 若 CPU 仍太慢, 可手动指定更小的模型:
  ```bash
  castflux video.mp4 --model tiny    # 最快, ~100MB
  castflux video.mp4 --model base    # 默认 CPU 模式, ~200MB
  castflux video.mp4 --model small   # 平衡, ~500MB
  ```

### 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `ffmpeg 未安装` | 系统缺 ffmpeg | `brew install ffmpeg` |
| `No such filter: 'drawtext'` | ffmpeg 没编译 libfreetype | `brew install ffmpeg-full` 或自动降级 Pillow 叠加 |
| `DEEPSEEK_API_KEY 未设置` | 缺 API key | 设置对应提供商的环境变量, 见 LLM 提供商表格 |
| `HF_TOKEN 未设置` | 缺 HuggingFace token | 见配置说明 |
| `说话人分离失败` | token 未授权 | 检查是否已接受模型协议 |
| `'DiarizeOutput' object has no attribute 'itertracks'` | pyannote.audio 4.x API 变化 | 已兼容处理 |
| `无 QA 对` | 无双人对话 / 声纹不准确 | 检查视频内容 |
| `LLM 调用全部失败` | 网络 / key 问题 | 检查网络和 key |

### 本地 LLM 替代

CastFlux 使用 OpenAI 兼容 API, 任何提供此接口的本地服务都可接入:

```bash
# Ollama
export LLM_PROVIDER=openai
export OPENAI_BASE_URL="http://localhost:11434/v1"
export OPENAI_API_KEY="ollama"

# vLLM / TGI
export LLM_PROVIDER=openai
export OPENAI_BASE_URL="http://localhost:8000/v1"
export OPENAI_API_KEY="sk-xxx"
```

### 缓存清理

```bash
rm -rf ~/.cache/whisper/ ~/.cache/huggingface/hub/
```

---

## 开源许可

[MIT License](LICENSE) © 2026 cybertronic23
