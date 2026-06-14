"""VideoDub Edge-TTS 配音引擎。

基于微软 edge-tts 库实现逐句合成，
支持中英文语音选择，返回音频文件路径。
"""

from __future__ import annotations

import asyncio
import os
import threading
from typing import Any, Callable, Dict, List, Optional

import edge_tts

from src.core.data_models import Segment, SegmentStatus, TTSError


class TTSEngine:
    """Edge-TTS 配音引擎。

    逐句调用 edge-tts 生成配音音频，
    支持中文普通话和英文语音。

    Attributes:
        _voice: TTS 语音名称
        _rate: 语速（如 "+0%" 为标准）
        _volume: 音量（如 "+0%"）
        _connect_timeout: 连接超时秒数
    """

    # 常用语音映射
    COMMON_VOICES: Dict[str, str] = {
        "zh-CN-XiaoxiaoNeural": "中文普通话（女声）",
        "zh-CN-YunxiNeural": "中文普通话（男声）",
        "en-US-JennyNeural": "英文美式（女声）",
        "en-US-GuyNeural": "英文美式（男声）",
        "en-GB-SoniaNeural": "英文英式（女声）",
        "ja-JP-NanamiNeural": "日语（女声）",
        "ko-KR-SunHiNeural": "韩语（女声）",
    }

    def __init__(
        self,
        voice: str = "zh-CN-XiaoxiaoNeural",
        rate: str = "+0%",
        volume: str = "+0%",
        connect_timeout: int = 10,
    ) -> None:
        """初始化 TTS 引擎。

        Args:
            voice: edge-tts 语音名称
            rate: 语速（"+0%" 标准, "+50%" 1.5 倍速）
            volume: 音量
            connect_timeout: 连接超时（秒）
        """
        self._voice: str = voice
        self._rate: str = rate
        self._volume: str = volume
        self._connect_timeout: int = connect_timeout

    def synthesize(self, segment: Segment, output_dir: str) -> str:
        """为单个句段生成 TTS 配音音频。

        Args:
            segment: 句段（使用 translated_text）
            output_dir: 输出目录

        Returns:
            生成的音频文件路径

        Raises:
            TTSError: 配音合成失败
        """
        text = segment.translated_text.strip()
        if not text:
            # 无翻译文本，跳过
            segment.tts_audio_path = ""
            segment.status = SegmentStatus.TTS_DONE
            return ""

        # 生成输出路径
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(
            output_dir, f"seg_{segment.index:04d}.wav"
        )

        # 在独立线程中运行 edge-tts，自带事件循环，避免与 Gradio 异步上下文冲突
        tts_ok = False
        tts_error: Optional[Exception] = None

        def _run_tts_in_thread() -> None:
            nonlocal tts_ok, tts_error
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                new_loop.run_until_complete(self._run_tts(text, output_path))
                new_loop.close()
                tts_ok = True
            except Exception as e:
                tts_error = e

        t = threading.Thread(target=_run_tts_in_thread, daemon=True)
        t.start()
        t.join(timeout=self._connect_timeout + 30)

        if t.is_alive():
            raise TTSError(f"Edge-TTS 配音超时 [{segment.index}]")

        if not tts_ok:
            error_msg = str(tts_error) if tts_error else "未知错误"
            if "No connection could be made" in error_msg:
                raise TTSError(
                    f"Edge-TTS 连接失败，请检查网络连接: {error_msg[:100]}"
                )
            raise TTSError(f"Edge-TTS 配音失败 [{segment.index}]: {error_msg}")

        if not os.path.isfile(output_path):
            raise TTSError(
                f"Edge-TTS 未生成音频文件 [{segment.index}]"
            )

        segment.tts_audio_path = os.path.abspath(output_path)
        segment.status = SegmentStatus.TTS_DONE
        return os.path.abspath(output_path)

    def batch_synthesize(
        self,
        segments: List[Segment],
        output_dir: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> List[Segment]:
        """批量合成多个句段的配音（失败自动重试最多 3 次）。

        Args:
            segments: 句段列表
            output_dir: TTS 输出目录
            progress_callback: 进度回调 (percent, message)

        Returns:
            配音完成后的句段列表
        """
        total = len(segments)
        failed_segments: List[int] = []
        max_retries = 3

        for i, seg in enumerate(segments):
            if progress_callback:
                percent = (i / total) * 100.0
                progress_callback(
                    percent, f"配音第 {i + 1}/{total} 句"
                )

            # 跳过已配音的句段
            if seg.status == SegmentStatus.TTS_DONE or seg.status == SegmentStatus.COMPLETED:
                continue

            # 重试循环（最多 3 次）
            success = False
            last_error = ""
            for attempt in range(1, max_retries + 1):
                try:
                    self.synthesize(seg, output_dir)
                    success = True
                    break
                except TTSError as e:
                    last_error = str(e)
                    if attempt < max_retries:
                        import time
                        wait = attempt * 2  # 递增等待: 2s, 4s
                        if progress_callback:
                            progress_callback(
                                (i / total) * 100.0,
                                f"配音第 {i + 1}/{total} 句 (重试 {attempt}/{max_retries})",
                            )
                        time.sleep(wait)

            if not success:
                seg.status = SegmentStatus.FAILED
                seg.error_message = last_error
                failed_segments.append(seg.index)
                print(f"[TTS] 句段 {seg.index} 配音失败 (已重试 {max_retries} 次): {last_error}")

        # 汇总失败句子
        if failed_segments:
            print(f"[TTS] 配音完成，{len(failed_segments)} 句失败: 第 {', '.join(str(s) for s in failed_segments)} 句")

        if progress_callback:
            progress_callback(100.0, "配音合成完成")

        return segments

    async def _run_tts(self, text: str, output_path: str) -> None:
        """异步执行 edge-tts 合成。

        Args:
            text: 要合成的文本
            output_path: 输出文件路径
        """
        communicate = edge_tts.Communicate(
            text=text,
            voice=self._voice,
            rate=self._rate,
            volume=self._volume,
        )
        await communicate.save(output_path)

    @classmethod
    def validate_voice(cls, voice: str) -> bool:
        """校验语音名称是否有效。

        Args:
            voice: 语音名称

        Returns:
            是否有效
        """
        return voice in cls.COMMON_VOICES

    @classmethod
    def list_voices(cls) -> List[str]:
        """列出所有常用的语音名称。

        Returns:
            语音名称列表
        """
        return list(cls.COMMON_VOICES.keys())

    @classmethod
    def list_voices_with_description(cls) -> List[Dict[str, str]]:
        """列出所有常用语音及其描述。

        Returns:
            语音信息字典列表
        """
        return [
            {"name": name, "description": desc}
            for name, desc in cls.COMMON_VOICES.items()
        ]

    def set_voice(self, voice: str) -> None:
        """设置语音。

        Args:
            voice: 语音名称
        """
        self._voice = voice

    def set_rate(self, rate: str) -> None:
        """设置语速。

        Args:
            rate: 语速字符串，如 "+0%", "+50%", "-20%"
        """
        self._rate = rate
