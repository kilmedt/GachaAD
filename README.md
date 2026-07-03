# GachaAD - 游戏日常自动清理工具

一键按顺序启动多个游戏，自动完成日常任务的自动化工具。

## 功能特性

- **图形界面** - 直观的GUI，支持游戏管理和配置
- **图像识别** - 基于OpenCV的模板匹配，自动识别游戏状态
- **自动点击** - 模拟鼠标点击，完成日常任务
- **CLI模式** - 支持命令行参数直接启动工具
- **窗口检测** - 自动检测已运行的程序，避免重复启动
- **UAC自动绕过** - 首次确认后，后续启动自动提权
- **任务状态机** - 支持重试机制（默认3次）
- **执行历史** - 持久化保存执行记录
- **详细日志** - 每个步骤都有清晰的状态显示

## 快速开始

### 1. 运行程序

```bash
# 直接运行exe
dist\GachaAD\GachaAD.exe
//
# 或运行Python脚本
python main.py --gui
```

### 2. 首次运行配置

首次运行时会弹出UAC确认框，点击"是"创建管理员任务。之后所有启动都不会再弹UAC。

### 3. 配置游戏

在"配置"标签页中：
1. 点击"+ 添加"按钮添加新游戏
2. 填写游戏名称和可执行文件路径
3. 填写自动化工具的配置
4. 选择启动模式：
   - **CLI模式**（推荐）：工具通过命令行参数自动完成任务
   - **GUI点击模式**：通过图像识别点击按钮

### 4. 开始执行

在"执行"标签页中：
1. 选择要执行的游戏（勾选复选框）
2. 点击"开始执行"按钮
3. 观察日志输出和状态变化

## 项目结构

```
GachaAD/
├── main.py              # 命令行入口
├── gui.py               # 图形界面
├── orchestrator.py      # 核心编排器
├── vision.py            # 图像识别模块
├── elevated_runner.py   # UAC绕过模块
├── task_manager.py      # 任务状态管理
├── config.py            # 配置管理
├── logger.py            # 日志模块
├── games.yaml           # 游戏配置文件
├── images/              # 图像资源目录
├── logs/                # 日志目录
├── dist/                # 编译后的exe
└── requirements.txt     # Python依赖
```

## 配置说明

### games.yaml

```yaml
settings:
  default_wait_after_launch: 30  # 游戏启动等待时间(秒)
  image_dir: images              # 图像资源目录
  confidence: 0.8                # 图像匹配置信度阈值
  cleanup:
    force_close: true            # 强制关闭进程
    timeout: 30                  # 关闭超时(秒)
  retry:
    max_attempts: 3              # 最大重试次数
    interval: 5                  # 重试间隔(秒)

pairs:
  - name: "游戏名称"
    game:
      executable: "游戏路径"
      auto_start: false          # 是否自动启动游戏（false=由工具启动）
    tool:
      executable: "工具路径"
      working_dir: "工具工作目录"
      cli_args: "-t 1 -e"        # 命令行参数
      wait_for_exit: true        # 是否等待工具退出
      timeout: 1800              # 等待超时(秒)
      use_gui_click: false       # 是否使用GUI点击模式
      start_button_image: "开始按钮图像路径"
      completion_image: "完成标识图像路径"
      completion_timeout: 1800   # 完成等待超时(秒)
```

### 启动模式说明

#### CLI模式（推荐）

适用于支持命令行参数的自动化工具，如：
- **鸣潮 (ok-ww)**: `-t 1 -e`
- **绝区零 (OneDragon)**: `-o -c`（-o=运行，-c=完成后关闭）
- **异环 (ok-nte)**: `-t 1 -e`

配置示例：
```yaml
tool:
  executable: "E:/ElectronicGame/ZZZOneDragon/OneDragon-Launcher.exe"
  cli_args: "-o -c"
  use_gui_click: false
```

#### GUI点击模式

适用于需要图形界面操作的工具。需要提供按钮截图：
- `start_button_image` - 开始按钮截图
- `completion_image` - 完成标识截图

## 执行流程

```
开始执行
  ↓
[步骤1] 检测工具是否运行
  ├─ 已运行 → 跳过启动
  └─ 未运行 → 启动工具
  ↓
[步骤2] 寻找启动按键（GUI模式）
  ├─ CLI模式 → 跳过
  └─ GUI模式 → 图像识别点击
  ↓
[步骤3] 检测游戏是否启动
  └─ 循环等待游戏进程出现
  ↓
[步骤4] 检测工具运行状态
  ├─ 检查完成标识
  ├─ 检查进程是否退出
  └─ 检查超时
  ↓
[步骤5] 清理进程
  └─ 关闭工具和游戏
```

## 命令行模式

```bash
# 列出所有配置
python main.py --list

# 运行指定游戏
python main.py --game "绝区零"

# 运行所有游戏
python main.py

# 启动GUI
python main.py --gui
```

## 图像识别使用指南

### 何时需要图像识别

只有在工具不支持CLI参数时才需要图像识别模式。大多数工具都支持CLI参数，优先使用CLI模式。

### 截图方法

1. 使用"截图测试"按钮自动截取屏幕
2. 用画图工具裁剪按钮区域
3. 保存到 `images/` 目录

### 截图注意事项

- 只截取按钮本身，不要包含太多背景
- 确保按钮状态正确（未点击状态）
- 分辨率要和运行时一致

## 故障排除

**Q: 工具启动失败？**
- 检查路径是否正确
- 确认文件存在
- 查看日志中的具体错误信息

**Q: 图像识别找不到按钮？**
- 使用"截图测试"验证截图功能
- 使用"查找测试"验证匹配
- 尝试降低置信度阈值

**Q: 首次运行没有弹出UAC？**
- 手动删除旧任务：`schtasks /delete /tn "GachaAD_Elevated_Launcher" /f`
- 重新运行程序

**Q: 如何查看执行历史？**
- 执行历史保存在 `task_history.json`

## 开发说明

### 依赖

```
pyautogui>=0.9.54
opencv-python>=4.8.0
pyyaml>=6.0
Pillow>=10.0.0
numpy>=1.24.0
```

### 构建exe

```bash
pyinstaller --clean -y GachaAD.spec
```

## 许可证

MIT License
