"""VideoDub SiliconFlow 翻译引擎实现。

通过 SiliconFlow API 调用翻译服务，
兼容 OpenAI Chat Completions API 格式。
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import httpx

from src.core.data_models import Segment, SegmentStatus, TranslationError
from src.translator.base_engine import BaseTranslator


class SiliconFlowEngine(BaseTranslator):
    """SiliconFlow API 翻译引擎。

    调用 SiliconFlow 的 OpenAI 兼容 API 进行翻译。
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        """初始化 SiliconFlow 引擎。

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
            # 清理可能的引号
            segment.translated_text = translated.strip().strip('"').strip("'")
            segment.status = SegmentStatus.TRANSLATED
        except TranslationError:
            segment.translated_text = segment.original_text
            segment.status = SegmentStatus.TRANSLATED
            segment.error_message = "翻译失败，保留原文"

        return segment

    def _call_api(self, messages: List[Dict[str, str]]) -> str:
        """调用 SiliconFlow API。

        Args:
            messages: OpenAI 格式消息列表

        Returns:
            翻译后文本

        Raises:
            TranslationError: API 调用失败
        """
        if not self._api_key:
            raise TranslationError("SiliconFlow API Key 未配置")

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
        }

        # 重试逻辑
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
                        f"API 响应中无有效 choices: {data}"
                    )
                elif response.status_code == 401:
                    raise TranslationError(
                        "SiliconFlow API 认证失败，请检查 API Key"
                    )
                elif response.status_code == 429:
                    # 速率限制，等待后重试
                    time.sleep(2 ** attempt)
                    continue
                else:
                    raise TranslationError(
                        f"SiliconFlow API 返回错误 (HTTP {response.status_code}): "
                        f"{response.text[:200]}"
                    )

            except httpx.TimeoutException as e:
                last_error = TranslationError(
                    f"SiliconFlow API 请求超时 ({self._timeout}s)"
                )
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue
            except httpx.RequestError as e:
                last_error = TranslationError(
                    f"SiliconFlow API 请求失败: {e}"
                )
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue
            except TranslationError:
                raise
            except Exception as e:
                last_error = TranslationError(
                    f"SiliconFlow API 未预期错误: {e}"
                )
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue

        raise last_error or TranslationError("SiliconFlow API 调用失败（已达最大重试次数）")

    def validate_config(self) -> bool:
        """校验 SiliconFlow 配置。

        Returns:
            配置合法返回 True

        Raises:
            TranslationError: 配置不合法
        """
        if not self._api_url:
            raise TranslationError("SiliconFlow: api_url 未配置")
        if not self._api_key:
            raise TranslationError("SiliconFlow: api_key 未配置")
        if not self._model_name:
            raise TranslationError("SiliconFlow: model_name 未配置")
        return True
