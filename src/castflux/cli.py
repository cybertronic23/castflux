import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

import torch

from castflux.llm import PROVIDER_CONFIG, DEFAULT_PROVIDER

logger = logging.getLogger("castflux")


def is_configured_secret(value: str | None) -> bool:
    if not value:
        return False
    value = value.strip()
    if not value:
        return False
    placeholders = ("你的", "your_", "your-", "sk-...", "hf_...")
    return not any(marker in value.lower() for marker in placeholders)


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def check_prerequisites(provider: str | None = None):
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("ffmpeg 未安装，请先安装: brew install ffmpeg / apt install ffmpeg / choco install ffmpeg")
        sys.exit(1)

    provider = provider or os.environ.get("LLM_PROVIDER") or DEFAULT_PROVIDER
    cfg = PROVIDER_CONFIG.get(provider.lower())

    if cfg:
        api_key = os.environ.get(cfg["api_key_env"]) or os.environ.get("OPENAI_API_KEY")
        if not is_configured_secret(api_key):
            logger.error(
                f"请设置环境变量 %s (或回退 %s)",
                cfg["api_key_env"],
                "OPENAI_API_KEY",
            )
            sys.exit(1)
    else:
        if not is_configured_secret(os.environ.get("OPENAI_API_KEY")):
            logger.error("请设置 OPENAI_API_KEY 环境变量")
            sys.exit(1)

    if not is_configured_secret(os.environ.get("HF_TOKEN")):
        logger.error(
            "请设置 HF_TOKEN 环境变量\n"
            "  1. 在 https://huggingface.co/settings/tokens 创建 token\n"
            "  2. 接受模型协议:\n"
            "     https://huggingface.co/pyannote/speaker-diarization-3.1\n"
            "     https://huggingface.co/pyannote/segmentation-3.0\n"
            "  3. export HF_TOKEN=hf_..."
        )
        sys.exit(1)


def resolve_font_path() -> str:
    candidates = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "C:\\Windows\\Fonts\\msyh.ttc",
        "C:\\Windows\\Fonts\\simhei.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    logger.warning("未找到系统字体，drawtext 可能失败")
    return "C:\\Windows\\Fonts\\arial.ttf" if sys.platform == "win32" else "/System/Library/Fonts/Helvetica.ttc"


def build_parser() -> argparse.ArgumentParser:
    available = ", ".join(PROVIDER_CONFIG)
    has_gpu = torch.cuda.is_available()
    default_model = "large-v3" if has_gpu else "base"
    parser = argparse.ArgumentParser(
        description="CastFlux - 直播内容切片流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "LLM 提供商:\n"
            "  默认 deepseek (需设置 DEEPSEEK_API_KEY)\n"
            "  qwen (QWEN_API_KEY)  |  glm (GLM_API_KEY)\n"
            "  minimax (MINIMAX_API_KEY)  |  openai (OPENAI_API_KEY)\n\n"
            "示例:\n"
            "  castflux live.mp4 -o slices\n"
            "  castflux live.mp4 --llm-provider qwen\n"
            "  castflux live.mp4 --llm-provider deepseek --llm-model deepseek-chat\n"
        ),
    )
    parser.add_argument("video", help="输入 MP4 视频文件路径")
    parser.add_argument("-o", "--output", default="output_slices", help="输出目录 (默认: output_slices)")
    parser.add_argument("--model", default="auto", help=f"Whisper 模型大小 (默认: auto, 有 GPU→large-v3, 无 GPU→base; 可选: tiny/base/small/medium/large-v3)")
    parser.add_argument("--num-slices", type=int, default=10, help="输出切片数量 (默认: 10)")
    parser.add_argument("--speed", type=float, default=1.3, help="视频加速倍率 (默认: 1.3)")
    parser.add_argument("--llm-provider", default=None, help=f"LLM 提供商 ({available}), 默认: {DEFAULT_PROVIDER}, 也支持 LLM_PROVIDER 环境变量")
    parser.add_argument("--llm-model", default=None, help="LLM 模型名 (如 deepseek-chat, qwen-plus), 也支持 LLM_MODEL 环境变量")
    parser.add_argument("--llm-workers", type=int, default=5, help="LLM 并发数 (默认: 5)")
    parser.add_argument("--keep-audio", action="store_true", help="保留临时音频文件")
    parser.add_argument("--verbose", action="store_true", help="详细日志")
    return parser
