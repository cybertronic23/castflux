import json
import logging
import os
import sys
from pathlib import Path

from castflux.cli import build_parser, check_prerequisites, resolve_font_path, setup_logging
from castflux.audio import extract_audio
from castflux.transcribe import transcribe_audio
from castflux.diarize import diarize_audio, assign_speakers_to_words, build_speaker_segments
from castflux.qa import find_qa_blocks
from castflux.llm import batch_generate
from castflux.slice import slice_all_blocks, save_manifest

logger = logging.getLogger("castflux")


def main():
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger.info("=" * 50)
    logger.info("CastFlux 启动")

    check_prerequisites(args.llm_provider)

    video_path = Path(args.video)
    if not video_path.exists():
        logger.error(f"视频文件不存在: {video_path}")
        sys.exit(1)

    output_dir = Path(args.output)
    font_path = resolve_font_path()
    logger.info(f"字体: {font_path}")
    logger.info(f"目标: {args.num_slices} 切片 @ {args.speed}x 倍速")

    temp_audio = "temp_audio.wav"

    try:
        audio_path = extract_audio(str(video_path), temp_audio)

        words = transcribe_audio(audio_path, args.model)

        speaker_turns = diarize_audio(audio_path)
        words = assign_speakers_to_words(words, speaker_turns)
        segments = build_speaker_segments(words)

        output_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = output_dir / "transcript.json"
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump({"words": words, "segments": segments}, f, ensure_ascii=False, indent=2)

        qa_blocks = find_qa_blocks(segments, target_count=args.num_slices)

        metas = batch_generate(
            qa_blocks,
            max_workers=args.llm_workers,
            provider=args.llm_provider,
            model=args.llm_model,
        )

        titles = slice_all_blocks(
            str(video_path), output_dir, qa_blocks, metas,
            speed=args.speed, font_path=font_path,
        )

        save_manifest(titles, output_dir)

        logger.info(f"✅ 完成！{len(titles)} 个切片 → {output_dir.resolve()}")
        logger.info(f"📄 清单: {(output_dir / 'titles.txt').resolve()}")

    except Exception as e:
        logger.exception(f"❌ 处理失败: {e}")
        sys.exit(1)
    finally:
        if os.path.exists(temp_audio) and not args.keep_audio:
            os.remove(temp_audio)
