import logging
import os
import sys
from datetime import datetime


def get_app_dir() -> str:
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        internal_dir = os.path.join(exe_dir, "_internal")
        if os.path.exists(internal_dir):
            return internal_dir
        return exe_dir
    return os.path.dirname(os.path.abspath(__file__))


class QueueHandler(logging.Handler):
    """将日志发送到GUI队列"""

    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        try:
            msg = self.format(record)
            level = record.levelname
            if level == "DEBUG":
                level = "INFO"
            self.log_queue.put(("log", (msg, level)))
        except Exception:
            pass


def setup_logger(log_dir: str = "logs", log_queue=None) -> logging.Logger:
    if not os.path.isabs(log_dir):
        log_dir = os.path.join(get_app_dir(), log_dir)
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger("gacha_ad")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        # 如果已有handler但需要添加QueueHandler
        if log_queue and not any(isinstance(h, QueueHandler) for h in logger.handlers):
            queue_handler = QueueHandler(log_queue)
            queue_handler.setLevel(logging.INFO)
            queue_handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(queue_handler)
        return logger

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_handler = logging.FileHandler(
        os.path.join(log_dir, f"run_{timestamp}.log"),
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # 添加GUI队列handler
    if log_queue:
        queue_handler = QueueHandler(log_queue)
        queue_handler.setLevel(logging.INFO)
        queue_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(queue_handler)

    return logger
