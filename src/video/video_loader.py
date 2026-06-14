"""VideoDub 视频加载器。

负责视频格式校验、媒体信息提取（通过 ffprobe）、
以及音频流分离（通过 ffmpeg）。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any, Dict, List, Optional

from src.core.data_models import VideoProcessingError


class VideoLoader:
    """视频加载器。

    支持格式: MP4, MKV, AVI, MOV, WebM
    所有操作通过调用 ffprobe/ffmpeg 完成。

    Attributes:
        SUPPORTED_FORMATS: 支持的文件扩展名列表
    """

    SUPPORTED_FORMATS: List[str] = [".mp4", ".mkv", ".avi", ".mov", ".webm"]

    @classmethod
    def load(cls, video_path: str) -> Dict[str, Any]:
        """加载视频并返回媒体信息。

        此方法是 validate_format + get_media_info 的快捷组合。

        Args:
            video_path: 视频文件路径

        Returns:
            媒体信息字典

        Raises:
            VideoProcessingError: 格式不合法或无法读取
        """
        cls.validate_format(video_path)
        return cls.get_media_info(video_path)

    @classmethod
    def validate_format(cls, video_path: str) -> bool:
        """校验视频格式是否支持。

        Args:
            video_path: 视频文件路径

        Returns:
            格式合法返回 True

        Raises:
            VideoProcessingError: 文件不存在或格式不支持
        """
        if not os.path.isfile(video_path):
            raise VideoProcessingError(f"视频文件不存在: {video_path}")

        ext = os.path.splitext(video_path)[1].lower()
        if ext not in cls.SUPPORTED_FORMATS:
            raise VideoProcessingError(
                f"不支持的视频格式 '{ext}'，支持格式: {', '.join(cls.SUPPORTED_FORMATS)}"
            )
        return True

    @classmethod
    def get_media_info(cls, video_path: str) -> Dict[str, Any]:
        """使用 ffprobe 提取视频媒体信息。

        Args:
            video_path: 视频文件路径

        Returns:
            包含时长、编码、分辨率等信息的字典

        Raises:
            VideoProcessingError: ffprobe 调用失败
        """
        if not os.path.isfile(video_path):
            raise VideoProcessingError(f"视频文件不存在: {video_path}")

        # 查找 ffprobe 可执行文件（不依赖 PATH）
        ffprobe_path = cls._find_ffprobe()
        if ffprobe_path is None:
            raise VideoProcessingError(
                "未找到 ffprobe，请确保已安装 ffmpeg\n"
                "下载地址: https://ffmpeg.org/download.html\n"
                "常见安装路径: %USERPROFILE%\\AppData\\Local\\ffmpeg\\"
            )

        cmd: List[str] = [
            ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            video_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            raise VideoProcessingError("ffprobe 超时 (30s)")
        except FileNotFoundError:
            raise VideoProcessingError(
                "未找到 ffprobe，请确保已安装 ffmpeg 并添加到 PATH"
            )

        if result.returncode != 0:
            raise VideoProcessingError(
                f"ffprobe 调用失败: {result.stderr.strip()}"
            )

        try:
            if result.stdout is None:
                raise VideoProcessingError("ffprobe 输出为空")
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise VideoProcessingError(f"ffprobe 输出解析失败: {e}")

        # 提取格式信息
        fmt = data.get("format", {})
        duration_str = fmt.get("duration", "0")
        try:
            duration = float(duration_str)
        except (ValueError, TypeError):
            duration = 0.0

        # 提取视频流信息
        video_stream: Optional[Dict[str, Any]] = None
        audio_stream: Optional[Dict[str, Any]] = None
        for stream in data.get("streams", []):
            codec_type = stream.get("codec_type")
            if codec_type == "video" and video_stream is None:
                video_stream = stream
            elif codec_type == "audio" and audio_stream is None:
                audio_stream = stream

        media_info: Dict[str, Any] = {
            "file_path": os.path.abspath(video_path),
            "file_name": os.path.basename(video_path),
            "file_size": os.path.getsize(video_path),
            "duration": duration,
            "format": fmt.get("format_name", ""),
            "bit_rate": fmt.get("bit_rate", "0"),
            "video": {},
            "audio": {},
        }

        if video_stream:
            media_info["video"] = {
                "codec": video_stream.get("codec_name", ""),
                "width": video_stream.get("width", 0),
                "height": video_stream.get("height", 0),
                "fps": cls._parse_fps(video_stream.get("r_frame_rate", "0/1")),
                "bit_rate": video_stream.get("bit_rate", "0"),
            }

        if audio_stream:
            media_info["audio"] = {
                "codec": audio_stream.get("codec_name", ""),
                "sample_rate": audio_stream.get("sample_rate", "0"),
                "channels": audio_stream.get("channels", 0),
                "bit_rate": audio_stream.get("bit_rate", "0"),
            }

        return media_info

    @classmethod
    def extract_audio(
        cls, video_path: str, output_path: str, sample_rate: int = 16000
    ) -> str:
        """使用 ffmpeg 从视频中提取音频流。

        Args:
            video_path: 视频文件路径
            output_path: 输出音频 WAV 文件路径
            sample_rate: 采样率（默认 16000，适合 whisper）

        Returns:
            提取后的音频文件路径

        Raises:
            VideoProcessingError: ffmpeg 调用失败
        """
        # 确保输出目录存在
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        cmd: List[str] = [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-vn",                    # 无视频流
            "-acodec", "pcm_s16le",   # PCM 16-bit 编码
            "-ar", str(sample_rate),  # 采样率
            "-ac", "1",               # 单声道（whisper 最佳）
            output_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.TimeoutExpired:
            raise VideoProcessingError("ffmpeg 音频提取超时 (300s)")
        except FileNotFoundError:
            raise VideoProcessingError(
                "未找到 ffmpeg，请确保已安装 ffmpeg 并添加到 PATH"
            )

        if result.returncode != 0:
            raise VideoProcessingError(
                f"ffmpeg 音频提取失败: {result.stderr.strip()[:500]}"
            )

        if not os.path.isfile(output_path):
            raise VideoProcessingError(f"音频提取后文件未生成: {output_path}")

        return os.path.abspath(output_path)

    @classmethod
    def _find_ffprobe(cls) -> Optional[str]:
        """查找 ffprobe 可执行文件。

        搜索顺序:
        1. shutil.which (系统 PATH)
        2. 常见 ffmpeg 安装目录

        Returns:
            ffprobe 完整路径，未找到返回 None
        """
        import shutil

        # 1. 系统 PATH
        path = shutil.which("ffprobe")
        if path:
            return path

        # 2. 常见安装目录
        home = os.environ.get("USERPROFILE", "")
        common_paths = [
            os.path.join(home, "AppData", "Local", "ffmpeg", "bin", "ffprobe.exe"),
            os.path.join(home, "AppData", "Local", "ffmpeg", "ffmpeg-8.0.1-essentials_build", "bin", "ffprobe.exe"),
            os.path.join(home, "scoop", "apps", "ffmpeg", "current", "bin", "ffprobe.exe"),
            "C:\\ffmpeg\\bin\\ffprobe.exe",
            "C:\\Program Files\\ffmpeg\\bin\\ffprobe.exe",
        ]
        for p in common_paths:
            if os.path.isfile(p):
                return p

        return None

    @classmethod
    def _parse_fps(cls, fps_str: str) -> float:
        """解析 ffprobe 的 fps 字符串。

        Args:
            fps_str: 如 "30000/1001" 或 "25/1"

        Returns:
            浮点数帧率
        """
        match = re.match(r"(\d+)/(\d+)", fps_str)
        if match:
            try:
                return float(match.group(1)) / float(match.group(2))
            except (ValueError, ZeroDivisionError):
                return 0.0
        try:
            return float(fps_str)
        except (ValueError, TypeError):
            return 0.0
