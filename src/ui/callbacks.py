"""VideoDub Gradio 事件回调绑定。

定义所有 UI 事件的处理逻辑：
- 文件上传 → 显示视频信息
- 引擎切换 → 更新配置面板
- 一键启动 → 调用 PipelineManager
- 进度轮询更新
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

import gradio as gr

from src.core.config_manager import ConfigManager
from src.core.data_models import (
    EngineType,
    PipelineContext,
    PipelineStage,
    Segment,
)
from src.core.logger import Logger
from src.core.pipeline_manager import PipelineManager
from src.core.progress_manager import ProgressManager
from src.core.queue_manager import QueueManager
from src.ui.components import (
    render_log_entry,
    _render_progress_bar,
    _render_overall_progress,
    get_voices_for_language,
    get_default_voice,
)
from src.video.video_loader import VideoLoader


def _create_pipeline_managers(
    config_path: str = "config.yaml",
) -> Tuple[ConfigManager, Logger, ProgressManager, PipelineManager]:
    """创建全局的配置、日志、进度和管理器实例。

    Args:
        config_path: 配置文件路径

    Returns:
        (ConfigManager, Logger, ProgressManager, PipelineManager) 四元组
    """
    config = ConfigManager(config_path)
    logger = Logger(log_dir=config.get("general.log_dir", "logs"))
    progress = ProgressManager()
    pipeline = PipelineManager(config, progress, logger)
    return config, logger, progress, pipeline


def on_video_upload(
    files: Optional[List[gr.FileData]],
    config: ConfigManager,
    logger: Logger,
) -> Dict[str, Any]:
    """视频上传事件回调（支持多文件拖拽）。
    验证第一个视频的格式，提取并显示媒体信息。

    Returns:
        更新 UI 组件的字典
    """
    if not files:
        return (
            gr.update(value=""), gr.update(value=""),
            gr.update(value=""), gr.update(value=""), gr.update(value=""),
        )

    file = files[0]
    video_path = file.path if hasattr(file, "path") else str(file)
    return _load_video_info(video_path, logger)


def on_file_path_input(
    text_path: str,
    config: ConfigManager,
    logger: Logger,
) -> Dict[str, Any]:
    """视频文件路径输入回调。
    用户输入本地文件路径时触发，验证并显示视频信息。

    Returns:
        更新 UI 组件的字典
    """
    if not text_path or not text_path.strip():
        return (
            gr.update(value=""), gr.update(value=""),
            gr.update(value=""), gr.update(value=""), gr.update(value=""),
        )

    video_path = text_path.strip()
    if not os.path.isfile(video_path):
        logger.warning(f"文件路径无效: {video_path}", module="UI")
        return (
            gr.update(value=""), gr.update(value=""),
            gr.update(value=""), gr.update(value=""), gr.update(value=""),
        )

    return _load_video_info(video_path, logger)


def _load_video_info(video_path: str, logger: Logger) -> Tuple:
    """加载并返回视频信息（共用函数）。"""
    logger.info(f"加载视频: {video_path}", module="UI")
    try:
        media_info = VideoLoader.load(video_path)
        file_size = media_info.get("file_size", 0)
        size_str = _format_file_size(file_size)
        duration = media_info.get("duration", 0)
        duration_str = _format_duration(duration)
        video_info = media_info.get("video", {})
        codec = video_info.get("codec", "N/A")
        width = video_info.get("width", 0)
        height = video_info.get("height", 0)
        resolution_str = f"{width}x{height}" if width and height else "N/A"
        logger.info(
            f"视频信息: {media_info.get('file_name')}, "
            f"{duration_str}, {resolution_str}, {codec}",
            module="UI",
        )
        return (
            gr.update(value=media_info.get("file_name", "")),
            gr.update(value=size_str),
            gr.update(value=duration_str),
            gr.update(value=codec),
            gr.update(value=resolution_str),
        )
    except Exception as e:
        logger.error(f"加载视频信息失败: {e}", module="UI")
        return (
            gr.update(value=""), gr.update(value=""),
            gr.update(value=""), gr.update(value=""), gr.update(value=""),
        )
        logger.error(f"视频加载失败: {e}", module="UI")
        return (
            gr.update(value=f"加载失败: {e}"),
            gr.update(value=""),
            gr.update(value=""),
            gr.update(value=""),
            gr.update(value=""),
        )


def on_engine_switch(
    engine_type_str: str,
    config: ConfigManager,
    logger: Logger,
) -> Dict[str, Any]:
    """翻译引擎切换事件回调。

    根据选择的引擎类型更新配置面板显示。

    Args:
        engine_type_str: 引擎类型字符串
        config: 配置管理器
        logger: 日志记录器

    Returns:
        更新 UI 组件的字典
    """
    try:
        engine_type = EngineType.from_string(engine_type_str)
        config.set_active_engine(engine_type)
        engine_config = config.get_engine_config(engine_type)

        logger.info(f"切换翻译引擎至: {engine_type.value}", module="UI")

        return (
            gr.update(value=engine_config.get("api_url", "")),
            gr.update(value=engine_config.get("api_key", "")),
            gr.update(value=engine_config.get("model_name", "")),
            gr.update(value=engine_config.get("temperature", 0.3)),
            gr.update(value=engine_config.get("max_tokens", 1024)),
            gr.update(value=engine_config.get("timeout", 30)),
        )

    except Exception as e:
        logger.error(f"引擎切换失败: {e}", module="UI")
        return (
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
        )


def on_target_lang_change(lang_code: str) -> Tuple[List[tuple[str, str]], str]:
    """目标语言切换事件回调：动态更新配音音色下拉框。

    根据选择的目标语言，过滤出该语言可用的 TTS 音色列表，
    并自动选择默认音色。

    Args:
        lang_code: 目标语言代码（如 "zh", "en", "ja"）

    Returns:
        (音色下拉选项列表, 默认音色值)
    """
    voices = get_voices_for_language(lang_code)
    if not voices:
        # 如果不支持 TTS 配音，提供中文默认选项作为兜底
        voices = get_voices_for_language("zh")
        default = get_default_voice("zh")
    else:
        default = get_default_voice(lang_code)
    return voices, default


def on_start_pipeline(
    video_text_path: str,
    video_files: Optional[List[gr.FileData]],
    engine_type_str: str,
    source_lang: str,
    target_lang: str,
    api_url: str,
    api_key: str,
    model_name: str,
    temperature: float,
    max_tokens: int,
    timeout_val: int,
    output_format: str,
    subtitle_mode: str,
    output_dir: str,
    tts_voice: str,
    config: ConfigManager,
    logger: Logger,
    progress: ProgressManager,
    pipeline: PipelineManager,
    queue_mgr: QueueManager,
) -> Dict[str, Any]:
    """一键启动 Pipeline 事件回调。

    支持多文件排队处理：优先使用文本路径输入（保留原始目录），
    其次使用拖拽上传的文件。

    Args:
        video_files: 拖拽上传的视频文件列表
        video_text_path: 文本输入的视频文件路径
        queue_mgr: 队列管理器

    Returns:
        更新 UI 组件的字典
    """
    # 收集视频路径：优先使用文本路径输入（保留原始目录信息）
    file_paths: List[str] = []

    # 检查文本路径输入
    if video_text_path and video_text_path.strip():
        raw_path = video_text_path.strip()
        if os.path.isfile(raw_path):
            file_paths.append(os.path.abspath(raw_path))
        else:
            gr.Warning(f"文件路径无效: {raw_path}")
            logger.warning(f"文本路径无效: {raw_path}", module="UI")
            return {}

    # 其次检查拖拽上传的文件
    if not file_paths and video_files:
        for vf in video_files:
            path = vf.path if hasattr(vf, "path") else str(vf)
            if os.path.isfile(path):
                file_paths.append(path)

    if not file_paths:
        gr.Warning("请先输入视频路径或拖拽视频文件")
        return {}

    # 保存运行时配置（所有任务共享同一套配置）

    # 保存运行时配置（所有任务共享同一套配置）
    config.set("translation.active_engine", engine_type_str)
    config.set(f"translation.{engine_type_str}.api_url", api_url)
    config.set(f"translation.{engine_type_str}.api_key", api_key)
    config.set(f"translation.{engine_type_str}.model_name", model_name)
    config.set(f"translation.{engine_type_str}.temperature", temperature)
    config.set(f"translation.{engine_type_str}.max_tokens", max_tokens)
    config.set(f"translation.{engine_type_str}.timeout", timeout_val)

    # 确定输出目录
    if not output_dir or not output_dir.strip():
        # 判断文件来源：文本路径输入（原始路径） vs 拖拽上传（Gradio 临时路径）
        first_file = file_paths[0]
        if video_text_path and video_text_path.strip():
            # 用户输入了文本路径 → 使用原视频所在目录
            output_dir = os.path.dirname(os.path.abspath(first_file))
            logger.info(
                f"文本路径输入，输出到原始目录: {output_dir}", module="UI"
            )
        else:
            # 拖拽上传 → 无法获取原始路径，使用项目 outputs/
            output_dir = os.path.abspath("outputs")
            logger.info(
                f"拖拽上传（Gradio 临时路径），输出到: {output_dir}", module="UI"
            )
    else:
        output_dir = os.path.abspath(output_dir.strip())

    # 校验输出目录
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            logger.error(f"输出目录创建失败: {output_dir} - {e}", module="UI")
            gr.Warning(f"输出目录创建失败: {e}")
            return {}
    if not os.access(output_dir, os.W_OK):
        logger.error(f"输出目录不可写入: {output_dir}", module="UI")
        gr.Warning(f"输出目录不可写入，请检查权限: {output_dir}")
        return {}

    # 构建配置快照（所有任务共享同一份配置）
    snapshot = config.snapshot()
    snapshot["output_format"] = output_format
    snapshot["subtitle_mode"] = subtitle_mode
    snapshot["output_dir"] = output_dir
    snapshot["tts_voice"] = tts_voice
    snapshot["source_lang"] = source_lang
    snapshot["target_lang"] = target_lang
    snapshot["engine_type_str"] = engine_type_str

    # 将所有文件添加到队列（带配置快照）
    task_ids = queue_mgr.add_tasks(file_paths, config_snapshot=snapshot)
    logger.info(f"添加 {len(task_ids)} 个任务到队列", module="UI")

    return (
        gr.update(
            value=_render_overall_progress(0, f"已添加 {len(task_ids)} 个任务到队列", 0)
        ),
        gr.update(value=queue_mgr.get_queue_data()),
        gr.update(value=queue_mgr.get_queue_status_text()),
    )


# 引用队列组件输出（由 app.py 绑定）
overall_progress = None
queue_list = None
queue_status = None


def on_cancel_pipeline(
    pipeline: PipelineManager,
    logger: Logger,
) -> Dict[str, Any]:
    """取消 Pipeline 事件回调。

    Args:
        pipeline: 管线管理器
        logger: 日志记录器

    Returns:
        更新 UI 组件的字典
    """
    pipeline.cancel()
    logger.warning("用户取消了 Pipeline", module="UI")
    gr.Info("已请求取消处理")
    return {}


def poll_progress(
    pipeline: PipelineManager,
) -> tuple:
    """轮询进度事件回调。

    由 Gradio 的定时器触发，获取最新进度并更新 UI。

    Args:
        pipeline: 管线管理器

    Returns:
        (8 个进度条 HTML, 1 个整体进度 HTML) 共 9 个元素的元组
    """
    status = pipeline.get_status()
    progress_data = status.get("progress", {})

    if not progress_data:
        return tuple(gr.update() for _ in range(9))

    stages = progress_data.get("stages", {})
    stage_keys = [
        "video_load",
        "asr",
        "sentence_split",
        "translate",
        "audio_segment",
        "tts",
        "audio_merge",
        "video_compose",
    ]
    stage_names = {
        "video_load": "视频加载",
        "asr": "语音识别",
        "sentence_split": "句子拆分",
        "translate": "翻译",
        "audio_segment": "音频分段",
        "tts": "配音合成",
        "audio_merge": "音频合并",
        "video_compose": "视频合成",
    }

    result = []

    # 更新各阶段进度条
    for stage_key in stage_keys:
        stage_data = stages.get(stage_key, {})
        percent = stage_data.get("percent", 0.0)
        message = stage_data.get("message", "")
        result.append(
            gr.update(
                value=_render_progress_bar(
                    stage_names.get(stage_key, stage_key), percent, message
                )
            )
        )

    # 更新整体进度
    overall_percent = progress_data.get("overall_percent", 0.0)
    overall_message = progress_data.get("overall_message", "")
    elapsed_time = progress_data.get("elapsed_time", 0.0)
    result.append(
        gr.update(
            value=_render_overall_progress(
                overall_percent, overall_message, elapsed_time
            )
        )
    )

    return tuple(result)


def poll_logs(
    log_filter: str,
    logger: Logger,
) -> str:
    """轮询日志事件回调。

    Args:
        log_filter: 日志级别过滤 ("ALL", "INFO", "WARNING", "ERROR")
        logger: 日志记录器

    Returns:
        日志 HTML 字符串
    """
    level = None if log_filter == "ALL" else log_filter
    entries = logger.get_recent(level=level, lines=100)

    if not entries:
        return (
            "<div style='height: 300px; overflow-y: auto; padding: 8px; "
            "background: #1e1e1e; color: #d4d4d4; font-family: monospace; "
            "font-size: 12px; border-radius: 4px;'>"
            "<p style='color: #888;'>暂无日志</p></div>"
        )

    log_html = (
        "<div style='height: 300px; overflow-y: auto; padding: 8px; "
        "background: #1e1e1e; color: #d4d4d4; font-family: monospace; "
        "font-size: 12px; border-radius: 4px;'>"
    )

    for entry in reversed(entries):
        log_html += render_log_entry(entry)

    log_html += "</div>"
    return log_html


def poll_queue(
    queue_mgr: QueueManager,
) -> Tuple[List[List[Any]], str]:
    """轮询队列状态事件回调。

    Args:
        queue_mgr: 队列管理器

    Returns:
        (队列表格数据, 队列状态 HTML)
    """
    return (
        [[r["#"], r["文件名"], r["状态"], r["进度"]] for r in queue_mgr.get_queue_data()],
        queue_mgr.get_queue_status_text(),
    )


def _format_file_size(size_bytes: int) -> str:
    """格式化文件大小显示。

    Args:
        size_bytes: 字节数

    Returns:
        格式化后的字符串
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _format_duration(seconds: float) -> str:
    """格式化时长显示。

    Args:
        seconds: 秒数

    Returns:
        格式化后的字符串，如 "1:23:45" 或 "3:45"
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"
