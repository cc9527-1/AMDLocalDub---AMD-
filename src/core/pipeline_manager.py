"""VideoDub 管线调度器。

负责编排 8 个处理阶段的执行顺序，
管理异常处理、取消支持、状态查询。
在后台线程中运行以避免阻塞 Gradio UI。
"""

from __future__ import annotations

import os
import threading
import time
import traceback
from typing import Any, Callable, Dict, Optional

from src.core.config_manager import ConfigManager
from src.core.data_models import (
    PipelineContext,
    PipelineStage,
    PipelineStatus,
    Segment,
    SegmentStatus,
    EngineType,
    VideoDubError,
    ASRError,
    TranslationError,
    TTSError,
    VideoProcessingError,
)
from src.core.logger import Logger
from src.core.progress_manager import ProgressManager, ProgressCallback

# 延迟导入（在 run_stage 中按需导入，避免循环依赖）


class PipelineManager:
    """管线调度器。

    编排 VideoDub 全部 8 个处理阶段的顺序执行。
    支持异步执行（后台线程）、取消和状态查询。

    Attributes:
        _config: 配置管理器
        _progress: 进度管理器
        _logger: 日志记录器
        _worker: 后台工作线程
        _cancelled: 取消标志
        _current_context: 当前正在处理的上下文
    """

    def __init__(
        self,
        config: ConfigManager,
        progress: ProgressManager,
        logger: Logger,
    ) -> None:
        """初始化管线调度器。

        Args:
            config: 配置管理器实例
            progress: 进度管理器实例
            logger: 日志记录器实例
        """
        self._config: ConfigManager = config
        self._progress: ProgressManager = progress
        self._logger: Logger = logger
        self._worker: Optional[threading.Thread] = None
        self._cancelled: bool = False
        self._current_context: Optional[PipelineContext] = None
        self._completion_callback: Optional[Callable[[PipelineContext], None]] = None

    def set_completion_callback(
        self, callback: Callable[[PipelineContext], None]
    ) -> None:
        """设置完成后回调。

        Args:
            callback: 完成后回调函数，接收 PipelineContext 参数
        """
        self._completion_callback = callback

    def execute(self, context: PipelineContext) -> PipelineContext:
        """启动 Pipeline 处理（在当前线程同步执行）。

        Args:
            context: 已初始化的 PipelineContext

        Returns:
            处理完成后的 PipelineContext
        """
        self._cancelled = False
        self._current_context = context
        context.status = PipelineStatus.RUNNING

        self._logger.info(
            f"Pipeline 启动: {context.video_path}",
            module="PipelineManager",
        )
        self._progress.reset()

        stages_in_order = [
            PipelineStage.VIDEO_LOAD,
            PipelineStage.ASR,
            PipelineStage.SENTENCE_SPLIT,
            PipelineStage.TRANSLATE,
            PipelineStage.AUDIO_SEGMENT,
            PipelineStage.TTS,
            PipelineStage.AUDIO_MERGE,
            PipelineStage.VIDEO_COMPOSE,
        ]

        try:
            for stage in stages_in_order:
                if self._cancelled:
                    context.status = PipelineStatus.CANCELLED
                    self._logger.warning(
                        "Pipeline 被用户取消", module="PipelineManager"
                    )
                    break

                self._run_stage(stage, context)

                if context.status == PipelineStatus.FAILED:
                    break

            if context.status == PipelineStatus.RUNNING:
                context.status = PipelineStatus.COMPLETED
                self._logger.info(
                    "Pipeline 全部完成",
                    module="PipelineManager",
                )

        except Exception as e:
            context.status = PipelineStatus.FAILED
            self._logger.error(
                f"Pipeline 未预期异常: {e}",
                module="PipelineManager",
                exc_info=True,
            )

        self._current_context = context

        if self._completion_callback:
            try:
                self._completion_callback(context)
            except Exception as e:
                self._logger.error(
                    f"完成回调执行失败: {e}",
                    module="PipelineManager",
                )

        return context

    def execute_async(self, context: PipelineContext) -> None:
        """在后台线程中异步启动 Pipeline 处理。

        Args:
            context: 已初始化的 PipelineContext
        """
        if self._worker and self._worker.is_alive():
            self._logger.warning(
                "上一个任务仍在运行，请等待完成或取消",
                module="PipelineManager",
            )
            return

        self._worker = threading.Thread(
            target=self.execute,
            args=(context,),
            daemon=True,
        )
        self._worker.start()

        self._logger.info(
            f"后台线程启动: task_id={context.task_id}",
            module="PipelineManager",
        )

    def cancel(self) -> None:
        """请求取消当前正在运行的 Pipeline。"""
        self._cancelled = True
        if self._current_context:
            self._current_context.status = PipelineStatus.CANCELLED
        self._logger.warning("用户请求取消 Pipeline", module="PipelineManager")

    def get_status(self) -> Dict[str, Any]:
        """获取当前 Pipeline 状态和进度。

        Returns:
            状态汇总字典
        """
        progress_summary = self._progress.get_summary()

        status_info: Dict[str, Any] = {
            "pipeline_status": (
                self._current_context.status.value
                if self._current_context
                else "idle"
            ),
            "task_id": (
                self._current_context.task_id
                if self._current_context
                else ""
            ),
            "is_running": (
                self._worker is not None and self._worker.is_alive()
            ),
            "progress": progress_summary,
        }
        return status_info

    def is_running(self) -> bool:
        """检查 Pipeline 是否正在运行。

        Returns:
            是否正在运行
        """
        return (
            self._worker is not None
            and self._worker.is_alive()
            and not self._cancelled
        )

    def _run_stage(self, stage: PipelineStage, context: PipelineContext) -> None:
        """执行单个处理阶段。

        Args:
            stage: 要执行的阶段
            context: Pipeline 上下文
        """
        self._logger.info(
            f"阶段开始: {stage.display_name}",
            module="PipelineManager",
        )

        try:
            if stage == PipelineStage.VIDEO_LOAD:
                self._stage_video_load(context)
            elif stage == PipelineStage.ASR:
                self._stage_asr(context)
            elif stage == PipelineStage.SENTENCE_SPLIT:
                self._stage_split(context)
            elif stage == PipelineStage.TRANSLATE:
                self._stage_translate(context)
            elif stage == PipelineStage.AUDIO_SEGMENT:
                self._stage_audio_segment(context)
            elif stage == PipelineStage.TTS:
                self._stage_tts(context)
            elif stage == PipelineStage.AUDIO_MERGE:
                self._stage_audio_merge(context)
            elif stage == PipelineStage.VIDEO_COMPOSE:
                self._stage_video_compose(context)

            self._progress.mark_stage_complete(stage)
            self._logger.info(
                f"阶段完成: {stage.display_name}",
                module="PipelineManager",
            )

        except VideoDubError as e:
            context.status = PipelineStatus.FAILED
            self._progress.mark_stage_failed(stage, str(e))
            self._logger.error(
                f"阶段失败 [{stage.display_name}]: {e}",
                module="PipelineManager",
            )
        except Exception as e:
            context.status = PipelineStatus.FAILED
            self._progress.mark_stage_failed(stage, str(e))
            self._logger.error(
                f"阶段未预期异常 [{stage.display_name}]: {e}",
                module="PipelineManager",
                exc_info=True,
            )

    def _stage_video_load(self, ctx: PipelineContext) -> None:
        """阶段 1: 视频加载。"""
        from src.video.video_loader import VideoLoader

        self._progress.update(
            PipelineStage.VIDEO_LOAD, 10.0, "正在校验视频格式..."
        )
        VideoLoader.validate_format(ctx.video_path)

        self._progress.update(
            PipelineStage.VIDEO_LOAD, 30.0, "正在提取视频元信息..."
        )
        media_info = VideoLoader.get_media_info(ctx.video_path)
        ctx.metadata = media_info
        ctx.duration = media_info.get("duration", 0.0)

        self._progress.update(
            PipelineStage.VIDEO_LOAD, 60.0, "正在提取音频流..."
        )
        audio_dir = os.path.join(ctx.working_dir, "audio_raw.wav")
        ctx.audio_path = VideoLoader.extract_audio(ctx.video_path, audio_dir)

        self._progress.update(
            PipelineStage.VIDEO_LOAD, 100.0, "视频加载完成"
        )

    def _stage_asr(self, ctx: PipelineContext) -> None:
        """阶段 2: 语音识别。"""
        from src.asr.asr_engine import ASREngine

        asr_config = self._config.get_asr_config()
        engine = ASREngine(
            model_path=asr_config.get("model_path", "models/ggml-large-v3.bin"),
            backend=asr_config.get("backend", "vulkan"),
            gpu_device=asr_config.get("gpu_device", 0),
        )

        self._progress.update(PipelineStage.ASR, 5.0, "正在初始化 ASR 引擎...")
        engine.initialize()

        def asr_callback(percent: float, message: str) -> None:
            self._progress.update(PipelineStage.ASR, percent, message)

        self._progress.update(PipelineStage.ASR, 10.0, "正在进行语音识别...")
        raw_segments = engine.transcribe(ctx.audio_path, progress_callback=asr_callback)

        # 将原始 ASR 结果转为 Segment
        for i, seg_data in enumerate(raw_segments, 1):
            segment = Segment(
                index=i,
                original_text=seg_data.get("text", ""),
                start_time=seg_data.get("start", 0.0),
                end_time=seg_data.get("end", 0.0),
            )
            ctx.add_segment(segment)

        engine.shutdown()
        self._progress.update(
            PipelineStage.ASR,
            100.0,
            f"语音识别完成，检测到 {len(ctx.segments)} 个片段",
        )

    def _stage_split(self, ctx: PipelineContext) -> None:
        """阶段 3: 句子拆分。"""
        from src.splitter.sentence_splitter import SentenceSplitter

        splitter_config = self._config.get_splitter_config()
        splitter = SentenceSplitter(
            max_segment_duration=splitter_config.get("max_segment_duration", 10.0)
        )

        self._progress.update(
            PipelineStage.SENTENCE_SPLIT, 20.0, "正在智能拆分句子..."
        )
        ctx.segments = splitter.split(ctx.segments)

        self._progress.update(
            PipelineStage.SENTENCE_SPLIT, 60.0, "正在合并短句..."
        )
        min_duration = splitter_config.get("min_segment_duration", 0.5)
        ctx.segments = splitter.merge_short_segments(ctx.segments, min_duration)

        self._progress.update(
            PipelineStage.SENTENCE_SPLIT,
            100.0,
            f"句子拆分完成，共 {len(ctx.segments)} 句",
        )

    def _stage_translate(self, ctx: PipelineContext) -> None:
        """阶段 4: 翻译。"""
        from src.translator.translation_engine import TranslationEngineFactory

        factory = TranslationEngineFactory()
        engine_config = self._config.get_engine_config(ctx.engine_type)
        engine = factory.create_engine(ctx.engine_type, engine_config)

        self._progress.update(
            PipelineStage.TRANSLATE, 5.0, f"正在使用 {ctx.engine_type.value} 引擎翻译..."
        )

        def translate_callback(percent: float, message: str) -> None:
            self._progress.update(PipelineStage.TRANSLATE, percent, message)

        ctx.segments = engine.batch_translate(
            ctx.segments,
            source_lang=ctx.source_lang,
            target_lang=ctx.target_lang,
            progress_callback=translate_callback,
        )

        self._progress.update(
            PipelineStage.TRANSLATE, 100.0, "翻译完成"
        )

        # 生成 SRT 字幕文件（含翻译文本）—— 放在工作目录中
        srt_path = os.path.join(ctx.working_dir, "subtitles.srt")
        try:
            with open(srt_path, "w", encoding="utf-8") as f:
                for idx, seg in enumerate(ctx.segments, 1):
                    text = seg.translated_text or seg.original_text
                    if not text:
                        continue
                    # SRT 时间戳格式: HH:MM:SS,mmm
                    start_srt = self._format_srt_time(seg.start_time)
                    end_srt = self._format_srt_time(seg.end_time)
                    f.write(f"{idx}\n{start_srt} --> {end_srt}\n{text}\n\n")
            ctx.subtitle_path = srt_path
            self._logger.info(
                f"字幕文件已生成: {srt_path} ({len(ctx.segments)} 条)",
                module="PipelineManager",
            )
        except OSError as e:
            self._logger.warning(
                f"字幕文件生成失败: {e}", module="PipelineManager"
            )

    def _stage_audio_segment(self, ctx: PipelineContext) -> None:
        """阶段 5: 音频分段。"""
        from src.audio.audio_segmenter import AudioSegmenter

        self._progress.update(
            PipelineStage.AUDIO_SEGMENT, 10.0, "正在切分原始音频..."
        )
        seg_dir = os.path.join(ctx.working_dir, "segments")
        os.makedirs(seg_dir, exist_ok=True)
        ctx.segments = AudioSegmenter.segment_audio(
            ctx.audio_path, ctx.segments, seg_dir
        )

        self._progress.update(
            PipelineStage.AUDIO_SEGMENT, 100.0, "音频分段完成"
        )

    def _stage_tts(self, ctx: PipelineContext) -> None:
        """阶段 6: TTS 配音。"""
        from src.tts.tts_engine import TTSEngine

        tts_config = self._config.get_tts_config()
        # 优先使用用户在 UI 中选择的音色，其次按目标语言自动选择
        voice = ctx.tts_voice or tts_config.get("voice_zh", "zh-CN-XiaoxiaoNeural")

        tts_engine = TTSEngine(
            voice=voice,
            rate=tts_config.get("rate", "+0%"),
        )

        self._progress.update(
            PipelineStage.TTS, 5.0, "正在生成配音..."
        )
        tts_dir = os.path.join(ctx.working_dir, "tts")
        os.makedirs(tts_dir, exist_ok=True)

        def tts_callback(percent: float, message: str) -> None:
            self._progress.update(PipelineStage.TTS, percent, message)

        ctx.segments = tts_engine.batch_synthesize(
            ctx.segments, tts_dir, progress_callback=tts_callback
        )

        self._progress.update(
            PipelineStage.TTS, 100.0, "配音合成完成"
        )

        # TTS 完成后：将每段配音按原时间戳拉伸/压缩对齐
        self._align_tts_audio(ctx)

    def _align_tts_audio(self, ctx: PipelineContext) -> None:
        """将 TTS 配音音频按原字幕时间戳拉伸/压缩对齐。

        TTS 配音的语速与原视频不同，使用 ffmpeg atempo 滤镜
        将每段 TTS 音频拉伸/压缩到原始时间窗口的时长，
        使配音与字幕时间戳完全同步。
        """
        import subprocess
        import wave

        for seg in ctx.segments:
            if not seg.tts_audio_path or not os.path.isfile(seg.tts_audio_path):
                continue

            orig_duration = seg.end_time - seg.start_time
            if orig_duration <= 0:
                continue

            # 获取 TTS 音频实际时长
            try:
                with wave.open(seg.tts_audio_path, "r") as wf:
                    tts_frames = wf.getnframes()
                    tts_rate = wf.getframerate()
                    tts_duration = tts_frames / tts_rate if tts_rate > 0 else orig_duration
            except Exception:
                tts_duration = orig_duration

            if tts_duration <= 0:
                continue

            # 计算拉伸/压缩比
            tempo = tts_duration / orig_duration

            # atempo 只支持 0.5~2.0，超出范围则链式组合
            if 0.5 <= tempo <= 2.0:
                atempo_filter = f"atempo={tempo:.4f}"
            else:
                n = max(2, int(abs(tempo) // 0.5 + 1))
                step = pow(tempo, 1.0 / n)
                step = max(0.5, min(2.0, step))
                atempo_filter = ",".join([f"atempo={step:.4f}"] * n)

            stretched_path = seg.tts_audio_path.replace(".wav", "_stretched.wav")
            try:
                result = subprocess.run(
                    ["ffmpeg", "-y", "-i", seg.tts_audio_path,
                     "-af", atempo_filter,
                     "-c:a", "pcm_s16le", "-ar", "16000", "-ac", "1",
                     stretched_path],
                    capture_output=True, text=True, timeout=60,
                )
                if result.returncode == 0 and os.path.isfile(stretched_path):
                    seg.tts_audio_path = stretched_path
                    self._logger.info(
                        f"句段 {seg.index} 音频对齐: {tts_duration:.2f}s→{orig_duration:.2f}s "
                        f"(tempo={tempo:.3f})",
                        module="PipelineManager",
                    )
                else:
                    self._logger.warning(
                        f"句段 {seg.index} 音频对齐失败，使用原始时长",
                        module="PipelineManager",
                    )
            except Exception as e:
                self._logger.warning(
                    f"句段 {seg.index} 音频对齐异常: {e}", module="PipelineManager"
                )

    def _stage_audio_merge(self, ctx: PipelineContext) -> None:
        """阶段 7: 音频合并。"""
        from src.video.audio_merger import AudioMerger

        self._progress.update(
            PipelineStage.AUDIO_MERGE, 20.0, "正在合并配音音频..."
        )
        merged_path = os.path.join(ctx.working_dir, "audio_dub.wav")
        ctx.merged_audio_path = AudioMerger.merge(
            ctx.segments, merged_path, total_duration=ctx.duration
        )

        self._progress.update(
            PipelineStage.AUDIO_MERGE, 80.0, "正在归一化音频..."
        )
        ctx.merged_audio_path = AudioMerger.normalize_audio(ctx.merged_audio_path)

        self._progress.update(
            PipelineStage.AUDIO_MERGE, 100.0, "音频合并完成"
        )

    def _stage_video_compose(self, ctx: PipelineContext) -> None:
        """阶段 8: 视频合成。"""
        from src.video.video_composer import VideoComposer

        self._progress.update(
            PipelineStage.VIDEO_COMPOSE, 10.0, "正在合成最终视频..."
        )

        # 生成输出路径（默认输出到原视频所在目录）
        basename = os.path.splitext(os.path.basename(ctx.video_path))[0]
        output_dir = ctx.output_dir if ctx.output_dir else os.path.dirname(ctx.video_path)
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(
            output_dir, f"{basename}_dubbed.{ctx.output_format}"
        )

        subtitle_path = ctx.subtitle_path if ctx.subtitle_path else ""
        ctx.output_video_path = VideoComposer.compose(
            video_path=ctx.video_path,
            audio_path=ctx.merged_audio_path,
            output_path=output_path,
            subtitle_path=subtitle_path,
            subtitle_mode=ctx.subtitle_mode,
        )

        # 将字幕文件复制到输出视频同目录
        if ctx.subtitle_path and os.path.isfile(ctx.subtitle_path):
            srt_output = os.path.join(
                output_dir, f"{basename}_dubbed.srt"
            )
            try:
                import shutil
                shutil.copy2(ctx.subtitle_path, srt_output)
            except OSError:
                pass

        # 日志输出成品路径
        self._logger.info(
            f"✅ 成品视频: {os.path.abspath(ctx.output_video_path)}",
            module="PipelineManager",
        )
        self._logger.info(
            f"✅ 字幕文件: {os.path.join(output_dir, f'{basename}_dubbed.srt')}",
            module="PipelineManager",
        )

        self._progress.update(
            PipelineStage.VIDEO_COMPOSE, 100.0, "视频合成完成"
        )

    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        """将秒数格式化为 SRT 时间戳格式 HH:MM:SS,mmm。

        Args:
            seconds: 秒数

        Returns:
            SRT 格式时间戳
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds - int(seconds)) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
