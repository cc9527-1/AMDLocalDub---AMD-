"""VideoDub 翻译引擎工厂单元测试。

测试覆盖:
- 引擎工厂创建各类型引擎
- 引擎类型枚举转换
- 配置校验
- 可用引擎列表
"""

import pytest

from src.core.data_models import EngineType
from src.translator.base_engine import BaseTranslator
from src.translator.deepseek_engine import DeepSeekEngine
from src.translator.lmstudio_engine import LMStudioEngine
from src.translator.siliconflow_engine import SiliconFlowEngine
from src.translator.translation_engine import TranslationEngineFactory


# 最小配置
MINIMAL_CONFIG = {
    "api_url": "https://test.api.com/v1/chat/completions",
    "api_key": "test_key",
    "model_name": "test-model",
    "temperature": 0.3,
    "max_tokens": 1024,
    "top_p": 0.9,
    "timeout": 30,
}


class TestTranslationEngineFactory:
    """翻译引擎工厂测试。"""

    def test_create_siliconflow_engine(self):
        """测试创建 SiliconFlow 引擎。"""
        engine = TranslationEngineFactory.create_engine(
            EngineType.SILICONFLOW, MINIMAL_CONFIG
        )
        assert isinstance(engine, SiliconFlowEngine)
        assert isinstance(engine, BaseTranslator)

    def test_create_lmstudio_engine(self):
        """测试创建 LM Studio 引擎。"""
        engine = TranslationEngineFactory.create_engine(
            EngineType.LM_STUDIO, MINIMAL_CONFIG
        )
        assert isinstance(engine, LMStudioEngine)
        assert isinstance(engine, BaseTranslator)

    def test_create_deepseek_engine(self):
        """测试创建 DeepSeek 引擎。"""
        engine = TranslationEngineFactory.create_engine(
            EngineType.DEEPSEEK, MINIMAL_CONFIG
        )
        assert isinstance(engine, DeepSeekEngine)
        assert isinstance(engine, BaseTranslator)

    def test_create_unknown_engine_raises(self):
        """测试创建未知引擎抛出 ValueError。"""
        with pytest.raises(ValueError, match="不支持的引擎类型"):
            TranslationEngineFactory.create_engine(
                "unknown_type", MINIMAL_CONFIG  # type: ignore
            )

    def test_list_available_engines(self):
        """测试列出可用引擎类型。"""
        engines = TranslationEngineFactory.list_available_engines()
        assert EngineType.SILICONFLOW in engines
        assert EngineType.LM_STUDIO in engines
        assert EngineType.DEEPSEEK in engines
        assert len(engines) == 3

    def test_list_engine_names(self):
        """测试列出可用引擎名称。"""
        names = TranslationEngineFactory.list_engine_names()
        assert "siliconflow" in names
        assert "lmstudio" in names
        assert "deepseek" in names
        assert len(names) == 3

    def test_validate_engine_config_valid(self):
        """测试合法配置校验。"""
        config = {
            "api_url": "https://api.siliconflow.cn/v1/chat/completions",
            "api_key": "test_key",
            "model_name": "test-model",
        }
        result = TranslationEngineFactory.validate_engine_config(
            EngineType.SILICONFLOW, config
        )
        assert result is True

    def test_validate_engine_config_invalid(self):
        """测试不合法配置校验。"""
        config = {
            "api_url": "",
            "api_key": "",
            "model_name": "",
        }
        with pytest.raises(Exception):
            TranslationEngineFactory.validate_engine_config(
                EngineType.SILICONFLOW, config
            )

    def test_validate_engine_config_unknown_type(self):
        """测试未知引擎类型校验。"""
        with pytest.raises(ValueError):
            TranslationEngineFactory.validate_engine_config(
                "unknown_type", MINIMAL_CONFIG  # type: ignore
            )


class TestBaseTranslator:
    """翻译引擎基类测试。"""

    def test_init_sets_config(self):
        """测试基类初始化设置配置。"""
        engine = SiliconFlowEngine(MINIMAL_CONFIG)
        assert engine._api_url == "https://test.api.com/v1/chat/completions"
        assert engine._api_key == "test_key"
        assert engine._model_name == "test-model"
        assert engine._params["temperature"] == 0.3
        assert engine._params["max_tokens"] == 1024
        assert engine._params["top_p"] == 0.9
        assert engine._timeout == 30

    def test_init_empty_config(self):
        """测试空配置初始化。"""
        engine = SiliconFlowEngine({})
        assert engine._api_url == ""
        assert engine._api_key == ""
        assert engine._model_name == ""
        assert engine._timeout == 30  # 默认值

    def test_build_system_prompt(self):
        """测试构建 system prompt。"""
        engine = SiliconFlowEngine(MINIMAL_CONFIG)
        prompt = engine._build_system_prompt("en", "zh-CN")
        assert "en" in prompt
        assert "zh-CN" in prompt
        assert "professional translator" in prompt

    def test_build_messages(self):
        """测试构建消息列表。"""
        engine = SiliconFlowEngine(MINIMAL_CONFIG)
        messages = engine._build_messages("Hello world", "en", "zh-CN")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "Hello world"


class TestSiliconFlowEngineSpecific:
    """SiliconFlow 引擎特性测试。"""

    def test_validate_config_valid(self):
        """测试合法配置。"""
        config = {
            "api_url": "https://api.test.com",
            "api_key": "key123",
            "model_name": "model-v1",
        }
        engine = SiliconFlowEngine(config)
        assert engine.validate_config() is True

    def test_validate_config_missing_api_url(self):
        """测试缺少 api_url。"""
        engine = SiliconFlowEngine({"api_key": "key", "model_name": "model"})
        with pytest.raises(Exception, match="api_url 未配置"):
            engine.validate_config()

    def test_validate_config_missing_api_key(self):
        """测试缺少 api_key。"""
        engine = SiliconFlowEngine({"api_url": "url", "model_name": "model"})
        with pytest.raises(Exception, match="api_key 未配置"):
            engine.validate_config()

    def test_validate_config_missing_model_name(self):
        """测试缺少 model_name。"""
        engine = SiliconFlowEngine({"api_url": "url", "api_key": "key"})
        with pytest.raises(Exception, match="model_name 未配置"):
            engine.validate_config()

    def test_translate_empty_text(self):
        """测试空文本翻译。"""
        from src.core.data_models import Segment

        engine = SiliconFlowEngine(MINIMAL_CONFIG)
        seg = Segment(index=1, original_text="", start_time=0.0, end_time=1.0)
        result = engine.translate(seg)
        assert result.translated_text == ""
        assert result.status.name == "TRANSLATED"


@pytest.mark.skip(reason="需要实际的 API 连接")
class TestSiliconFlowEngineIntegration:
    """需要实际 API 连接的集成测试。"""

    def test_actual_translate(self):
        """实际翻译测试（需要 API Key）。"""
        config = {
            "api_url": "https://api.siliconflow.cn/v1/chat/completions",
            "api_key": "your_key_here",
            "model_name": "Qwen/Qwen2.5-7B-Instruct",
        }
        engine = SiliconFlowEngine(config)
        from src.core.data_models import Segment

        seg = Segment(index=1, original_text="Hello world", start_time=0.0, end_time=1.0)
        result = engine.translate(seg)
        assert result.translated_text != ""
