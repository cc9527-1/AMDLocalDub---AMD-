"""VideoDub 任务队列管理器。

管理多个视频文件的排队处理，支持：
- 添加任务到队列
- 顺序处理（上一个完成自动启动下一个）
- 查询队列状态
- 取消队列中的任务
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class QueueTaskStatus(Enum):
    """队列任务状态。"""
    WAITING = "排队中"
    PROCESSING = "处理中"
    COMPLETED = "已完成"
    FAILED = "失败"
    CANCELLED = "已取消"


@dataclass
class QueueTask:
    """队列中的单个任务。

    Attributes:
        task_id: 任务唯一标识
        file_name: 文件名
        file_path: 文件完整路径
        status: 任务状态
        progress: 进度描述
        config_snapshot: 任务配置快照
        callback: 任务开始时触发的回调
    """
    task_id: str
    file_name: str
    file_path: str
    status: QueueTaskStatus = QueueTaskStatus.WAITING
    progress: str = "0%"
    error: str = ""
    config_snapshot: Dict[str, Any] = field(default_factory=dict)


class QueueManager:
    """任务队列管理器。

    支持添加多个任务，顺序处理，实时查询队列状态。
    """

    def __init__(self) -> None:
        self._tasks: List[QueueTask] = []
        self._lock: threading.Lock = threading.Lock()
        self._current_index: int = -1
        self._on_task_start: Optional[Callable[[QueueTask], None]] = None
        self._on_queue_update: Optional[Callable[[], None]] = None

    def set_callbacks(
        self,
        on_task_start: Optional[Callable[[QueueTask], None]] = None,
        on_queue_update: Optional[Callable[[], None]] = None,
    ) -> None:
        """设置队列回调。"""
        self._on_task_start = on_task_start
        self._on_queue_update = on_queue_update

    def add_tasks(self, file_paths: List[str], config_snapshot: Optional[Dict[str, Any]] = None) -> List[str]:
        """批量添加任务到队列。

        Args:
            file_paths: 视频文件路径列表
            config_snapshot: 可选的配置快照（所有任务共享）

        Returns:
            任务 ID 列表
        """
        if config_snapshot is None:
            config_snapshot = {}
        task_ids: List[str] = []
        with self._lock:
            for fp in file_paths:
                tid = uuid.uuid4().hex[:12]
                task = QueueTask(
                    task_id=tid,
                    file_name=fp.split("\\")[-1].split("/")[-1],
                    file_path=fp,
                    config_snapshot=dict(config_snapshot),
                )
                self._tasks.append(task)
                task_ids.append(tid)
            # 如果队列之前是空的，立即启动第一个
            if self._current_index < 0:
                self._start_next()
        self._notify_update()
        return task_ids

    def start_next(self) -> Optional[QueueTask]:
        """启动队列中的下一个任务。"""
        with self._lock:
            return self._start_next()

    def _start_next(self) -> Optional[QueueTask]:
        """启动下一个待处理任务（需在锁内调用）。"""
        for i, task in enumerate(self._tasks):
            if task.status == QueueTaskStatus.WAITING:
                task.status = QueueTaskStatus.PROCESSING
                self._current_index = i
                if self._on_task_start:
                    self._on_task_start(task)
                return task
        self._current_index = -1
        return None

    def mark_completed(self, task_id: str, error: str = "") -> None:
        """标记任务完成并启动下一个。"""
        with self._lock:
            for task in self._tasks:
                if task.task_id == task_id:
                    if error:
                        task.status = QueueTaskStatus.FAILED
                        task.error = error
                        task.progress = f"失败: {error}"
                    else:
                        task.status = QueueTaskStatus.COMPLETED
                        task.progress = "100%"
                    break
            self._start_next()
        self._notify_update()

    def update_progress(self, task_id: str, progress: str) -> None:
        """更新任务进度。"""
        with self._lock:
            for task in self._tasks:
                if task.task_id == task_id:
                    task.progress = progress
                    break
        self._notify_update()

    def cancel(self, task_id: str) -> None:
        """取消队列中的某个任务。"""
        with self._lock:
            for task in self._tasks:
                if task.task_id == task_id and task.status == QueueTaskStatus.WAITING:
                    task.status = QueueTaskStatus.CANCELLED
                    break
        self._notify_update()

    def get_queue_data(self) -> List[Dict[str, Any]]:
        """获取队列数据（用于前端表格显示）。

        Returns:
            队列数据列表 [{文件名, 状态, 进度}, ...]
        """
        with self._lock:
            return [
                {
                    "#": i + 1,
                    "文件名": t.file_name,
                    "状态": t.status.value,
                    "进度": t.progress,
                }
                for i, t in enumerate(self._tasks)
                if t.status != QueueTaskStatus.CANCELLED
            ]

    def get_queue_status_text(self) -> str:
        """获取队列状态文本（用于前端 HTML 显示）。

        Returns:
            HTML 状态文本
        """
        with self._lock:
            total = len(self._tasks)
            completed = sum(1 for t in self._tasks if t.status == QueueTaskStatus.COMPLETED)
            failed = sum(1 for t in self._tasks if t.status == QueueTaskStatus.FAILED)
            processing = sum(1 for t in self._tasks if t.status == QueueTaskStatus.PROCESSING)
            waiting = sum(1 for t in self._tasks if t.status == QueueTaskStatus.WAITING)

            if total == 0:
                return "<span style='color: #888;'>暂无排队任务</span>"

            parts = [f"共 {total} 个任务"]
            if processing:
                parts.append(f"🔄 处理中")
            if waiting:
                parts.append(f"⏳ 排队 {waiting}")
            if completed:
                parts.append(f"✅ 完成 {completed}")
            if failed:
                parts.append(f"❌ 失败 {failed}")
            return f"<span style='color: #4FC1FF;'>{' | '.join(parts)}</span>"

    def _notify_update(self) -> None:
        """通知队列更新。"""
        if self._on_queue_update:
            self._on_queue_update()
