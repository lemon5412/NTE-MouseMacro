# -*- mode: python ; coding: utf-8 -*-
import os
import sys

# Paths
SITE_PACKAGES = r"C:\Users\zacku\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages"
RAPIDOCR_DIR  = os.path.join(SITE_PACKAGES, "rapidocr_onnxruntime")

# Collect rapidocr data files (models, config)
rapidocr_datas = []
if os.path.exists(RAPIDOCR_DIR):
    rapidocr_datas = [(RAPIDOCR_DIR, "rapidocr_onnxruntime")]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=rapidocr_datas,
    hiddenimports=[
        # rapidocr
        "rapidocr_onnxruntime",
        "onnxruntime",
        "onnxruntime.capi",
        "onnxruntime.capi.onnxruntime_inference_collection",
        "pyclipper",
        "shapely",
        "shapely.geometry",
        # image
        "PIL",
        "PIL.Image",
        "cv2",
        # pynput
        "pynput",
        "pynput.mouse",
        "pynput.keyboard",
        "pynput._util",
        "pynput._util.win32",
        # mss
        "mss",
        "mss.windows",
        # project modules
        "core.action",
        "core.config",
        "core.executor",
        "core.input_sim",
        "core.ocr_engine",
        "core.win_utils",
        "core.image_match",
        "ui.main_panel",
        "ui.action_editor",
        "ui.text_verify_dialog",
        "ui.position_picker",
        "ui.widgets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "paddleocr", "paddlepaddle",
        "easyocr", "torch", "torchvision",
        "matplotlib", "IPython", "jupyter",
        "test", "tests",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MouseMacro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MouseMacro",
)
