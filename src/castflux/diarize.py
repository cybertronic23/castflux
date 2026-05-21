import logging
import os

import torch
from pyannote.audio import Pipeline

logger = logging.getLogger("castflux")


def diarize_audio(audio_path: str) -> list[dict]:
    logger.info("步骤3/6: 说话人分离 (pyannote.audio)...")
    hf_token = os.environ["HF_TOKEN"]

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=hf_token,
    )

    if torch.cuda.is_available():
        pipeline.to(torch.device("cuda"))

    result = pipeline(audio_path)

    # pyannote 4.x returns DiarizeOutput, 3.x returns Annotation directly
    diarization = result.speaker_diarization if hasattr(result, "speaker_diarization") else result

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
