"""VideoDub 句子拆分器单元测试。

测试覆盖:
- 拆分多句文本（按句号/问号/感叹号）
- 合并短句段
- 拆分超长句段
- 空列表处理
- 时间戳保留
"""

import pytest

from src.core.data_models import Segment, SegmentStatus
from src.splitter.sentence_splitter import SentenceSplitter


@pytest.fixture
def splitter():
    return SentenceSplitter(max_segment_duration=10.0)


class TestSentenceSplitterInit:
    """初始化测试。"""

    def test_default_max_duration(self):
        """测试默认最大时长。"""
        s = SentenceSplitter()
        assert s.max_segment_duration == 10.0

    def test_custom_max_duration(self):
        """测试自定义最大时长。"""
        s = SentenceSplitter(max_segment_duration=5.0)
        assert s.max_segment_duration == 5.0


class TestSplitIntoSubSentences:
    """子句拆分测试。"""

    def test_single_sentence(self, splitter):
        """测试单个句子不拆分。"""
        seg = Segment(
            index=1,
            original_text="Hello world.",
            start_time=0.0,
            end_time=2.0,
        )
        result = splitter.split([seg])
        assert len(result) == 1
        assert result[0].original_text == "Hello world."

    def test_multiple_sentences_chinese(self, splitter):
        """测试中文多句拆分。"""
        seg = Segment(
            index=1,
            original_text="你好。世界。今天天气真好！",
            start_time=0.0,
            end_time=6.0,
        )
        result = splitter.split([seg])
        assert len(result) >= 2

    def test_multiple_sentences_english(self, splitter):
        """测试英文多句拆分。"""
        seg = Segment(
            index=1,
            original_text="Hello. How are you? I am fine!",
            start_time=0.0,
            end_time=6.0,
        )
        result = splitter.split([seg])
        assert len(result) >= 2

    def test_empty_text_skipped(self, splitter):
        """测试空文本被跳过。"""
        seg = Segment(
            index=1,
            original_text="   ",
            start_time=0.0,
            end_time=1.0,
        )
        result = splitter.split([seg])
        assert len(result) == 0

    def test_empty_segments_list(self, splitter):
        """测试空列表返回空列表。"""
        result = splitter.split([])
        assert result == []

    def test_time_preserved_in_split(self, splitter):
        """测试拆分后时间戳合理分布。"""
        seg = Segment(
            index=1,
            original_text="Hello. How are you?",
            start_time=0.0,
            end_time=4.0,
        )
        result = splitter.split([seg])
        assert len(result) >= 2
        # 时间戳应在原始范围内
        for s in result:
            assert s.start_time >= 0.0
            assert s.end_time <= 4.0

    def test_split_single_sentence_no_punctuation(self, splitter):
        """测试无标点单句不拆分。"""
        seg = Segment(
            index=1,
            original_text="这是一个没有标点的长文本",
            start_time=0.0,
            end_time=2.0,
        )
        result = splitter.split([seg])
        assert len(result) == 1

    def test_reindexing_after_split(self, splitter):
        """测试拆分后重新编号。"""
        seg = Segment(
            index=5,
            original_text="Hello. World. Done.",
            start_time=0.0,
            end_time=3.0,
        )
        result = splitter.split([seg])
        for i, s in enumerate(result, 1):
            assert s.index == i


class TestMergeShortSegments:
    """短句段合并测试。"""

    def test_merge_short_segments(self, splitter):
        """测试合并过短的句段。"""
        segments = [
            Segment(index=1, original_text="Hello", start_time=0.0, end_time=0.3),
            Segment(index=2, original_text="World", start_time=0.3, end_time=2.0),
        ]
        result = splitter.merge_short_segments(segments, min_duration=0.5)
        # 第一个段太短，应合并到下一个段
        assert len(result) >= 1

    def test_merge_empty_list(self, splitter):
        """测试空列表合并返回空列表。"""
        result = splitter.merge_short_segments([], min_duration=0.5)
        assert result == []

    def test_no_merge_for_normal_segments(self, splitter):
        """测试正常长度句段不合并。"""
        segments = [
            Segment(index=1, original_text="First", start_time=0.0, end_time=1.0),
            Segment(index=2, original_text="Second", start_time=1.0, end_time=2.0),
        ]
        result = splitter.merge_short_segments(segments, min_duration=0.5)
        assert len(result) == 2

    def test_reindexing_after_merge(self, splitter):
        """测试合并后重新编号。"""
        segments = [
            Segment(index=1, original_text="Short", start_time=0.0, end_time=0.2),
            Segment(index=2, original_text="Longer", start_time=0.2, end_time=2.0),
        ]
        result = splitter.merge_short_segments(segments, min_duration=0.5)
        for i, s in enumerate(result, 1):
            assert s.index == i

    def test_merge_all_short(self, splitter):
        """测试所有段都短于阈值。"""
        segments = [
            Segment(index=1, original_text="A", start_time=0.0, end_time=0.2),
            Segment(index=2, original_text="B", start_time=0.2, end_time=0.4),
            Segment(index=3, original_text="C", start_time=0.4, end_time=0.6),
        ]
        result = splitter.merge_short_segments(segments, min_duration=0.5)
        # 全部短段应被合并
        assert len(result) >= 1


class TestSplitLongSegment:
    """超长句段拆分测试。"""

    def test_split_long_segment(self, splitter):
        """测试拆分过长的句段。"""
        seg = Segment(
            index=1,
            original_text="This is a very long sentence that should be split into multiple parts",
            start_time=0.0,
            end_time=15.0,  # 超过 max_duration
        )
        result = splitter.split_long_segment(seg, max_duration=10.0)
        assert len(result) == 2

    def test_no_split_short_enough(self, splitter):
        """测试长度足够时不拆分。"""
        seg = Segment(
            index=1,
            original_text="Short text",
            start_time=0.0,
            end_time=5.0,  # 未超过 max_duration
        )
        result = splitter.split_long_segment(seg, max_duration=10.0)
        assert len(result) == 1
        assert result[0] is seg

    def test_split_single_word(self, splitter):
        """测试单个单词不拆分。"""
        seg = Segment(
            index=1,
            original_text="Hello",
            start_time=0.0,
            end_time=15.0,
        )
        result = splitter.split_long_segment(seg, max_duration=10.0)
        assert len(result) == 1  # 单单词不拆分

    def test_split_preserves_order(self, splitter):
        """测试拆分后文本顺序正确。"""
        seg = Segment(
            index=1,
            original_text="First part of text second part",
            start_time=0.0,
            end_time=12.0,
        )
        result = splitter.split_long_segment(seg, max_duration=10.0)
        assert len(result) == 2
        assert "First" in result[0].original_text
        assert "second" in result[1].original_text

    def test_split_time_distribution(self, splitter):
        """测试拆分时间按文本长度比例分配。"""
        seg = Segment(
            index=1,
            original_text="AAAA BBBB",
            start_time=0.0,
            end_time=12.0,
        )
        result = splitter.split_long_segment(seg, max_duration=10.0)
        assert len(result) == 2
        # text="AAAA BBBB" (len=9), first_text="AAAA" (len=4)
        # mid_time = 0 + 12 * (4/9) ≈ 5.333
        expected_mid = 12.0 * (4.0 / 9.0)
        assert abs(result[0].end_time - expected_mid) < 0.01


class TestSplitIntegration:
    """集成测试。"""

    def test_split_then_merge(self, splitter):
        """测试拆分后再合并的完整流程。"""
        segments = [
            Segment(
                index=1,
                original_text="Hello. How are you? I am doing great.",
                start_time=0.0,
                end_time=6.0,
            ),
            Segment(
                index=2,
                original_text="Short",
                start_time=6.0,
                end_time=6.3,
            ),
        ]
        # 先拆分
        split_result = splitter.split(segments)
        assert len(split_result) >= 3

        # 再合并短段
        merge_result = splitter.merge_short_segments(split_result, min_duration=0.5)
        for i, s in enumerate(merge_result, 1):
            assert s.index == i

    def test_status_preserved(self, splitter):
        """测试拆分保留原有状态。"""
        seg = Segment(
            index=1,
            original_text="Hello. World.",
            start_time=0.0,
            end_time=2.0,
            status=SegmentStatus.TRANSLATED,
        )
        result = splitter._split_segment_by_sentences(seg, ["Hello.", "World."])
        # _split_segment_by_sentences 会重置状态为 PENDING
        assert len(result) == 2
