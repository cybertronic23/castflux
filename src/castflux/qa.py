import logging
from collections import Counter

logger = logging.getLogger("castflux")


def find_qa_blocks(
    segments: list[dict],
    target_count: int | None = None,
    host_speaker: str | None = None,
) -> list[dict]:
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

    if not target_count or target_count <= 0:
        logger.info(f"  自动模式: 使用全部 {len(qa_blocks)} 个 QA 对")
        return qa_blocks

    if len(qa_blocks) <= target_count:
        logger.warning(f"  仅 {len(qa_blocks)} 个 QA 对 (目标 {target_count})，全部使用")
        return qa_blocks

    qa_blocks.sort(key=lambda x: len(x["answer_text"]), reverse=True)
    selected = qa_blocks[:target_count]
    selected.sort(key=lambda x: x["start_time"])
    logger.info(f"  选取 {len(selected)} 个最长的 QA 对")
    return selected
