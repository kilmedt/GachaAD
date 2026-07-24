import os
import sys
import yaml

_app_dir_cache = None


def get_app_dir() -> str:
    global _app_dir_cache
    if _app_dir_cache is not None:
        return _app_dir_cache
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        internal_dir = os.path.join(exe_dir, "_internal")
        if os.path.exists(internal_dir):
            _app_dir_cache = internal_dir
        else:
            _app_dir_cache = exe_dir
    else:
        _app_dir_cache = os.path.dirname(os.path.abspath(__file__))
    return _app_dir_cache


def load_config(config_path: str = "games.yaml") -> dict:
    if not os.path.isabs(config_path):
        config_path = os.path.join(get_app_dir(), config_path)
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    _validate_config(config)
    return config


def _validate_config(config: dict):
    if "pairs" not in config:
        raise ValueError("Config must contain 'pairs' list")

    settings = config.get("settings", {})
    config["settings"] = {
        "screenshot_region": settings.get("screenshot_region"),
        "default_wait_after_launch": settings.get("default_wait_after_launch", 30),
        "log_dir": settings.get("log_dir", "logs"),
        "image_dir": settings.get("image_dir", "images"),
        "confidence": settings.get("confidence", 0.8),
        "retry": {
            "max_attempts": settings.get("retry", {}).get("max_attempts", 3),
            "interval": settings.get("retry", {}).get("interval", 2),
        },
        "cleanup": {
            "force_close": settings.get("cleanup", {}).get("force_close", True),
            "timeout": settings.get("cleanup", {}).get("timeout", 60),
        },
    }

    for i, pair in enumerate(config["pairs"]):
        if "name" not in pair:
            raise ValueError(f"Pair at index {i} missing 'name'")

        game = pair.get("game", {})
        if "executable" not in game:
            raise ValueError(f"Pair '{pair['name']}' missing 'game.executable'")
        game.setdefault("working_dir", os.path.dirname(game["executable"]))
        game.setdefault("wait_after_launch", config["settings"]["default_wait_after_launch"])
        game.setdefault("auto_start", True)

        tool = pair.get("tool", {})
        if "executable" not in tool:
            raise ValueError(f"Pair '{pair['name']}' missing 'tool.executable'")
        tool.setdefault("working_dir", os.path.dirname(tool["executable"]))
        tool.setdefault("wait_after_launch", 10)
        tool.setdefault("completion_timeout", 600)
