# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('games.yaml', '.'),
        ('images', 'images'),
        ('web', 'web'),
    ],
    hiddenimports=[
        'webview',
        'yaml',
        'cv2',
        'numpy',
        'PIL',
        'PIL.ImageGrab',
        'pyautogui',
        'orchestrator',
        'config',
        'logger',
        'vision',
        'task_manager',
        'elevated_runner',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'pandas',
        'notebook',
        'jupyter',
        'tkinter',
        'tkinter.ttk',
        'PIL.ImageTk',
        'flask',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GachaAD',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    uac_admin=True,
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
    name='GachaAD',
)
