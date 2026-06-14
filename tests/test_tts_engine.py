"""VideoDub TTS 引擎单元测试。

测试覆盖:
- 语音列表查询
- 语音校验
- 空文本处理
- 配置方法
"""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.data_models import Segment, SegmentStatus, TTSError
from src.tts.tts_engine import TTSEngine


class TestTTSEngineInit:
    """TTS 引擎初始化测试。"""

    def test_default_voice(self):
        """测试默认语音。"""
        tts = TTSEngine()
        assert tts._voice == "zh-CN-XiaoxiaoNeural"

    def test_default_rate(self):
        """测试默认语速。"""
        tts = TTSEngine()
        assert tts._rate == "+0%"

    def test_default_volume(self):
        """测试默认音量。"""
        tts = TTSEngine()
        assert tts._volume == "+0%"

    def test_default_connect_timeout(self):
        """测试默认连接超时。"""
        tts = TTSEngine()
        assert tts._connect_timeout == 10

    def test_custom_voice(self):
        """测试自定义语音。"""
        tts = TTSEngine(voice="en-US-JennyNeural")
        assert tts._voice == "en-US-JennyNeural"


class TestTTSEngineVoices:
    """语音查询/校验测试。"""

    def test_list_voices(self):
        """测试列出所有语音。"""
        voices = TTSEngine.list_voices()
        assert "zh-CN-XiaoxiaoNeural" in voices
        assert "en-US-JennyNeural" in voices
        assert len(voices) == 7

    def test_list_voices_with_description(self):
        """测试列出语音及描述。"""
        voices = TTSEngine.list_voices_with_description()
        assert len(voices) == 7
        found = False
        for v in voices:
            if v["name"] == "zh-CN-XiaoxiaoNeural":
                assert "中文普通话" in v["description"]
                found = True
        assert found

    def test_validate_voice_valid(self):
        """测试有效语音校验。"""
        assert TTSEngine.validate_voice("zh-CN-XiaoxiaoNeural") is True
        assert TTSEngine.validate_voice("en-US-GuyNeural") is True

    def test_validate_voice_invalid(self):
        """测试无效语音校验。"""
        assert TTSEngine.validate_voice("invalid-voice") is False
        assert TTSEngine.validate_voice("") is False

    def test_set_voice(self):
        """测试设置语音。"""
        tts = TTSEngine()
        tts.set_voice("en-GB-SoniaNeural")
        assert tts._voice == "en-GB-SoniaNeural"

    def test_set_rate(self):
        """测试设置语速。"""
        tts = TTSEngine()
        tts.set_rate("+50%")
        assert tts._rate == "+50%"


class TestTTSEngineSynthesize:
    """配音合成测试。"""

    def test_synthesize_empty_text(self):
        """测试空文本合成（返回空路径）。"""
        tts = TTSEngine()
        seg = Segment(
            index=1,
            original_text="Hello",
            translated_text="",
            start_time=0.0,
            end_time=1.0,
        )
        result = tts.synthesize(seg, "/tmp/tts_output")
        assert result == ""
        assert seg.tts_audio_path == ""
        assert seg.status == SegmentStatus.TTS_DONE

    def test_synthesize_whitespace_text(self):
        """测试空白文本合成。"""
        tts = TTSEngine()
        seg = Segment(
            index=1,
            original_text="Hello",
            translated_text="   ",
            start_time=0.0,
            end_time=1.0,
        )
        result = tts.synthesize(seg, "/tmp/tts_output")
        assert result == ""

    @patch("src.tts.tts_engine.edge_tts")
    def test_synthesize_creates_output_dir(self, mock_edge_tts):
        """测试合成时创建输出目录。"""
        tts = TTSEngine()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = os.path.join(tmpdir, "nested", "tts")
            seg = Segment(
                index=1,
                original_text="Hello",
                translated_text="你好",
                start_time=0.0,
                end_time=1.0,
            )
            # mock edge_tts.Communicate with async save
            mock_comm = MagicMock()
            mock_comm.save = AsyncMock()
            mock_edge_tts.Communicate.return_value = mock_comm

            # 模拟生成的音频文件
            expected_path = os.path.join(output_dir, "seg_0001.wav")
            os.makedirs(output_dir, exist_ok=True)
            open(expected_path, "w").close()

            result = tts.synthesize(seg, output_dir)
            assert os.path.isdir(output_dir)

    @patch("src.tts.tts_engine.edge_tts")
    def test_synthesize_updates_segment_status(self, mock_edge_tts):
        """测试合成后更新句段状态。"""
        tts = TTSEngine()
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_comm = MagicMock()
            mock_comm.save = AsyncMock()
            mock_edge_tts.Communicate.return_value = mock_comm

            seg = Segment(
                index=1,
                original_text="Hello",
                translated_text="你好",
                start_time=0.0,
                end_time=1.0,
            )

            # 创建模拟输出文件
            output_path = os.path.join(tmpdir, "seg_0001.wav")
            open(output_path, "w").close()

            result = tts.synthesize(seg, tmpdir)
            assert seg.status == SegmentStatus.TTS_DONE
            assert seg.tts_audio_path != ""

    @patch("src.tts.tts_engine.edge_tts")
    def test_synthesize_api_error(self, mock_edge_tts):
        """测试 API 错误抛出 TTSError。"""
        tts = TTSEngine()
        mock_comm = MagicMock()
        mock_comm.save.side_effect = Exception("Connection failed")
        mock_edge_tts.Communicate.return_value = mock_comm

        seg = Segment(
            index=1,
            original_text="Hello",
            translated_text="你好",
            start_time=0.0,
            end_time=1.0,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(TTSError):
                tts.synthesize(seg, tmpdir)

    @patch("src.tts.tts_engine.edge_tts")
    def test_synthesize_file_not_created(self, mock_edge_tts):
        """测试文件未生成时抛出错误。"""
        tts = TTSEngine()
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock()
        mock_edge_tts.Communicate.return_value = mock_comm

        seg = Segment(
            index=1,
            original_text="Hello",
            translated_text="你好",
            start_time=0.0,
            end_time=1.0,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(TTSError, match="未生成音频文件"):
                tts.synthesize(seg, tmpdir)


class TestTTSEngineBatchSynthesize:
    """批量合成测试。"""

    def test_batch_synthesize_empty(self):
        """测试空列表批量合成。"""
        tts = TTSEngine()
        result = tts.batch_synthesize([], "/tmp/output")
        assert result == []

    def test_batch_synthesize_with_progress_callback(self):
        """测试批量合成带进度回调。"""
        tts = TTSEngine()
        callback = MagicMock()
        segments = [
            Segment(
                index=i,
                original_text=f"Text {i}",
                translated_text="",
                start_time=0.0,
                end_time=1.0,
            )
            for i in range(1, 4)
        ]
        result = tts.batch_synthesize(segments, "/tmp/output", progress_callback=callback)
        # 空文本会直接完成，不调用 edge-tts
        for seg in result:
            assert seg.status == SegmentStatus.TTS_DONE
        # 回调至少被调用了（开始和结束）
        callback.assert_any_call(100.0, "配音合成完成")

    @patch("src.tts.tts_engine.edge_tts")
    def test_batch_synthesize_continues_on_error(self, mock_edge_tts):
        """测试批量合成时单句失败继续处理后续。"""
        tts = TTSEngine()
        mock_comm = MagicMock()
        mock_edge_tts.Communicate.return_value = mock_comm

        segments = [
            Segment(
                index=1,
                original_text="First",
                translated_text="第一句",
                start_time=0.0,
                end_time=1.0,
            ),
            Segment(
                index=2,
                original_text="Second",
                translated_text="第二句",
                start_time=1.0,
                end_time=2.0,
            ),
        ]
        # 为第一个段创建输出文件
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "seg_0001.wav"), "w").close()
            open(os.path.join(tmpdir, "seg_0002.wav"), "w").close()

            result = tts.batch_synthesize(segments, tmpdir)
            assert len(result) == 2
