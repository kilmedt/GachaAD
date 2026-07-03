"""任务管理器 - 管理任务状态和执行历史"""
import json
import os
import time
from datetime import datetime
from enum import Enum
from typing import Optional
from logger import setup_logger

logger = setup_logger()


class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    STOPPED = "stopped"


class TaskResult:
    def __init__(self, task_id: str, name: str):
        self.task_id = task_id
        self.name = name
        self.state = TaskState.PENDING
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.duration: float = 0
        self.steps: list[dict] = []
        self.error: Optional[str] = None
        self.retry_count: int = 0
        self.logs: list[str] = []

    def start(self):
        self.state = TaskState.RUNNING
        self.start_time = time.time()

    def complete(self):
        self.state = TaskState.COMPLETED
        self.end_time = time.time()
        if self.start_time:
            self.duration = self.end_time - self.start_time

    def fail(self, error: str = None):
        self.state = TaskState.FAILED
        self.end_time = time.time()
        self.error = error
        if self.start_time:
            self.duration = self.end_time - self.start_time

    def retry(self):
        self.state = TaskState.RETRYING
        self.retry_count += 1

    def stop(self):
        self.state = TaskState.STOPPED
        self.end_time = time.time()
        if self.start_time:
            self.duration = self.end_time - self.start_time

    def add_step(self, step: str, success: bool, detail: str = ""):
        self.steps.append({
            "step": step,
            "success": success,
            "detail": detail,
            "time": datetime.now().strftime("%H:%M:%S")
        })

    def add_log(self, log: str):
        self.logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {log}")

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "state": self.state.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "steps": self.steps,
            "error": self.error,
            "retry_count": self.retry_count,
        }


class TaskManager:
    def __init__(self, history_file: str = "task_history.json"):
        self.tasks: dict[str, TaskResult] = {}
        self.history_file = history_file
        self.max_retries = 3
        self.retry_delay = 5  # seconds

    def create_task(self, task_id: str, name: str) -> TaskResult:
        task = TaskResult(task_id, name)
        self.tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> Optional[TaskResult]:
        return self.tasks.get(task_id)

    def save_history(self):
        """保存执行历史到文件"""
        try:
            history = []
            if os.path.exists(self.history_file):
                with open(self.history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)

            # 添加本次执行记录
            for task in self.tasks.values():
                history.append(task.to_dict())

            # 只保留最近100条记录
            history = history[-100:]

            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)

            logger.info(f"✅ 执行历史已保存: {self.history_file}")
        except Exception as e:
            logger.error(f"❌ 保存执行历史失败: {e}")

    def load_history(self) -> list[dict]:
        """加载执行历史"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def clear_old_history(self, days: int = 7):
        """清理旧的执行历史"""
        try:
            if not os.path.exists(self.history_file):
                return

            with open(self.history_file, "r", encoding="utf-8") as f:
                history = json.load(f)

            cutoff = time.time() - (days * 24 * 3600)
            history = [h for h in history if h.get("start_time", 0) > cutoff]

            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)

            logger.info(f"✅ 已清理 {days} 天前的历史记录")
        except Exception as e:
            logger.error(f"❌ 清理历史记录失败: {e}")
