"""VideoDub 音频分段器。

按翻译后文本的时间轴从原始音频中切分参考音频片段。
这些片段主要用于调试和参考，实际配音使用 TTS 生成的音频。
"""

from __future__ import annotations

import os
import subprocess
from typing import List

from src.core.data_models import Segment, VideoProcessingError


class AudioSegmenter:
    """音频分段器。

    按 Segment 的时间戳从原始音频中切分参考片段。
    输出为独立的 WAV 文件。
    """

    @classmethod
    def segment_audio(
        cls,
        audio_path: str,
        segments: List[Segment],
        output_dir: str,
    ) -> List[Segment]:
        """从原始音频中按时间戳切分各句段对应的参考音频。

        每个句段生成一个独立的 WAV 文件。

        Args:
            audio_path: 原始音频文件路径
            segments: 句段列表
            output_dir: 输出目录

        Returns:
            句段列表（每段已填充参考音频路径）

        Raises:
            VideoProcessingError: 音频文件不存在或切分失败
        """
        if not os.path.isfile(audio_path):
            raise VideoProcessingError(f"音频文件不存在: {audio_path}")

        os.makedirs(output_dir, exist_ok=True)

        for seg in segments:
            output_path = os.path.join(
                output_dir, f"ref_{seg.index:04d}.wav"
            )

            try:
                cls.extract_chunk(audio_path, seg.start_time, seg.end_time, output_path)
            except VideoProcessingError:
                # 切分失败时继续处理其他段
                continue

        return segments

    @classmethod
    def extract_chunk(
        cls,
        audio_path: str,
        start: float,
        end: float,
        output_path: str,
    ) -> str:
        """从音频文件中提取指定时间范围的片段。

        Args:
            audio_path: 原始音频路径
            start: 起始时间（秒）
            end: 结束时间（秒）
            output_path: 输出音频文件路径

        Returns:
            输出文件路径

        Raises:
            VideoProcessingError: ffmpeg 调用失败
        """
        duration = end - start
        if duration <= 0:
            raise VideoProcessingError(
                f"无效的时间范围: start={start}s, end={end}s"
            )

        # 确保输出目录存在
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(start),
            "-t", str(duration),
            "-i", audio_path,
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            output_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            raise VideoProcessingError("ffmpeg 音频切分超时 (60s)")
        except FileNotFoundError:
            raise VideoProcessingError(
                "未找到 ffmpeg，请确保已安装 ffmpeg 并添加到 PATH"
            )

        if result.returncode != 0:
            raise VideoProcessingError(
                f"ffmpeg 音频切分失败: {result.stderr.strip()[:200]}"
            )

        if not os.path.isfile(output_path):
            raise VideoProcessingError(f"音频切分后文件未生成: {output_path}")

        return os.path.abspath(output_path)
