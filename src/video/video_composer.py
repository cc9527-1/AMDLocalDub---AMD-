"""VideoDub 视频合成器。

负责将原视频流 + 新的配音音轨 + 可选字幕轨
合成为最终的 MP4/MKV 输出文件。

支持 GPU 硬件加速编码（自动检测）：
- AMD GPU → h264_amf (AMF)
- 其他/回退 → libx264 (CPU)
"""

from __future__ import annotations

import os
import subprocess
from typing import List, Optional

from src.core.data_models import VideoProcessingError


class VideoComposer:
    """视频合成器。

    支持三种字幕模式：
    - "none": 不包含字幕
    - "soft": 嵌入软字幕（作为独立字幕轨）
    - "burn": 硬字幕烧录（直接渲染到画面）

    编码器自动选择（优先 GPU 硬件加速）：
    - h264_amf (AMD GPU) → 最快
    - libx264 (CPU) → 兼容性最佳
    """

    _encoder: Optional[str] = None  # 缓存的编码器名称

    @classmethod
    def _detect_best_encoder(cls) -> str:
        """检测系统中可用的最佳视频编码器。

        优先级: h264_amf (AMD GPU) > libx264 (CPU)

        Returns:
            编码器名称
        """
        if cls._encoder is not None:
            return cls._encoder

        try:
            result = subprocess.run(
                ["ffmpeg", "-encoders"],
                capture_output=True, text=True, timeout=10,
            )
            encoders = result.stdout + result.stderr

            if "h264_amf" in encoders:
                cls._encoder = "h264_amf"
            else:
                cls._encoder = "libx264"
        except Exception:
            cls._encoder = "libx264"

        return cls._encoder

    @classmethod
    def _get_video_encoder_args(cls) -> List[str]:
        """获取视频编码器相关参数。

        不同编码器使用不同的质量/速度参数：
        - h264_amf: -quality balanced (替代 -preset 和 -crf)
        - libx264:  -preset medium -crf 23

        Returns:
            ffmpeg 参数字段列表
        """
        encoder = cls._detect_best_encoder()

        if encoder == "h264_amf":
            return [
                "-c:v", "h264_amf",
                "-quality", "quality",    # 最高画质模式
                "-qp_i", "22",
                "-qp_p", "23",
                "-rc", "vbr_peak",         # 可变码率
                "-profile:v", "main",
            ]
        else:
            return [
                "-c:v", "libx264",
                "-crf", "23",
                "-preset", "medium",
            ]

    @classmethod
    def compose(
        cls,
        video_path: str,
        audio_path: str,
        output_path: str,
        subtitle_path: str = "",
        subtitle_mode: str = "none",
    ) -> str:
        """将原视频 + 新音轨 + 可选字幕合成为最终输出文件。

        Args:
            video_path: 原视频文件路径
            audio_path: 新的配音音轨文件路径
            output_path: 输出文件路径
            subtitle_path: 字幕文件路径（SRT 格式），为空则不处理字幕
            subtitle_mode: 字幕模式: "none" / "soft" / "burn"

        Returns:
            输出视频文件路径

        Raises:
            VideoProcessingError: ffmpeg 调用失败或输入文件不存在
        """
        if not os.path.isfile(video_path):
            raise VideoProcessingError(f"视频文件不存在: {video_path}")
        if not os.path.isfile(audio_path):
            raise VideoProcessingError(f"音频文件不存在: {audio_path}")

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        if subtitle_mode == "burn" and subtitle_path and os.path.isfile(subtitle_path):
            return cls.burn_subtitles(video_path, audio_path, subtitle_path, output_path)
        elif subtitle_mode == "soft" and subtitle_path and os.path.isfile(subtitle_path):
            return cls.add_subtitle_track(video_path, audio_path, subtitle_path, output_path)
        else:
            return cls._merge_audio_video(video_path, audio_path, output_path)

    @classmethod
    def add_subtitle_track(
        cls,
        video_path: str,
        audio_path: str,
        subtitle_path: str,
        output_path: str,
    ) -> str:
        ext = os.path.splitext(output_path)[1].lower()
        cmd: List[str] = ["ffmpeg", "-y", "-i", video_path, "-i", audio_path]

        subtitle_input_added = False
        if ext == ".mkv":
            cmd.extend(["-i", subtitle_path])
            subtitle_input_added = True

        cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])
        if subtitle_input_added:
            cmd.extend(["-map", "2:s:0"])

        cmd.extend(cls._get_video_encoder_args())
        cmd.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])

        if ext == ".mp4" and subtitle_input_added:
            cmd.extend(["-c:s", "mov_text"])

        cmd.append(output_path)
        return cls._run_ffmpeg(cmd, output_path)

    @classmethod
    def burn_subtitles(
        cls,
        video_path: str,
        audio_path: str,
        subtitle_path: str,
        output_path: str,
    ) -> str:
        """将字幕硬烧录到视频画面中（黑色背景 + 白色字体）。

        Args:
            video_path: 原视频路径
            audio_path: 配音音轨路径
            subtitle_path: SRT 字幕文件路径
            output_path: 输出路径

        Returns:
            输出文件路径
        """
        # 将 SRT 复制到输出目录（纯文件名，无盘符冒号问题）
        output_dir = os.path.dirname(output_path) or "."
        simple_srt_name = "_subtitle.srt"
        simple_srt_path = os.path.join(output_dir, simple_srt_name)
        try:
            import shutil
            shutil.copy2(subtitle_path, simple_srt_path)
        except OSError as e:
            raise VideoProcessingError(f"复制字幕文件失败: {e}")

        # 使用纯文件名（无路径），ffmpeg 会在 CWD 中查找
        # 通过设置 cwd=output_dir 确保 ffmpeg 能找到 _subtitle.srt
        rel_path = simple_srt_name

        style_opts = (
            "FontName=Arial,"
            "FontSize=20,"
            "PrimaryColour=&H00FFFFFF,"
            "BackColour=&H80000000,"
            "Bold=1,"
            "Alignment=2,"
            "MarginV=24"
        )

        filter_str = (
            f"[0:v]subtitles={rel_path}:"
            f"force_style='{style_opts}'[vid]"
        )

        cmd: List[str] = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-filter_complex", filter_str,
            "-map", "[vid]",
            "-map", "1:a:0",
        ]
        cmd.extend(cls._get_video_encoder_args())
        cmd.extend(["-c:a", "aac", "-b:a", "192k", "-shortest", output_path])

        return cls._run_ffmpeg(cmd, output_path, cwd=output_dir)

    @classmethod
    def _merge_audio_video(
        cls, video_path: str, audio_path: str, output_path: str
    ) -> str:
        cmd: List[str] = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-map", "0:v:0",
            "-map", "1:a:0",
        ]
        cmd.extend(cls._get_video_encoder_args())
        cmd.extend(["-c:a", "aac", "-b:a", "192k", "-shortest", output_path])
        return cls._run_ffmpeg(cmd, output_path, cwd=os.path.dirname(output_path))

    @classmethod
    def _run_ffmpeg(
        cls, cmd: List[str], output_path: str,
        cwd: Optional[str] = None,
    ) -> str:
        """执行 ffmpeg 命令。

        Args:
            cmd: ffmpeg 命令行参数列表
            output_path: 输出文件路径
            cwd: 工作目录（用于查找 _subtitle.srt 等辅助文件）

        Returns:
            输出文件的绝对路径

        Raises:
            VideoProcessingError: ffmpeg 调用失败
        """
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired:
            raise VideoProcessingError("ffmpeg 视频合成超时 (600s)")
        except FileNotFoundError:
            raise VideoProcessingError(
                "未找到 ffmpeg，请确保已安装 ffmpeg 并添加到 PATH"
            )

        if result.returncode != 0:
            error_msg = result.stderr.strip()[:2000] if result.stderr else "未知错误"
            raise VideoProcessingError(f"ffmpeg 视频合成失败: {error_msg}")

        if not os.path.isfile(output_path):
            raise VideoProcessingError(f"合成后视频文件未生成: {output_path}")

        return os.path.abspath(output_path)
