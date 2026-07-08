import os
import sys
import json
import threading
import queue
import webview
import yaml
from config import load_config, get_app_dir


def get_web_dir():
    return os.path.join(get_app_dir(), "web")


class API:
    def __init__(self):
        self.config = {}
        self.pairs = []
        self.window = None
        self.log_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.orchestrator = None
        self.is_running = False

    def init(self):
        self._load_config()
        return {"config": self.config, "pairs": self.pairs}

    def _load_config(self):
        try:
            self.config = load_config("games.yaml")
            self.pairs = self.config.get("pairs", [])
        except Exception:
            self.pairs = []
            self.config = {"pairs": [], "settings": {}, "app": {}}

    def set_theme(self, theme):
        self.config.setdefault("app", {})["theme"] = theme
        self._save_yaml()

    def add_pair(self, pair):
        self.pairs.append(pair)
        self.config["pairs"] = self.pairs
        self._save_yaml()

    def delete_pair(self, name):
        self.pairs = [p for p in self.pairs if p["name"] != name]
        self.config["pairs"] = self.pairs
        self._save_yaml()

    def reorder_pairs(self, names):
        m = {p["name"]: p for p in self.pairs}
        self.pairs = [m[n] for n in names if n in m]
        self.config["pairs"] = self.pairs
        self._save_yaml()

    def save_config(self, pairs_json):
        self.pairs = json.loads(pairs_json)
        self.config["pairs"] = self.pairs
        self._save_yaml()

    def save_settings(self, settings_json):
        s = json.loads(settings_json)
        a = self.config.setdefault("app", {})
        a["theme"] = s.get("theme", "dark")
        a["auto_start"] = s.get("auto_start", False)
        a["auto_execute"] = s.get("auto_execute", False)
        a["log_level"] = s.get("log_level", "INFO")
        self._save_yaml()

    def _save_yaml(self):
        path = os.path.join(get_app_dir(), "games.yaml")
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def browse_file(self):
        try:
            result = self.window.create_file_dialog(
                webview.OPEN_DIALOG, file_types=("可执行文件 (*.exe)", "所有文件 (*.*)"))
            return result[0].replace("\\", "/") if result else ""
        except Exception:
            return ""

    def browse_dir(self):
        try:
            result = self.window.create_file_dialog(webview.FOLDER_DIALOG)
            return result[0].replace("\\", "/") if result else ""
        except Exception:
            return ""

    def open_log_dir(self):
        log_dir = os.path.join(get_app_dir(), "logs")
        if os.path.exists(log_dir):
            os.startfile(log_dir)

    def start(self, selected_json):
        if self.is_running:
            return
        selected = json.loads(selected_json)
        name_to_pair = {p["name"]: p for p in self.pairs}
        pairs = []
        ui_indices = []
        for item in selected:
            name = item["name"]
            if name in name_to_pair:
                pair = dict(name_to_pair[name])  # copy to avoid mutating config
                tool = dict(pair.get("tool", {}))
                cli = tool.get("cli_args", "")
                # Strip existing -e, then add back based on autoClose toggle
                cli_clean = cli.replace("-e", "").strip()
                if item.get("autoClose"):
                    cli_clean = (cli_clean + " -e").strip()
                tool["cli_args"] = cli_clean
                pair["tool"] = tool
                pairs.append(pair)
                ui_indices.append(item["uiIdx"])
        if not pairs:
            return
        self.is_running = True
        self.stop_event.clear()
        self.log_queue = queue.Queue()
        threading.Thread(target=self._run_worker, args=(pairs, ui_indices), daemon=True).start()

    def stop(self):
        self.stop_event.set()
        if self.orchestrator:
            self.orchestrator.pm.stop_all()

    def _push(self, js_code):
        try:
            if self.window:
                self.window.evaluate_js(js_code)
        except Exception:
            pass

    def _run_worker(self, pairs, indices):
        try:
            self._push("appendLog('后台线程启动', 'INFO')")
            from orchestrator import Orchestrator, ProcessManager
            from logger import setup_logger
            from vision import GameClicker
            from task_manager import TaskManager
            import logging
            self._push("appendLog('模块加载完成', 'INFO')")

            log = logging.getLogger("gacha_ad")
            log.handlers.clear()
            setup_logger(log_queue=self.log_queue)

            # Add handler that pushes logs directly to JS via evaluate_js
            push_handler = logging.StreamHandler()
            push_handler.setLevel(logging.INFO)
            push_handler.setFormatter(logging.Formatter("%(message)s"))
            _orig_emit = push_handler.emit
            def _push_emit(record):
                msg = push_handler.format(record)
                self._push(f"appendLog({json.dumps(msg)}, 'INFO')")
            push_handler.emit = _push_emit
            log.addHandler(push_handler)

            orch = Orchestrator.__new__(Orchestrator)
            orch.config = self.config
            orch.settings = self.config.get("settings", {})
            orch.pm = ProcessManager()
            orch.results = []
            orch.stop_event = self.stop_event
            orch.clicker = GameClicker(
                image_dir=orch.settings.get("image_dir", "images"),
                confidence=orch.settings.get("confidence", 0.8))
            orch.vision = orch.clicker.vision
            rc = orch.settings.get("retry", {})
            orch.task_manager = TaskManager()
            orch.task_manager.max_retries = rc.get("max_attempts", 3)
            orch.task_manager.retry_delay = rc.get("interval", 5)
            orch._tool_child_pids = set()
            orch._baseline_pids = set()
            orch._setup_admin_for_tools()
            orch.set_stop_event(self.stop_event)
            self.orchestrator = orch

            for i, pair in enumerate(pairs):
                if self.stop_event.is_set():
                    self.log_queue.put(("done", {"message": "已停止", "error": False}))
                    return
                idx = indices[i] if i < len(indices) else i
                self.log_queue.put(("status", (idx, "运行中", "#2563eb")))
                self._push(f"setStatus({idx}, '运行中', '#2563eb')")
                orch._run_pair_with_retry(pair)
                if self.stop_event.is_set():
                    self.log_queue.put(("done", {"message": "已停止", "error": False}))
                    return
                task = list(orch.task_manager.tasks.values())[-1] if orch.task_manager.tasks else None
                color = "#16a34a" if task and task.state.value == "completed" else "#dc2626"
                text = "完成" if task and task.state.value == "completed" else "失败"
                self.log_queue.put(("status", (idx, text, color)))
                self._push(f"setStatus({idx}, '{text}', '{color}')")
            self.log_queue.put(("done", {"message": "执行完成", "error": False}))
            self._push("isRunning=false;document.getElementById('btn-start').disabled=false;document.getElementById('btn-stop').disabled=true;document.getElementById('status-text').textContent='执行完成';document.getElementById('status-text').style.color='var(--green)';stopPolling();")
        except Exception as e:
            self.log_queue.put(("log", (f"{type(e).__name__}: {e}", "ERROR")))
            self.log_queue.put(("done", {"message": f"出错: {e}", "error": True}))
            self._push(f"appendLog('{type(e).__name__}: {e}', 'ERROR');isRunning=false;document.getElementById('btn-start').disabled=false;document.getElementById('btn-stop').disabled=true;stopPolling();")

    def poll(self):
        logs, statuses, done = [], [], None
        try:
            while True:
                msg = self.log_queue.get_nowait()
                if msg[0] == "log": logs.append(msg[1])
                elif msg[0] == "status": statuses.append(msg[1])
                elif msg[0] == "done":
                    done = msg[1]
                    self.is_running = False
        except queue.Empty:
            pass
        return {"logs": logs, "statuses": statuses, "done": done,
                "message": done.get("message") if done else None,
                "error": done.get("error", False) if done else False}


def main():
    api = API()
    api._load_config()
    web_dir = get_web_dir()
    html_path = os.path.join(web_dir, "index.html")
    css_path = os.path.join(web_dir, "style.css")
    js_path = os.path.join(web_dir, "app.js")

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()
    with open(js_path, "r", encoding="utf-8") as f:
        js = f.read()

    html = html.replace('<link rel="stylesheet" href="style.css">', f'<style>{css}</style>')

    init_data = json.dumps({"config": api.config, "pairs": api.pairs})
    js_init = f"window.__INIT_DATA__ = {init_data};"
    html = html.replace('<script src="app.js"></script>', f'<script>{js_init}</script><script>{js}</script>')

    window = webview.create_window(
        "GachaAD", html=html, js_api=api,
        width=1100, height=750, min_size=(900, 600), resizable=True,
    )
    api.window = window
    webview.start()


if __name__ == "__main__":
    main()
