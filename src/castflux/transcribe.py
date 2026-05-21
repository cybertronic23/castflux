import logging

import torch
from faster_whisper import WhisperModel

logger = logging.getLogger("castflux")

# GPU 可用时的默认模型, CPU 用更小的
def _resolve_model(model_size: str | None) -> str:
    if model_size and model_size != "auto":
        return model_size
    if torch.cuda.is_available():
        logger.info("  检测到 GPU, 使用 large-v3 模型")
        return "large-v3"
    logger.info("  未检测到 GPU, 使用 base 模型 (CPU 推荐)")
    return "base"


def transcribe_audio(audio_path: str, model_size: str | None = "auto") -> list[dict]:
    model_size = _resolve_model(model_size)
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
