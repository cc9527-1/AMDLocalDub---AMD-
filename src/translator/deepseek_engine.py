"""VideoDub DeepSeek 翻译引擎实现。

通过 DeepSeek API 调用翻译服务，
兼容 OpenAI Chat Completions API 格式。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import httpx

from src.core.data_models import Segment, SegmentStatus, TranslationError
from src.translator.base_engine import BaseTranslator


class DeepSeekEngine(BaseTranslator):
    """DeepSeek API 翻译引擎。

    调用 DeepSeek 的 OpenAI 兼容 API 进行翻译。
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """初始化 DeepSeek 引擎。

        Args:
            config: 配置字典（需包含 api_key, api_url, model_name 等）
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
        """调用 DeepSeek API。

        Args:
            messages: OpenAI 格式消息列表

        Returns:
            翻译后文本

        Raises:
            TranslationError: API 调用失败
        """
        if not self._api_key:
            raise TranslationError("DeepSeek API Key 未配置")

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": self._model_name,
            "messages": messages,
            "temperature": self._params["temperature"],
            "max_tokens": self._params["max_tokens"],
            "top_p": self._params["top_p"],
            "stream": False,
        }

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
                        f"DeepSeek API 响应中无有效 choices: {data}"
                    )
                elif response.status_code == 401:
                    raise TranslationError(
                        "DeepSeek API 认证失败，请检查 API Key"
                    )
                elif response.status_code == 429:
                    # 速率限制，等待后重试
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                    continue
                else:
                    raise TranslationError(
                        f"DeepSeek API 返回错误 (HTTP {response.status_code}): "
                        f"{response.text[:200]}"
                    )

            except httpx.TimeoutException as e:
                last_error = TranslationError(
                    f"DeepSeek API 请求超时 ({self._timeout}s)"
                )
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue
            except httpx.RequestError as e:
                last_error = TranslationError(
                    f"DeepSeek API 请求失败: {e}"
                )
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue
            except TranslationError:
                raise
            except Exception as e:
                last_error = TranslationError(
                    f"DeepSeek API 未预期错误: {e}"
                )
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue

        raise last_error or TranslationError("DeepSeek API 调用失败（已达最大重试次数）")

    def validate_config(self) -> bool:
        """校验 DeepSeek 配置。

        Returns:
            配置合法返回 True

        Raises:
            TranslationError: 配置不合法
        """
        if not self._api_url:
            raise TranslationError("DeepSeek: api_url 未配置")
        if not self._api_key:
            raise TranslationError("DeepSeek: api_key 未配置")
        if not self._model_name:
            raise TranslationError("DeepSeek: model_name 未配置")
        return True
