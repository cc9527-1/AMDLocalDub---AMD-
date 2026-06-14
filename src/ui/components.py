"""VideoDub 可复用 UI 组件。

提供进度面板、日志面板、引擎配置面板、视频上传区、
输出预览区、翻译编辑器等 Gradio UI 组件。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import gradio as gr

from src.core.data_models import EngineType


# ==================== Edge-TTS 配音音色映射表 ====================
# 按目标语言分组，key=语言代码，value=[(显示名, 音色ID), ...]
# 首个音色为该语言的默认推荐音色
TTS_VOICE_MAP: Dict[str, List[tuple[str, str]]] = {
    "zh": [
        ("🇨🇳 中文-晓晓 (女)", "zh-CN-XiaoxiaoNeural"),
        ("🇨🇳 中文-云希 (男)", "zh-CN-YunxiNeural"),
        ("🇨🇳 中文-晓萱 (女)", "zh-CN-XiaoxuanNeural"),
        ("🇨🇳 中文-晓涵 (女)", "zh-CN-XiaohanNeural"),
        ("🇨🇳 中文-晓墨 (女)", "zh-CN-XiaomoNeural"),
        ("🇭🇰 粤语-晓佳 (女)", "zh-HK-HiuGaaiNeural"),
        ("🇭🇰 粤语-晓曼 (女)", "zh-HK-HiuMaanNeural"),
        ("🇭🇰 粤语-云朗 (男)", "zh-HK-WanLungNeural"),
    ],
    "en": [
        ("🇺🇸 美式-Jenny (女)", "en-US-JennyNeural"),
        ("🇺🇸 美式-Guy (男)", "en-US-GuyNeural"),
        ("🇺🇸 美式-Aria (女)", "en-US-AriaNeural"),
        ("🇺🇸 美式-Ana (女)", "en-US-AnaNeural"),
        ("🇬🇧 英式-Sonia (女)", "en-GB-SoniaNeural"),
        ("🇬🇧 英式-Ryan (男)", "en-GB-RyanNeural"),
        ("🇬🇧 英式-Libby (女)", "en-GB-LibbyNeural"),
        ("🇦🇺 澳式-Natasha (女)", "en-AU-NatashaNeural"),
    ],
    "ja": [
        ("🇯🇵 日语-Nanami (女)", "ja-JP-NanamiNeural"),
        ("🇯🇵 日语-Keita (男)", "ja-JP-KeitaNeural"),
    ],
    "ko": [
        ("🇰🇷 韩语-SunHi (女)", "ko-KR-SunHiNeural"),
        ("🇰🇷 韩语-InJoon (男)", "ko-KR-InJoonNeural"),
    ],
    "fr": [
        ("🇫🇷 法语-Denise (女)", "fr-FR-DeniseNeural"),
        ("🇫🇷 法语-Henri (男)", "fr-FR-HenriNeural"),
        ("🇫🇷 法语-Brigitte (女)", "fr-FR-BrigitteNeural"),
    ],
    "de": [
        ("🇩🇪 德语-Katja (女)", "de-DE-KatjaNeural"),
        ("🇩🇪 德语-Conrad (男)", "de-DE-ConradNeural"),
        ("🇩🇪 德语-Amala (女)", "de-DE-AmalaNeural"),
    ],
    "es": [
        ("🇪🇸 西语-Elvira (女)", "es-ES-ElviraNeural"),
        ("🇪🇸 西语-Alvaro (男)", "es-ES-AlvaroNeural"),
    ],
    "ru": [
        ("🇷🇺 俄语-Svetlana (女)", "ru-RU-SvetlanaNeural"),
        ("🇷🇺 俄语-Dmitry (男)", "ru-RU-DmitryNeural"),
    ],
    "pt": [
        ("🇵🇹 葡语-Francisca (女)", "pt-BR-FranciscaNeural"),
        ("🇵🇹 葡语-Antonio (男)", "pt-BR-AntonioNeural"),
    ],
    "hi": [
        ("🇮🇳 印地语-Swara (女)", "hi-IN-SwaraNeural"),
        ("🇮🇳 印地语-Madhur (男)", "hi-IN-MadhurNeural"),
    ],
    "ar": [
        ("🇸🇦 阿语-Zariyah (女)", "ar-SA-ZariyahNeural"),
        ("🇸🇦 阿语-Hamed (男)", "ar-SA-HamedNeural"),
    ],
    "vi": [
        ("🇻🇳 越南语-HoaiMy (女)", "vi-VN-HoaiMyNeural"),
        ("🇻🇳 越南语-NamMinh (男)", "vi-VN-NamMinhNeural"),
    ],
    "it": [
        ("🇮🇹 意语-Elsa (女)", "it-IT-ElsaNeural"),
        ("🇮🇹 意语-Diego (男)", "it-IT-DiegoNeural"),
    ],
    "th": [
        ("🇹🇭 泰语-Premwadee (女)", "th-TH-PremwadeeNeural"),
        ("🇹🇭 泰语-Niwat (男)", "th-TH-NiwatNeural"),
    ],
    "id": [
        ("🇮🇩 印尼语-Gadis (女)", "id-ID-GadisNeural"),
        ("🇮🇩 印尼语-Ardi (男)", "id-ID-ArdiNeural"),
    ],
    "tr": [
        ("🇹🇷 土语-Emel (女)", "tr-TR-EmelNeural"),
        ("🇹🇷 土语-Ahmet (男)", "tr-TR-AhmetNeural"),
    ],
    "pl": [
        ("🇵🇱 波兰语-Agnieszka (女)", "pl-PL-AgnieszkaNeural"),
        ("🇵🇱 波兰语-Marek (男)", "pl-PL-MarekNeural"),
    ],
    "nl": [
        ("🇳🇱 荷兰语-Colette (女)", "nl-NL-ColetteNeural"),
        ("🇳🇱 荷兰语-Maarten (男)", "nl-NL-MaartenNeural"),
    ],
    "sv": [
        ("🇸🇪 瑞典语-Sofie (女)", "sv-SE-SofieNeural"),
        ("🇸🇪 瑞典语-Mattias (男)", "sv-SE-MattiasNeural"),
    ],
    "fi": [
        ("🇫🇮 芬兰语-Selma (女)", "fi-FI-SelmaNeural"),
    ],
    "nb": [
        ("🇳🇴 挪威语-Pernille (女)", "nb-NO-PernilleNeural"),
        ("🇳🇴 挪威语-Finn (男)", "nb-NO-FinnNeural"),
    ],
    "da": [
        ("🇩🇰 丹麦语-Christel (女)", "da-DK-ChristelNeural"),
    ],
    "bn": [
        ("🇧🇩 孟加拉语-Purnima (女)", "bn-BD-PurnimaNeural"),
    ],
}


def get_voices_for_language(lang_code: str) -> List[tuple[str, str]]:
    """根据语言代码获取可用的 TTS 音色列表。

    Args:
        lang_code: 语言代码（如 "zh", "en", "ja"）

    Returns:
        音色列表 [(显示名, 音色ID), ...]，未找到返回空列表
    """
    return TTS_VOICE_MAP.get(lang_code, [])


def get_default_voice(lang_code: str) -> str:
    """根据语言代码获取默认推荐音色。

    Args:
        lang_code: 语言代码

    Returns:
        默认音色 ID
    """
    voices = get_voices_for_language(lang_code)
    if voices:
        return voices[0][1]
    # 兜底：中文
    return "zh-CN-XiaoxiaoNeural"


# 目标语言选项（所有支持 TTS 配音的语言，按使用人数排序）
TARGET_LANG_CHOICES: List[tuple[str, str]] = [
    ("🇨🇳 中文", "zh"),
    ("🇺🇸 英语", "en"),
    ("🇯🇵 日语", "ja"),
    ("🇰🇷 韩语", "ko"),
    ("🇫🇷 法语", "fr"),
    ("🇩🇪 德语", "de"),
    ("🇪🇸 西班牙语", "es"),
    ("🇷🇺 俄语", "ru"),
    ("🇵🇹 葡萄牙语", "pt"),
    ("🇮🇳 印地语", "hi"),
    ("🇮🇹 意大利语", "it"),
    ("🇸🇦 阿拉伯语", "ar"),
    ("🇻🇳 越南语", "vi"),
    ("🇹🇷 土耳其语", "tr"),
    ("🇵🇱 波兰语", "pl"),
    ("🇳🇱 荷兰语", "nl"),
    ("🇸🇪 瑞典语", "sv"),
    ("🇫🇮 芬兰语", "fi"),
    ("🇳🇴 挪威语", "nb"),
    ("🇩🇰 丹麦语", "da"),
    ("🇹🇭 泰语", "th"),
    ("🇮🇩 印尼语", "id"),
    ("🇧🇩 孟加拉语", "bn"),
]


def create_video_upload_area() -> gr.Column:
    """创建视频上传/路径输入区域组件。

    支持两种方式：
    1. 输入本地视频文件路径（推荐：可保留原视频目录）
    2. 拖拽或选择文件（路径会丢失，输出到 outputs/）
    """
    with gr.Column(variant="panel") as column:
        gr.Markdown("### 📁 视频文件")

        # 方式1：输入文件路径（推荐）
        file_path = gr.Textbox(
            label="输入视频文件路径（推荐）",
            placeholder="例如: D:\\视频\\my video.mp4",
            value="",
        )
        gr.Markdown(
            "<p style='color: #888; font-size: 12px; text-align: center;'>"
            "— 或拖拽文件到下方 —</p>"
        )
        # 方式2：拖拽上传
        upload = gr.File(
            label="拖拽选择视频文件",
            file_types=[".mp4", ".mkv", ".avi", ".mov", ".webm"],
            file_count="multiple",
        )
        with gr.Row():
            file_name = gr.Textbox(label="文件名", interactive=False, scale=2)
            file_size = gr.Textbox(label="文件大小", interactive=False, scale=1)
        with gr.Row():
            duration = gr.Textbox(label="时长", interactive=False, scale=1)
            video_codec = gr.Textbox(label="视频编码", interactive=False, scale=1)
            resolution = gr.Textbox(label="分辨率", interactive=False, scale=1)

    # 存储引用以便从 callbacks 访问
    column.__video_upload_refs__ = {
        "file_path": file_path,
        "upload": upload,
        "file_name": file_name,
        "file_size": file_size,
        "duration": duration,
        "video_codec": video_codec,
        "resolution": resolution,
    }
    return column


def create_engine_config_panel() -> gr.Column:
    """创建翻译引擎配置面板组件。

    Returns:
        Gradio Column 包含引擎选择和参数配置
    """
    with gr.Column(variant="panel") as column:
        gr.Markdown("### ⚙️ 翻译引擎配置")

        engine_radio = gr.Radio(
            choices=[
                ("SiliconFlow API", "siliconflow"),
                ("LM Studio 本地", "lmstudio"),
                ("DeepSeek API", "deepseek"),
            ],
            label="选择翻译引擎",
            value="siliconflow",
        )

        with gr.Row():
            source_lang = gr.Dropdown(
                choices=[
                    ("🇺🇸 英语 en", "en"),
                    ("🇨🇳 中文 zh", "zh"),
                    ("🇮🇳 印地语 hi", "hi"),
                    ("🇪🇸 西班牙语 es", "es"),
                    ("🇫🇷 法语 fr", "fr"),
                    ("🇸🇦 阿拉伯语 ar", "ar"),
                    ("🇧🇩 孟加拉语 bn", "bn"),
                    ("🇵🇹 葡萄牙语 pt", "pt"),
                    ("🇷🇺 俄语 ru", "ru"),
                    ("🇵🇰 乌尔都语 ur", "ur"),
                    ("🇮🇩 印尼语 id", "id"),
                    ("🇩🇪 德语 de", "de"),
                    ("🇯🇵 日语 ja", "ja"),
                    ("🇹🇿 斯瓦希里语 sw", "sw"),
                    ("🇮🇳 旁遮普语 pa", "pa"),
                    ("🇮🇳 马拉地语 mr", "mr"),
                    ("🇮🇳 泰卢固语 te", "te"),
                    ("🇹🇷 土耳其语 tr", "tr"),
                    ("🇮🇳 泰米尔语 ta", "ta"),
                    ("🇻🇳 越南语 vi", "vi"),
                ],
                label="源语言",
                value="en",
                scale=1,
            )
            target_lang = gr.Dropdown(
                choices=TARGET_LANG_CHOICES,
                label="目标语言",
                value="zh",
                scale=1,
            )

        # 引擎特有配置（根据选择的引擎动态显示）
        api_url = gr.Textbox(
            label="API 地址",
            placeholder="https://api.siliconflow.cn/v1/chat/completions",
            value="https://api.siliconflow.cn/v1/chat/completions",
        )
        api_key = gr.Textbox(
            label="API Key",
            type="password",
            placeholder="输入 API Key（LM Studio 不需要）",
        )
        model_name = gr.Textbox(
            label="模型名称",
            placeholder="deepseek-ai/DeepSeek-V4-Flash",
            value="deepseek-ai/DeepSeek-V4-Flash",
        )

        with gr.Accordion("高级参数", open=False):
            temperature = gr.Slider(
                label="温度 (temperature)",
                minimum=0.0,
                maximum=1.0,
                value=0.3,
                step=0.05,
            )
            max_tokens = gr.Slider(
                label="最大 Token",
                minimum=128,
                maximum=4096,
                value=1024,
                step=128,
            )
            timeout = gr.Slider(
                label="超时（秒）",
                minimum=10,
                maximum=120,
                value=30,
                step=5,
            )

    column.__engine_config_refs__ = {
        "engine_radio": engine_radio,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "api_url": api_url,
        "api_key": api_key,
        "model_name": model_name,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": timeout,
    }
    return column


def create_progress_panel() -> gr.Column:
    """创建处理进度总览面板组件。

    Returns:
        Gradio Column 包含各阶段进度条和状态信息
    """
    with gr.Column(variant="panel") as column:
        gr.Markdown("### 📊 处理进度总览")

        # 各阶段进度条
        stages = [
            ("video_load", "视频加载"),
            ("asr", "语音识别"),
            ("sentence_split", "句子拆分"),
            ("translate", "翻译"),
            ("audio_segment", "音频分段"),
            ("tts", "配音合成"),
            ("audio_merge", "音频合并"),
            ("video_compose", "视频合成"),
        ]

        progress_bars = {}
        for stage_key, stage_name in stages:
            progress_bars[stage_key] = gr.HTML(
                value=_render_progress_bar(stage_name, 0, "等待中"),
                label=stage_name,
            )

        gr.Markdown("---")
        overall_progress = gr.HTML(
            value=_render_overall_progress(0, "等待启动", 0),
        )

    column.__progress_refs__ = {
        "progress_bars": progress_bars,
        "overall_progress": overall_progress,
    }
    return column


def create_log_panel() -> gr.Column:
    """创建实时日志显示面板组件（支持自动滚动和复制）。

    Returns:
        Gradio Column 包含日志显示和过滤控件
    """
    with gr.Column(variant="panel") as column:
        gr.Markdown("### 📋 实时日志")

        with gr.Row():
            log_filter = gr.Radio(
                choices=["ALL", "INFO", "WARNING", "ERROR"],
                label="日志级别过滤",
                value="ALL",
                scale=1,
            )
            copy_log_btn = gr.Button("📋 复制日志", size="sm", scale=0, variant="secondary")
            log_clear = gr.Button("清空日志", size="sm", scale=0)

        log_display = gr.HTML(
            value=(
                "<div style='height: 300px; overflow-y: auto; padding: 8px; "
                "background: #1e1e1e; color: #d4d4d4; font-family: monospace; "
                "font-size: 12px; border-radius: 4px;' id='log-container'>"
                "<p style='color: #888;'>等待日志输出...</p></div>"
            ),
            label="日志内容",
        )

        # 隐藏的文本框用于复制
        log_copy_text = gr.Textbox(
            value="",
            visible=False,
            label="日志文本",
            elem_id="log-copy-text",
        )

    column.__log_refs__ = {
        "log_filter": log_filter,
        "log_clear": log_clear,
        "log_display": log_display,
        "log_copy_text": log_copy_text,
        "copy_log_btn": copy_log_btn,
    }
    return column


def create_output_preview() -> gr.Column:
    """创建输出预览区域组件。

    Returns:
        Gradio Column 包含视频播放器和下载按钮
    """
    with gr.Column(variant="panel", visible=False) as column:
        gr.Markdown("### 📥 输出预览")
        output_video = gr.Video(label="配音完成视频", interactive=False)
        with gr.Row():
            download_btn = gr.Button("📥 下载视频", variant="primary")
            download_subtitle = gr.Button("📄 下载字幕", variant="secondary")

    column.__output_refs__ = {
        "output_video": output_video,
        "download_btn": download_btn,
        "download_subtitle": download_subtitle,
    }
    return column


def create_queue_panel() -> gr.Column:
    """创建任务队列面板组件。

    Returns:
        Gradio Column 包含队列列表和状态
    """
    with gr.Column(variant="panel") as column:
        gr.Markdown("### 📋 任务队列")
        queue_list = gr.Dataframe(
            headers=["#", "文件名", "状态", "进度"],
            datatype=["number", "str", "str", "str"],
            row_count=5,
            column_count=(4, "fixed"),
            value=[],
            label="排队任务",
            interactive=False,
        )
        queue_status = gr.HTML(
            value="<span style='color: #888;'>暂无排队任务</span>",
        )

    column.__queue_refs__ = {
        "queue_list": queue_list,
        "queue_status": queue_status,
    }
    return column


def create_translation_editor() -> gr.Column:
    """创建翻译文本编辑弹窗组件。

    Returns:
        Gradio Column 包含逐句编辑功能
    """
    with gr.Column(variant="panel", visible=False) as column:
        gr.Markdown("### ✏️ 翻译校对")

        segment_selector = gr.Dropdown(
            label="选择句段",
            choices=[],
            value=None,
            interactive=True,
        )
        original_text = gr.Textbox(
            label="原始文本（ASR 结果）",
            interactive=False,
            lines=2,
        )
        translated_text = gr.Textbox(
            label="翻译文本（可编辑）",
            interactive=True,
            lines=2,
        )
        time_info = gr.Textbox(
            label="时间戳",
            interactive=False,
        )

        with gr.Row():
            save_btn = gr.Button("💾 保存", variant="primary")
            skip_btn = gr.Button("⏭ 跳过", variant="secondary")

    column.__editor_refs__ = {
        "segment_selector": segment_selector,
        "original_text": original_text,
        "translated_text": translated_text,
        "time_info": time_info,
        "save_btn": save_btn,
        "skip_btn": skip_btn,
    }
    return column


def _render_progress_bar(
    label: str, percent: float, message: str
) -> str:
    """渲染单个进度条的 HTML。

    Args:
        label: 阶段名称
        percent: 进度百分比
        message: 状态描述

    Returns:
        HTML 字符串
    """
    color = _get_progress_color(percent)
    return f"""
    <div style="margin-bottom: 6px;">
        <div style="display: flex; justify-content: space-between; font-size: 13px;">
            <span>{label}</span>
            <span>{percent:.0f}% - {message}</span>
        </div>
        <div style="background: #333; border-radius: 4px; height: 20px; overflow: hidden;">
            <div style="background: {color}; width: {percent}%; height: 100%;
                        border-radius: 4px; transition: width 0.5s ease;"></div>
        </div>
    </div>
    """


def _render_overall_progress(
    percent: float, message: str, elapsed: float
) -> str:
    """渲染整体进度的 HTML。

    Args:
        percent: 整体进度百分比
        message: 状态描述
        elapsed: 已耗时（秒）

    Returns:
        HTML 字符串
    """
    time_str = f"{int(elapsed // 60)}分 {int(elapsed % 60)}秒" if elapsed > 0 else "0秒"
    color = _get_progress_color(percent)
    return f"""
    <div style="margin-top: 8px;">
        <div style="display: flex; justify-content: space-between; font-size: 14px; font-weight: bold;">
            <span>整体进度</span>
            <span>{percent:.1f}%</span>
        </div>
        <div style="background: #333; border-radius: 4px; height: 24px; overflow: hidden;">
            <div style="background: {color}; width: {percent}%; height: 100%;
                        border-radius: 4px; transition: width 0.5s ease;"></div>
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 12px; color: #888; margin-top: 4px;">
            <span>{message}</span>
            <span>已耗时: {time_str}</span>
        </div>
    </div>
    """


def _get_progress_color(percent: float) -> str:
    """根据进度百分比返回颜色。

    Args:
        percent: 进度百分比

    Returns:
        CSS 颜色字符串
    """
    if percent >= 100:
        return "#4CAF50"
    elif percent >= 60:
        return "#2196F3"
    elif percent >= 30:
        return "#FF9800"
    elif percent < 0:
        return "#f44336"
    else:
        return "#2196F3"


def render_log_entry(entry: Dict[str, Any]) -> str:
    """渲染单条日志条目的 HTML。

    Args:
        entry: 日志条目字典

    Returns:
        HTML 字符串
    """
    level = entry.get("level", "INFO")
    color_map = {
        "INFO": "#4FC1FF",
        "WARNING": "#FFD700",
        "ERROR": "#FF4444",
    }
    color = color_map.get(level, "#d4d4d4")
    return (
        f"<p style='margin: 0; line-height: 1.5;'>"
        f"<span style='color: #888;'>{entry.get('timestamp', '')}</span> "
        f"<span style='color: {color}; font-weight: bold;'>[{level}]</span> "
        f"<span style='color: #569CD6;'>[{entry.get('module', '')}]</span> "
        f"<span>{entry.get('message', '')}</span>"
        f"</p>"
    )
