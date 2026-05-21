#!/usr/bin/env python3
"""
CastFlux - 直播内容切片工坊

从直播视频中自动提取"粉丝提问→博主回答"片段，
生成带有前情提要文字的爆款短视频。

工作流程:
  1. 提取音频 (ffmpeg)
  2. 语音转文字 + 词级时间戳 (faster-whisper)
  3. 说话人分离 (pyannote.audio)
  4. 提取 N 个"提问-回答"信息块
  5. 对每个块: 切片 → 1.3x 加速 → LLM 生成标题/提要 → 叠加前情提要文字
  6. 输出 N 个独立 MP4 + 标题清单
"""

import argparse
import concurrent.futures
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path

import torch
from faster_whisper import WhisperModel
from openai import OpenAI
from pyannote.audio import Pipeline
from tqdm import tqdm

logger = logging.getLogger("castflux")


# ============================================================
#  辅助函数
# ============================================================

def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def check_prerequisites():
    """检查 ffmpeg、API key 等前置条件"""
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


# ============================================================
#  步骤1: 提取音频
# ============================================================

def extract_audio(video_path: str, audio_path: str = "temp_audio.wav") -> str:
    logger.info("步骤1/6: 提取音频...")
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        audio_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    logger.debug(f"音频已保存: {audio_path}")
    return audio_path


# ============================================================
#  步骤2: 语音转文字（词级时间戳）
# ============================================================

def transcribe_audio(audio_path: str, model_size: str = "large-v3") -> list[dict]:
    logger.info(f"步骤2/6: 语音转文字 (模型: {model_size})...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    logger.info(f"  设备: {device}, 计算类型: {compute_type}")

    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    segments, info = model.transcribe(
        audio_path,
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,
    )

    words = []
    for seg in segments:
        if hasattr(seg, "words") and seg.words:
            for w in seg.words:
                if w.word.strip():
                    words.append({
                        "start": w.start,
                        "end": w.end,
                        "word": w.word.strip(),
                        "probability": w.probability,
                    })
        else:
            words.append({
                "start": seg.start,
                "end": seg.end,
                "word": seg.text.strip(),
                "probability": 1.0,
            })

    logger.info(f"  转录完成: {info.duration:.1f}s 音频 → {len(words)} 词")
    return words


# ============================================================
#  步骤3: 说话人分离
# ============================================================

def diarize_audio(audio_path: str) -> list[dict]:
    logger.info("步骤3/6: 说话人分离 (pyannote.audio)...")
    hf_token = os.environ["HF_TOKEN"]

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=hf_token,
    )

    if torch.cuda.is_available():
        pipeline.to(torch.device("cuda"))

    diarization = pipeline(audio_path)

    speaker_turns = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        speaker_turns.append({
            "start": turn.start,
            "end": turn.end,
            "speaker": speaker,
        })

    logger.info(f"  说话人分离完成: {len(speaker_turns)} 段")
    return speaker_turns


def assign_speakers_to_words(words: list[dict], speaker_turns: list[dict]) -> list[dict]:
    """将说话人标签按时间戳分配到每个词（比 segment 级更精确）"""
    for word in words:
        mid = (word["start"] + word["end"]) / 2
        assigned = "UNKNOWN"
        for turn in speaker_turns:
            if turn["start"] <= mid <= turn["end"]:
                assigned = turn["speaker"]
                break
        word["speaker"] = assigned
    return words


def build_speaker_segments(words: list[dict]) -> list[dict]:
    """将连续同说话人的词合并为说话段"""
    if not words:
        return []

    segments = []
    cur = {
        "start": words[0]["start"],
        "end": words[0]["end"],
        "speaker": words[0]["speaker"],
        "text": words[0]["word"],
    }

    for w in words[1:]:
        if w["speaker"] == cur["speaker"]:
            cur["end"] = w["end"]
            cur["text"] += " " + w["word"]
        else:
            segments.append(cur)
            cur = {
                "start": w["start"],
                "end": w["end"],
                "speaker": w["speaker"],
                "text": w["word"],
            }
    segments.append(cur)
    return segments


# ============================================================
#  步骤4: 提取"提问-回答"块
# ============================================================

def find_qa_blocks(
    segments: list[dict],
    target_count: int = 10,
    host_speaker: str | None = None,
) -> list[dict]:
    """
    基于说话人标签识别粉丝提问 + 博主回答的闭环:
      - 出现最多的说话人是博主 (host)
      - 粉丝为其他说话人
      - 粉丝连续说话段 = 提问
      - 紧接着博主的一段或多段 = 回答
    """
    speaker_counts = Counter(s["speaker"] for s in segments if s["speaker"] != "UNKNOWN")
    if not speaker_counts:
        raise RuntimeError("说话人分离失败，无法识别博主和粉丝")

    host = host_speaker or speaker_counts.most_common(1)[0][0]
    logger.info(f"  博主 speaker: {host} (共 {speaker_counts[host]} 段)")

    qa_blocks = []
    i = 0
    while i < len(segments) - 1:
        cur = segments[i]
        if cur["speaker"] != host:
            if i + 1 < len(segments) and segments[i + 1]["speaker"] == host:
                question = dict(cur)
                answer = dict(segments[i + 1])
                j = i + 2
                while j < len(segments) and segments[j]["speaker"] == host:
                    answer["end"] = segments[j]["end"]
                    answer["text"] += " " + segments[j]["text"]
                    j += 1

                qa_blocks.append({
                    "start_time": question["start"],
                    "end_time": answer["end"],
                    "question_text": question["text"].strip(),
                    "answer_text": answer["text"].strip(),
                    "full_text": (
                        f"【粉丝提问】{question['text'].strip()}\n"
                        f"【博主回答】{answer['text'].strip()}"
                    ),
                    "duration": answer["end"] - question["start"],
                })
                i = j
                continue
        i += 1

    logger.info(f"  检测到 {len(qa_blocks)} 个 QA 对")

    if not qa_blocks:
        raise RuntimeError("未检测到任何 QA 对，无法继续")

    if len(qa_blocks) <= target_count:
        logger.warning(f"  仅 {len(qa_blocks)} 个 QA 对 (目标 {target_count})，全部使用")
        return qa_blocks

    qa_blocks.sort(key=lambda x: len(x["answer_text"]), reverse=True)
    selected = qa_blocks[:target_count]
    selected.sort(key=lambda x: x["start_time"])
    logger.info(f"  选取 {len(selected)} 个最长的 QA 对")
    return selected


# ============================================================
#  步骤5: LLM 生成标题 & 前情提要
# ============================================================

SYSTEM_PROMPT = """你是一个短视频运营专家，擅长将直播中的问答内容提炼为爆款短视频。

下面是一段"粉丝提问→博主回答"的完整文字记录。请完成以下任务：
1. 提取核心信息：明确指出目标人群、具体问题、博主给出的解决方法（一句话总结）。
2. 生成一个爆款短视频标题（15字以内），必须包含"人群+问题+解决方法"的结构，吸引点击。
3. 找出一句最具冲突、干货或情绪冲击的句子作为"前情提要"（20字以内），用于视频开头抓人。

请按JSON格式返回，不要加其他文字：
{
  "crowd": "目标人群",
  "problem": "遇到的问题",
  "solution": "解决方法",
  "title": "爆款标题",
  "teaser": "前情提要文字"
}"""


def _call_llm(block_text: str, client: OpenAI) -> dict:
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": SYSTEM_PROMPT + "\n\n" + block_text}],
                temperature=0.7,
                max_tokens=300,
                timeout=30,
            )
            content = response.choices[0].message.content
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            data = json.loads(json_match.group()) if json_match else json.loads(content)
            return {
                "teaser": data.get("teaser", "").strip(),
                "title": data.get("title", "").strip(),
                "crowd": data.get("crowd", "").strip(),
                "problem": data.get("problem", "").strip(),
                "solution": data.get("solution", "").strip(),
            }
        except Exception as e:
            logger.warning(f"  LLM 调用失败 (尝试 {attempt + 1}/3): {e}")
            time.sleep(1)

    logger.error("  LLM 调用全部失败，使用默认值")
    return {
        "teaser": "精彩问答片段",
        "title": "直播精华问答",
        "crowd": "用户",
        "problem": "常见问题",
        "solution": "专家解答",
    }


def batch_generate(blocks: list[dict], max_workers: int = 5) -> list[dict]:
    """并发调用 LLM 生成所有块的标题和提要"""
    logger.info(f"步骤5/6: 生成标题和提要 (并发 {max_workers})...")
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=30)

    results = [None] * len(blocks)

    def task(i: int, block: dict) -> tuple[int, dict]:
        return i, _call_llm(block["full_text"], client)

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(task, i, b): i for i, b in enumerate(blocks)}
        for future in tqdm(
            concurrent.futures.as_completed(futures),
            total=len(futures),
            desc="  生成标题",
        ):
            idx, meta = future.result()
            results[idx] = meta

    return results


# ============================================================
#  步骤6: 切片 + 加速 + 叠加文字
# ============================================================

def _process_single_block(
    video_path: str,
    output_dir: Path,
    block: dict,
    meta: dict,
    index: int,
    speed: float,
    font_path: str,
) -> dict:
    teaser = meta["teaser"]
    title = meta["title"]

    start = max(0, block["start_time"] - 0.5)
    end = block["end_time"]
    duration = end - start

    output_file = output_dir / f"part_{index + 1:02d}.mp4"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(teaser)
        textfile = f.name

    video_pts = 1.0 / speed
    overlay = (
        f"drawtext="
        f"textfile='{textfile}':"
        f"fontfile='{font_path}':"
        f"fontcolor=white:fontsize=40:"
        f"box=1:boxcolor=black@0.6:boxborderw=10:"
        f"x=(w-text_w)/2:y=h/4:"
        f"enable='between(t,0,5)'"
    )

    filter_chain = (
        f"[0:v]setpts={video_pts:.3f}*PTS,"
        f"{overlay}[vout];"
        f"[0:a]atempo={speed}[aout]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timedelta(seconds=start)),
        "-i", video_path,
        "-t", str(timedelta(seconds=duration)),
        "-filter_complex", filter_chain,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-avoid_negative_ts", "make_zero",
        str(output_file),
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    except subprocess.CalledProcessError as e:
        logger.error(f"  切片 {index + 1} ffmpeg 失败\n  {e.stderr.decode()[:500]}")
        raise
    finally:
        try:
            os.unlink(textfile)
        except OSError:
            pass

    return {
        "index": index + 1,
        "title": title,
        "crowd": meta.get("crowd", ""),
        "problem": meta.get("problem", ""),
        "solution": meta.get("solution", ""),
        "file": output_file.name,
        "start_time": round(block["start_time"], 2),
        "end_time": round(block["end_time"], 2),
        "duration": round(block["end_time"] - block["start_time"], 2),
    }


def slice_all_blocks(
    video_path: str,
    output_dir: Path,
    blocks: list[dict],
    metas: list[dict],
    speed: float,
    font_path: str,
) -> list[dict]:
    logger.info(f"步骤6/6: 切片 + {speed}x 加速 + 叠加文字 (并发 2)...")
    output_dir.mkdir(parents=True, exist_ok=True)

    titles = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                _process_single_block,
                video_path, output_dir, b, m, i, speed, font_path,
            )
            for i, (b, m) in enumerate(zip(blocks, metas))
        ]
        for future in tqdm(
            concurrent.futures.as_completed(futures),
            total=len(futures),
            desc="  生成切片",
        ):
            titles.append(future.result())

    titles.sort(key=lambda x: x["index"])
    return titles


def save_manifest(titles: list[dict], output_dir: Path):
    json_path = output_dir / "titles.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(titles, f, ensure_ascii=False, indent=2)
    logger.info(f"  JSON 清单: {json_path}")

    txt_path = output_dir / "titles.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        for item in titles:
            f.write(
                f"P{item['index']:02d} | {item['title']}\n"
                f"      人群: {item['crowd']} | 问题: {item['problem']} | 解法: {item['solution']}\n"
                f"      文件: {item['file']}\n\n"
            )
    logger.info(f"  TXT 清单: {txt_path}")


# ============================================================
#  主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="CastFlux - 直播内容切片工坊",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python main.py live.mp4 -o slices\n"
            "  python main.py live.mp4 --model medium --num-slices 5\n"
            "  python main.py live.mp4 --speed 1.5\n"
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
    args = parser.parse_args()

    setup_logging(args.verbose)
    logger.info("=" * 50)
    logger.info("CastFlux 启动")

    check_prerequisites()

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

        metas = batch_generate(qa_blocks, max_workers=args.llm_workers)

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


if __name__ == "__main__":
    main()
