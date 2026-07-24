"""自动设置工具以管理员身份运行，绕过UAC"""
import os
import ctypes
import winreg
from logger import setup_logger

logger = setup_logger()

_REG_KEY = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def set_run_as_admin(exe_path: str) -> bool:
    """设置程序始终以管理员身份运行"""
    if not os.path.exists(exe_path):
        return False

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_ALL_ACCESS
        )
        try:
            val, _ = winreg.QueryValueEx(key, exe_path)
            if "RUNASADMIN" in val.upper():
                winreg.CloseKey(key)
                return True
        except FileNotFoundError:
            pass
        winreg.SetValueEx(key, exe_path, 0, winreg.REG_SZ, "RUNASADMIN")
        winreg.CloseKey(key)
        logger.info(f"✅ 已设置管理员运行: {os.path.basename(exe_path)}")
        return True
    except Exception as e:
        logger.warning(f"⚠️ 设置管理员运行失败: {e}")
        return False


def remove_run_as_admin(exe_path: str) -> bool:
    """移除管理员运行设置"""
    if not os.path.exists(exe_path):
        return False

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_ALL_ACCESS
        )
        try:
            winreg.DeleteValue(key, exe_path)
        except FileNotFoundError:
            pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False


def ensure_admin_for_tools(tools: list[dict]):
    """批量设置工具以管理员身份运行"""
    logger.info("🔧 检查工具管理员权限设置...")

    for tool in tools:
        exe_path = tool.get("executable", "")
        if exe_path and os.path.exists(exe_path):
            set_run_as_admin(exe_path)
