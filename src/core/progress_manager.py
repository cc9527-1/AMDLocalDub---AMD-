"""VideoDub 进度管理器（观察者模式）。

负责追踪 Pipeline 各阶段的处理进度，
提供实时进度回调、预估剩余时间、阶段状态查询等功能。
"""

from __future__ import annotations

import datetime
import time
from typing import Any, Callable, Dict, List, Optional

from src.core.data_models import PipelineStage


# 进度回调函数类型签名
ProgressCallback = Callable[[PipelineStage, float, str], None]


class ProgressManager:
    """进度管理器。

    使用回调模式，每个阶段上报 (stage, percent, message)。
    Gradio UI 通过轮询 get_summary() 获取最新进度。

    Attributes:
        _callback: 外部回调函数
        _stage_progress: 各阶段最新进度字典
        _stage_start: 当前阶段开始时间
        _pipeline_start: 整个 Pipeline 开始时间
        _weight: 各阶段权重（用于整体进度计算）
    """

    # 各阶段默认权重（总和为 100）
    DEFAULT_WEIGHTS: Dict[PipelineStage, float] = {
        PipelineStage.VIDEO_LOAD: 5.0,
        PipelineStage.ASR: 30.0,
        PipelineStage.SENTENCE_SPLIT: 5.0,
        PipelineStage.TRANSLATE: 30.0,
        PipelineStage.AUDIO_SEGMENT: 5.0,
        PipelineStage.TTS: 15.0,
        PipelineStage.AUDIO_MERGE: 5.0,
        PipelineStage.VIDEO_COMPOSE: 5.0,
    }

    def __init__(
        self, callback: Optional[ProgressCallback] = None
    ) -> None:
        """初始化进度管理器。

        Args:
            callback: 外部进度回调函数，签名见 ProgressCallback
        """
        self._callback: Optional[ProgressCallback] = callback
        self._stage_progress: Dict[str, Dict[str, Any]] = {}
        self._stage_start: Optional[float] = None
        self._pipeline_start: Optional[float] = None
        self._weights: Dict[PipelineStage, float] = dict(self.DEFAULT_WEIGHTS)
        self._last_update_time: float = 0.0
        self._last_stage: Optional[PipelineStage] = None

        # 初始化各阶段进度
        for stage in PipelineStage:
            self._stage_progress[stage.value] = {
                "percent": 0.0,
                "message": "等待中",
                "status": "pending",
                "start_time": None,
                "end_time": None,
            }

    def set_callback(self, callback: ProgressCallback) -> None:
        """设置进度回调函数。

        Args:
            callback: 进度回调函数
        """
        self._callback = callback

    def update(
        self, stage: PipelineStage, percent: float, message: str
    ) -> None:
        """更新指定阶段的进度。

        Args:
            stage: 当前执行阶段
            percent: 进度百分比（0.0 ~ 100.0）
            message: 人类可读的状态描述
        """
        # 阶段切换时记录开始时间
        if self._last_stage != stage:
            if self._stage_progress[stage.value]["status"] == "pending":
                self._stage_progress[stage.value]["start_time"] = time.time()
                self._stage_progress[stage.value]["status"] = "running"
            self._stage_start = time.time()
            self._last_stage = stage

        # Pipeline 首次启动
        if self._pipeline_start is None:
            self._pipeline_start = time.time()

        # 更新阶段进度
        self._stage_progress[stage.value]["percent"] = min(percent, 100.0)
        self._stage_progress[stage.value]["message"] = message
        self._last_update_time = time.time()

        # 调用外部回调
        if self._callback is not None:
            try:
                self._callback(stage, percent, message)
            except Exception:
                pass  # 回调失败不应影响主流程

    def get_summary(self) -> Dict[str, Any]:
        """获取所有阶段的进度概览。

        Returns:
            包含各阶段进度及整体状态的字典
        """
        overall = self._calculate_overall_progress()
        return {
            "overall_percent": overall,
            "overall_message": self._get_overall_message(),
            "stages": {
                stage.value: {
                    "percent": self._stage_progress[stage.value]["percent"],
                    "message": self._stage_progress[stage.value]["message"],
                    "status": self._stage_progress[stage.value]["status"],
                }
                for stage in PipelineStage
            },
            "elapsed_time": self._get_elapsed_time(),
            "estimated_remaining": self.estimate_remaining(),
        }

    def get_stage_progress(self, stage: PipelineStage) -> Dict[str, Any]:
        """获取指定阶段的进度详情。

        Args:
            stage: 要查询的阶段

        Returns:
            该阶段的进度字典
        """
        return dict(self._stage_progress[stage.value])

    def estimate_remaining(self) -> float:
        """估算剩余处理时间。

        基于已完成阶段的实际耗时和权重计算。

        Returns:
            预估剩余秒数。如果无法估算则返回 -1。
        """
        if self._pipeline_start is None:
            return -1.0

        elapsed = time.time() - self._pipeline_start
        overall = self._calculate_overall_progress()

        if overall <= 0:
            return -1.0

        total_estimated = elapsed / (overall / 100.0)
        remaining = total_estimated - elapsed
        return max(remaining, 0.0)

    def reset(self) -> None:
        """重置所有进度状态。"""
        self._stage_start = None
        self._pipeline_start = None
        self._last_stage = None
        self._last_update_time = 0.0

        for stage in PipelineStage:
            self._stage_progress[stage.value] = {
                "percent": 0.0,
                "message": "等待中",
                "status": "pending",
                "start_time": None,
                "end_time": None,
            }

    def mark_stage_complete(self, stage: PipelineStage) -> None:
        """标记指定阶段为已完成。

        Args:
            stage: 完成的阶段
        """
        self._stage_progress[stage.value]["percent"] = 100.0
        self._stage_progress[stage.value]["message"] = "已完成"
        self._stage_progress[stage.value]["status"] = "completed"
        self._stage_progress[stage.value]["end_time"] = time.time()

        if self._callback is not None:
            try:
                self._callback(stage, 100.0, "已完成")
            except Exception:
                pass

    def mark_stage_failed(self, stage: PipelineStage, error: str) -> None:
        """标记指定阶段为失败。

        Args:
            stage: 失败的阶段
            error: 错误描述
        """
        self._stage_progress[stage.value]["status"] = "failed"
        self._stage_progress[stage.value]["message"] = f"失败: {error}"
        self._stage_progress[stage.value]["end_time"] = time.time()

        if self._callback is not None:
            try:
                self._callback(stage, -1.0, f"失败: {error}")
            except Exception:
                pass

    def _calculate_overall_progress(self) -> float:
        """计算整体进度百分比。

        基于各阶段进度与权重的加权平均。

        Returns:
            整体进度百分比（0.0 ~ 100.0）
        """
        total_weight = sum(self._weights.values())
        if total_weight <= 0:
            return 0.0

        weighted_sum = 0.0
        for stage in PipelineStage:
            stage_data = self._stage_progress[stage.value]
            weight = self._weights.get(stage, 0)
            weighted_sum += stage_data["percent"] * weight

        return min(weighted_sum / total_weight, 100.0)

    def _get_overall_message(self) -> str:
        """生成整体状态描述。"""
        completed = sum(
            1 for s in PipelineStage
            if self._stage_progress[s.value]["status"] == "completed"
        )
        total = len(PipelineStage)

        if completed == total:
            return "全部完成"
        elif self._last_stage is not None:
            stage_info = self._stage_progress[self._last_stage.value]
            return f"进行中: {self._last_stage.display_name} - {stage_info['message']}"
        else:
            return "等待启动"

    def _get_elapsed_time(self) -> float:
        """获取已耗时的秒数。

        Returns:
            已耗时秒数
        """
        if self._pipeline_start is None:
            return 0.0
        return time.time() - self._pipeline_start

    def set_weights(self, weights: Dict[PipelineStage, float]) -> None:
        """自定义各阶段权重。

        Args:
            weights: 阶段到权重的映射字典
        """
        self._weights.update(weights)

        # 标准化权重使总和为 100
        total = sum(self._weights.values())
        if total > 0:
            for stage in self._weights:
                self._weights[stage] = (self._weights[stage] / total) * 100.0
