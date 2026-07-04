# GachaAD - 游戏日常自动清理工具

一键按顺序启动多个游戏，自动完成日常任务的自动化工具。

## 功能特性

- **pywebview GUI** - 基于 Edge WebView2 的独立窗口图形界面
- **拖拽排序** - 执行界面支持拖拽调整游戏执行顺序
- **深色/浅色主题** - 支持主题切换
- **CLI驱动** - 通过命令行参数控制自动化工具，无需图像识别
- **进程监控** - 自动检测工具进程状态，等待完成后继续
- **UAC自动提权** - 内置管理员权限manifest，启动即提权
- **任务重试** - 可配置重试次数和间隔
- **子进程追踪** - PID快照差分追踪工具子进程
- **配置持久化** - 游戏配置保存在 games.yaml，支持热修改

## 快速开始

### 1. 运行程序

```bash
# 直接运行exe
dist\GachaAD\GachaAD.exe
```

### 2. 配置游戏

在"配置"标签页中：
1. 点击"+ 添加"按钮添加新游戏
2. 填写游戏名称和可执行文件路径
3. 填写自动化工具的路径和CLI参数
4. 可选配置启动器路径（如 WeGame）

### 3. 开始执行

在"执行"标签页中：
1. 拖拽调整执行顺序
2. 勾选要执行的游戏
3. 点击"开始执行"
4. 观察日志输出和状态变化

## 项目结构

```
GachaAD/
├── gui.py               # pywebview GUI入口
├── orchestrator.py      # 核心编排器
├── config.py            # 配置管理
├── logger.py            # 日志模块（QueueHandler → GUI）
├── task_manager.py      # 任务状态管理
├── elevated_runner.py   # UAC提权模块
├── vision.py            # 图像识别模块（备用）
├── main.py              # 命令行入口
├── games.yaml           # 游戏配置文件
├── web/                 # 前端资源
│   ├── index.html       # 三标签页布局
│   ├── app.js           # 前端逻辑
│   └── style.css        # CSS主题
├── images/              # 图像资源目录
├── GachaAD.spec         # PyInstaller打包配置
└── requirements.txt     # Python依赖
```

## 配置说明

### games.yaml

```yaml
settings:
  default_wait_after_launch: 30
  image_dir: images
  confidence: 0.8
  cleanup:
    force_close: true
    timeout: 30
  retry:
    max_attempts: 3
    interval: 5

app:
  theme: dark             # dark / light
  auto_start: false       # 开机自启动
  auto_execute: false     # 启动后自动执行
  log_level: INFO

pairs:
  - name: "游戏名称"
    game:
      executable: "游戏路径"
      process_name: "进程名"     # 用于tasklist检测
      auto_start: false
    launcher:
      executable: "启动器路径"   # 可选，如WeGame
    tool:
      executable: "工具路径"
      working_dir: "工作目录"
      cli_args: "-t 1 -e"
      process_name: "工具进程名"
      wait_for_exit: true
      timeout: 1800
      completion_timeout: 600
```

### 已支持的游戏和工具

| 游戏 | 工具 | CLI参数 | 说明 |
|------|------|---------|------|
| 鸣潮 | ok-ww | `-t 1 -e` | -t 选择任务，-e 完成后退出 |
| 绝区零 | OneDragon | `-o -c` | -o 运行，-c 完成后关闭游戏 |
| 异环 | ok-nte | `-t 2 -e` | process_name: HTGame |
| 尘白禁区 | — | — | 仅启动游戏 |

## 执行流程

```
开始执行
  ↓
[步骤0] 启动游戏启动器（如WeGame）  [可选]
  ↓
[步骤1] 检测工具是否运行
  ├─ 已运行 → 跳过启动
  └─ 未运行 → 启动工具
  ↓
[步骤2] 检测游戏状态
  └─ 循环等待游戏进程出现
  ↓
[步骤3] 检测工具运行状态
  ├─ 追踪子进程（PID快照差分）
  ├─ 检查主进程是否退出
  └─ 检查超时
  ↓
[步骤4] 清理进程
  └─ 关闭工具和游戏
```

## 故障排除

**Q: 工具启动失败？**
- 检查 executable 路径是否正确
- 确认文件存在
- 查看日志中的具体错误信息

**Q: 执行顺序不对？**
- 在"执行"标签页拖拽调整顺序后再执行

**Q: 日志不显示？**
- 确认 exe 版本包含最新代码
- 重启程序

**Q: 游戏进程检测不到？**
- 配置 process_name 字段（如 HTGame）
- 使用任务管理器确认实际进程名

## 构建

```bash
# 需要先关闭运行中的GachaAD.exe
pyinstaller GachaAD.spec --noconfirm
```

## 依赖

```
pywebview>=5.0
pyyaml>=6.0
opencv-python>=4.8.0
numpy>=1.24.0
Pillow>=10.0.0
pyautogui>=0.9.54
```

## 许可证

MIT License
