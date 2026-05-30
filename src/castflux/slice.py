import concurrent.futures
import json
import logging
import os
import re
import subprocess
import tempfile
from difflib import SequenceMatcher
from datetime import timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from tqdm import tqdm

logger = logging.getLogger("castflux")


def _probe_video_size(video_path: str) -> tuple[int, int]:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        video_path,
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    width, height = result.stdout.strip().split("x")
    return int(width), int(height)


def _load_font(font_path: str, size: int):
    try:
        return ImageFont.truetype(font_path, size)
    except (OSError, AttributeError):
        return ImageFont.load_default()


def _wrap_by_pixels(text: str, draw: ImageDraw.ImageDraw, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        current = ""
        for char in paragraph:
            trial = current + char
            bbox = draw.textbbox((0, 0), trial, font=font)
            if bbox[2] - bbox[0] <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = char
        if current:
            lines.append(current)
    return lines or [text]


def _create_intro_card(
    teaser: str,
    title: str,
    font_path: str,
    video_size: tuple[int, int],
) -> str:
    width, height = video_size
    img = Image.new("RGB", video_size, (10, 10, 10))
    draw = ImageDraw.Draw(img)

    title_font = _load_font(font_path, max(42, width // 18))
    teaser_font = _load_font(font_path, max(52, width // 14))
    label_font = _load_font(font_path, max(26, width // 34))

    margin = int(width * 0.08)
    max_text_width = width - margin * 2
    teaser_lines = _wrap_by_pixels(teaser or "精彩问答马上开始", draw, teaser_font, max_text_width)
    title_lines = _wrap_by_pixels(title or "直播精华问答", draw, title_font, max_text_width)

    overlay_top = int(height * 0.18)
    overlay_bottom = int(height * 0.82)
    draw.rounded_rectangle(
        [margin // 2, overlay_top, width - margin // 2, overlay_bottom],
        radius=24,
        fill=(0, 0, 0),
        outline=(255, 210, 80),
        width=4,
    )

    label = "前情提要"
    label_bbox = draw.textbbox((0, 0), label, font=label_font)
    label_w = label_bbox[2] - label_bbox[0]
    label_h = label_bbox[3] - label_bbox[1]
    label_x = margin
    label_y = overlay_top + int(height * 0.04)
    draw.rounded_rectangle(
        [label_x - 18, label_y - 12, label_x + label_w + 18, label_y + label_h + 14],
        radius=12,
        fill=(255, 210, 80),
    )
    draw.text((label_x, label_y), label, font=label_font, fill=(0, 0, 0))

    y = label_y + label_h + int(height * 0.07)
    for line in teaser_lines[:4]:
        bbox = draw.textbbox((0, 0), line, font=teaser_font)
        line_w = bbox[2] - bbox[0]
        line_h = bbox[3] - bbox[1]
        draw.text(((width - line_w) // 2, y), line, font=teaser_font, fill=(255, 255, 255))
        y += line_h + 18

    y += int(height * 0.03)
    for line in title_lines[:2]:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        line_w = bbox[2] - bbox[0]
        line_h = bbox[3] - bbox[1]
        draw.text(((width - line_w) // 2, y), line, font=title_font, fill=(255, 230, 130))
        y += line_h + 12

    fd, path = tempfile.mkstemp(suffix=".jpg")
    os.close(fd)
    img.save(path, "JPEG", quality=95)
    return path


def _atempo_filter(speed: float) -> str:
    if speed <= 0:
        raise ValueError("speed must be greater than 0")
    parts = []
    remaining = speed
    while remaining > 2.0:
        parts.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        parts.append("atempo=0.5")
        remaining /= 0.5
    parts.append(f"atempo={remaining:.3f}")
    return ",".join(parts)


def _normalize_text(text: str) -> str:
    return re.sub(r"[\s，。！？、：；,.!?:;\"'“”‘’（）()【】\[\]《》<>]+", "", text or "")


def _bounded_range(
    start: float,
    end: float,
    block_start: float,
    block_end: float,
    min_duration: float,
    max_duration: float,
) -> tuple[float, float]:
    start = max(block_start, start)
    end = min(block_end, end)
    duration = max(0.1, end - start)

    if duration > max_duration:
        center = (start + end) / 2
        start = center - max_duration / 2
        end = center + max_duration / 2
    elif duration < min_duration:
        center = (start + end) / 2
        start = center - min_duration / 2
        end = center + min_duration / 2

    if start < block_start:
        end += block_start - start
        start = block_start
    if end > block_end:
        start -= end - block_end
        end = block_end
    return max(block_start, start), min(block_end, end)


def _locate_hook_range(
    block: dict,
    hook_quote: str,
    min_duration: float = 3.0,
    max_duration: float = 14.0,
) -> tuple[float, float]:
    block_start = float(block["start_time"])
    block_end = float(block["end_time"])
    target = _normalize_text(hook_quote)
    words = block.get("words") or []

    if target and words:
        chars: list[str] = []
        char_to_word: list[int] = []
        for idx, word in enumerate(words):
            normalized = _normalize_text(word.get("word", ""))
            for char in normalized:
                chars.append(char)
                char_to_word.append(idx)

        text = "".join(chars)
        if text:
            best = (0.0, 0, min(len(text), max(1, len(target))))
            target_len = max(1, len(target))
            min_len = max(1, int(target_len * 0.65))
            max_len = min(len(text), max(target_len + 12, int(target_len * 1.35)))
            for start_idx in range(len(text)):
                for length in (target_len, min_len, max_len):
                    end_idx = min(len(text), start_idx + length)
                    if end_idx <= start_idx:
                        continue
                    score = SequenceMatcher(None, target, text[start_idx:end_idx]).ratio()
                    if score > best[0]:
                        best = (score, start_idx, end_idx)
            if best[0] >= 0.45:
                start_word = words[char_to_word[best[1]]]
                end_word = words[char_to_word[max(best[2] - 1, best[1])]]
                return _bounded_range(
                    float(start_word["start"]) - 0.8,
                    float(end_word["end"]) + 0.8,
                    block_start,
                    block_end,
                    min_duration,
                    max_duration,
                )

    best_segment = None
    best_score = -1.0
    for segment in block.get("segments") or []:
        text = _normalize_text(segment.get("text", ""))
        if not text:
            continue
        score = SequenceMatcher(None, target, text).ratio() if target else len(text)
        if score > best_score:
            best_score = score
            best_segment = segment

    if best_segment:
        return _bounded_range(
            float(best_segment["start"]) - 0.8,
            float(best_segment["end"]) + 0.8,
            block_start,
            block_end,
            min_duration,
            max_duration,
        )

    return _bounded_range(
        block_start,
        min(block_end, block_start + max_duration),
        block_start,
        block_end,
        min_duration,
        max_duration,
    )


def _run_ffmpeg(cmd: list[str], label: str):
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=900)
    except subprocess.CalledProcessError as e:
        logger.error(f"  {label} ffmpeg 失败\n  {e.stderr.decode(errors='replace')[:800]}")
        raise


def _render_clip(
    video_path: str,
    output_path: str,
    start: float,
    end: float,
    speed: float,
    label: str,
):
    duration = max(0.1, end - start)
    video_pts = 1.0 / speed
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timedelta(seconds=start)),
        "-i", video_path,
        "-t", str(timedelta(seconds=duration)),
        "-filter_complex",
        f"[0:v]setpts={video_pts:.3f}*PTS[vout];[0:a]{_atempo_filter(speed)}[aout]",
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-avoid_negative_ts", "make_zero",
        output_path,
    ]
    _run_ffmpeg(cmd, label)


def _process_single_block(
    video_path: str,
    output_dir: Path,
    block: dict,
    meta: dict,
    index: int,
    speed: float,
    font_path: str,
) -> dict:
    teaser = meta.get("teaser") or "精彩问答马上开始"
    title = meta.get("title") or "直播精华问答"
    hook_quote = meta.get("hook_quote") or teaser

    start = max(0, block["start_time"] - 0.5)
    end = block["end_time"]
    hook_start, hook_end = _locate_hook_range(block, hook_quote)

    output_file = output_dir / f"part_{index + 1:02d}.mp4"
    temp_files: list[str] = []

    video_size = _probe_video_size(video_path)
    intro_card = _create_intro_card(teaser, title, font_path, video_size)
    temp_files.append(intro_card)

    content_fd, content_path = tempfile.mkstemp(suffix=".mp4")
    intro_fd, intro_path = tempfile.mkstemp(suffix=".mp4")
    hook_fd, hook_path = tempfile.mkstemp(suffix=".mp4")
    os.close(content_fd)
    os.close(intro_fd)
    os.close(hook_fd)
    temp_files.extend([content_path, intro_path, hook_path])

    intro_cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", intro_card,
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", "3.2",
        "-vf", "format=yuv420p",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        intro_path,
    ]

    concat_cmd = [
        "ffmpeg", "-y",
        "-i", intro_path,
        "-i", hook_path,
        "-i", content_path,
        "-filter_complex", "[0:v][0:a][1:v][1:a][2:v][2:a]concat=n=3:v=1:a=1[vout][aout]",
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        str(output_file),
    ]

    try:
        _run_ffmpeg(intro_cmd, f"切片 {index + 1} 前情提要")
        _render_clip(video_path, hook_path, hook_start, hook_end, speed, f"切片 {index + 1} 高能精华")
        _render_clip(video_path, content_path, start, end, speed, f"切片 {index + 1} 内容")
        _run_ffmpeg(concat_cmd, f"切片 {index + 1} 合成")
    finally:
        for temp_file in temp_files:
            try:
                os.unlink(temp_file)
            except OSError:
                pass

    return {
        "index": index + 1,
        "title": title,
        "teaser": teaser,
        "hook_quote": hook_quote,
        "hook_start_time": round(hook_start, 2),
        "hook_end_time": round(hook_end, 2),
        "hook_duration": round(hook_end - hook_start, 2),
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
                f"      前情提要: {item.get('teaser', '')}\n"
                f"      高能原话: {item.get('hook_quote', '')}\n"
                f"      高能片段: {item.get('hook_start_time', '')}s - {item.get('hook_end_time', '')}s\n"
                f"      人群: {item['crowd']} | 问题: {item['problem']} | 解法: {item['solution']}\n"
                f"      文件: {item['file']}\n\n"
            )
    logger.info(f"  TXT 清单: {txt_path}")
