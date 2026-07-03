import os
import time
import numpy as np
import cv2
from PIL import ImageGrab
from logger import setup_logger

logger = setup_logger()


class Vision:
    """图像识别与点击模块"""

    def __init__(self, confidence: float = 0.8, screenshot_region: tuple = None):
        self.confidence = confidence
        self.screenshot_region = screenshot_region
        self.stop_event = None

    def set_stop_event(self, event):
        self.stop_event = event

    def is_stopped(self):
        return self.stop_event and self.stop_event.is_set()

    def screenshot(self) -> np.ndarray:
        try:
            img = ImageGrab.grab(bbox=self.screenshot_region)
            return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return None

    def find_image(self, template_path: str, screen: np.ndarray = None) -> tuple:
        template_path = template_path.replace("\\", "/")

        if not os.path.exists(template_path):
            return False, 0, 0, 0

        template = cv2.imread(template_path)
        if template is None:
            return False, 0, 0, 0

        if screen is None:
            screen = self.screenshot()
        if screen is None:
            return False, 0, 0, 0

        result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= self.confidence:
            h, w = template.shape[:2]
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            return True, center_x, center_y, max_val

        return False, 0, 0, max_val

    def wait_for_image(self, template_path: str, timeout: float = 30, interval: float = 0.5) -> tuple:
        """等待图像出现"""
        template_path = template_path.replace("\\", "/")
        start = time.time()
        last_log = 0
        while time.time() - start < timeout:
            if self.is_stopped():
                logger.info("🛑 用户停止，取消等待")
                return False, 0, 0, 0

            found, x, y, conf = self.find_image(template_path)
            if found:
                return True, x, y, conf

            elapsed = time.time() - start
            if elapsed - last_log >= 5:
                logger.info(f"   ⏳ 搜索中... 已等待={elapsed:.0f}s")
                last_log = elapsed

            time.sleep(interval)
        logger.warning(f"⏰ 等待超时: {template_path} ({timeout}s)")
        return False, 0, 0, 0

    def click(self, x: int, y: int, button: str = "left", clicks: int = 1):
        try:
            import pyautogui
            pyautogui.click(x, y, clicks=clicks, button=button)
            logger.debug(f"点击: ({x}, {y}) button={button}")
        except Exception as e:
            logger.error(f"点击失败: {e}")

    def click_image(self, template_path: str, screen: np.ndarray = None) -> bool:
        found, x, y, conf = self.find_image(template_path, screen)
        if found:
            self.click(x, y)
            return True
        return False

    def wait_and_click(self, template_path: str, timeout: float = 30) -> bool:
        found, x, y, conf = self.wait_for_image(template_path, timeout)
        if found:
            self.click(x, y)
            return True
        return False


class GameClicker:
    """游戏自动化点击器"""

    def __init__(self, image_dir: str = "images", confidence: float = 0.8):
        self.image_dir = image_dir
        self.vision = Vision(confidence=confidence)
        self.stop_event = None

    def set_stop_event(self, event):
        self.stop_event = event
        self.vision.set_stop_event(event)

    def get_image_path(self, filename: str) -> str:
        if os.path.isabs(filename):
            return filename
        return os.path.join(self.image_dir, filename).replace("\\", "/")

    def start_task(self, start_button_image: str, timeout: float = 30) -> bool:
        path = self.get_image_path(start_button_image)
        logger.info(f"🔍 搜索启动按钮: {start_button_image}")

        if not os.path.exists(path):
            logger.error(f"❌ 模板图像不存在: {path}")
            return False

        return self.vision.wait_and_click(path, timeout)

    def wait_completion(self, completion_image: str, timeout: float = 1800) -> bool:
        path = self.get_image_path(completion_image)
        logger.info(f"🔍 等待完成标识: {completion_image} (超时={timeout}s)")

        if not os.path.exists(path):
            logger.error(f"❌ 完成标识图像不存在: {path}")
            return False

        found, _, _, _ = self.vision.wait_for_image(path, timeout, interval=1.0)
        return found

    def check_image(self, image_name: str) -> bool:
        path = self.get_image_path(image_name)
        found, _, _, _ = self.vision.find_image(path)
        return found
