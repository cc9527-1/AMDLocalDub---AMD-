"""VideoDub 翻译引擎工厂。

根据 EngineType 动态创建对应的翻译引擎实例。
支持运行时动态切换引擎。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.core.data_models import EngineType
from src.translator.base_engine import BaseTranslator
from src.translator.deepseek_engine import DeepSeekEngine
from src.translator.lmstudio_engine import LMStudioEngine
from src.translator.siliconflow_engine import SiliconFlowEngine


class TranslationEngineFactory:
    """翻译引擎工厂。

    根据 EngineType 创建对应的翻译引擎实例。
    支持在运行时动态切换引擎。

    Usage:
        factory = TranslationEngineFactory()
        engine = factory.create_engine(EngineType.SILICONFLOW, config)
    """

    # 引擎类型到实现类的映射
    _ENGINE_MAP = {
        EngineType.SILICONFLOW: SiliconFlowEngine,
        EngineType.LM_STUDIO: LMStudioEngine,
        EngineType.DEEPSEEK: DeepSeekEngine,
    }

    @classmethod
    def create_engine(
        cls, engine_type: EngineType, config: Dict[str, Any]
    ) -> BaseTranslator:
        """创建指定类型的翻译引擎实例。

        Args:
            engine_type: 翻译引擎类型枚举
            config: 引擎配置字典

        Returns:
            翻译引擎实例（BaseTranslator 子类）

        Raises:
            ValueError: 不支持的引擎类型
        """
        engine_class = cls._ENGINE_MAP.get(engine_type)
        if engine_class is None:
            raise ValueError(
                f"不支持的引擎类型: {engine_type}。"
                f"支持的类型: {[e.value for e in cls._ENGINE_MAP]}"
            )

        return engine_class(config)

    @classmethod
    def list_available_engines(cls) -> List[EngineType]:
        """列出所有可用的引擎类型。

        Returns:
            可用的 EngineType 列表
        """
        return list(cls._ENGINE_MAP.keys())

    @classmethod
    def list_engine_names(cls) -> List[str]:
        """列出所有可用的引擎名称。

        Returns:
            引擎名称字符串列表
        """
        return [e.value for e in cls._ENGINE_MAP]

    @classmethod
    def validate_engine_config(
        cls, engine_type: EngineType, config: Dict[str, Any]
    ) -> bool:
        """校验指定引擎的配置是否合法。

        Args:
            engine_type: 引擎类型
            config: 配置字典

        Returns:
            配置合法返回 True

        Raises:
            ValueError: 引擎类型不支持
        """
        engine = cls.create_engine(engine_type, config)
        return engine.validate_config()
