"""VideoDub Gradio 界面布局定义。

定义主界面的左右两栏布局：
- 左侧面板: 视频上传、翻译引擎配置、输出设置
- 右侧面板: 处理进度总览、实时日志
- 底部区域: 输出预览（处理完成后显示）

在 Gradio 6.x 中，所有事件绑定必须在 gr.Blocks 上下文内完成。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import gradio as gr

from src.ui.components import (
    create_video_upload_area,
    create_engine_config_panel,
    create_progress_panel,
    create_log_panel,
    create_output_preview,
    create_translation_editor,
    create_queue_panel,
    get_voices_for_language,
    get_default_voice,
)


def create_app_layout(
    bind_callbacks: Optional[Callable[[Dict[str, Any], gr.Blocks], None]] = None,
) -> gr.Blocks:
    """创建 VideoDub 主界面布局。

    在 Gradio 6.x 中，所有事件绑定必须在 gr.Blocks 上下文内完成。
    通过 bind_callbacks 回调在 Blocks 上下文内绑定事件。

    Args:
        bind_callbacks: 可选的回调函数，接收 (组件引用字典, gr.Blocks 实例)，在 Blocks 上下文内绑定事件

    Returns:
        Gradio Blocks 应用实例
    """
    with gr.Blocks(
        title="AMDLocalDub - AMD离线配音",
    ) as app:

        # 顶部标题
        gr.Markdown(
            """
            # ⚡ AMDLocalDub — AMD离线配音
            纯本地运行 · AMD GPU 加速 · 视频翻译配音一体化
            """,
        )

        # 主区域：左右两栏
        with gr.Row(equal_height=False):
            # 左侧面板
            with gr.Column(scale=1, min_width=400):
                video_panel = create_video_upload_area()
                engine_panel = create_engine_config_panel()

                # 输出设置
                with gr.Column(variant="panel"):
                    gr.Markdown("### 🎯 输出设置")
                    with gr.Row():
                        output_format = gr.Radio(
                            choices=["mp4", "mkv"],
                            label="输出格式",
                            value="mp4",
                        )
                        subtitle_mode = gr.Radio(
                            choices=["none", "soft", "burn"],
                            label="字幕模式",
                            value="burn",
                        )
                    output_dir = gr.Textbox(
                        label="输出目录（留空=自动: 路径输入→原视频目录 / 拖拽→outputs/）",
                        placeholder="留空则自动判断输出位置，也可手动指定",
                        value="",
                    )
                    tts_voice = gr.Dropdown(
                        choices=get_voices_for_language("zh"),
                        label="配音音色（随目标语言自动筛选）",
                        value=get_default_voice("zh"),
                    )

                    start_btn = gr.Button(
                        "▶ 一键启动处理",
                        variant="primary",
                        size="lg",
                    )
                    cancel_btn = gr.Button(
                        "⏹ 取消处理",
                        variant="stop",
                        size="lg",
                        visible=True,
                    )

            # 右侧面板
            with gr.Column(scale=1, min_width=400):
                progress_panel = create_progress_panel()
                queue_panel = create_queue_panel()
                log_panel = create_log_panel()

        # 底部：输出预览 + 翻译编辑
        output_panel = create_output_preview()
        editor_panel = create_translation_editor()

        # 组件引用字典
        refs = {
            "video_panel": video_panel,
            "engine_panel": engine_panel,
            "progress_panel": progress_panel,
            "queue_panel": queue_panel,
            "log_panel": log_panel,
            "output_panel": output_panel,
            "editor_panel": editor_panel,
            "output_format": output_format,
            "subtitle_mode": subtitle_mode,
            "output_dir": output_dir,
            "tts_voice": tts_voice,
            "start_btn": start_btn,
            "cancel_btn": cancel_btn,
        }

        # 在 Blocks 上下文内绑定事件回调（Gradio 6.x 要求）
        if bind_callbacks is not None:
            bind_callbacks(refs, app)

        # 存储组件引用（供外部轮询等非事件绑定场景使用）
        app._component_refs = refs

    return app
