import logging
from collections import Counter

logger = logging.getLogger("castflux")


def _text_len(segment: dict) -> int:
    return len(segment.get("text", "").replace(" ", "").strip())


def _is_real_guest_segment(segment: dict, host: str) -> bool:
    if segment["speaker"] in (host, "UNKNOWN"):
        return False
    duration = segment["end"] - segment["start"]
    return duration >= 1.5 and _text_len(segment) >= 6


def _is_short_bridge(segment: dict, host: str) -> bool:
    duration = segment["end"] - segment["start"]
    chars = _text_len(segment)
    if segment["speaker"] == "UNKNOWN":
        return duration <= 2.5 and chars <= 8
    if segment["speaker"] == host:
        return duration <= 2.0 and chars <= 10
    return False


def _merge_text(segments: list[dict]) -> str:
    return " ".join(s["text"].strip() for s in segments if s.get("text", "").strip())


def _compact(text: str) -> str:
    return text.replace(" ", "").strip()


def _looks_like_followup_close(question_text: str, answer_text: str) -> bool:
    q = _compact(question_text)
    a = _compact(answer_text)
    close_markers = ("谢谢", "明白", "懂了", "我就去", "回去我", "加油")
    answer_openers = ("不客气", "是的", "对的", "加油")
    promo_markers = ("直播间", "弹幕", "评论", "扣出来", "发消息", "有问题")
    if any(marker in q for marker in close_markers) and a.startswith(answer_openers):
        return True
    if any(marker in q[-40:] for marker in close_markers) and any(marker in a[:120] for marker in promo_markers):
        return True
    return False


def _words_in_range(words: list[dict] | None, start_time: float, end_time: float) -> list[dict]:
    if not words:
        return []
    return [
        dict(w)
        for w in words
        if start_time <= w.get("start", 0) <= end_time
    ]


def find_qa_blocks(
    segments: list[dict],
    target_count: int | None = None,
    host_speaker: str | None = None,
    words: list[dict] | None = None,
) -> list[dict]:
    speaker_counts = Counter(s["speaker"] for s in segments if s["speaker"] != "UNKNOWN")
    if not speaker_counts:
        raise RuntimeError("说话人分离失败，无法识别博主和粉丝")

    host = host_speaker or speaker_counts.most_common(1)[0][0]
    logger.info(f"  博主 speaker: {host} (共 {speaker_counts[host]} 段)")

    qa_blocks = []
    i = 0
    while i < len(segments):
        cur = segments[i]
        if not _is_real_guest_segment(cur, host):
            i += 1
            continue

        question_segments = [dict(cur)]
        guest_speaker = cur["speaker"]
        j = i + 1
        while j < len(segments):
            nxt = segments[j]
            if nxt["speaker"] == guest_speaker or _is_short_bridge(nxt, host):
                question_segments.append(dict(nxt))
                j += 1
                continue
            break

        real_question_segments = [
            s for s in question_segments
            if s["speaker"] not in (host, "UNKNOWN")
        ]
        question_text = _merge_text(real_question_segments)
        question_duration = question_segments[-1]["end"] - question_segments[0]["start"]
        if len(question_text.replace(" ", "")) < 18 or question_duration < 3:
            i += 1
            continue

        while j < len(segments) and segments[j]["speaker"] != host:
            if _is_short_bridge(segments[j], host):
                j += 1
                continue
            break

        if j >= len(segments) or segments[j]["speaker"] != host:
            i += 1
            continue

        answer_segments = []
        while j < len(segments):
            nxt = segments[j]
            if nxt["speaker"] == host or _is_short_bridge(nxt, host):
                answer_segments.append(dict(nxt))
                j += 1
                continue
            if _is_real_guest_segment(nxt, host):
                break
            j += 1

        real_answer_segments = [s for s in answer_segments if s["speaker"] == host]
        answer_text = _merge_text(real_answer_segments)
        if len(answer_text.replace(" ", "")) < 30:
            i += 1
            continue
        if _looks_like_followup_close(question_text, answer_text):
            logger.debug("  跳过疑似收尾反馈段: %s", question_text[:80])
            i = j
            continue

        start_time = question_segments[0]["start"]
        end_time = answer_segments[-1]["end"]
        qa_blocks.append({
            "start_time": start_time,
            "end_time": end_time,
            "question_text": question_text.strip(),
            "answer_text": answer_text.strip(),
            "full_text": (
                f"【粉丝提问】{question_text.strip()}\n"
                f"【博主回答】{answer_text.strip()}"
            ),
            "duration": end_time - start_time,
            "segments": question_segments + answer_segments,
            "words": _words_in_range(words, start_time, end_time),
        })
        i = j

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
