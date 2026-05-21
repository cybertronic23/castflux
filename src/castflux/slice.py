import concurrent.futures
import json
import logging
import os
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from tqdm import tqdm

logger = logging.getLogger("castflux")


def _has_drawtext() -> bool:
    """检测 ffmpeg 是否支持 drawtext 滤镜。"""
    try:
        result = subprocess.run(["ffmpeg", "-filters"], capture_output=True, text=True)
        return "drawtext" in result.stdout
    except FileNotFoundError:
        raise RuntimeError("ffmpeg not found")


def _create_text_overlay(
    text: str, font_path: str, video_size: tuple[int, int] = (1280, 720),
    fontsize: int = 40,
) -> str:
    """用 Pillow 生成带文字的半透明底条 PNG，返回临时文件路径。"""
    img = Image.new("RGBA", video_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(font_path, fontsize)
    except (OSError, AttributeError):
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pad = 10
    x = (video_size[0] - text_w) // 2
    y = video_size[1] // 4 - text_h // 2

    draw.rectangle(
        [x - pad, y - pad, x + text_w + pad, y + text_h + pad],
        fill=(0, 0, 0, 153),
    )
    draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)

    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(path, "PNG")
    return path


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

    start = max(0, block["start_time"] - 0.5)
    end = block["end_time"]
    duration = end - start

    output_file = output_dir / f"part_{index + 1:02d}.mp4"

    video_pts = 1.0 / speed
    use_drawtext = _has_drawtext()

    if use_drawtext:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write(teaser)
            textfile = f.name

        overlay_filter = (
            f"drawtext="
            f"textfile='{textfile}':"
            f"fontfile='{font_path}':"
            f"fontcolor=white:fontsize=40:"
            f"box=1:boxcolor=black@0.6:boxborderw=10:"
            f"x=(w-text_w)/2:y=h/4:"
            f"enable='between(t,0,5)'"
        )
        inputs = [
            "-ss", str(timedelta(seconds=start)),
            "-i", video_path,
            "-t", str(timedelta(seconds=duration)),
        ]
        filter_chain = (
            f"[0:v]setpts={video_pts:.3f}*PTS,"
            f"{overlay_filter}[vout];"
            f"[0:a]atempo={speed}[aout]"
        )
    else:
        overlay_path = _create_text_overlay(teaser, font_path)
        inputs = [
            "-ss", str(timedelta(seconds=start)),
            "-i", video_path,
            "-i", overlay_path,
            "-t", str(timedelta(seconds=duration)),
        ]
        overlay_x, overlay_y = 0, "H/4-H/2"
        filter_chain = (
            f"[0:v]setpts={video_pts:.3f}*PTS[vscaled];"
            f"[vscaled][1:v]overlay={overlay_x}:{overlay_y}:enable='between(t,0,5)'[vout];"
            f"[0:a]atempo={speed}[aout]"
        )

    cmd = [
        "ffmpeg", "-y", *inputs,
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
        if use_drawtext:
            try:
                os.unlink(textfile)
            except OSError:
                pass
        else:
            try:
                os.unlink(overlay_path)
            except OSError:
                pass

    return {
        "index": index + 1,
        "title": meta["title"],
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
