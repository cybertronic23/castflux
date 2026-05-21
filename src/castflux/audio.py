import subprocess
import logging

logger = logging.getLogger("castflux")


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
