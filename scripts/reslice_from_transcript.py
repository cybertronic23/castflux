#!/usr/bin/env python3
import argparse
import json
import logging
import sys
from pathlib import Path

from castflux.cli import resolve_font_path, setup_logging
from castflux.env import load_env_files
from castflux.llm import batch_generate
from castflux.qa import find_qa_blocks
from castflux.slice import save_manifest, slice_all_blocks


logger = logging.getLogger("castflux")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reuse an existing transcript.json to regenerate CastFlux clips.",
    )
    parser.add_argument("video", help="Original MP4 video path")
    parser.add_argument("transcript", help="Existing transcript.json path")
    parser.add_argument("-o", "--output", default="output_slices/reslice", help="Output directory")
    parser.add_argument("--num-slices", type=int, default=0, help="0 means all detected QA blocks; positive number selects top N")
    parser.add_argument("--speed", type=float, default=1.3, help="Playback speed multiplier")
    parser.add_argument("--llm-provider", default=None, help="LLM provider")
    parser.add_argument("--llm-model", default=None, help="LLM model")
    parser.add_argument("--llm-workers", type=int, default=5, help="LLM concurrency")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    load_env_files(include_home=True)
    setup_logging(args.verbose)

    video_path = Path(args.video)
    transcript_path = Path(args.transcript)
    output_dir = Path(args.output)

    if not video_path.exists():
        logger.error("视频文件不存在: %s", video_path)
        return 1
    if not transcript_path.exists():
        logger.error("transcript.json 不存在: %s", transcript_path)
        return 1

    data = json.loads(transcript_path.read_text(encoding="utf-8"))
    words = data.get("words") or []
    segments = data.get("segments") or []
    if not segments:
        logger.error("transcript.json 里没有 segments，无法重新切片")
        return 1

    logger.info("=" * 50)
    logger.info("CastFlux 复用 transcript 重新切片")
    logger.info("视频: %s", video_path)
    logger.info("transcript: %s", transcript_path)
    logger.info("输出: %s", output_dir)

    qa_blocks = find_qa_blocks(segments, target_count=args.num_slices, words=words)
    metas = batch_generate(
        qa_blocks,
        max_workers=args.llm_workers,
        provider=args.llm_provider,
        model=args.llm_model,
    )
    titles = slice_all_blocks(
        str(video_path),
        output_dir,
        qa_blocks,
        metas,
        speed=args.speed,
        font_path=resolve_font_path(),
    )
    save_manifest(titles, output_dir)

    logger.info("完成！%s 个切片 -> %s", len(titles), output_dir.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
