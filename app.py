"""AMDLocalDub Gradio 应用主入口。

启动 Gradio Web 服务，组装 UI 布局与回调，
让用户通过浏览器访问 AMDLocalDub（AMD离线配音，纯本地/AMD GPU 加速）。
"""

from __future__ import annotations

import functools
import os
import sys
from typing import Any, Dict, List, Optional

import gradio as gr

from src.core.config_manager import ConfigManager
from src.core.data_models import PipelineContext, PipelineStatus, EngineType
from src.core.logger import Logger
from src.core.pipeline_manager import PipelineManager
from src.core.progress_manager import ProgressManager
from src.core.queue_manager import QueueManager, QueueTask
from src.ui.app_layout import create_app_layout
from src.ui.callbacks import (
    _create_pipeline_managers,
    on_video_upload,
    on_file_path_input,
    on_engine_switch,
    on_target_lang_change,
    on_start_pipeline,
    on_cancel_pipeline,
    poll_progress,
    poll_logs,
    poll_queue,
)


def main() -> None:
    """启动 AMDLocalDub Gradio 应用的主函数。

    1. 创建全局管理器实例
    2. 初始化 UI 布局并绑定事件回调
    3. 启动 Gradio 服务
    """
    # 确保项目目录在 Python 路径中
    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # 确保所需目录存在
    os.makedirs("outputs", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    os.makedirs("models", exist_ok=True)

    # 创建全局管理器
    config_path = os.path.join(project_root, "config.yaml")
    config, logger, progress, pipeline = _create_pipeline_managers(config_path)
    queue_mgr = QueueManager()

    # 队列任务启动回调：运行 Pipeline
    def _on_queue_task_start(task: QueueTask) -> None:
        """队列中的任务启动时执行 Pipeline。"""
        snap = task.config_snapshot or {}
        if not snap:
            logger.error(f"任务 {task.task_id} 配置快照不存在", module="Queue")
            queue_mgr.mark_completed(task.task_id, error="配置丢失")
            return

        video_path = task.file_path
        output_dir = snap.get("output_dir", "")
        if not output_dir:
            # 兜底：使用项目 outputs/ 目录
            project_root = os.path.dirname(os.path.abspath(__file__))
            output_dir = os.path.join(project_root, "outputs")
        # 校验输出目录
        try:
            os.makedirs(output_dir, exist_ok=True)
            if not os.access(output_dir, os.W_OK):
                raise OSError("目录不可写入")
        except OSError as e:
            err = f"输出目录无效或不可写入: {output_dir} - {e}"
            logger.error(err, module="Queue")
            queue_mgr.mark_completed(task.task_id, error=err)
            return

        task_id = task.task_id
        # 中间文件放在系统临时目录（避免中文路径编码问题）
        project_root = os.path.dirname(os.path.abspath(__file__))
        working_dir = os.path.join(
            project_root, "outputs", f".cache_{task_id}",
        )
        os.makedirs(working_dir, exist_ok=True)

        logger.info(f"输出目录: {output_dir}", module="Queue")
        logger.info(f"缓存目录: {working_dir}", module="Queue")

        ctx = PipelineContext(
            video_path=video_path,
            source_lang=snap.get("source_lang", "en"),
            target_lang=snap.get("target_lang", "zh"),
            engine_type=EngineType.from_string(snap.get("engine_type_str", "siliconflow")),
            output_format=snap.get("output_format", "mp4"),
            subtitle_mode=snap.get("subtitle_mode", "burn"),
            output_dir=output_dir,
            tts_voice=snap.get("tts_voice", "zh-CN-XiaoxiaoNeural"),
            working_dir=working_dir,
            config_snapshot=snap,
            task_id=task_id,
        )

        logger.info(f"队列启动任务: {task.file_name} (task_id={task_id})", module="Queue")
        pipeline.execute_async(ctx)

    # 设置队列完成回调（由 Pipeline 完成后触发）
    def _on_pipeline_complete(context: PipelineContext) -> None:
        """Pipeline 完成后，标记队列任务完成并启动下一个。"""
        tid = context.task_id
        if context.status == PipelineStatus.FAILED:
            # 查找失败原因
            error_msg = "处理失败"
            for seg in context.segments:
                if seg.error_message:
                    error_msg = seg.error_message
                    break
            queue_mgr.mark_completed(tid, error=error_msg)
        else:
            queue_mgr.mark_completed(tid)
        logger.info(f"队列任务完成: {tid}", module="Queue")
        # 打印输出路径
        if context.output_video_path:
            logger.info(f"输出文件: {context.output_video_path}", module="Queue")

    pipeline.set_completion_callback(_on_pipeline_complete)

    # 设置队列回调：任务启动时执行 Pipeline
    queue_mgr.set_callbacks(on_task_start=_on_queue_task_start)

    # 检查配置
    config_errors = config.validate()
    if config_errors:
        logger.warning(
            f"配置校验发现 {len(config_errors)} 个问题:\n" +
            "\n".join(f"  - {e}" for e in config_errors),
            module="App",
        )

    logger.info("AMDLocalDub 应用启动中...", module="App")

    # ====== 在 Blocks 上下文内绑定回调 ======
    def _bind_callbacks(refs: Dict[str, Any], blocks: gr.Blocks) -> None:
        """在 Blocks 上下文内绑定所有事件回调。"""
        video_refs = refs["video_panel"].__video_upload_refs__
        engine_refs = refs["engine_panel"].__engine_config_refs__
        progress_refs = refs["progress_panel"].__progress_refs__
        log_refs = refs["log_panel"].__log_refs__
        output_refs = refs["output_panel"].__output_refs__

        # 1. 视频上传回调（拖拽上传）
        video_refs["upload"].upload(
            fn=functools.partial(on_video_upload, config=config, logger=logger),
            inputs=[video_refs["upload"]],
            outputs=[
                video_refs["file_name"],
                video_refs["file_size"],
                video_refs["duration"],
                video_refs["video_codec"],
                video_refs["resolution"],
            ],
            queue=False,
        )

        # 1b. 文件路径文本输入回调
        video_refs["file_path"].change(
            fn=functools.partial(on_file_path_input, config=config, logger=logger),
            inputs=[video_refs["file_path"]],
            outputs=[
                video_refs["file_name"],
                video_refs["file_size"],
                video_refs["duration"],
                video_refs["video_codec"],
                video_refs["resolution"],
            ],
            queue=False,
        )

        # 2. 引擎切换回调
        engine_refs["engine_radio"].change(
            fn=functools.partial(on_engine_switch, config=config, logger=logger),
            inputs=[engine_refs["engine_radio"]],
            outputs=[
                engine_refs["api_url"],
                engine_refs["api_key"],
                engine_refs["model_name"],
                engine_refs["temperature"],
                engine_refs["max_tokens"],
                engine_refs["timeout"],
            ],
            queue=False,
        )

        # 2b. 目标语言切换 → 动态更新配音音色
        engine_refs["target_lang"].change(
            fn=on_target_lang_change,
            inputs=[engine_refs["target_lang"]],
            outputs=[refs["tts_voice"]],
            queue=False,
        )

        # 3. 一键启动回调（多文件排队）
        queue_refs = refs["queue_panel"].__queue_refs__
        refs["start_btn"].click(
            fn=functools.partial(
                on_start_pipeline,
                config=config,
                logger=logger,
                progress=progress,
                pipeline=pipeline,
                queue_mgr=queue_mgr,
            ),
            inputs=[
                video_refs["file_path"],   # 文本路径输入（优先）
                video_refs["upload"],      # 拖拽上传（备选）
                engine_refs["engine_radio"],
                engine_refs["source_lang"],
                engine_refs["target_lang"],
                engine_refs["api_url"],
                engine_refs["api_key"],
                engine_refs["model_name"],
                engine_refs["temperature"],
                engine_refs["max_tokens"],
                engine_refs["timeout"],
                refs["output_format"],
                refs["subtitle_mode"],
                refs["output_dir"],
                refs["tts_voice"],
            ],
            outputs=[
                progress_refs["overall_progress"],
                queue_refs["queue_list"],
                queue_refs["queue_status"],
            ],
            queue=True,
        )

        # 4. 取消按钮回调
        refs["cancel_btn"].click(
            fn=functools.partial(on_cancel_pipeline, pipeline=pipeline, logger=logger),
            queue=False,
        )

        # 4b. 复制日志按钮（获取纯文本日志，写入隐藏文本框）
        log_refs["copy_log_btn"].click(
            fn=lambda: logger.get_all_plain_text() if hasattr(logger, 'get_all_plain_text') else "",
            outputs=[log_refs["log_copy_text"]],
            queue=False,
        )

        # 5. 日志过滤回调
        log_refs["log_filter"].change(
            fn=functools.partial(poll_logs, logger=logger),
            inputs=[log_refs["log_filter"]],
            outputs=[log_refs["log_display"]],
            queue=False,
        )

        # 6. 进度轮询（每 2 秒）
        progress_update = [
            progress_refs["progress_bars"]["video_load"],
            progress_refs["progress_bars"]["asr"],
            progress_refs["progress_bars"]["sentence_split"],
            progress_refs["progress_bars"]["translate"],
            progress_refs["progress_bars"]["audio_segment"],
            progress_refs["progress_bars"]["tts"],
            progress_refs["progress_bars"]["audio_merge"],
            progress_refs["progress_bars"]["video_compose"],
            progress_refs["overall_progress"],
        ]

        blocks.load(
            fn=lambda: poll_progress(pipeline),
            outputs=progress_update,
            queue=False,
        )
        gr.Timer(value=2.0).tick(
            fn=lambda: poll_progress(pipeline),
            outputs=progress_update,
            queue=False,
        )

        # 7. 日志自动刷新（每 3 秒）
        blocks.load(
            fn=lambda: poll_logs("ALL", logger),
            outputs=[log_refs["log_display"]],
            queue=False,
        )
        gr.Timer(value=3.0).tick(
            fn=lambda: poll_logs("ALL", logger),
            outputs=[log_refs["log_display"]],
            queue=False,
        )

        # 8. 队列状态轮询（每 3 秒）
        blocks.load(
            fn=lambda: poll_queue(queue_mgr),
            outputs=[queue_refs["queue_list"], queue_refs["queue_status"]],
            queue=False,
        )
        gr.Timer(value=3.0).tick(
            fn=lambda: poll_queue(queue_mgr),
            outputs=[queue_refs["queue_list"], queue_refs["queue_status"]],
            queue=False,
        )

        # 9. 日志自动滚动（页面加载时执行 JS）
        blocks.load(js="""
        () => {
            setInterval(function() {
                var c = document.getElementById('log-container');
                if(c) c.scrollTop = c.scrollHeight;
            }, 1000);
        }
        """)

    # 创建 UI 布局（在 Blocks 上下文内绑定回调）
    app = create_app_layout(bind_callbacks=_bind_callbacks)

    logger.info("AMDLocalDub 应用已就绪", module="App")

    # 启动服务
    app.queue(default_concurrency_limit=5)
    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        show_error=True,
        theme=gr.themes.Soft(
            primary_hue="blue",
            secondary_hue="indigo",
        ),
        css=_get_css(),
    )


def _get_css() -> str:
    """返回自定义 CSS 样式。"""
    return """
    .gradio-container {
        max-width: 1400px !important;
        margin: 0 auto;
    }
    .progress-bar {
        transition: width 0.5s ease;
    }
    .log-container {
        font-family: 'Consolas', 'Courier New', monospace;
        font-size: 12px;
    }
    .panel {
        border-radius: 8px;
        padding: 12px;
    }
    button.primary {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border: none;
        color: white;
        font-weight: bold;
    }
    button.primary:hover {
        opacity: 0.9;
    }
    """


if __name__ == "__main__":
    main()
