"""VideoDub LM Studio 本地翻译引擎实现。

通过 LM Studio 提供的本地 API 调用翻译服务，
兼容 OpenAI Chat Completions API 格式。
无需 API Key，所有推理在本地完成。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import httpx

from src.core.data_models import Segment, SegmentStatus, TranslationError
from src.translator.base_engine import BaseTranslator


class LMStudioEngine(BaseTranslator):
    """LM Studio 本地翻译引擎。

    调用 LM Studio 的本地 API 进行翻译。
    所有推理在本地 GPU/CPU 上完成，无需联网。
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """初始化 LM Studio 引擎。

        Args:
            config: 配置字典
        """
        super().__init__(config)

    def translate(
        self,
        segment: Segment,
        source_lang: str = "en",
        target_lang: str = "zh-CN",
    ) -> Segment:
        """翻译单个句段。

        Args:
            segment: 待翻译句段
            source_lang: 源语言
            target_lang: 目标语言

        Returns:
            翻译后的句段
        """
        if not segment.original_text.strip():
            segment.translated_text = ""
            segment.status = SegmentStatus.TRANSLATED
            return segment

        messages = self._build_messages(
            segment.original_text, source_lang, target_lang
        )

        try:
            translated = self._call_api(messages)
            segment.translated_text = translated.strip().strip('"').strip("'")
            segment.status = SegmentStatus.TRANSLATED
        except TranslationError:
            segment.translated_text = segment.original_text
            segment.status = SegmentStatus.TRANSLATED
            segment.error_message = "翻译失败，保留原文"

        return segment

    def _call_api(self, messages: List[Dict[str, str]]) -> str:
        """调用 LM Studio 本地 API。

        Args:
            messages: OpenAI 格式消息列表

        Returns:
            翻译后文本

        Raises:
            TranslationError: API 调用失败
        """
        headers = {
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "messages": messages,
            "temperature": self._params["temperature"],
            "max_tokens": self._params["max_tokens"],
            "top_p": self._params["top_p"],
            "stream": False,
        }

        # 如果指定了模型名则传入
        if self._model_name:
            payload["model"] = self._model_name

        max_retries = 3
        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(
                        self._api_url,
                        headers=headers,
                        json=payload,
                    )

                if response.status_code == 200:
                    data = response.json()
                    choices = data.get("choices", [])
                    if choices:
                        content = choices[0].get("message", {}).get("content", "")
                        return content
                    raise TranslationError(
                        f"LM Studio 响应中无有效 choices: {data}"
                    )
                elif response.status_code == 404:
                    raise TranslationError(
                        "LM Studio API 端点未找到，请确认 LM Studio 已启动并加载了模型"
                    )
                elif response.status_code == 503:
                    # 模型加载中，等待后重试
                    if attempt < max_retries - 1:
                        time.sleep(5)
                        continue
                    raise TranslationError(
                        "LM Studio 模型未就绪，请确认已加载模型"
                    )
                else:
                    raise TranslationError(
                        f"LM Studio API 返回错误 (HTTP {response.status_code}): "
                        f"{response.text[:200]}"
                    )

            except httpx.TimeoutException as e:
                last_error = TranslationError(
                    f"LM Studio API 请求超时 ({self._timeout}s)"
                )
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue
            except httpx.RequestError as e:
                last_error = TranslationError(
                    f"LM Studio 连接失败: {e}。请确认 LM Studio 已启动并运行在 {self._api_url}"
                )
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue
            except TranslationError:
                raise
            except Exception as e:
                last_error = TranslationError(
                    f"LM Studio 未预期错误: {e}"
                )
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue

        raise last_error or TranslationError("LM Studio API 调用失败（已达最大重试次数）")

    def validate_config(self) -> bool:
        """校验 LM Studio 配置。

        Returns:
            配置合法返回 True

        Raises:
            TranslationError: 配置不合法
        """
        if not self._api_url:
            raise TranslationError("LM Studio: api_url 未配置")
        # LM Studio 不需要 api_key
        return True
