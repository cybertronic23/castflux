import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("castflux")


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def check_prerequisites():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("ffmpeg 未安装，请先安装: brew install ffmpeg / apt install ffmpeg")
        sys.exit(1)

    if not os.environ.get("OPENAI_API_KEY"):
        logger.error("请设置 OPENAI_API_KEY 环境变量")
        sys.exit(1)

    if not os.environ.get("HF_TOKEN"):
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
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    logger.warning("未找到系统字体，drawtext 可能失败")
    return "/System/Library/Fonts/Helvetica.ttc"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CastFlux - 直播内容切片流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  castflux live.mp4 -o slices\n"
            "  castflux live.mp4 --model medium --num-slices 5\n"
            "  castflux live.mp4 --speed 1.5\n"
        ),
    )
    parser.add_argument("video", help="输入 MP4 视频文件路径")
    parser.add_argument("-o", "--output", default="output_slices", help="输出目录 (默认: output_slices)")
    parser.add_argument("--model", default="large-v3", help="Whisper 模型大小 (默认: large-v3)")
    parser.add_argument("--num-slices", type=int, default=10, help="输出切片数量 (默认: 10)")
    parser.add_argument("--speed", type=float, default=1.3, help="视频加速倍率 (默认: 1.3)")
    parser.add_argument("--llm-workers", type=int, default=5, help="LLM 并发数 (默认: 5)")
    parser.add_argument("--keep-audio", action="store_true", help="保留临时音频文件")
    parser.add_argument("--verbose", action="store_true", help="详细日志")
    return parser
