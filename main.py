import argparse
import sys
import os


def is_admin():
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def main():
    parser = argparse.ArgumentParser(description="游戏日常自动清理工具")
    parser.add_argument("--gui", action="store_true", help="启动图形界面")
    parser.add_argument("-c", "--config", default="games.yaml", help="配置文件路径")
    parser.add_argument("--game", type=str, default=None, help="只运行指定游戏")
    parser.add_argument("--list", action="store_true", help="列出所有配置")
    args = parser.parse_args()

    if args.gui:
        if not is_admin():
            import ctypes
            script = os.path.abspath(sys.argv[0])
            params = " ".join([f'"{a}"' for a in sys.argv[1:]])
            ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" {params}', None, 1)
            return

        from gui import App
        app = App()
        app.run()
        return

    from orchestrator import Orchestrator
    from logger import setup_logger

    logger = setup_logger()
    logger.info("游戏日常自动清理工具 启动")

    if args.list:
        from config import load_config
        config = load_config(args.config)
        pairs = config.get("pairs", [])
        print(f"\n共 {len(pairs)} 组游戏:\n")
        for i, p in enumerate(pairs, 1):
            tool = p.get("tool", {})
            print(f"  {i}. {p['name']}")
            print(f"     工具: {tool.get('executable', '')}")
            print(f"     参数: {tool.get('cli_args', '')}")
            print()
        return

    orch = Orchestrator(args.config)
    if args.game:
        orch.run_single(args.game)
    else:
        orch.run_all()


if __name__ == "__main__":
    main()
