"""VideoDub 音频合并器。

将分段 TTS 配音音频按原始时间戳叠加到时间轴上，
使用 Python wave 模块逐采样点叠加，完全避免 ffmpeg 滤镜复杂度限制。
"""
from __future__ import annotations

import os
import subprocess
from typing import List

from src.core.data_models import Segment, VideoProcessingError


class AudioMerger:
    """音频合并器。

    使用 Python 的 wave 模块将各段 TTS 音频按原始时间戳叠加，
    确保所有配音段都能精确对齐到时间轴。
    """

    SAMPLE_RATE = 16000
    SAMPLE_WIDTH = 2  # 16-bit
    CHANNELS = 1

    @classmethod
    def merge(cls, segments: List[Segment], output_path: str,
              total_duration: float = 0.0) -> str:
        """将分段 TTS 音频按原始时间戳叠加为完整音轨。

        使用 Python 高效叠加每段音频到时间轴对应位置。

        Args:
            segments: 句段列表
            output_path: 输出合并音频路径
            total_duration: 视频总时长（秒）

        Returns:
            合并后的音频文件路径
        """
        import array
        import wave

        valid_segments = [
            seg for seg in segments
            if seg.tts_audio_path and os.path.isfile(seg.tts_audio_path)
        ]

        if not valid_segments:
            raise VideoProcessingError("没有有效的 TTS 音频段可供合并")

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # 确定输出总长度
        if total_duration > 0:
            total_samples = int(total_duration * cls.SAMPLE_RATE)
        else:
            last_end = max(s.end_time for s in valid_segments)
            total_samples = int(last_end * cls.SAMPLE_RATE) + cls.SAMPLE_RATE

        # 用 int32 缓冲区避免 int16 溢出（叠加时）
        buf = array.array("i", [0]) * total_samples

        # 叠加每段音频
        for seg in valid_segments:
            try:
                with wave.open(seg.tts_audio_path, "r") as wf:
                    raw = wf.readframes(wf.getnframes())
            except Exception:
                continue

            # 将 WAV 字节解码为 int16 数组
            samples = array.array("h")
            samples.frombytes(raw)
            n = len(samples)

            start_pos = max(0, int(seg.start_time * cls.SAMPLE_RATE))
            end_pos = min(start_pos + n, total_samples)
            copy_len = end_pos - start_pos

            if copy_len <= 0:
                continue

            # 批量叠加（避免逐采样点循环）
            for i in range(copy_len):
                buf[start_pos + i] += samples[i]

        # 归一化防削波
        max_val = max(abs(max(buf)), abs(min(buf)), 1)
        scale = 32767.0 / max_val * 0.95

        # 输出 int16 WAV
        out = array.array("h", [0]) * total_samples
        for i in range(total_samples):
            out[i] = int(buf[i] * scale)

        try:
            with wave.open(output_path, "w") as wf:
                wf.setnchannels(cls.CHANNELS)
                wf.setsampwidth(cls.SAMPLE_WIDTH)
                wf.setframerate(cls.SAMPLE_RATE)
                wf.writeframes(out.tobytes())
        except Exception as e:
            raise VideoProcessingError(f"音频合并写入失败: {e}")

        if not os.path.isfile(output_path):
            raise VideoProcessingError(f"合并后音频文件未生成: {output_path}")

        return os.path.abspath(output_path)

    @classmethod
    def normalize_audio(cls, audio_path: str) -> str:
        """对音频文件进行音量归一化处理。"""
        if not os.path.isfile(audio_path):
            return audio_path

        base, ext = os.path.splitext(audio_path)
        normalized_path = f"{base}_normalized{ext}"
        cmd = [
            "ffmpeg", "-y",
            "-i", audio_path,
            "-af", "loudnorm=I=-16:LRA=11:TP=-1.5",
            "-c:a", "pcm_s16le",
            normalized_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and os.path.isfile(normalized_path):
                os.remove(audio_path)
                os.rename(normalized_path, audio_path)
                return os.path.abspath(audio_path)
            else:
                if os.path.isfile(normalized_path):
                    os.remove(normalized_path)
                return os.path.abspath(audio_path)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return os.path.abspath(audio_path)
