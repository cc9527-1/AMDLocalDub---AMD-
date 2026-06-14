"""VideoDub 数据模型定义。

包含贯穿全流程的数据类 PipelineContext、句段 Segment、
以及各枚举类型和自定义异常。
"""

from __future__ import annotations

import copy
import enum
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ==================== 枚举定义 ====================


class PipelineStage(enum.Enum):
    """Pipeline 处理阶段枚举。"""

    VIDEO_LOAD = "video_load"
    ASR = "asr"
    SENTENCE_SPLIT = "sentence_split"
    TRANSLATE = "translate"
    AUDIO_SEGMENT = "audio_segment"
    TTS = "tts"
    AUDIO_MERGE = "audio_merge"
    VIDEO_COMPOSE = "video_compose"

    def __str__(self) -> str:
        return self.value

    @property
    def display_name(self) -> str:
        """返回中文展示名称。"""
        names = {
            "video_load": "视频加载",
            "asr": "语音识别",
            "sentence_split": "句子拆分",
            "translate": "翻译",
            "audio_segment": "音频分段",
            "tts": "配音合成",
            "audio_merge": "音频合并",
            "video_compose": "视频合成",
        }
        return names.get(self.value, self.value)


class PipelineStatus(enum.Enum):
    """Pipeline 整体状态枚举。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def __str__(self) -> str:
        return self.value


class SegmentStatus(enum.Enum):
    """单个句段的状态枚举。"""

    PENDING = "pending"
    TRANSLATED = "translated"
    TTS_DONE = "tts_done"
    COMPLETED = "completed"
    FAILED = "failed"

    def __str__(self) -> str:
        return self.value


class EngineType(enum.Enum):
    """翻译引擎类型枚举。"""

    SILICONFLOW = "siliconflow"
    LM_STUDIO = "lmstudio"
    DEEPSEEK = "deepseek"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> EngineType:
        """从字符串创建 EngineType，不区分大小写。"""
        for member in cls:
            if member.value == value.lower():
                return member
        raise ValueError(f"Unknown engine type: {value}")

    @classmethod
    def all_types(cls) -> List[EngineType]:
        """返回所有引擎类型列表。"""
        return list(cls)


# ==================== 异常定义 ====================


class VideoDubError(Exception):
    """所有 VideoDub 异常的基类。"""

    def __init__(self, message: str, module: str = "Unknown") -> None:
        self.module = module
        super().__init__(f"[{module}] {message}")


class ASRError(VideoDubError):
    """ASR 模块异常。"""

    def __init__(self, message: str, module: str = "ASREngine") -> None:
        super().__init__(message, module)


class TranslationError(VideoDubError):
    """翻译模块异常（含 API 错误、超时、无效响应）。"""

    def __init__(self, message: str, module: str = "TranslationEngine") -> None:
        super().__init__(message, module)


class TTSError(VideoDubError):
    """TTS 模块异常。"""

    def __init__(self, message: str, module: str = "TTSEngine") -> None:
        super().__init__(message, module)


class VideoProcessingError(VideoDubError):
    """视频/音频处理异常（ffmpeg 调用失败）。"""

    def __init__(self, message: str, module: str = "VideoProcessor") -> None:
        super().__init__(message, module)


# ==================== 数据类定义 ====================


@dataclass
class Segment:
    """单个句子分段的数据模型。

    Attributes:
        index: 句段序号（从 1 开始）
        original_text: ASR 识别的原始文本
        translated_text: 翻译后的文本（初始为空字符串）
        start_time: 起始时间（秒）
        end_time: 结束时间（秒）
        tts_audio_path: TTS 生成的音频文件路径（初始为空字符串）
        status: 句段当前处理状态
        error_message: 错误信息（可选）
    """

    index: int
    original_text: str
    start_time: float
    end_time: float
    translated_text: str = ""
    tts_audio_path: str = ""
    status: SegmentStatus = SegmentStatus.PENDING
    error_message: str = ""

    def __post_init__(self) -> None:
        """初始化后校验数据合法性。"""
        if self.start_time < 0:
            raise ValueError(f"start_time must be >= 0, got {self.start_time}")
        if self.end_time < self.start_time:
            raise ValueError(
                f"end_time ({self.end_time}) must be >= start_time ({self.start_time})"
            )
        if self.index < 1:
            raise ValueError(f"index must be >= 1, got {self.index}")

    @property
    def duration(self) -> float:
        """句段时长（秒）。"""
        return self.end_time - self.start_time

    def to_dict(self) -> Dict[str, Any]:
        """将 Segment 序列化为字典。"""
        return {
            "index": self.index,
            "original_text": self.original_text,
            "translated_text": self.translated_text,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "tts_audio_path": self.tts_audio_path,
            "status": self.status.value,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Segment:
        """从字典反序列化创建 Segment 实例。"""
        return cls(
            index=data["index"],
            original_text=data["original_text"],
            start_time=data["start_time"],
            end_time=data["end_time"],
            translated_text=data.get("translated_text", ""),
            tts_audio_path=data.get("tts_audio_path", ""),
            status=SegmentStatus(data.get("status", "pending")),
            error_message=data.get("error_message", ""),
        )

    def __repr__(self) -> str:
        return (
            f"Segment(idx={self.index}, "
            f"'{self.original_text[:30]}...', "
            f"{self.start_time:.2f}s-{self.end_time:.2f}s, "
            f"{self.status.value})"
        )


@dataclass
class PipelineContext:
    """贯穿全流程的数据上下文。

    每个处理模块从 PipelineContext 读取所需数据，
    处理完成后将结果写回。模块间无直接耦合。

    Attributes:
        video_path: 原始视频文件路径
        audio_path: 提取的音频文件路径
        duration: 视频总时长（秒）
        source_lang: 源语言代码
        target_lang: 目标语言代码
        output_format: 输出视频格式
        subtitle_mode: 字幕模式 (none/soft/burn)
        engine_type: 当前翻译引擎类型
        status: Pipeline 整体状态
        segments: 句段列表（贯穿全流程的核心数据）
        merged_audio_path: 合并后的配音音频路径
        output_video_path: 最终输出视频路径
        subtitle_path: 字幕文件路径
        metadata: 视频元信息字典
        config_snapshot: 运行时配置快照
        working_dir: 工作目录路径（临时文件）
        task_id: 任务唯一标识
        output_dir: 输出目录（留空则输出到原视频所在目录）
        tts_voice: TTS 配音音色
    """

    video_path: str
    audio_path: str = ""
    duration: float = 0.0
    source_lang: str = "en"
    target_lang: str = "zh"
    output_format: str = "mp4"
    subtitle_mode: str = "soft"
    engine_type: EngineType = EngineType.SILICONFLOW
    status: PipelineStatus = PipelineStatus.PENDING
    segments: List[Segment] = field(default_factory=list)
    merged_audio_path: str = ""
    output_video_path: str = ""
    subtitle_path: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    config_snapshot: Dict[str, Any] = field(default_factory=dict)
    working_dir: str = ""
    task_id: str = ""
    output_dir: str = ""  # 输出目录，空=原视频目录
    tts_voice: str = "zh-CN-XiaoxiaoNeural"  # TTS 配音音色

    def __post_init__(self) -> None:
        """初始化后生成任务 ID。"""
        if not self.task_id:
            self.task_id = uuid.uuid4().hex[:12]

    def add_segment(self, segment: Segment) -> None:
        """添加一个句段到列表。"""
        self.segments.append(segment)

    def get_segment(self, index: int) -> Optional[Segment]:
        """按序号获取句段。"""
        for seg in self.segments:
            if seg.index == index:
                return seg
        return None

    def to_dict(self) -> Dict[str, Any]:
        """将 PipelineContext 序列化为字典。"""
        return {
            "task_id": self.task_id,
            "video_path": self.video_path,
            "audio_path": self.audio_path,
            "duration": self.duration,
            "source_lang": self.source_lang,
            "target_lang": self.target_lang,
            "output_format": self.output_format,
            "subtitle_mode": self.subtitle_mode,
            "engine_type": self.engine_type.value,
            "status": self.status.value,
            "segments": [seg.to_dict() for seg in self.segments],
            "merged_audio_path": self.merged_audio_path,
            "output_video_path": self.output_video_path,
            "subtitle_path": self.subtitle_path,
            "metadata": copy.deepcopy(self.metadata),
            "working_dir": self.working_dir,
        }

    def __repr__(self) -> str:
        return (
            f"PipelineContext(task={self.task_id}, "
            f"video={self.video_path}, "
            f"segments={len(self.segments)}, "
            f"status={self.status.value})"
        )
