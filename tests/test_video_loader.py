"""VideoDub 视频加载器单元测试。

测试覆盖:
- 格式校验 (合法/非法格式)
- 文件不存在处理
- ffprobe 调用（mock）
- ffmpeg 音频提取（mock）
- fps 解析
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.core.data_models import VideoProcessingError
from src.video.video_loader import VideoLoader


class TestVideoLoaderFormat:
    """视频格式校验测试。"""

    def test_supported_formats(self):
        """测试支持的格式列表。"""
        expected = [".mp4", ".mkv", ".avi", ".mov", ".webm"]
        assert VideoLoader.SUPPORTED_FORMATS == expected

    def test_validate_format_mp4(self):
        """测试 .mp4 格式合法。"""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name
        try:
            assert VideoLoader.validate_format(path) is True
        finally:
            os.unlink(path)

    def test_validate_format_mkv(self):
        """测试 .mkv 格式合法。"""
        with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as f:
            path = f.name
        try:
            assert VideoLoader.validate_format(path) is True
        finally:
            os.unlink(path)

    def test_validate_format_mov(self):
        """测试 .mov 格式合法。"""
        with tempfile.NamedTemporaryFile(suffix=".mov", delete=False) as f:
            path = f.name
        try:
            assert VideoLoader.validate_format(path) is True
        finally:
            os.unlink(path)

    def test_validate_format_webm(self):
        """测试 .webm 格式合法。"""
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            path = f.name
        try:
            assert VideoLoader.validate_format(path) is True
        finally:
            os.unlink(path)

    def test_validate_format_avi(self):
        """测试 .avi 格式合法。"""
        with tempfile.NamedTemporaryFile(suffix=".avi", delete=False) as f:
            path = f.name
        try:
            assert VideoLoader.validate_format(path) is True
        finally:
            os.unlink(path)

    def test_validate_format_invalid_extension(self):
        """测试不合法扩展名抛出异常。"""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            path = f.name
        try:
            with pytest.raises(VideoProcessingError, match="不支持的视频格式"):
                VideoLoader.validate_format(path)
        finally:
            os.unlink(path)

    def test_validate_format_no_extension(self):
        """测试无扩展名抛出异常。"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        try:
            with pytest.raises(VideoProcessingError, match="不支持的视频格式"):
                VideoLoader.validate_format(path)
        finally:
            os.unlink(path)

    def test_validate_format_uppercase_extension(self):
        """测试大写扩展名也合法。"""
        with tempfile.NamedTemporaryFile(suffix=".MP4", delete=False) as f:
            path = f.name
        try:
            # 内部做了 .lower()
            assert VideoLoader.validate_format(path) is True
        finally:
            os.unlink(path)

    def test_validate_format_file_not_found(self):
        """测试文件不存在时抛出异常。"""
        with pytest.raises(VideoProcessingError, match="视频文件不存在"):
            VideoLoader.validate_format("/nonexistent/video.mp4")


class TestVideoLoaderGetMediaInfo:
    """视频媒体信息获取测试。"""

    @patch("src.video.video_loader.subprocess.run")
    def test_get_media_info_success(self, mock_run):
        """测试成功获取媒体信息。"""
        # 模拟 ffprobe 输出
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "format": {
                "duration": "120.5",
                "format_name": "mp4",
                "bit_rate": "2000000",
            },
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "30000/1001",
                    "bit_rate": "1500000",
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "sample_rate": "44100",
                    "channels": 2,
                    "bit_rate": "128000",
                },
            ],
        })
        mock_run.return_value = mock_result

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name

        try:
            info = VideoLoader.get_media_info(path)

            assert info["duration"] == 120.5
            assert info["format"] == "mp4"
            assert info["video"]["codec"] == "h264"
            assert info["video"]["width"] == 1920
            assert info["video"]["height"] == 1080
            assert abs(info["video"]["fps"] - 29.97) < 0.1
            assert info["audio"]["codec"] == "aac"
            assert info["audio"]["sample_rate"] == "44100"
            assert info["audio"]["channels"] == 2
        finally:
            os.unlink(path)

    @patch("src.video.video_loader.subprocess.run")
    def test_get_media_info_no_streams(self, mock_run):
        """测试无音视频流。"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "format": {"duration": "10.0", "format_name": "mp4"},
            "streams": [],
        })
        mock_run.return_value = mock_result

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name

        try:
            info = VideoLoader.get_media_info(path)
            assert info["video"] == {}
            assert info["audio"] == {}
        finally:
            os.unlink(path)

    @patch("src.video.video_loader.subprocess.run")
    def test_get_media_info_file_not_found(self, mock_run):
        """测试文件不存在。"""
        with pytest.raises(VideoProcessingError, match="视频文件不存在"):
            VideoLoader.get_media_info("/nonexistent/file.mp4")

    @patch("src.video.video_loader.subprocess.run")
    def test_get_media_info_ffprobe_timeout(self, mock_run):
        """测试 ffprobe 超时。"""
        mock_run.side_effect = __import__("subprocess").TimeoutExpired(
            cmd="ffprobe", timeout=30
        )

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name

        try:
            with pytest.raises(VideoProcessingError, match="ffprobe 超时"):
                VideoLoader.get_media_info(path)
        finally:
            os.unlink(path)

    @patch("src.video.video_loader.subprocess.run")
    def test_get_media_info_ffprobe_not_found(self, mock_run):
        """测试 ffprobe 未安装。"""
        mock_run.side_effect = FileNotFoundError()

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name

        try:
            with pytest.raises(VideoProcessingError, match="未找到 ffprobe"):
                VideoLoader.get_media_info(path)
        finally:
            os.unlink(path)

    @patch("src.video.video_loader.subprocess.run")
    def test_get_media_info_ffprobe_error(self, mock_run):
        """测试 ffprobe 返回非零退出码。"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error: file corrupt"
        mock_run.return_value = mock_result

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name

        try:
            with pytest.raises(VideoProcessingError, match="ffprobe 调用失败"):
                VideoLoader.get_media_info(path)
        finally:
            os.unlink(path)

    @patch("src.video.video_loader.subprocess.run")
    def test_get_media_info_json_decode_error(self, mock_run):
        """测试 ffprobe 输出 JSON 解析失败。"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json"
        mock_run.return_value = mock_result

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name

        try:
            with pytest.raises(VideoProcessingError, match="ffprobe 输出解析失败"):
                VideoLoader.get_media_info(path)
        finally:
            os.unlink(path)

    @patch("src.video.video_loader.subprocess.run")
    def test_get_media_info_missing_duration(self, mock_run):
        """测试缺少 duration 字段。"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "format": {"format_name": "mp4"},
            "streams": [],
        })
        mock_run.return_value = mock_result

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name

        try:
            info = VideoLoader.get_media_info(path)
            assert info["duration"] == 0.0
        finally:
            os.unlink(path)


class TestVideoLoaderLoad:
    """load 方法测试（validate_format + get_media_info 快捷组合）。"""

    @patch("src.video.video_loader.subprocess.run")
    def test_load_success(self, mock_run):
        """测试 load 成功。"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "format": {"duration": "30.0", "format_name": "mp4"},
            "streams": [],
        })
        mock_run.return_value = mock_result

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            path = f.name

        try:
            info = VideoLoader.load(path)
            assert info["duration"] == 30.0
        finally:
            os.unlink(path)

    def test_load_invalid_format(self):
        """测试 load 时格式不合法。"""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            path = f.name
        try:
            with pytest.raises(VideoProcessingError, match="不支持的视频格式"):
                VideoLoader.load(path)
        finally:
            os.unlink(path)

    def test_load_file_not_found(self):
        """测试 load 时文件不存在。"""
        with pytest.raises(VideoProcessingError, match="视频文件不存在"):
            VideoLoader.load("/nonexistent/video.mp4")


class TestVideoLoaderExtractAudio:
    """音频提取测试。"""

    @patch("src.video.video_loader.subprocess.run")
    def test_extract_audio_success(self, mock_run):
        """测试成功提取音频。"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            video_path = f.name

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                output_path = os.path.join(tmpdir, "audio.wav")
                # 创建模拟输出文件
                open(output_path, "w").close()

                result = VideoLoader.extract_audio(video_path, output_path)
                assert result == os.path.abspath(output_path)
        finally:
            os.unlink(video_path)

    @patch("src.video.video_loader.subprocess.run")
    def test_extract_audio_timeout(self, mock_run):
        """测试音频提取超时。"""
        mock_run.side_effect = __import__("subprocess").TimeoutExpired(
            cmd="ffmpeg", timeout=300
        )

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            video_path = f.name

        try:
            with pytest.raises(VideoProcessingError, match="ffmpeg 音频提取超时"):
                VideoLoader.extract_audio(video_path, "/tmp/output.wav")
        finally:
            os.unlink(video_path)

    @patch("src.video.video_loader.subprocess.run")
    def test_extract_audio_ffmpeg_not_found(self, mock_run):
        """测试 ffmpeg 未安装。"""
        mock_run.side_effect = FileNotFoundError()

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            video_path = f.name

        try:
            with pytest.raises(VideoProcessingError, match="未找到 ffmpeg"):
                VideoLoader.extract_audio(video_path, "/tmp/output.wav")
        finally:
            os.unlink(video_path)

    @patch("src.video.video_loader.subprocess.run")
    def test_extract_audio_ffmpeg_error(self, mock_run):
        """测试 ffmpeg 返回错误。"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error processing"
        mock_run.return_value = mock_result

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            video_path = f.name

        try:
            with pytest.raises(VideoProcessingError, match="ffmpeg 音频提取失败"):
                VideoLoader.extract_audio(video_path, "/tmp/output.wav")
        finally:
            os.unlink(video_path)

    @patch("src.video.video_loader.subprocess.run")
    def test_extract_audio_no_output_file(self, mock_run):
        """测试提取后文件未生成。"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            video_path = f.name

        try:
            with pytest.raises(VideoProcessingError, match="音频提取后文件未生成"):
                VideoLoader.extract_audio(video_path, "/nonexistent_dir/output.wav")
        finally:
            os.unlink(video_path)


class TestVideoLoaderParseFps:
    """FPS 解析测试。"""

    def test_parse_fps_fraction(self):
        """测试分数格式 FPS 解析。"""
        fps = VideoLoader._parse_fps("30000/1001")
        assert abs(fps - 29.97) < 0.01

    def test_parse_fps_integer_fraction(self):
        """测试整数分数格式。"""
        fps = VideoLoader._parse_fps("25/1")
        assert fps == 25.0

    def test_parse_fps_float_string(self):
        """测试浮点数字符串。"""
        fps = VideoLoader._parse_fps("29.97")
        assert abs(fps - 29.97) < 0.01

    def test_parse_fps_zero_division(self):
        """测试除零返回 0。"""
        fps = VideoLoader._parse_fps("1/0")
        assert fps == 0.0

    def test_parse_fps_invalid_string(self):
        """测试无效字符串返回 0。"""
        fps = VideoLoader._parse_fps("invalid")
        assert fps == 0.0

    def test_parse_fps_empty_string(self):
        """测试空字符串返回 0。"""
        fps = VideoLoader._parse_fps("")
        assert fps == 0.0
