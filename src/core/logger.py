"""VideoDub 分级日志系统。

支持 INFO / WARNING / ERROR 三级日志，
按日期滚动存储到 logs/ 目录，并可查询最近的日志条目供前端展示。
"""

from __future__ import annotations

import datetime
import os
import sys
import traceback
from typing import Any, Dict, List, Optional


class Logger:
    """分级日志记录器。

    日志文件格式:
        [YYYY-MM-DD HH:MM:SS.mmm] [LEVEL] [ModuleName] 消息内容

    Attributes:
        _log_dir: 日志文件存储目录
        _log_file: 当前日志文件路径
        _buffer: 内存缓冲区，用于前端实时查询
        _max_buffer_size: 内存缓冲区最大条目数
    """

    _LEVELS: Dict[str, int] = {
        "INFO": 0,
        "WARNING": 1,
        "ERROR": 2,
    }

    def __init__(self, log_dir: str = "logs", max_buffer_size: int = 1000) -> None:
        """初始化日志系统。

        Args:
            log_dir: 日志文件目录路径
            max_buffer_size: 内存缓冲区最大条目数
        """
        self._log_dir: str = log_dir
        self._max_buffer_size: int = max_buffer_size
        self._buffer: List[Dict[str, Any]] = []
        self._log_file: str = ""

        # 确保日志目录存在
        os.makedirs(self._log_dir, exist_ok=True)

        # 初始化日志文件
        self._rotate_log_file()

    def _rotate_log_file(self) -> None:
        """按日期切换日志文件。"""
        today = datetime.datetime.now().strftime("%Y%m%d")
        self._log_file = os.path.join(self._log_dir, f"amdlocaldub_{today}.log")

    def _get_timestamp(self) -> str:
        """获取格式化的时间戳字符串。

        Returns:
            格式: YYYY-MM-DD HH:MM:SS.mmm
        """
        now = datetime.datetime.now()
        return now.strftime("%Y-%m-%d %H:%M:%S.") + f"{now.microsecond // 1000:03d}"

    def _write(self, level: str, message: str, module: str) -> None:
        """内部写入方法。

        Args:
            level: 日志级别
            message: 日志消息
            module: 模块名称
        """
        timestamp = self._get_timestamp()
        log_line = f"[{timestamp}] [{level}] [{module}] {message}"

        # 写入文件
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(log_line + "\n")
        except OSError as e:
            # 文件写入失败时回退到 stderr
            print(f"[LOGGER ERROR] 写入日志文件失败: {e}", file=sys.stderr)
            print(log_line, file=sys.stderr)

        # 写入内存缓冲区
        entry: Dict[str, Any] = {
            "timestamp": timestamp,
            "level": level,
            "module": module,
            "message": message,
        }
        self._buffer.append(entry)

        # 限制缓冲区大小
        if len(self._buffer) > self._max_buffer_size:
            self._buffer = self._buffer[-self._max_buffer_size:]

    def info(self, message: str, module: str = "VideoDub") -> None:
        """记录 INFO 级别日志。

        Args:
            message: 日志消息
            module: 模块名称
        """
        self._write("INFO", message, module)

    def warning(self, message: str, module: str = "VideoDub") -> None:
        """记录 WARNING 级别日志。

        Args:
            message: 日志消息
            module: 模块名称
        """
        self._write("WARNING", message, module)

    def error(
        self, message: str, module: str = "VideoDub", exc_info: bool = False
    ) -> None:
        """记录 ERROR 级别日志。

        Args:
            message: 日志消息
            module: 模块名称
            exc_info: 是否附加异常堆栈信息
        """
        if exc_info:
            tb = traceback.format_exc()
            if tb and tb != "NoneType: None\n":
                message = f"{message}\n{tb}"
        self._write("ERROR", message, module)

    def get_recent(
        self, level: Optional[str] = None, lines: int = 50
    ) -> List[Dict[str, Any]]:
        """获取最近的日志条目。

        Args:
            level: 过滤级别，None 表示不过滤
            lines: 返回的最大条目数

        Returns:
            日志条目字典列表，按时间降序排列
        """
        result = list(reversed(self._buffer))
        if level:
            level_upper = level.upper()
            result = [e for e in result if e["level"] == level_upper]
        return result[:lines]

    def get_file_path(self) -> str:
        """获取当前日志文件路径。

        Returns:
            日志文件绝对路径
        """
        return os.path.abspath(self._log_file)

    def get_all_plain_text(self, level: Optional[str] = None) -> str:
        """获取所有日志的纯文本格式（用于复制到剪贴板）。

        Args:
            level: 过滤级别

        Returns:
            纯文本格式的日志内容
        """
        entries = self.get_recent(level=level, lines=9999)
        lines: List[str] = []
        for entry in reversed(entries):
            ts = entry.get("timestamp", "")
            lv = entry.get("level", "INFO")
            mod = entry.get("module", "")
            msg = entry.get("message", "")
            lines.append(f"[{ts}] [{lv}] [{mod}] {msg}")
        return "\n".join(lines)

    def clear_buffer(self) -> None:
        """清空内存缓冲区。"""
        self._buffer.clear()

    def get_stats(self) -> Dict[str, int]:
        """获取日志统计信息。

        Returns:
            各级别日志条数
        """
        stats: Dict[str, int] = {"INFO": 0, "WARNING": 0, "ERROR": 0}
        for entry in self._buffer:
            level = entry.get("level", "INFO")
            if level in stats:
                stats[level] += 1
        return stats
