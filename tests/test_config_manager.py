"""VideoDub 配置管理器单元测试。

测试覆盖:
- 配置加载/获取/设置 (点分隔键路径)
- 引擎配置获取
- 配置校验 (合法/非法配置)
- 配置快照不可变
"""

import copy
import os
import tempfile

import pytest
import yaml

from src.core.config_manager import ConfigManager
from src.core.data_models import EngineType


# 完整的合法配置样例
VALID_CONFIG = {
    "general": {
        "working_dir": "outputs",
        "log_dir": "logs",
        "models_dir": "models",
        "temp_cleanup": True,
        "max_retries": 3,
        "retry_delay": 3.0,
    },
    "asr": {
        "model_path": "models/ggml-large-v3.bin",
        "model_type": "large-v3",
        "backend": "vulkan",
        "gpu_device": 0,
        "whisper_executable": "whisper-cli",
        "language": "en",
        "extra_params": ["--threads", "8"],
    },
    "translation": {
        "active_engine": "siliconflow",
        "siliconflow": {
            "api_url": "https://api.siliconflow.cn/v1/chat/completions",
            "api_key": "test_key",
            "model_name": "Qwen/Qwen2.5-7B-Instruct",
            "temperature": 0.3,
            "max_tokens": 1024,
            "top_p": 0.9,
            "timeout": 30,
        },
        "lmstudio": {
            "api_url": "http://localhost:1234/v1/chat/completions",
            "api_key": "",
            "model_name": "",
            "temperature": 0.3,
            "max_tokens": 1024,
            "top_p": 0.9,
            "timeout": 60,
        },
        "deepseek": {
            "api_url": "https://api.deepseek.com/v1/chat/completions",
            "api_key": "test_deepseek_key",
            "model_name": "deepseek-chat",
            "temperature": 0.3,
            "max_tokens": 1024,
            "top_p": 0.9,
            "timeout": 30,
        },
    },
    "tts": {
        "voice_zh": "zh-CN-XiaoxiaoNeural",
        "voice_en": "en-US-JennyNeural",
        "rate": "+0%",
        "volume": "+0%",
        "connect_timeout": 10,
    },
    "output": {
        "format": "mp4",
        "subtitle_mode": "soft",
        "video_codec": "libx264",
        "audio_codec": "aac",
        "crf": 23,
    },
    "splitter": {
        "max_segment_duration": 10.0,
        "min_segment_duration": 0.5,
        "merge_threshold": 0.3,
    },
    "language": {
        "source_lang": "en",
        "target_lang": "zh-CN",
    },
}


@pytest.fixture
def valid_config_path():
    """创建合法配置文件的临时路径。"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", encoding="utf-8", delete=False
    ) as f:
        yaml.dump(VALID_CONFIG, f, allow_unicode=True)
        config_path = f.name
    yield config_path
    os.unlink(config_path)


@pytest.fixture
def manager(valid_config_path):
    """创建配置管理器实例。"""
    return ConfigManager(valid_config_path)


class TestConfigManagerInit:
    """配置管理器初始化测试。"""

    def test_init_with_valid_path(self, valid_config_path):
        """测试使用合法路径初始化。"""
        mgr = ConfigManager(valid_config_path)
        assert mgr._config is not None
        assert mgr._path == valid_config_path

    def test_init_with_nonexistent_path(self):
        """测试使用不存在的路径应抛出 FileNotFoundError。"""
        with pytest.raises(FileNotFoundError, match="配置文件不存在"):
            ConfigManager("/nonexistent/path/config.yaml")

    def test_init_loads_config(self, valid_config_path):
        """测试初始化时自动加载配置。"""
        mgr = ConfigManager(valid_config_path)
        assert mgr.get("general.working_dir") == "outputs"


class TestConfigManagerGet:
    """配置获取测试。"""

    def test_get_simple_key(self, manager):
        """测试获取顶级键值。"""
        assert manager.get("general") is not None
        assert isinstance(manager.get("general"), dict)

    def test_get_nested_key(self, manager):
        """测试获取嵌套键值。"""
        assert manager.get("general.working_dir") == "outputs"
        assert manager.get("asr.backend") == "vulkan"
        assert manager.get("tts.voice_zh") == "zh-CN-XiaoxiaoNeural"

    def test_get_deep_nested_key(self, manager):
        """测试获取深层嵌套键值。"""
        assert (
            manager.get("translation.siliconflow.api_url")
            == "https://api.siliconflow.cn/v1/chat/completions"
        )

    def test_get_nonexistent_key_returns_default(self, manager):
        """测试获取不存在的键应返回默认值。"""
        assert manager.get("nonexistent.key") is None
        assert manager.get("nonexistent.key", "default_val") == "default_val"

    def test_get_partial_nonexistent_returns_default(self, manager):
        """测试部分路径不存在的键应返回默认值。"""
        assert manager.get("general.nonexistent") is None
        assert manager.get("general.nonexistent.subkey") is None

    def test_get_returns_none_for_none_value(self, manager):
        """测试值本身为 None 时返回默认值。"""
        # 创建一个临时配置，其中某个字段为 None
        assert manager.get("asr.nonexistent") is None


class TestConfigManagerSet:
    """配置设置测试。"""

    def test_set_simple_value(self, manager):
        """测试设置顶级键值。"""
        manager.set("general.working_dir", "new_outputs")
        assert manager.get("general.working_dir") == "new_outputs"

    def test_set_nested_value(self, manager):
        """测试设置嵌套键值。"""
        manager.set("asr.backend", "rocm")
        assert manager.get("asr.backend") == "rocm"

    def test_set_new_nested_key(self, manager):
        """测试设置新的嵌套键路径（自动创建中间字典）。"""
        manager.set("new.section.value", 42)
        assert manager.get("new.section.value") == 42

    def test_set_with_save_and_reload(self, manager, valid_config_path):
        """测试设置值后保存并重新加载。"""
        manager.set("general.working_dir", "modified")
        manager.save()

        # 重新加载
        mgr2 = ConfigManager(valid_config_path)
        assert mgr2.get("general.working_dir") == "modified"

    def test_set_integer_value(self, manager):
        """测试设置整数值。"""
        manager.set("general.max_retries", 5)
        assert manager.get("general.max_retries") == 5

    def test_set_boolean_value(self, manager):
        """测试设置布尔值。"""
        manager.set("general.temp_cleanup", False)
        assert manager.get("general.temp_cleanup") is False


class TestConfigManagerEngineConfig:
    """引擎配置获取测试。"""

    def test_get_engine_config(self, manager):
        """测试获取指定引擎的配置。"""
        config = manager.get_engine_config(EngineType.SILICONFLOW)
        assert config["api_key"] == "test_key"
        assert config["model_name"] == "Qwen/Qwen2.5-7B-Instruct"

    def test_get_engine_config_immutable(self, manager):
        """测试引擎配置为深拷贝，修改不影响原配置。"""
        config = manager.get_engine_config(EngineType.SILICONFLOW)
        config["api_key"] = "modified"
        # 重新获取应不受影响
        config2 = manager.get_engine_config(EngineType.SILICONFLOW)
        assert config2["api_key"] == "test_key"

    def test_get_active_engine(self, manager):
        """测试获取当前激活引擎。"""
        engine = manager.get_active_engine()
        assert engine == EngineType.SILICONFLOW

    def test_set_active_engine(self, manager):
        """测试设置当前激活引擎。"""
        manager.set_active_engine(EngineType.DEEPSEEK)
        assert manager.get_active_engine() == EngineType.DEEPSEEK
        assert manager.get("translation.active_engine") == "deepseek"

    def test_get_all_engine_configs(self, manager):
        """测试获取所有引擎配置。"""
        all_configs = manager.get_all_engine_configs()
        assert "siliconflow" in all_configs
        assert "lmstudio" in all_configs
        assert "deepseek" in all_configs
        assert all_configs["siliconflow"]["api_key"] == "test_key"

    def test_get_all_engine_configs_immutable(self, manager):
        """测试所有引擎配置为深拷贝。"""
        all_configs = manager.get_all_engine_configs()
        all_configs["siliconflow"]["api_key"] = "hacked"
        assert manager.get_engine_config(EngineType.SILICONFLOW)["api_key"] == "test_key"


class TestConfigManagerValidate:
    """配置校验测试。"""

    def test_valid_config_returns_empty_errors(self, manager):
        """测试合法配置返回空错误列表。"""
        errors = manager.validate()
        assert errors == []

    def test_missing_required_key(self, valid_config_path):
        """测试缺少必需顶级键应报告错误。"""
        config = copy.deepcopy(VALID_CONFIG)
        del config["general"]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", encoding="utf-8", delete=False
        ) as f:
            yaml.dump(config, f, allow_unicode=True)
            path = f.name
        try:
            mgr = ConfigManager(path)
            errors = mgr.validate()
            assert any("缺少必需配置项: general" in e for e in errors)
        finally:
            os.unlink(path)

    def test_missing_asr_model_path(self, valid_config_path):
        """测试缺少 asr.model_path 应报告错误。"""
        config = copy.deepcopy(VALID_CONFIG)
        del config["asr"]["model_path"]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", encoding="utf-8", delete=False
        ) as f:
            yaml.dump(config, f, allow_unicode=True)
            path = f.name
        try:
            mgr = ConfigManager(path)
            errors = mgr.validate()
            assert any("asr.model_path 未配置" in e for e in errors)
        finally:
            os.unlink(path)

    def test_invalid_asr_backend(self, valid_config_path):
        """测试不合法的 asr.backend 应报告错误。"""
        config = copy.deepcopy(VALID_CONFIG)
        config["asr"]["backend"] = "invalid_backend"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", encoding="utf-8", delete=False
        ) as f:
            yaml.dump(config, f, allow_unicode=True)
            path = f.name
        try:
            mgr = ConfigManager(path)
            errors = mgr.validate()
            assert any("asr.backend 必须是" in e for e in errors)
        finally:
            os.unlink(path)

    def test_invalid_output_format(self, valid_config_path):
        """测试不合法的 output.format 应报告错误。"""
        config = copy.deepcopy(VALID_CONFIG)
        config["output"]["format"] = "avi"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", encoding="utf-8", delete=False
        ) as f:
            yaml.dump(config, f, allow_unicode=True)
            path = f.name
        try:
            mgr = ConfigManager(path)
            errors = mgr.validate()
            assert any("output.format 必须是" in e for e in errors)
        finally:
            os.unlink(path)

    def test_invalid_subtitle_mode(self, valid_config_path):
        """测试不合法的 subtitle_mode 应报告错误。"""
        config = copy.deepcopy(VALID_CONFIG)
        config["output"]["subtitle_mode"] = "invalid"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", encoding="utf-8", delete=False
        ) as f:
            yaml.dump(config, f, allow_unicode=True)
            path = f.name
        try:
            mgr = ConfigManager(path)
            errors = mgr.validate()
            assert any("subtitle_mode 必须是" in e for e in errors)
        finally:
            os.unlink(path)

    def test_invalid_max_segment_duration(self, valid_config_path):
        """测试非法的 splitter.max_segment_duration 应报告错误。"""
        config = copy.deepcopy(VALID_CONFIG)
        config["splitter"]["max_segment_duration"] = -5
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", encoding="utf-8", delete=False
        ) as f:
            yaml.dump(config, f, allow_unicode=True)
            path = f.name
        try:
            mgr = ConfigManager(path)
            errors = mgr.validate()
            assert any("max_segment_duration 必须 > 0" in e for e in errors)
        finally:
            os.unlink(path)

    def test_missing_tts_voice(self, valid_config_path):
        """测试缺少 tts 语音配置应报告错误。"""
        config = copy.deepcopy(VALID_CONFIG)
        del config["tts"]["voice_zh"]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", encoding="utf-8", delete=False
        ) as f:
            yaml.dump(config, f, allow_unicode=True)
            path = f.name
        try:
            mgr = ConfigManager(path)
            errors = mgr.validate()
            assert any("tts.voice_zh 未配置" in e for e in errors)
        finally:
            os.unlink(path)

    def test_invalid_active_engine(self, valid_config_path):
        """测试无效的 active_engine 应报告错误。"""
        config = copy.deepcopy(VALID_CONFIG)
        config["translation"]["active_engine"] = "nonexistent_engine"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", encoding="utf-8", delete=False
        ) as f:
            yaml.dump(config, f, allow_unicode=True)
            path = f.name
        try:
            mgr = ConfigManager(path)
            errors = mgr.validate()
            assert any("active_engine 配置无效" in e for e in errors)
        finally:
            os.unlink(path)

    def test_missing_engine_api_url(self, valid_config_path):
        """测试缺少引擎 api_url 应报告错误。"""
        config = copy.deepcopy(VALID_CONFIG)
        del config["translation"]["siliconflow"]["api_url"]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", encoding="utf-8", delete=False
        ) as f:
            yaml.dump(config, f, allow_unicode=True)
            path = f.name
        try:
            mgr = ConfigManager(path)
            errors = mgr.validate()
            assert any("api_url 未配置" in e for e in errors)
        finally:
            os.unlink(path)


class TestConfigManagerSnapshot:
    """配置快照测试。"""

    def test_snapshot_immutable(self, manager):
        """测试快照为深拷贝，修改快照不影响原配置。"""
        snap = manager.snapshot()
        snap["general"]["working_dir"] = "hacked"
        assert manager.get("general.working_dir") == "outputs"

    def test_snapshot_contains_all_keys(self, manager):
        """测试快照包含所有配置项。"""
        snap = manager.snapshot()
        assert "general" in snap
        assert "asr" in snap
        assert "translation" in snap
        assert "tts" in snap
        assert "output" in snap
        assert "splitter" in snap


class TestConfigManagerSubConfig:
    """子配置获取测试。"""

    def test_get_asr_config(self, manager):
        """测试获取 ASR 配置。"""
        asr_config = manager.get_asr_config()
        assert asr_config["backend"] == "vulkan"
        assert asr_config["model_path"] == "models/ggml-large-v3.bin"

    def test_get_tts_config(self, manager):
        """测试获取 TTS 配置。"""
        tts_config = manager.get_tts_config()
        assert tts_config["voice_zh"] == "zh-CN-XiaoxiaoNeural"

    def test_get_output_config(self, manager):
        """测试获取输出配置。"""
        output_config = manager.get_output_config()
        assert output_config["format"] == "mp4"

    def test_get_splitter_config(self, manager):
        """测试获取拆分配置。"""
        splitter_config = manager.get_splitter_config()
        assert splitter_config["max_segment_duration"] == 10.0

    def test_get_general_config(self, manager):
        """测试获取通用配置。"""
        general_config = manager.get_general_config()
        assert general_config["working_dir"] == "outputs"

    def test_get_language_config(self, manager):
        """测试获取语言配置。"""
        lang_config = manager.get_language_config()
        assert lang_config["source_lang"] == "en"
        assert lang_config["target_lang"] == "zh-CN"
