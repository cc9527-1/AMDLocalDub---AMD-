"""VideoDub 数据模型单元测试。

测试覆盖:
- Segment 创建/校验/序列化/反序列化
- PipelineContext 创建/添加句段
- 所有枚举类型的正确性
- 异常类继承关系
"""

import copy
import pickle

import pytest

from src.core.data_models import (
    ASRError,
    EngineType,
    PipelineContext,
    PipelineStage,
    PipelineStatus,
    Segment,
    SegmentStatus,
    TTSError,
    TranslationError,
    VideoDubError,
    VideoProcessingError,
)


# ==================== Segment 测试 ====================


class TestSegment:
    """Segment 数据模型测试。"""

    def test_create_valid_segment(self):
        """测试创建合法的句段对象。"""
        seg = Segment(
            index=1,
            original_text="Hello world",
            start_time=0.0,
            end_time=2.5,
        )
        assert seg.index == 1
        assert seg.original_text == "Hello world"
        assert seg.start_time == 0.0
        assert seg.end_time == 2.5
        assert seg.translated_text == ""  # 默认值
        assert seg.tts_audio_path == ""  # 默认值
        assert seg.status == SegmentStatus.PENDING  # 默认值
        assert seg.error_message == ""  # 默认值

    def test_create_segment_with_defaults(self):
        """测试创建句段并显式指定部分默认值。"""
        seg = Segment(
            index=2,
            original_text="Test",
            start_time=1.0,
            end_time=3.0,
            translated_text="测试",
            tts_audio_path="/path/to/audio.wav",
            status=SegmentStatus.TTS_DONE,
            error_message="",
        )
        assert seg.translated_text == "测试"
        assert seg.tts_audio_path == "/path/to/audio.wav"
        assert seg.status == SegmentStatus.TTS_DONE

    def test_segment_duration_property(self):
        """测试 duration 属性返回正确的时长。"""
        seg = Segment(index=1, original_text="Hi", start_time=1.0, end_time=4.0)
        assert seg.duration == 3.0

    def test_segment_duration_zero_length(self):
        """测试起始时间相同时时长为 0。"""
        seg = Segment(index=1, original_text="Hi", start_time=2.0, end_time=2.0)
        assert seg.duration == 0.0

    def test_segment_negative_start_time_raises(self):
        """测试负起始时间应抛出 ValueError。"""
        with pytest.raises(ValueError, match="start_time must be >= 0"):
            Segment(index=1, original_text="Hi", start_time=-1.0, end_time=2.0)

    def test_segment_end_before_start_raises(self):
        """测试结束时间早于起始时间应抛出 ValueError。"""
        with pytest.raises(ValueError, match="end_time.*must be >= start_time"):
            Segment(index=1, original_text="Hi", start_time=5.0, end_time=3.0)

    def test_segment_index_less_than_one_raises(self):
        """测试序号小于 1 应抛出 ValueError。"""
        with pytest.raises(ValueError, match="index must be >= 1"):
            Segment(index=0, original_text="Hi", start_time=0.0, end_time=1.0)

    def test_segment_index_zero_raises(self):
        """测试序号为 0 应抛出 ValueError。"""
        with pytest.raises(ValueError):
            Segment(index=0, original_text="Hi", start_time=0.0, end_time=1.0)

    def test_segment_negative_index_raises(self):
        """测试负序号应抛出 ValueError。"""
        with pytest.raises(ValueError):
            Segment(index=-5, original_text="Hi", start_time=0.0, end_time=1.0)

    # ---- 序列化/反序列化 ----

    def test_to_dict(self):
        """测试 Segment 序列化为字典。"""
        seg = Segment(
            index=1,
            original_text="Hello world",
            start_time=0.0,
            end_time=2.5,
            translated_text="你好世界",
            tts_audio_path="/path/to/tts.wav",
            status=SegmentStatus.TTS_DONE,
            error_message="",
        )
        d = seg.to_dict()
        assert d["index"] == 1
        assert d["original_text"] == "Hello world"
        assert d["translated_text"] == "你好世界"
        assert d["start_time"] == 0.0
        assert d["end_time"] == 2.5
        assert d["tts_audio_path"] == "/path/to/tts.wav"
        assert d["status"] == "tts_done"
        assert d["error_message"] == ""

    def test_from_dict(self):
        """测试从字典反序列化创建 Segment。"""
        data = {
            "index": 3,
            "original_text": "Good morning",
            "translated_text": "早上好",
            "start_time": 10.0,
            "end_time": 12.5,
            "tts_audio_path": "/path/to/seg_0003.wav",
            "status": "translated",
            "error_message": "",
        }
        seg = Segment.from_dict(data)
        assert seg.index == 3
        assert seg.original_text == "Good morning"
        assert seg.translated_text == "早上好"
        assert seg.start_time == 10.0
        assert seg.end_time == 12.5
        assert seg.tts_audio_path == "/path/to/seg_0003.wav"
        assert seg.status == SegmentStatus.TRANSLATED
        assert seg.error_message == ""

    def test_from_dict_minimal(self):
        """测试从最小字段字典反序列化（使用默认值）。"""
        data = {
            "index": 1,
            "original_text": "Hello",
            "start_time": 0.0,
            "end_time": 1.0,
        }
        seg = Segment.from_dict(data)
        assert seg.translated_text == ""
        assert seg.tts_audio_path == ""
        assert seg.status == SegmentStatus.PENDING
        assert seg.error_message == ""

    def test_to_dict_from_dict_roundtrip(self):
        """测试序列化后反序列化得到等价对象。"""
        seg1 = Segment(
            index=5,
            original_text="Round trip test",
            start_time=3.0,
            end_time=6.0,
            translated_text="往返测试",
            tts_audio_path="/tmp/audio.wav",
            status=SegmentStatus.COMPLETED,
            error_message="",
        )
        seg2 = Segment.from_dict(seg1.to_dict())
        assert seg2.index == seg1.index
        assert seg2.original_text == seg1.original_text
        assert seg2.translated_text == seg1.translated_text
        assert seg2.start_time == seg1.start_time
        assert seg2.end_time == seg1.end_time
        assert seg2.tts_audio_path == seg1.tts_audio_path
        assert seg2.status == seg1.status

    def test_repr(self):
        """测试 __repr__ 输出格式。"""
        seg = Segment(index=1, original_text="Hello world", start_time=0.0, end_time=2.5)
        r = repr(seg)
        assert "Segment" in r
        assert "idx=1" in r
        assert "Hello" in r
        assert "0.00s" in r
        assert "2.50s" in r
        assert "pending" in r


# ==================== PipelineContext 测试 ====================


class TestPipelineContext:
    """PipelineContext 数据模型测试。"""

    def test_create_minimal_context(self):
        """测试创建最小 PipelineContext。"""
        ctx = PipelineContext(video_path="/path/to/video.mp4")
        assert ctx.video_path == "/path/to/video.mp4"
        assert ctx.audio_path == ""
        assert ctx.duration == 0.0
        assert ctx.source_lang == "en"
        assert ctx.target_lang == "zh"
        assert ctx.output_format == "mp4"
        assert ctx.subtitle_mode == "soft"
        assert ctx.engine_type == EngineType.SILICONFLOW
        assert ctx.status == PipelineStatus.PENDING
        assert ctx.segments == []
        assert ctx.merged_audio_path == ""
        assert ctx.output_video_path == ""
        assert ctx.subtitle_path == ""
        assert ctx.metadata == {}
        assert ctx.config_snapshot == {}
        assert ctx.working_dir == ""
        assert len(ctx.task_id) == 12  # uuid4 hex[:12]

    def test_auto_generate_task_id(self):
        """测试自动生成 task_id。"""
        ctx1 = PipelineContext(video_path="/a.mp4")
        ctx2 = PipelineContext(video_path="/b.mp4")
        assert ctx1.task_id != ctx2.task_id  # 两次应不同

    def test_provided_task_id(self):
        """测试提供自定义 task_id。"""
        ctx = PipelineContext(video_path="/a.mp4", task_id="my-task-001")
        assert ctx.task_id == "my-task-001"

    def test_add_segment(self):
        """测试添加句段。"""
        ctx = PipelineContext(video_path="/v.mp4")
        seg1 = Segment(index=1, original_text="Hello", start_time=0.0, end_time=1.0)
        seg2 = Segment(index=2, original_text="World", start_time=1.0, end_time=2.0)
        ctx.add_segment(seg1)
        ctx.add_segment(seg2)
        assert len(ctx.segments) == 2
        assert ctx.segments[0].original_text == "Hello"
        assert ctx.segments[1].original_text == "World"

    def test_get_segment_by_index(self):
        """测试按序号获取句段。"""
        ctx = PipelineContext(video_path="/v.mp4")
        seg1 = Segment(index=1, original_text="First", start_time=0.0, end_time=1.0)
        seg2 = Segment(index=3, original_text="Third", start_time=2.0, end_time=3.0)
        ctx.add_segment(seg1)
        ctx.add_segment(seg2)
        assert ctx.get_segment(1).original_text == "First"
        assert ctx.get_segment(3).original_text == "Third"
        assert ctx.get_segment(2) is None

    def test_get_segment_not_found(self):
        """测试获取不存在的句段返回 None。"""
        ctx = PipelineContext(video_path="/v.mp4")
        assert ctx.get_segment(99) is None

    def test_to_dict(self):
        """测试 PipelineContext 序列化。"""
        ctx = PipelineContext(video_path="/v.mp4", task_id="test-123")
        seg = Segment(index=1, original_text="Hi", start_time=0.0, end_time=1.0)
        ctx.add_segment(seg)
        d = ctx.to_dict()
        assert d["task_id"] == "test-123"
        assert d["video_path"] == "/v.mp4"
        assert d["status"] == "pending"
        assert len(d["segments"]) == 1
        assert d["segments"][0]["original_text"] == "Hi"
        assert d["engine_type"] == "siliconflow"

    def test_repr(self):
        """测试 __repr__ 输出格式。"""
        ctx = PipelineContext(video_path="/v.mp4")
        ctx.add_segment(Segment(index=1, original_text="Hi", start_time=0.0, end_time=1.0))
        r = repr(ctx)
        assert "PipelineContext" in r
        assert "/v.mp4" in r
        assert "segments=1" in r
        assert "pending" in r

    def test_to_dict_immutable_metadata(self):
        """测试序列化后 metadata 不被外部修改影响。"""
        ctx = PipelineContext(video_path="/v.mp4")
        ctx.metadata["key"] = "value"
        d = ctx.to_dict()
        d["metadata"]["key"] = "changed"
        assert ctx.metadata["key"] == "value"


# ==================== 枚举测试 ====================


class TestEnums:
    """枚举类型正确性测试。"""

    def test_pipeline_stage_values(self):
        """测试 PipelineStage 枚举值。"""
        assert PipelineStage.VIDEO_LOAD.value == "video_load"
        assert PipelineStage.ASR.value == "asr"
        assert PipelineStage.SENTENCE_SPLIT.value == "sentence_split"
        assert PipelineStage.TRANSLATE.value == "translate"
        assert PipelineStage.AUDIO_SEGMENT.value == "audio_segment"
        assert PipelineStage.TTS.value == "tts"
        assert PipelineStage.AUDIO_MERGE.value == "audio_merge"
        assert PipelineStage.VIDEO_COMPOSE.value == "video_compose"
        assert len(list(PipelineStage)) == 8

    def test_pipeline_stage_display_name(self):
        """测试 PipelineStage 显示名称。"""
        assert PipelineStage.VIDEO_LOAD.display_name == "视频加载"
        assert PipelineStage.ASR.display_name == "语音识别"
        assert PipelineStage.TRANSLATE.display_name == "翻译"
        assert PipelineStage.TTS.display_name == "配音合成"
        assert PipelineStage.VIDEO_COMPOSE.display_name == "视频合成"

    def test_pipeline_stage_str(self):
        """测试 PipelineStage __str__。"""
        assert str(PipelineStage.ASR) == "asr"

    def test_pipeline_status_values(self):
        """测试 PipelineStatus 枚举值。"""
        assert PipelineStatus.PENDING.value == "pending"
        assert PipelineStatus.RUNNING.value == "running"
        assert PipelineStatus.COMPLETED.value == "completed"
        assert PipelineStatus.FAILED.value == "failed"
        assert PipelineStatus.CANCELLED.value == "cancelled"
        assert len(list(PipelineStatus)) == 5

    def test_pipeline_status_str(self):
        """测试 PipelineStatus __str__。"""
        assert str(PipelineStatus.RUNNING) == "running"

    def test_segment_status_values(self):
        """测试 SegmentStatus 枚举值。"""
        assert SegmentStatus.PENDING.value == "pending"
        assert SegmentStatus.TRANSLATED.value == "translated"
        assert SegmentStatus.TTS_DONE.value == "tts_done"
        assert SegmentStatus.COMPLETED.value == "completed"
        assert SegmentStatus.FAILED.value == "failed"
        assert len(list(SegmentStatus)) == 5

    def test_engine_type_values(self):
        """测试 EngineType 枚举值。"""
        assert EngineType.SILICONFLOW.value == "siliconflow"
        assert EngineType.LM_STUDIO.value == "lmstudio"
        assert EngineType.DEEPSEEK.value == "deepseek"
        assert len(list(EngineType)) == 3

    def test_engine_type_from_string(self):
        """测试 EngineType.from_string 方法。"""
        assert EngineType.from_string("siliconflow") == EngineType.SILICONFLOW
        assert EngineType.from_string("LMSTUDIO") == EngineType.LM_STUDIO
        assert EngineType.from_string("DeepSeek") == EngineType.DEEPSEEK
        assert EngineType.from_string("DEEPSEEK") == EngineType.DEEPSEEK

    def test_engine_type_from_string_invalid(self):
        """测试无效字符串应抛出 ValueError。"""
        with pytest.raises(ValueError, match="Unknown engine type"):
            EngineType.from_string("invalid_engine")

    def test_engine_type_all_types(self):
        """测试 all_types 类方法。"""
        types = EngineType.all_types()
        assert EngineType.SILICONFLOW in types
        assert EngineType.LM_STUDIO in types
        assert EngineType.DEEPSEEK in types
        assert len(types) == 3

    def test_engine_type_str(self):
        """测试 EngineType __str__。"""
        assert str(EngineType.SILICONFLOW) == "siliconflow"


# ==================== 异常测试 ====================


class TestExceptions:
    """异常类继承关系测试。"""

    def test_video_dub_error_base(self):
        """测试 VideoDubError 基类。"""
        err = VideoDubError("Something went wrong", "TestModule")
        assert err.module == "TestModule"
        assert "[TestModule]" in str(err)
        assert "Something went wrong" in str(err)
        assert isinstance(err, Exception)

    def test_asr_error(self):
        """测试 ASRError 继承自 VideoDubError。"""
        err = ASRError("ASR failed")
        assert isinstance(err, VideoDubError)
        assert isinstance(err, Exception)
        assert err.module == "ASREngine"
        assert "ASR failed" in str(err)

    def test_translation_error(self):
        """测试 TranslationError 继承自 VideoDubError。"""
        err = TranslationError("Translation failed")
        assert isinstance(err, VideoDubError)
        assert isinstance(err, Exception)
        assert err.module == "TranslationEngine"

    def test_tts_error(self):
        """测试 TTSError 继承自 VideoDubError。"""
        err = TTSError("TTS failed")
        assert isinstance(err, VideoDubError)
        assert isinstance(err, Exception)
        assert err.module == "TTSEngine"

    def test_video_processing_error(self):
        """测试 VideoProcessingError 继承自 VideoDubError。"""
        err = VideoProcessingError("Video processing failed")
        assert isinstance(err, VideoDubError)
        assert isinstance(err, Exception)
        assert err.module == "VideoProcessor"

    def test_custom_message_format(self):
        """测试异常消息格式。"""
        err = VideoDubError("错误信息", "CustomModule")
        assert str(err) == "[CustomModule] 错误信息"
