"""自动设置工具以管理员身份运行，绕过UAC"""
import os
import subprocess
import ctypes
from logger import setup_logger

logger = setup_logger()


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def set_run_as_admin(exe_path: str) -> bool:
    """设置程序始终以管理员身份运行"""
    if not os.path.exists(exe_path):
        return False

    # 使用注册表设置RunAsAdmin
    # 这会让Windows记住这个程序需要管理员权限
    # 之后启动时会自动提权，不再弹UAC
    exe_name = os.path.basename(exe_path)

    # 检查是否已设置
    check_cmd = f'reg query "HKCU\\Software\\Microsoft\\Windows NT\\CurrentVersion\\AppCompatFlags\\Layers" /v "{exe_path}" 2>nul'
    result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)

    if "RUNASADMIN" in result.stdout.upper():
        return True  # 已经设置了

    # 设置RunAsAdmin
    set_cmd = f'reg add "HKCU\\Software\\Microsoft\\Windows NT\\CurrentVersion\\AppCompatFlags\\Layers" /v "{exe_path}" /t REG_SZ /d "RUNASADMIN" /f'
    result = subprocess.run(set_cmd, shell=True, capture_output=True, text=True)

    if result.returncode == 0:
        logger.info(f"✅ 已设置管理员运行: {exe_name}")
        return True
    else:
        logger.warning(f"⚠️ 设置管理员运行失败: {result.stderr}")
        return False


def remove_run_as_admin(exe_path: str) -> bool:
    """移除管理员运行设置"""
    if not os.path.exists(exe_path):
        return False

    cmd = f'reg delete "HKCU\\Software\\Microsoft\\Windows NT\\CurrentVersion\\AppCompatFlags\\Layers" /v "{exe_path}" /f'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode == 0


def ensure_admin_for_tools(tools: list[dict]):
    """批量设置工具以管理员身份运行"""
    logger.info("🔧 检查工具管理员权限设置...")

    for tool in tools:
        exe_path = tool.get("executable", "")
        if exe_path and os.path.exists(exe_path):
            set_run_as_admin(exe_path)
