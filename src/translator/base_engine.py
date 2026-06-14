"""VideoDub 翻译引擎抽象基类。

定义所有翻译引擎的统一接口契约。
所有具体引擎（SiliconFlow / LM Studio / DeepSeek）必须实现此抽象类。
支持并发批量翻译（默认 30 句并发），大幅提升翻译速度。
"""

from __future__ import annotations

import abc
import concurrent.futures
import threading
from typing import Any, Callable, Dict, List, Optional

from src.core.data_models import Segment, TranslationError


class BaseTranslator(abc.ABC):
    """翻译引擎抽象基类。

    统一接口:
    - translate(): 翻译单个句段
    - batch_translate(): 批处理翻译多个句段（默认 30 句并发）
    - _call_api(): 实际调用底层 API
    - validate_config(): 校验引擎配置

    Attributes:
        _api_url: API 端点 URL
        _model_name: 模型名称
        _api_key: API 密钥
        _params: 额外参数字典（temperature, max_tokens, top_p 等）
        _concurrency: 并发翻译数（默认 30）
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """初始化翻译引擎。

        Args:
            config: 引擎配置字典，需包含 api_url, model_name, api_key 等
        """
        self._api_url: str = config.get("api_url", "")
        self._model_name: str = config.get("model_name", "")
        self._api_key: str = config.get("api_key", "")
        self._params: Dict[str, Any] = {
            "temperature": config.get("temperature", 0.3),
            "max_tokens": config.get("max_tokens", 1024),
            "top_p": config.get("top_p", 0.9),
        }
        self._timeout: int = config.get("timeout", 30)
        self._concurrency: int = 30  # 默认 30 句并发翻译

    @abc.abstractmethod
    def translate(
        self,
        segment: Segment,
        source_lang: str = "en",
        target_lang: str = "zh-CN",
    ) -> Segment:
        """翻译单个句段。

        Args:
            segment: 待翻译的句段
            source_lang: 源语言代码（如 "en"）
            target_lang: 目标语言代码（如 "zh-CN"）

        Returns:
            翻译完成后的 Segment（translated_text 已填充）

        Raises:
            TranslationError: 翻译失败
        """
        ...

    def batch_translate(
        self,
        segments: List[Segment],
        source_lang: str = "en",
        target_lang: str = "zh-CN",
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> List[Segment]:
        """批量翻译多个句段（默认 30 句并发执行）。

        使用 ThreadPoolExecutor 并发调用 translate()，
        大幅缩短大批量翻译的总耗时。

        Args:
            segments: 待翻译的句段列表
            source_lang: 源语言代码
            target_lang: 目标语言代码
            progress_callback: 进度回调 (percent, message)

        Returns:
            翻译完成后的句段列表
        """
        total = len(segments)
        if total == 0:
            return segments

        completed = [0]  # 线程安全的计数器
        lock = threading.Lock()
        errors: List[str] = []

        def _translate_one(seg: Segment) -> Segment:
            """在线程池中翻译单个句段。"""
            try:
                result = self.translate(seg, source_lang, target_lang)
            except TranslationError as e:
                seg.translated_text = seg.original_text
                seg.error_message = str(e)
                with lock:
                    errors.append(str(e))
            except Exception as e:
                seg.translated_text = seg.original_text
                seg.error_message = str(e)
            finally:
                with lock:
                    completed[0] += 1
                    done = completed[0]
                if progress_callback:
                    pct = min((done / total) * 100.0, 100.0)
                    progress_callback(pct, f"翻译第 {done}/{total} 句")
            return seg

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self._concurrency
        ) as executor:
            list(executor.map(_translate_one, segments))

        return segments

    @abc.abstractmethod
    def _call_api(self, messages: List[Dict[str, str]]) -> str:
        """调用底层 API 进行翻译。

        Args:
            messages: OpenAI 格式的消息列表

        Returns:
            翻译后的文本内容

        Raises:
            TranslationError: API 调用失败
        """
        ...

    @abc.abstractmethod
    def validate_config(self) -> bool:
        """校验引擎配置是否合法。

        Returns:
            配置合法返回 True

        Raises:
            TranslationError: 配置不合法时抛出异常
        """
        ...

    def _build_system_prompt(
        self, source_lang: str, target_lang: str
    ) -> str:
        """构建翻译用的 system prompt。

        Args:
            source_lang: 源语言代码
            target_lang: 目标语言代码

        Returns:
            System prompt 字符串
        """
        return (
            f"You are a professional translator. "
            f"Translate the following text from {source_lang} to {target_lang}. "
            f"Only output the translation, no explanations, no notes, no quotation marks."
        )

    def _build_messages(
        self, text: str, source_lang: str, target_lang: str
    ) -> List[Dict[str, str]]:
        """构建 OpenAI 格式的消息列表。

        Args:
            text: 待翻译文本
            source_lang: 源语言
            target_lang: 目标语言

        Returns:
            消息列表 [system, user]
        """
        return [
            {
                "role": "system",
                "content": self._build_system_prompt(source_lang, target_lang),
            },
            {
                "role": "user",
                "content": text,
            },
        ]
