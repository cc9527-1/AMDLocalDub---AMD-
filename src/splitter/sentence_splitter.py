"""VideoDub 智能句子拆分器。

基于语义边界（句号/问号/感叹号/停顿）进行分段，
支持合并短句和拆分超长句，保持时间戳连续性和完整性。
"""

from __future__ import annotations

import re
from typing import List

from src.core.data_models import Segment, SegmentStatus


class SentenceSplitter:
    """智能句子拆分器。

    主要功能:
    1. split(): 对 ASR 输出的原始分段进行智能拆分和重组
    2. merge_short_segments(): 合并过短的句段
    3. split_long_segment(): 拆分过长的句段

    Attributes:
        max_segment_duration: 单句最长持续时间（秒）
    """

    # 句子结束标点
    SENTENCE_END_PATTERN = re.compile(r"[。！？.!?]+")
    # 停顿标点
    PAUSE_PATTERN = re.compile(r"[，,、；;：:]")

    def __init__(self, max_segment_duration: float = 10.0) -> None:
        """初始化句子拆分器。

        Args:
            max_segment_duration: 单句最长持续时间（秒），超过则拆分
        """
        self.max_segment_duration: float = max_segment_duration

    def split(self, segments: List[Segment]) -> List[Segment]:
        """对原始分段列表进行智能拆分。

        对每个原始段，若包含多个句子则按语义边界拆分；
        随后合并过短段和拆分超长段。

        Args:
            segments: 原始 Segment 列表（通常来自 ASR 输出）

        Returns:
            拆分后的 Segment 列表（重新编号）
        """
        if not segments:
            return []

        result: List[Segment] = []

        for seg in segments:
            text = seg.original_text.strip()
            if not text:
                continue

            # 检查是否包含多个句子
            sub_sentences = self._split_into_sentences(text)
            if len(sub_sentences) > 1:
                # 按句子在原文中的比例分配时间
                sub_segments = self._split_segment_by_sentences(seg, sub_sentences)
                result.extend(sub_segments)
            else:
                result.append(seg)

        # 为每个句段生成新的连续索引
        for i, seg in enumerate(result, 1):
            seg.index = i

        return result

    def merge_short_segments(
        self, segments: List[Segment], min_duration: float = 0.5
    ) -> List[Segment]:
        """合并过短的句段到相邻句段。

        短句段会合并到前一句段（如果前一句段存在且合并后不超长）。

        Args:
            segments: 句段列表
            min_duration: 最短持续时间（秒），短于此值时尝试合并

        Returns:
            合并后的句段列表
        """
        if not segments:
            return []

        result: List[Segment] = []
        buffer: List[Segment] = []

        for seg in segments:
            duration = seg.end_time - seg.start_time

            if duration < min_duration:
                buffer.append(seg)
                continue

            # 如果当前段长度正常且缓冲区有待合并的段
            if buffer:
                # 将缓冲区中的段合并到当前段
                combined_text = " ".join(s.original_text for s in buffer)
                buffer_seg = buffer[0]
                buffer_seg.original_text = (buffer_seg.original_text + " " + combined_text).strip()
                buffer_seg.end_time = seg.end_time
                result.append(buffer_seg)
                buffer = []

            result.append(seg)

        # 处理剩余的缓冲区段
        if buffer:
            if result:
                # 合并到最后一段
                last_seg = result[-1]
                combined_text = " ".join(s.original_text for s in buffer)
                last_seg.original_text = (last_seg.original_text + " " + combined_text).strip()
                last_seg.end_time = buffer[-1].end_time
            else:
                result.extend(buffer)

        # 重新编号
        for i, seg in enumerate(result, 1):
            seg.index = i

        return result

    def split_long_segment(
        self, segment: Segment, max_duration: float = 10.0
    ) -> List[Segment]:
        """拆分过长的句段为多个句段。

        基于文本长度和标点位置进行拆分，
        时间按文本长度比例分配。

        Args:
            segment: 需要拆分的句段
            max_duration: 每个子段的最大时长（秒）

        Returns:
            拆分后的句段列表
        """
        duration = segment.end_time - segment.start_time
        if duration <= max_duration:
            return [segment]

        text = segment.original_text
        words = text.split()
        if len(words) <= 1:
            return [segment]

        # 按字数比例拆分
        mid_point = len(words) // 2
        first_text = " ".join(words[:mid_point])
        second_text = " ".join(words[mid_point:])

        mid_time = segment.start_time + duration * (len(first_text) / len(text))

        seg1 = Segment(
            index=segment.index,
            original_text=first_text,
            start_time=segment.start_time,
            end_time=mid_time,
            status=segment.status,
        )

        seg2 = Segment(
            index=segment.index + 1,
            original_text=second_text,
            start_time=mid_time,
            end_time=segment.end_time,
            status=segment.status,
        )

        return [seg1, seg2]

    def _split_into_sentences(self, text: str) -> List[str]:
        """将文本按语义边界拆分为句子列表。

        Args:
            text: 输入文本

        Returns:
            句子列表
        """
        # 使用句子结束标点拆分
        parts = self.SENTENCE_END_PATTERN.split(text)
        # 过滤空字符串
        sentences = [p.strip() for p in parts if p.strip()]

        if not sentences:
            return [text.strip()]

        return sentences

    def _split_segment_by_sentences(
        self, segment: Segment, sentences: List[str]
    ) -> List[Segment]:
        """将一个句段按句子列表拆分为多个句段。

        Args:
            segment: 原始句段
            sentences: 拆分后的句子列表

        Returns:
            拆分为多个句段
        """
        if len(sentences) <= 1:
            return [segment]

        duration = segment.end_time - segment.start_time
        total_chars = sum(len(s) for s in sentences)
        if total_chars == 0:
            return [segment]

        result: List[Segment] = []
        current_start = segment.start_time

        for i, sentence in enumerate(sentences):
            # 按字符比例分配时间
            char_ratio = len(sentence) / total_chars
            sentence_duration = duration * char_ratio

            seg = Segment(
                index=segment.index + i,
                original_text=sentence,
                start_time=current_start,
                end_time=current_start + sentence_duration,
                status=SegmentStatus.PENDING,
            )
            result.append(seg)
            current_start += sentence_duration

        return result
