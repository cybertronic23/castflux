import pytest
from castflux.qa import find_qa_blocks


def test_find_qa_blocks_basic():
    segments = [
        {"start": 0, "end": 2, "speaker": "FAN", "text": "你好吗"},
        {"start": 2, "end": 5, "speaker": "HOST", "text": "我很好谢谢"},
    ]
    blocks = find_qa_blocks(segments, target_count=5, host_speaker="HOST")
    assert len(blocks) == 1
    assert blocks[0]["start_time"] == 0
    assert blocks[0]["end_time"] == 5


def test_find_qa_blocks_multiple_host_segments():
    segments = [
        {"start": 0, "end": 2, "speaker": "FAN", "text": "第一个问题"},
        {"start": 2, "end": 4, "speaker": "HOST", "text": "第一个回答"},
        {"start": 4, "end": 5, "speaker": "HOST", "text": "继续回答"},
        {"start": 5, "end": 7, "speaker": "FAN", "text": "第二个问题"},
        {"start": 7, "end": 9, "speaker": "HOST", "text": "第二个回答"},
    ]
    blocks = find_qa_blocks(segments, target_count=5, host_speaker="HOST")
    assert len(blocks) == 2
    assert blocks[0]["end_time"] == 5
    assert blocks[1]["end_time"] == 9


def test_find_qa_blocks_empty_raises():
    with pytest.raises(RuntimeError, match="说话人分离失败"):
        find_qa_blocks([], target_count=5, host_speaker="HOST")


def test_find_qa_blocks_no_qa_raises():
    segments = [
        {"start": 0, "end": 2, "speaker": "FAN", "text": "只有粉丝"},
    ]
    with pytest.raises(RuntimeError, match="未检测到任何 QA 对"):
        find_qa_blocks(segments, target_count=5, host_speaker="HOST")


def test_find_qa_blocks_too_few_uses_all():
    segments = [
        {"start": 0, "end": 2, "speaker": "FAN", "text": "你好"},
        {"start": 2, "end": 4, "speaker": "HOST", "text": "你好呀"},
    ]
    blocks = find_qa_blocks(segments, target_count=10, host_speaker="HOST")
    assert len(blocks) == 1
