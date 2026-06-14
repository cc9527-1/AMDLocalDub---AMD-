"""VideoDub 配置管理器。

负责从 YAML 文件加载、保存、校验配置，
并提供按引擎类型获取配置的快照方法。
"""

from __future__ import annotations

import copy
import os
from typing import Any, Dict, List, Optional

import yaml

from src.core.data_models import EngineType


class ConfigManager:
    """全局配置管理器。

    封装 YAML 配置文件的读写与校验逻辑。
    所有运行时配置变更通过此类集中管理。

    Attributes:
        _config: 当前配置字典
        _path: 配置文件路径
    """

    def __init__(self, config_path: str) -> None:
        """初始化配置管理器。

        Args:
            config_path: YAML 配置文件路径

        Raises:
            FileNotFoundError: 配置文件不存在
        """
        self._config: Dict[str, Any] = {}
        self._path: str = config_path
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        self.load()

    def load(self) -> Dict[str, Any]:
        """从 YAML 文件加载配置。

        Returns:
            加载后的配置字典
        """
        with open(self._path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f)
        return self._config

    def save(self) -> None:
        """将当前配置写回 YAML 文件。"""
        with open(self._path, "w", encoding="utf-8") as f:
            yaml.dump(self._config, f, default_flow_style=False, allow_unicode=True)

    def get(self, key: str, default: Any = None) -> Any:
        """通过点分隔的键路径获取配置值。

        Args:
            key: 点分隔的配置键，如 'asr.model_path'
            default: 键不存在时的默认值

        Returns:
            配置值或默认值
        """
        parts = key.split(".")
        value: Any = self._config
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return default
            if value is None:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """通过点分隔的键路径设置配置值。

        Args:
            key: 点分隔的配置键
            value: 要设置的值
        """
        parts = key.split(".")
        target = self._config
        for part in parts[:-1]:
            if part not in target or not isinstance(target[part], dict):
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value

    def get_engine_config(self, engine_type: EngineType) -> Dict[str, Any]:
        """获取指定翻译引擎的配置字典。

        Args:
            engine_type: 翻译引擎类型

        Returns:
            引擎配置字典（深拷贝，防止外部修改）
        """
        engine_key = engine_type.value
        config = self.get(f"translation.{engine_key}", {})
        return copy.deepcopy(config)

    def get_active_engine(self) -> EngineType:
        """获取当前激活的翻译引擎类型。

        Returns:
            当前激活的 EngineType

        Raises:
            ValueError: 配置中的 active_engine 值无效
        """
        engine_str = self.get("translation.active_engine", "siliconflow")
        return EngineType.from_string(engine_str)

    def set_active_engine(self, engine_type: EngineType) -> None:
        """设置当前激活的翻译引擎。

        Args:
            engine_type: 要激活的引擎类型
        """
        self.set("translation.active_engine", engine_type.value)

    def get_all_engine_configs(self) -> Dict[str, Dict[str, Any]]:
        """获取所有翻译引擎的配置字典。

        Returns:
            键为引擎名、值为配置字典的嵌套字典
        """
        return copy.deepcopy(self.get("translation", {}))

    def validate(self) -> List[str]:
        """校验配置的完整性和合法性。

        Returns:
            错误信息列表。列表为空表示配置合法。
        """
        errors: List[str] = []

        # 校验必需的顶级键
        required_keys = ["general", "asr", "translation", "tts", "output", "splitter"]
        for key in required_keys:
            if self.get(key) is None:
                errors.append(f"缺少必需配置项: {key}")

        # 校验 ASR 配置
        if self.get("asr.model_path") is None:
            errors.append("asr.model_path 未配置")
        if self.get("asr.backend") not in ("vulkan", "rocm", "cpu"):
            errors.append("asr.backend 必须是 vulkan/rocm/cpu 之一")

        # 校验翻译引擎配置
        try:
            active = self.get_active_engine()
            engine_config = self.get_engine_config(active)
            if not engine_config.get("api_url"):
                errors.append(f"引擎 {active.value} 的 api_url 未配置")
        except ValueError as e:
            errors.append(f"active_engine 配置无效: {e}")

        # 校验 TTS 配置
        if self.get("tts.voice_zh") is None:
            errors.append("tts.voice_zh 未配置")
        if self.get("tts.voice_en") is None:
            errors.append("tts.voice_en 未配置")

        # 校验输出配置
        if self.get("output.format") not in ("mp4", "mkv"):
            errors.append("output.format 必须是 mp4/mkv 之一")
        if self.get("output.subtitle_mode") not in ("none", "soft", "burn"):
            errors.append("output.subtitle_mode 必须是 none/soft/burn 之一")

        # 校验句子拆分配置
        if self.get("splitter.max_segment_duration", 10) <= 0:
            errors.append("splitter.max_segment_duration 必须 > 0")

        return errors

    def snapshot(self) -> Dict[str, Any]:
        """获取当前配置的不可变快照。

        Returns:
            配置字典的深拷贝
        """
        return copy.deepcopy(self._config)

    def get_asr_config(self) -> Dict[str, Any]:
        """获取 ASR 配置字典。"""
        return copy.deepcopy(self.get("asr", {}))

    def get_tts_config(self) -> Dict[str, Any]:
        """获取 TTS 配置字典。"""
        return copy.deepcopy(self.get("tts", {}))

    def get_output_config(self) -> Dict[str, Any]:
        """获取输出配置字典。"""
        return copy.deepcopy(self.get("output", {}))

    def get_splitter_config(self) -> Dict[str, Any]:
        """获取句子拆分配置字典。"""
        return copy.deepcopy(self.get("splitter", {}))

    def get_general_config(self) -> Dict[str, Any]:
        """获取通用配置字典。"""
        return copy.deepcopy(self.get("general", {}))

    def get_language_config(self) -> Dict[str, Any]:
        """获取语言配置字典。"""
        return copy.deepcopy(self.get("language", {}))
