FROM python:3.11-slim AS base

# 安装 ffmpeg 和系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# 安装 Python 依赖
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 复制源码
COPY src/ src/

# 安装自身
RUN uv pip install -e .

# 模型缓存目录 (运行时通过 volume 挂载)
ENV WHISPER_CACHE_DIR=/cache/whisper
ENV HF_HOME=/cache/huggingface
ENV XDG_CACHE_HOME=/cache/xdg

ENTRYPOINT ["castflux"]
