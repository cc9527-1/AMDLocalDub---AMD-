"""VideoDub 日志系统单元测试。

测试覆盖:
- INFO/WARNING/ERROR 三级日志写入
- 日志文件创建
- 内存缓冲区查询和过滤
- 异常堆栈追踪
"""

import os
import shutil
import tempfile

import pytest

from src.core.logger import Logger


@pytest.fixture
def log_dir():
    """创建临时日志目录。"""
    path = tempfile.mkdtemp()
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def logger(log_dir):
    """创建日志记录器实例。"""
    return Logger(log_dir=log_dir, max_buffer_size=100)


class TestLoggerInit:
    """日志系统初始化测试。"""

    def test_init_creates_log_dir(self, log_dir):
        """测试初始化时创建日志目录。"""
        sub_dir = os.path.join(log_dir, "sub_logs")
        logger = Logger(log_dir=sub_dir)
        assert os.path.isdir(sub_dir)
        logger.clear_buffer()

    def test_log_file_created_on_write(self, log_dir):
        """测试首次写入时创建日志文件。"""
        logger = Logger(log_dir=log_dir)
        file_path = logger.get_file_path()
        # 文件在首次写入前不存在
        logger.info("首次写入")
        assert os.path.isfile(file_path)
        logger.clear_buffer()

    def test_init_empty_buffer(self, log_dir):
        """测试初始化时缓冲区为空。"""
        logger = Logger(log_dir=log_dir)
        assert logger._buffer == []
        logger.clear_buffer()

    def test_init_sets_max_buffer_size(self, log_dir):
        """测试初始化时设置最大缓冲区大小。"""
        logger = Logger(log_dir=log_dir, max_buffer_size=500)
        assert logger._max_buffer_size == 500
        logger.clear_buffer()


class TestLoggerWrite:
    """日志写入测试。"""

    def test_write_info(self, logger):
        """测试写入 INFO 日志。"""
        logger.info("这是一条信息日志", module="TestModule")
        assert len(logger._buffer) == 1
        entry = logger._buffer[0]
        assert entry["level"] == "INFO"
        assert entry["message"] == "这是一条信息日志"
        assert entry["module"] == "TestModule"
        assert "timestamp" in entry

    def test_write_warning(self, logger):
        """测试写入 WARNING 日志。"""
        logger.warning("这是一条警告", module="WarnModule")
        entry = logger._buffer[0]
        assert entry["level"] == "WARNING"
        assert entry["module"] == "WarnModule"

    def test_write_error(self, logger):
        """测试写入 ERROR 日志。"""
        logger.error("这是一条错误", module="ErrModule")
        entry = logger._buffer[0]
        assert entry["level"] == "ERROR"
        assert entry["module"] == "ErrModule"

    def test_write_to_file(self, logger):
        """测试日志写入文件。"""
        logger.info("文件测试消息")
        file_path = logger.get_file_path()
        assert os.path.isfile(file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "文件测试消息" in content
        assert "[INFO]" in content

    def test_write_multiple_levels(self, logger):
        """测试写入多个级别的日志。"""
        logger.info("信息")
        logger.warning("警告")
        logger.error("错误")
        assert len(logger._buffer) == 3
        assert logger._buffer[0]["level"] == "INFO"
        assert logger._buffer[1]["level"] == "WARNING"
        assert logger._buffer[2]["level"] == "ERROR"

    def test_buffer_max_size(self, log_dir):
        """测试缓冲区大小限制。"""
        logger = Logger(log_dir=log_dir, max_buffer_size=5)
        for i in range(10):
            logger.info(f"消息 {i}")
        assert len(logger._buffer) == 5  # 只保留最新 5 条
        assert logger._buffer[0]["message"] == "消息 5"
        logger.clear_buffer()

    def test_error_with_exc_info(self, logger):
        """测试包含异常堆栈的错误日志。"""
        try:
            raise ValueError("测试异常")
        except ValueError:
            logger.error("发生异常", exc_info=True)

        entry = logger._buffer[0]
        assert entry["level"] == "ERROR"
        assert "发生异常" in entry["message"]
        assert "测试异常" in entry["message"]
        assert "ValueError" in entry["message"]
        logger.clear_buffer()

    def test_error_without_exc_info(self, logger):
        """测试不包含异常堆栈的错误日志。"""
        logger.error("简单错误")
        entry = logger._buffer[0]
        assert entry["message"] == "简单错误"
        assert "Traceback" not in entry["message"]
        logger.clear_buffer()

    def test_log_file_contains_timestamp(self, logger):
        """测试日志文件包含时间戳。"""
        logger.info("带时间戳测试")
        file_path = logger.get_file_path()
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "[" in content
        assert "]" in content


class TestLoggerQuery:
    """日志查询测试。"""

    def test_get_recent_all(self, logger):
        """测试获取最近的日志条目。"""
        logger.info("第一条")
        logger.info("第二条")
        logger.warning("第三条")
        recent = logger.get_recent()
        assert len(recent) == 3

    def test_get_recent_with_limit(self, logger):
        """测试限制返回条数。"""
        for i in range(10):
            logger.info(f"消息 {i}")
        recent = logger.get_recent(lines=3)
        assert len(recent) == 3

    def test_get_recent_filter_by_level(self, logger):
        """测试按级别过滤日志。"""
        logger.info("信息1")
        logger.warning("警告1")
        logger.info("信息2")
        logger.error("错误1")

        warnings = logger.get_recent(level="WARNING")
        assert len(warnings) == 1
        assert warnings[0]["level"] == "WARNING"

        errors = logger.get_recent(level="ERROR")
        assert len(errors) == 1
        assert errors[0]["level"] == "ERROR"

        infos = logger.get_recent(level="INFO")
        assert len(infos) == 2

    def test_get_recent_empty_buffer(self, logger):
        """测试空缓冲区查询。"""
        recent = logger.get_recent()
        assert recent == []

    def test_get_recent_descending_order(self, logger):
        """测试返回结果按时间降序排列。"""
        logger.info("最先")
        logger.info("中间")
        logger.info("最后")
        recent = logger.get_recent(lines=3)
        assert recent[0]["message"] == "最后"
        assert recent[2]["message"] == "最先"


class TestLoggerStats:
    """日志统计测试。"""

    def test_get_stats_empty(self, logger):
        """测试空日志统计。"""
        stats = logger.get_stats()
        assert stats["INFO"] == 0
        assert stats["WARNING"] == 0
        assert stats["ERROR"] == 0

    def test_get_stats_mixed(self, logger):
        """测试混合日志统计。"""
        logger.info("信息A")
        logger.info("信息B")
        logger.warning("警告A")
        logger.error("错误A")
        logger.error("错误B")

        stats = logger.get_stats()
        assert stats["INFO"] == 2
        assert stats["WARNING"] == 1
        assert stats["ERROR"] == 2

    def test_clear_buffer(self, logger):
        """测试清空缓冲区。"""
        logger.info("一条消息")
        assert len(logger._buffer) == 1
        logger.clear_buffer()
        assert len(logger._buffer) == 0

    def test_get_file_path_returns_absolute(self, logger):
        """测试 get_file_path 返回绝对路径。"""
        path = logger.get_file_path()
        assert os.path.isabs(path)
        assert path.endswith(".log")


class TestLoggerDefaultModule:
    """日志默认模块名测试。"""

    def test_info_default_module(self, logger):
        """测试 INFO 默认模块名为 'VideoDub'。"""
        logger.info("测试消息")
        assert logger._buffer[0]["module"] == "VideoDub"

    def test_warning_default_module(self, logger):
        """测试 WARNING 默认模块名为 'VideoDub'。"""
        logger.warning("测试警告")
        assert logger._buffer[0]["module"] == "VideoDub"

    def test_error_default_module(self, logger):
        """测试 ERROR 默认模块名为 'VideoDub'。"""
        logger.error("测试错误")
        assert logger._buffer[0]["module"] == "VideoDub"

    def test_custom_module_name(self, logger):
        """测试自定义模块名。"""
        logger.info("自定义模块", module="CustomPipeline")
        assert logger._buffer[0]["module"] == "CustomPipeline"


class TestLoggerRotation:
    """日志轮转测试。"""

    def test_log_file_name_contains_date(self, log_dir):
        """测试日志文件名包含日期。"""
        import datetime

        logger = Logger(log_dir=log_dir)
        today = datetime.datetime.now().strftime("%Y%m%d")
        assert today in logger.get_file_path()
        logger.clear_buffer()

    def test_multiple_loggers_same_dir(self, log_dir):
        """测试同一目录下多个日志实例。"""
        logger1 = Logger(log_dir=log_dir, max_buffer_size=50)
        logger2 = Logger(log_dir=log_dir, max_buffer_size=50)

        logger1.info("来自 logger1")
        logger2.info("来自 logger2")

        # 每个 logger 有自己的缓冲区
        assert len(logger1._buffer) == 1
        assert len(logger2._buffer) == 1

        # 但文件是同一个（同一天）
        assert logger1.get_file_path() == logger2.get_file_path()

        logger1.clear_buffer()
        logger2.clear_buffer()
