#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/cybertronic23/castflux.git"
PROJECT_DIR="${HOME}/castflux"

echo "=== CastFlux 安装脚本 (macOS/Linux) ==="

# 1. 检查/安装 ffmpeg
if ! command -v ffmpeg &>/dev/null; then
    echo "[1/4] 安装 ffmpeg..."
    if [[ "$(uname)" == "Darwin" ]]; then
        brew install ffmpeg
    elif command -v apt &>/dev/null; then
        sudo apt update && sudo apt install -y ffmpeg
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y ffmpeg
    else
        echo "请手动安装 ffmpeg: https://ffmpeg.org/download.html"
        exit 1
    fi
else
    echo "[1/4] ffmpeg 已安装"
fi

# 2. 检查/安装 uv
if ! command -v uv &>/dev/null; then
    echo "[2/4] 安装 uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
else
    echo "[2/4] uv 已安装"
fi

# 3. 克隆/更新仓库
if [[ -d "${PROJECT_DIR}/.git" ]]; then
    echo "[3/4] 更新 CastFlux..."
    git -C "${PROJECT_DIR}" pull
else
    echo "[3/4] 克隆 CastFlux..."
    git clone "${REPO_URL}" "${PROJECT_DIR}"
fi
cd "${PROJECT_DIR}"

# 4. 安装 Python 依赖
echo "[4/4] 安装 Python 依赖..."
uv sync
uv pip install -e .

echo ""
echo "=== 安装完成 ==="
echo ""
echo "下一步:"
echo "  1. 设置 API 密钥:"
echo "     export DEEPSEEK_API_KEY=\"sk-...\""
echo "     export HF_TOKEN=\"hf_...\""
echo ""
echo "  2. 运行 CastFlux:"
echo "     cd ${PROJECT_DIR}"
echo "     uv run castflux video.mp4 -o output"
echo ""
echo "  首次运行会自动下载 Whisper 模型 (~200MB for base, ~3GB for large-v3)"
echo "  无 GPU 环境建议使用默认 auto 模式, 自动选择 base 模型"
