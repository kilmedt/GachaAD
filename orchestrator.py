import os
import time
import subprocess
import traceback
import threading
from config import load_config, get_app_dir
from logger import setup_logger
from vision import GameClicker, Vision
from task_manager import TaskManager, TaskState
from elevated_runner import set_run_as_admin

logger = setup_logger()


def tasklist_snapshot() -> tuple[set, dict]:
    """一次调用获取系统所有进程的 PID 集合 + PID→名称映射"""
    pids = set()
    detail = {}
    try:
        output = subprocess.check_output(
            ['tasklist', '/FO', 'CSV', '/NH'],
            text=True, encoding='gbk', errors='ignore'
        )
        for line in output.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            parts = line.split('","')
            if len(parts) >= 2:
                name = parts[0].strip('"').strip()
                pid_str = parts[1].strip('"').strip()
                if pid_str.isdigit():
                    pid = int(pid_str)
                    pids.add(pid)
                    detail[pid] = {"name": name}
    except Exception:
        pass
    return pids, detail


def find_process_in_snapshot(detail: dict, exe_path: str, process_name: str = None) -> dict:
    """在快照数据中查找进程（不发起额外 subprocess），返回 {"name": ..., "pid": ...} 或 None"""
    if process_name:
        for pid, info in detail.items():
            pname = info.get("name", "")
            pname_lower = pname.lower()
            if pname_lower == (process_name + ".exe").lower() or pname_lower == process_name.lower():
                return {"name": pname, "pid": pid}
        # 模糊匹配中文显示名
        for pid, info in detail.items():
            pname = info.get("name", "")
            if process_name.lower() in pname.lower():
                return {"name": pname, "pid": pid}

    exe_name = os.path.basename(exe_path)
    name_without_ext = os.path.splitext(exe_name)[0]
    for pid, info in detail.items():
        pname = info.get("name", "").lower()
        if exe_name.lower() in pname or (name_without_ext + ".exe").lower() in pname:
            return {"name": info.get("name", ""), "pid": pid}
    return None


class ProcessManager:
    def __init__(self):
        self.processes: dict[str, subprocess.Popen] = {}

    def start(self, name: str, executable: str, args: str = "", working_dir: str = None, hide_window: bool = False) -> dict:
        """启动进程，返回 {"ok", "pid", "child_pids", "baseline_pids"}"""
        if not os.path.exists(executable):
            logger.error(f"❌ 文件不存在: {executable}")
            return {"ok": False, "pid": 0, "child_pids": set(), "baseline_pids": set()}

        try:
            # ===== 快照1: 记录启动前所有进程 PID =====
            before_pids, _ = tasklist_snapshot()
            logger.info(f"   📸 启动前进程数: {len(before_pids)}")

            # 启动工具
            cmd_str = f'"{executable}" {args}'.strip() if args else f'"{executable}"'
            kwargs = {"shell": True}
            if working_dir and os.path.exists(working_dir):
                kwargs["cwd"] = working_dir
            if hide_window:
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            proc = subprocess.Popen(cmd_str, **kwargs)
            shell_pid = proc.pid
            logger.info(f"✅ Shell进程已启动 PID={shell_pid}")

            # 等待工具创建子进程
            logger.info(f"   ⏳ 等待子进程创建 (3s)...")
            time.sleep(3)

            # ===== 快照2: 记录启动后所有进程 =====
            after_pids, after_detail = tasklist_snapshot()
            logger.info(f"   📸 启动后进程数: {len(after_pids)}")

            # 差分: 找出所有新增的进程
            new_pids = after_pids - before_pids
            logger.info(f"   📸 新增进程数: {len(new_pids)}")

            # 记录新增进程的详情
            child_pids = set()
            for pid in sorted(new_pids):
                info = after_detail.get(pid, {})
                pname = info.get("name", "unknown")
                logger.info(f"      新增 PID={pid} 名称={pname}")
                child_pids.add(pid)

            # 同时查找工具 exe 本身
            tool_info = find_process_in_snapshot(after_detail, executable)
            tool_pid = tool_info["pid"] if tool_info and "pid" in tool_info else 0
            if tool_pid == 0:
                for pid in new_pids:
                    pname = after_detail.get(pid, {}).get("name", "").lower()
                    exe_name = os.path.basename(executable).lower()
                    name_without_ext = os.path.splitext(os.path.basename(executable))[0].lower()
                    if name_without_ext in pname or exe_name in pname:
                        tool_pid = pid
                        break

            self.processes[name] = proc
            result = {
                "ok": True,
                "pid": shell_pid,
                "tool_pid": tool_pid,
                "child_pids": child_pids,
                "baseline_pids": after_pids  # 以后续快照为基线（包含本次新增的）
            }
            logger.info(f"✅ 启动完成: tool_pid={tool_pid}, 跟踪 {len(child_pids)} 个新进程")
            return result

        except Exception as e:
            logger.error(f"❌ 启动失败: {type(e).__name__}: {e}")
            return {"ok": False, "pid": 0, "child_pids": set(), "baseline_pids": set()}

    def is_process_alive(self, name: str) -> bool:
        proc = self.processes.get(name)
        if proc is None:
            return False
        return proc.poll() is None

    def stop(self, name: str, force: bool = True, timeout: int = 5) -> bool:
        proc = self.processes.get(name)
        if proc is None:
            return True
        try:
            if proc.poll() is not None:
                self.processes.pop(name, None)
                return True
            if force:
                proc.kill()
            else:
                proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
            logger.info(f"✅ 进程已关闭: {name}")
            self.processes.pop(name, None)
            return True
        except Exception as e:
            logger.error(f"❌ 关闭失败: {e}")
            return False

    def stop_all(self):
        for name in list(self.processes.keys()):
            self.stop(name, force=True)


class Orchestrator:
    def __init__(self, config_path: str = "games.yaml"):
        self.config = load_config(config_path)
        self.settings = self.config.get("settings", {})
        self.pm = ProcessManager()
        self.results: list[dict] = []
        self.stop_event = None

        image_dir = self.settings.get("image_dir", "images")
        confidence = self.settings.get("confidence", 0.8)
        self.clicker = GameClicker(image_dir=image_dir, confidence=confidence)
        self.vision = self.clicker.vision

        retry_config = self.settings.get("retry", {})
        self.task_manager = TaskManager()
        self.task_manager.max_retries = retry_config.get("max_attempts", 3)
        self.task_manager.retry_delay = retry_config.get("interval", 5)

        self._tool_child_pids: set = set()
        self._baseline_pids: set = set()  # 启动前的 PID 快照基线

        self._setup_admin_for_tools()

    def set_stop_event(self, event):
        self.stop_event = event
        self.clicker.set_stop_event(event)

    def _is_stopped(self):
        return self.stop_event and self.stop_event.is_set()

    def _setup_admin_for_tools(self):
        pairs = self.config.get("pairs", [])
        for pair in pairs:
            tool_exe = pair.get("tool", {}).get("executable", "")
            if tool_exe and os.path.exists(tool_exe):
                set_run_as_admin(tool_exe)

    def _are_tool_pids_alive(self, snapshot_pids: set = None) -> bool:
        """检查工具子进程是否还存活，返回并更新存活的 PID 集合"""
        if not self._tool_child_pids:
            return False
        if snapshot_pids is not None:
            alive = self._tool_child_pids & snapshot_pids
        else:
            current_pids, _ = tasklist_snapshot()
            alive = self._tool_child_pids & current_pids
        dead_count = len(self._tool_child_pids) - len(alive)
        if dead_count > 0 and alive:
            logger.debug(f"   子进程已退出 {dead_count} 个, 剩余 {len(alive)} 个")
        self._tool_child_pids = alive
        return len(alive) > 0

    def run_all(self):
        pairs = self.config.get("pairs", [])
        logger.info(f"{'='*60}")
        logger.info(f"🚀 开始执行 共 {len(pairs)} 组游戏")
        logger.info(f"{'='*60}")

        for i, pair in enumerate(pairs, 1):
            if self._is_stopped():
                logger.info("🛑 用户停止执行")
                break
            logger.info(f"\n{'─'*60}")
            logger.info(f"📌 [{i}/{len(pairs)}] {pair['name']}")
            logger.info(f"{'─'*60}")
            self._run_pair_with_retry(pair)

        self.task_manager.save_history()
        self._print_summary()

    def run_single(self, pair_name: str):
        pairs = self.config.get("pairs", [])
        match = [p for p in pairs if p["name"] == pair_name]
        if not match:
            logger.error(f"❌ 未找到游戏: {pair_name}")
            return
        self._run_pair_with_retry(match[0])
        self.task_manager.save_history()
        self._print_summary()

    def _run_pair_with_retry(self, pair: dict):
        name = pair["name"]
        task = self.task_manager.create_task(f"task_{name}_{int(time.time())}", name)

        for attempt in range(self.task_manager.max_retries + 1):
            if self._is_stopped():
                task.stop()
                return
            if attempt > 0:
                task.retry()
                logger.info(f"🔄 重试第 {attempt} 次 (间隔 {self.task_manager.retry_delay}s)")
                time.sleep(self.task_manager.retry_delay)
            task.start()
            success = self._run_pair(pair, task)
            if success:
                task.complete()
                return
            elif self._is_stopped():
                task.stop()
                return

        task.fail("所有重试都失败")
        logger.error(f"❌ {name} 失败，已重试 {self.task_manager.max_retries} 次")

    def _run_pair(self, pair: dict, task) -> bool:
        name = pair["name"]
        game_config = pair.get("game", {})
        tool_config = pair.get("tool", {})
        launcher_config = pair.get("launcher", {})
        cleanup = self.settings.get("cleanup", {})

        tool_exe = tool_config.get("executable", "")
        cli_args = tool_config.get("cli_args", "")
        working_dir = tool_config.get("working_dir", "")
        use_gui_click = tool_config.get("use_gui_click", False)
        start_button_image = tool_config.get("start_button_image", "")
        completion_image = tool_config.get("completion_image", "")
        completion_timeout = tool_config.get("completion_timeout", 1800)

        game_running = False

        try:
            if self._is_stopped():
                return False

            logger.info(f"🔍 开始处理: {name}")

            # ===== 步骤0: 启动启动器（如果有） =====
            launcher_exe = launcher_config.get("executable", "")
            if launcher_exe and os.path.exists(launcher_exe):
                logger.info(f"📋 [步骤0] 启动游戏启动器")
                launcher_args = launcher_config.get("args", "")
                if self.pm.start(f"{name}_launcher", launcher_exe, launcher_args)["ok"]:
                    logger.info(f"   ✅ 启动器已启动")
                    task.add_step("启动启动器", True, launcher_exe)
                    time.sleep(5)
                else:
                    logger.warning(f"   ⚠️ 启动器启动失败，继续执行...")

            # ===== 步骤1: 检测工具是否运行 =====
            logger.info(f"📋 [步骤1] 检测工具是否运行")
            task.add_step("检测工具", True, "开始检测")

            if not tool_exe:
                logger.error(f"   ❌ 未配置工具路径")
                task.add_step("检测工具", False, "未配置路径")
                return False

            snap_pids, snap_detail = tasklist_snapshot()
            tool_running_info = find_process_in_snapshot(snap_detail, tool_exe, tool_config.get("process_name"))
            if tool_running_info:
                logger.info(f"   ✅ 工具已在运行 PID={tool_running_info['pid']}")
                task.add_step("检测工具", True, f"已运行 PID={tool_running_info['pid']}")
            else:
                logger.info(f"   ⏳ 工具未运行，启动中...")
                logger.info(f"   路径: {tool_exe}")
                logger.info(f"   参数: {cli_args or '(无)'}")

                show_window = tool_config.get("show_window", False)
                start_result = self.pm.start(
                    f"{name}_tool", tool_exe, cli_args, working_dir,
                    hide_window=not show_window
                )

                if not start_result["ok"]:
                    logger.error(f"   ❌ 工具启动失败")
                    task.add_step("启动工具", False, "启动失败")
                    return False

                self._tool_child_pids = start_result.get("child_pids", set())
                self._baseline_pids = start_result.get("baseline_pids", set())
                tool_pid = start_result.get("tool_pid", 0)

                if self._tool_child_pids:
                    logger.info(f"   ✅ 追踪到 {len(self._tool_child_pids)} 个新进程")
                    task.add_step("启动工具", True, f"{len(self._tool_child_pids)}个新进程")
                elif tool_pid:
                    logger.info(f"   ✅ 工具已启动 PID={tool_pid}")
                    task.add_step("启动工具", True, f"PID={tool_pid}")
                else:
                    logger.warning(f"   ⚠️ 未检测到新进程，继续监控")
                    task.add_step("启动工具", True, "已启动")

            # ===== 步骤2: 寻找启动按键 =====
            logger.info(f"📋 [步骤2] 寻找启动按键")
            if use_gui_click and start_button_image:
                image_path = self.clicker.get_image_path(start_button_image)
                if not os.path.exists(image_path):
                    logger.error(f"   ❌ 启动按钮图像不存在: {image_path}")
                    task.add_step("启动按钮", False, "图像不存在")
                    return False
                logger.info(f"   🔍 搜索启动按钮: {start_button_image}")
                time.sleep(3)
                found = False
                for attempt in range(3):
                    if self._is_stopped():
                        return False
                    logger.info(f"   ⏳ 尝试识别... ({attempt + 1}/3)")
                    if self.clicker.start_task(start_button_image, timeout=10):
                        logger.info(f"   ✅ 已点击启动按钮")
                        found = True
                        break
                    time.sleep(2)
                if not found:
                    logger.error(f"   ❌ 未能找到启动按钮")
                    task.add_step("启动按钮", False, "未找到按钮")
                    return False
                task.add_step("启动按钮", True, start_button_image)
            else:
                logger.info(f"   ℹ️ 非GUI模式，工具自行启动游戏")
                task.add_step("启动游戏", True, "由工具启动")

            # ===== 步骤3: 检测游戏是否正常启动 =====
            logger.info(f"📋 [步骤3] 检测游戏状态")
            game_exe = game_config.get("executable", "")
            game_process_name = game_config.get("process_name", "")
            game_started = False
            game_started_by_us = False

            game_was_running_before = False
            if game_exe:
                snap_pids, snap_detail = tasklist_snapshot()
                game_was_running_before = find_process_in_snapshot(snap_detail, game_exe, game_process_name) is not None

            for check_count in range(50):
                if self._is_stopped():
                    return False
                if game_exe:
                    snap_pids, snap_detail = tasklist_snapshot()
                    game_info = find_process_in_snapshot(snap_detail, game_exe, game_process_name)
                    if game_info:
                        logger.info(f"   ✅ 游戏已启动 PID={game_info['pid']}")
                        game_running = True
                        game_started = True
                        game_started_by_us = not game_was_running_before
                        task.add_step("检测游戏", True, f"已启动 PID={game_info['pid']}")
                        break
                    else:
                        if check_count % 5 == 0:
                            logger.info(f"   ⏳ 等待游戏启动... ({check_count + 1})")
                else:
                    logger.info(f"   ℹ️ 未配置游戏路径，跳过检测")
                    game_started = True
                    task.add_step("检测游戏", True, "跳过")
                    break
                time.sleep(3)

            if not game_started:
                logger.warning(f"   ⚠️ 游戏未启动，继续检测工具状态")
                task.add_step("检测游戏", False, "未检测到")

            # ===== 步骤4: 检测工具运行状态 =====
            logger.info(f"📋 [步骤4] 检测工具运行状态")
            start_time = time.time()
            last_status_log = 0
            last_check_time = 0
            consecutive_dead = 0
            first_check = True
            found_main_process = False  # 是否已找到主进程（第一个pythonw.exe）

            tool_dir = os.path.dirname(tool_exe).lower()
            tool_base = os.path.splitext(os.path.basename(tool_exe))[0].lower()

            while True:
                if self._is_stopped():
                    return False

                elapsed = time.time() - start_time

                # ===== 一次快照供下面所有检查使用 =====
                current_pids, current_detail = tasklist_snapshot()

                # ===== 首次发现主进程后锁定，不再扫描新进程 =====
                if not found_main_process:
                    new_since_baseline = current_pids - self._baseline_pids

                    for pid in new_since_baseline:
                        if pid not in self._tool_child_pids:
                            pname = current_detail.get(pid, {}).get("name", "").lower()
                            if 'python' in pname:
                                self._tool_child_pids.add(pid)
                                logger.info(f"   📦 发现 Python 进程 PID={pid} 名称={pname}")

                    if self._tool_child_pids:
                        found_main_process = True
                        logger.info(f"   🔒 锁定 {len(self._tool_child_pids)} 个 Python 进程，不再扫描")

                # ===== 用同一份快照检查工具进程和子进程 =====
                tool_info = find_process_in_snapshot(current_detail, tool_exe, tool_config.get("process_name"))
                tool_exe_alive = tool_info is not None
                child_alive = self._are_tool_pids_alive(current_pids)
                tool_alive = tool_exe_alive or child_alive

                if first_check:
                    first_check = False
                    logger.info(f"   📊 主进程: {'运行中' if tool_exe_alive else '已退出'} | 子进程: {'运行中' if child_alive else '已退出'} (共{len(self._tool_child_pids)}个)")

                if elapsed - last_status_log >= 15:
                    parts = []
                    if tool_exe_alive:
                        parts.append("主进程")
                    if child_alive:
                        parts.append(f"子进程({len(self._tool_child_pids)}个)")
                    status = ', '.join(parts) if parts else "无活跃进程"
                    logger.info(f"   ⏳ [{status}] 已等待={elapsed:.0f}s")
                    last_status_log = elapsed

                if use_gui_click and completion_image:
                    if elapsed - last_check_time >= 2:
                        found, _, _, conf = self.vision.find_image(self.clicker.get_image_path(completion_image))
                        if found:
                            logger.info(f"   ✅ 检测到完成标识")
                            task.add_step("完成检测", True, f"耗时={elapsed:.1f}s")
                            break
                        last_check_time = elapsed

                if not tool_alive:
                    consecutive_dead += 1
                    if consecutive_dead == 1:
                        logger.info(f"   ℹ️ 所有进程已退出，等待确认...")
                    if consecutive_dead >= 3:
                        logger.info(f"   ✅ 工具已完成 耗时={elapsed:.1f}s")
                        task.add_step("完成检测", True, f"工具已退出")
                        break
                else:
                    consecutive_dead = 0

                time.sleep(2)

            # ===== 步骤5: 清理 =====
            logger.info(f"📋 [步骤5] 清理进程")
            self._cleanup(name, cleanup, not game_started_by_us, tool_exe, pair.get("launcher"), tool_config)
            task.add_step("清理", True, "完成")

            return True

        except Exception as e:
            logger.error(f"❌ 执行异常: {type(e).__name__}: {e}")
            logger.error(traceback.format_exc())
            task.add_step("异常", False, str(e))
            return False

    def _cleanup(self, pair_name, cleanup_config, game_was_running=False, tool_exe="", launcher_config=None, tool_config=None):
        force = cleanup_config.get("force_close", True)

        logger.info(f"   🔴 关闭工具")
        self.pm.stop(f"{pair_name}_tool", force=force)

        if self._tool_child_pids:
            for pid in self._tool_child_pids:
                try:
                    logger.info(f"   🔴 关闭工具子进程 PID={pid}")
                    subprocess.run(['taskkill', '/PID', str(pid), '/F'], capture_output=True)
                except Exception as e:
                    logger.warning(f"   ⚠️ 关闭子进程失败: {e}")
            self._tool_child_pids.clear()

        if not game_was_running:
            logger.info(f"   🔴 关闭游戏")
            self.pm.stop(f"{pair_name}_game", force=force)
        else:
            logger.info(f"   ℹ️ 游戏原本已运行，不关闭")

        if launcher_config:
            logger.info(f"   🔴 关闭启动器")
            self.pm.stop(f"{pair_name}_launcher", force=force)

        logger.info(f"   ✅ 清理完成")

    def _print_summary(self):
        total = len(self.task_manager.tasks)
        success = sum(1 for t in self.task_manager.tasks.values() if t.state == TaskState.COMPLETED)
        failed = sum(1 for t in self.task_manager.tasks.values() if t.state == TaskState.FAILED)
        total_time = sum(t.duration for t in self.task_manager.tasks.values())

        logger.info(f"\n{'='*60}")
        logger.info(f"📊 执行汇总")
        logger.info(f"{'='*60}")
        logger.info(f"总计: {total} | 成功: {success} | 失败: {failed} | 总耗时: {total_time:.1f}s")
        logger.info(f"{'─'*60}")

        for task in self.task_manager.tasks.values():
            state_icon = {
                TaskState.COMPLETED: "✅",
                TaskState.FAILED: "❌",
                TaskState.STOPPED: "⏹️",
            }.get(task.state, "❓")

            logger.info(f"{state_icon} {task.name} ({task.duration:.1f}s)")
            if task.retry_count > 0:
                logger.info(f"   重试次数: {task.retry_count}")
            for s in task.steps:
                s_status = "  ✓" if s["success"] else "  ✗"
                logger.info(f"   {s_status} {s['step']}: {s.get('detail', '')}")

        logger.info(f"{'='*60}")
