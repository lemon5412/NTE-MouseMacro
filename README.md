# MouseMacro

一个基于 Python 的鼠标宏工具，支持多种操作类型、OCR 文字验证、图像匹配、动作组联动等功能。

## 特性

- **多种动作类型**：单击、长按、滚动、中键、键盘按键、拖拽、等待
- **文字验证（OCR）**：基于 RapidOCR 的文字识别，支持匹配成功/失败时的不同处理
- **图片验证**：基于 OpenCV 模板匹配，支持截图和本地上传模板
- **动作组**：将多个动作组合在一起，通过图片匹配触发执行
- **联动跳转**：动作失败时可跳转到其他步骤
- **相对窗口坐标**：支持窗口移动和分辨率缩放
- **深色主题 UI**：自定义标题栏、自定义滚动条
- **配置导入/导出**：JSON 格式持久化
- **全局热键**：一键启动/停止宏执行

## 安装

```bash
pip install -r requirements.txt
```

OCR 功能需要 `rapidocr-onnxruntime`，首次安装较大（约 1GB），可选安装。

## 运行

```bash
python main.py
```

## 打包

```bash
python -m PyInstaller --clean --noconfirm MouseMacro.spec
```

打包后的可执行文件在 `dist/MouseMacro/` 目录下。

## 安全说明

- 所有操作为纯视觉模拟：鼠标/键盘事件由 pynput 发送，OCR/图像识别通过截屏实现
- 不读取或修改任何进程内存
- 窗口检测仅使用 Win32 公开 API

## 依赖

- pynput — 鼠标/键盘模拟
- mss — 屏幕截图
- Pillow — 图像处理
- opencv-python — 模板匹配（rapidocr 的间接依赖）
- rapidocr-onnxruntime — OCR 文字识别（可选）
