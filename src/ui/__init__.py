"""VideoDub UI 模块 - Gradio Web 界面"""

from src.ui.app_layout import create_app_layout
from src.ui.components import (
    create_progress_panel,
    create_log_panel,
    create_engine_config_panel,
    create_video_upload_area,
    create_output_preview,
    create_translation_editor,
)
from src.ui.callbacks import (
    on_video_upload,
    on_engine_switch,
    on_start_pipeline,
    on_cancel_pipeline,
    poll_progress,
    poll_logs,
)

__all__ = [
    "create_app_layout",
    "create_progress_panel",
    "create_log_panel",
    "create_engine_config_panel",
    "create_video_upload_area",
    "create_output_preview",
    "create_translation_editor",
    "on_video_upload",
    "on_engine_switch",
    "on_start_pipeline",
    "on_cancel_pipeline",
    "poll_progress",
    "poll_logs",
]
