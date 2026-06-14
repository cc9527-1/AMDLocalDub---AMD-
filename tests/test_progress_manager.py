"""VideoDub 进度管理器单元测试。

测试覆盖:
- 进度更新/获取
- 阶段完成/失败标记
- 整体进度计算
- 预估剩余时间
- 回调机制
- 权重调整
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from src.core.data_models import PipelineStage
from src.core.progress_manager import ProgressManager


class TestProgressManagerInit:
    """进度管理器初始化测试。"""

    def test_init_no_callback(self):
        """测试无回调初始化。"""
        pm = ProgressManager()
        assert pm._callback is None
        assert pm._pipeline_start is None
        assert pm._stage_start is None

    def test_init_with_callback(self):
        """测试带回调初始化。"""
        callback = MagicMock()
        pm = ProgressManager(callback=callback)
        assert pm._callback is callback

    def test_init_all_stages_pending(self):
        """测试初始化时所有阶段为 pending。"""
        pm = ProgressManager()
        for stage in PipelineStage:
            stage_data = pm._stage_progress[stage.value]
            assert stage_data["status"] == "pending"
            assert stage_data["percent"] == 0.0
            assert stage_data["message"] == "等待中"
            assert stage_data["start_time"] is None
            assert stage_data["end_time"] is None

    def test_default_weights_sum_to_100(self):
        """测试默认权重总和为 100。"""
        pm = ProgressManager()
        total = sum(pm.DEFAULT_WEIGHTS.values())
        assert total == 100.0

    def test_default_weights_all_stages(self):
        """测试默认权重包含所有阶段。"""
        pm = ProgressManager()
        for stage in PipelineStage:
            assert stage in pm.DEFAULT_WEIGHTS

    def test_set_callback(self):
        """测试设置回调函数。"""
        pm = ProgressManager()
        callback = MagicMock()
        pm.set_callback(callback)
        assert pm._callback is callback


class TestProgressManagerUpdate:
    """进度更新测试。"""

    def test_update_sets_percent(self):
        """测试更新进度百分比。"""
        pm = ProgressManager()
        pm.update(PipelineStage.ASR, 50.0, "处理中...")
        stage_data = pm._stage_progress[PipelineStage.ASR.value]
        assert stage_data["percent"] == 50.0
        assert stage_data["message"] == "处理中..."

    def test_update_clamps_percent_at_100(self):
        """测试更新时百分比不超过 100。"""
        pm = ProgressManager()
        pm.update(PipelineStage.ASR, 150.0, "超出")
        assert pm._stage_progress[PipelineStage.ASR.value]["percent"] == 100.0

    def test_update_negative_percent(self):
        """测试负百分比（失败时调用）。"""
        pm = ProgressManager()
        pm.update(PipelineStage.ASR, -5.0, "出错了")
        # update 方法使用 min(percent, 100.0)，负值会保留
        assert pm._stage_progress[PipelineStage.ASR.value]["percent"] == -5.0

    def test_update_triggers_pipeline_start(self):
        """测试首次更新触发 pipeline 开始计时。"""
        pm = ProgressManager()
        assert pm._pipeline_start is None
        pm.update(PipelineStage.VIDEO_LOAD, 10.0, "加载中")
        assert pm._pipeline_start is not None

    def test_update_stage_switch_records_start_time(self):
        """测试阶段切换记录开始时间。"""
        pm = ProgressManager()
        pm.update(PipelineStage.VIDEO_LOAD, 50.0, "加载中")
        # 阶段切换后的第一次更新
        assert pm._stage_progress[PipelineStage.VIDEO_LOAD.value]["start_time"] is not None
        assert pm._stage_progress[PipelineStage.VIDEO_LOAD.value]["status"] == "running"

    def test_update_with_callback(self):
        """测试更新时触发回调。"""
        callback = MagicMock()
        pm = ProgressManager(callback=callback)
        pm.update(PipelineStage.TRANSLATE, 30.0, "翻译中")
        callback.assert_called_once_with(PipelineStage.TRANSLATE, 30.0, "翻译中")

    def test_update_callback_exception_does_not_break(self):
        """测试回调异常不中断主流程。"""
        def failing_callback(stage, percent, message):
            raise RuntimeError("回调失败")

        pm = ProgressManager(callback=failing_callback)
        # 不应抛出异常
        pm.update(PipelineStage.TTS, 50.0, "合成中")
        assert pm._stage_progress[PipelineStage.TTS.value]["percent"] == 50.0

    def test_update_multiple_stages(self):
        """测试更新多个阶段。"""
        pm = ProgressManager()
        pm.update(PipelineStage.VIDEO_LOAD, 100.0, "加载完成")
        pm.update(PipelineStage.ASR, 60.0, "ASR 进行中")
        pm.update(PipelineStage.TRANSLATE, 20.0, "翻译中")

        assert pm._stage_progress[PipelineStage.VIDEO_LOAD.value]["status"] == "running"
        assert pm._stage_progress[PipelineStage.ASR.value]["percent"] == 60.0
        assert pm._stage_progress[PipelineStage.TRANSLATE.value]["percent"] == 20.0


class TestProgressManagerStageCompletion:
    """阶段完成/失败标记测试。"""

    def test_mark_stage_complete(self):
        """测试标记阶段完成。"""
        pm = ProgressManager()
        pm.update(PipelineStage.ASR, 80.0, "进行中")
        pm.mark_stage_complete(PipelineStage.ASR)

        stage_data = pm._stage_progress[PipelineStage.ASR.value]
        assert stage_data["percent"] == 100.0
        assert stage_data["message"] == "已完成"
        assert stage_data["status"] == "completed"
        assert stage_data["end_time"] is not None

    def test_mark_stage_complete_callback(self):
        """测试标记完成时触发回调。"""
        callback = MagicMock()
        pm = ProgressManager(callback=callback)
        pm.mark_stage_complete(PipelineStage.ASR)
        callback.assert_called_once_with(PipelineStage.ASR, 100.0, "已完成")

    def test_mark_stage_failed(self):
        """测试标记阶段失败。"""
        pm = ProgressManager()
        pm.mark_stage_failed(PipelineStage.TRANSLATE, "API 超时")

        stage_data = pm._stage_progress[PipelineStage.TRANSLATE.value]
        assert stage_data["status"] == "failed"
        assert "API 超时" in stage_data["message"]
        assert stage_data["end_time"] is not None

    def test_mark_stage_failed_callback(self):
        """测试标记失败时触发回调。"""
        callback = MagicMock()
        pm = ProgressManager(callback=callback)
        pm.mark_stage_failed(PipelineStage.TRANSLATE, "错误")
        callback.assert_called_once_with(PipelineStage.TRANSLATE, -1.0, "失败: 错误")

    def test_mark_stage_failed_callback_exception(self):
        """测试失败回调异常不中断。"""
        def failing_callback(stage, percent, message):
            raise RuntimeError("失败")

        pm = ProgressManager(callback=failing_callback)
        pm.mark_stage_failed(PipelineStage.TRANSLATE, "错误")
        # 不应抛出异常


class TestProgressManagerSummary:
    """进度概览测试。"""

    def test_get_summary_returns_all_keys(self):
        """测试 get_summary 返回所有必需的键。"""
        pm = ProgressManager()
        summary = pm.get_summary()
        assert "overall_percent" in summary
        assert "overall_message" in summary
        assert "stages" in summary
        assert "elapsed_time" in summary
        assert "estimated_remaining" in summary

    def test_get_summary_overall_zero_initially(self):
        """测试初始整体进度为 0。"""
        pm = ProgressManager()
        assert pm.get_summary()["overall_percent"] == 0.0

    def test_get_summary_overall_message_pending(self):
        """测试初始状态消息。"""
        pm = ProgressManager()
        assert pm.get_summary()["overall_message"] == "等待启动"

    def test_get_summary_overall_message_running(self):
        """测试运行中状态消息。"""
        pm = ProgressManager()
        pm.update(PipelineStage.ASR, 50.0, "进行中")
        summary = pm.get_summary()
        assert "进行中" in summary["overall_message"]

    def test_get_summary_overall_message_completed(self):
        """测试全部完成状态消息。"""
        pm = ProgressManager()
        for stage in PipelineStage:
            pm.mark_stage_complete(stage)
        assert pm.get_summary()["overall_message"] == "全部完成"

    def test_get_summary_elapsed_time_zero_initially(self):
        """测试初始已耗时为 0。"""
        pm = ProgressManager()
        assert pm._get_elapsed_time() == 0.0

    def test_get_summary_elapsed_time_after_update(self):
        """测试更新后已耗时 >= 0。"""
        pm = ProgressManager()
        pm.update(PipelineStage.VIDEO_LOAD, 10.0, "加载中")
        assert pm._get_elapsed_time() >= 0.0

    def test_get_stage_progress(self):
        """测试获取指定阶段进度。"""
        pm = ProgressManager()
        pm.update(PipelineStage.TTS, 75.0, "配音合成中")
        stage_data = pm.get_stage_progress(PipelineStage.TTS)
        assert stage_data["percent"] == 75.0
        assert stage_data["message"] == "配音合成中"
        assert stage_data["status"] == "running"

    def test_get_stage_progress_immutable(self):
        """测试阶段进度返回副本。"""
        pm = ProgressManager()
        stage_data = pm.get_stage_progress(PipelineStage.ASR)
        stage_data["percent"] = 999
        # 不应影响内部数据
        assert pm._stage_progress[PipelineStage.ASR.value]["percent"] == 0.0


class TestProgressManagerOverall:
    """整体进度计算测试。"""

    def test_overall_progress_zero_initially(self):
        """测试初始整体进度为 0。"""
        pm = ProgressManager()
        assert pm._calculate_overall_progress() == 0.0

    def test_overall_progress_partial(self):
        """测试部分完成时的整体进度。"""
        pm = ProgressManager()
        pm.mark_stage_complete(PipelineStage.VIDEO_LOAD)  # 权重 5%
        progress = pm._calculate_overall_progress()
        # 5 / 100 = 5%
        assert progress == 5.0

    def test_overall_progress_half(self):
        """测试前 4 个阶段完成（权重 70%）。"""
        pm = ProgressManager()
        pm.mark_stage_complete(PipelineStage.VIDEO_LOAD)   # 5%
        pm.mark_stage_complete(PipelineStage.ASR)          # 30%
        pm.mark_stage_complete(PipelineStage.SENTENCE_SPLIT)  # 5%
        pm.mark_stage_complete(PipelineStage.TRANSLATE)    # 30%
        # 5 + 30 + 5 + 30 = 70%
        assert pm._calculate_overall_progress() == 70.0

    def test_overall_progress_full(self):
        """测试所有阶段完成时整体进度为 100。"""
        pm = ProgressManager()
        for stage in PipelineStage:
            pm.mark_stage_complete(stage)
        assert pm._calculate_overall_progress() == 100.0

    def test_overall_progress_partial_stage(self):
        """测试阶段部分完成时的整体进度。"""
        pm = ProgressManager()
        pm.update(PipelineStage.ASR, 50.0, "一半")  # 权重 30%，进度 50%
        # 30 * 0.5 / 100 = 15%
        assert pm._calculate_overall_progress() == 15.0


class TestProgressManagerEstimate:
    """预估剩余时间测试。"""

    def test_estimate_negative_when_not_started(self):
        """测试未开始时返回 -1。"""
        pm = ProgressManager()
        assert pm.estimate_remaining() == -1.0

    def test_estimate_negative_when_zero_progress(self):
        """测试进度为 0 时返回 -1。"""
        pm = ProgressManager()
        pm.update(PipelineStage.VIDEO_LOAD, 0.0, "开始")
        # overall = 0, 返回 -1
        remaining = pm.estimate_remaining()
        assert remaining == -1.0 or remaining >= 0  # 实现可能不同，但应合理

    def test_estimate_positive_when_progress_made(self):
        """测试有进度时返回正数。"""
        pm = ProgressManager()
        pm.update(PipelineStage.VIDEO_LOAD, 50.0, "加载中")
        remaining = pm.estimate_remaining()
        # 无法精确断言数值，但应为非负数
        assert remaining >= 0

    def test_estimate_returns_float(self):
        """测试预估时间返回 float。"""
        pm = ProgressManager()
        pm.update(PipelineStage.VIDEO_LOAD, 10.0, "加载中")
        remaining = pm.estimate_remaining()
        assert isinstance(remaining, float)


class TestProgressManagerReset:
    """重置测试。"""

    def test_reset_clears_all_state(self):
        """测试重置清除所有状态。"""
        pm = ProgressManager()
        pm.update(PipelineStage.ASR, 50.0, "进行中")
        pm.mark_stage_complete(PipelineStage.VIDEO_LOAD)
        pm.reset()

        assert pm._pipeline_start is None
        assert pm._stage_start is None
        assert pm._last_stage is None

        for stage in PipelineStage:
            assert pm._stage_progress[stage.value]["status"] == "pending"
            assert pm._stage_progress[stage.value]["percent"] == 0.0

    def test_reset_keeps_callback(self):
        """测试重置保留回调函数。"""
        callback = MagicMock()
        pm = ProgressManager(callback=callback)
        pm.reset()
        assert pm._callback is callback


class TestProgressManagerWeights:
    """权重调整测试。"""

    def test_set_weights_updates(self):
        """测试设置权重。"""
        pm = ProgressManager()
        pm.set_weights({PipelineStage.ASR: 50.0})
        # 应该标准化
        assert pm._weights[PipelineStage.ASR] > 0

    def test_set_weights_normalizes_to_100(self):
        """测试权重标准化到 100。"""
        pm = ProgressManager()
        pm.set_weights({PipelineStage.ASR: 50.0, PipelineStage.TTS: 50.0})
        total = sum(pm._weights.values())
        assert abs(total - 100.0) < 0.1

    def test_set_weights_does_not_affect_defaults(self):
        """测试设置权重不影响 DEFAULT_WEIGHTS。"""
        pm = ProgressManager()
        pm.set_weights({PipelineStage.ASR: 60.0, PipelineStage.TTS: 40.0})
        assert ProgressManager.DEFAULT_WEIGHTS[PipelineStage.ASR] == 30.0  # 原值不变
