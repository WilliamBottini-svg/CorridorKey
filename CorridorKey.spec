# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for CorridorKey macOS .app bundle.

Build with:
    pyinstaller CorridorKey.spec --noconfirm

The resulting app is in dist/CorridorKey.app. Model weights are NOT
bundled (too large) — the app downloads them on first launch.
"""

import os
import sys
from pathlib import Path

# Locate customtkinter for bundling its assets (themes, etc.)
import customtkinter

ctk_path = os.path.dirname(customtkinter.__file__)

# Try to locate tkinterdnd2 (optional)
tkdnd_datas = []
try:
    import tkinterdnd2

    tkdnd_path = os.path.dirname(tkinterdnd2.__file__)
    tkdnd_datas = [(tkdnd_path, "tkinterdnd2")]
except ImportError:
    pass

# Project root
PROJECT_ROOT = os.path.abspath(".")

block_cipher = None

a = Analysis(
    ["corridorkey_gui.py"],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        # Backend package
        ("backend", "backend"),
        # Core inference module (code only — checkpoints excluded)
        ("CorridorKeyModule", "CorridorKeyModule"),
        # Device utilities
        ("device_utils.py", "."),
        # GVM core (alpha hint generator)
        ("gvm_core", "gvm_core"),
        # VideoMaMa inference module
        ("VideoMaMaInferenceModule", "VideoMaMaInferenceModule"),
        # BiRefNet module
        ("BiRefNetModule", "BiRefNetModule"),
        # customtkinter theme assets
        (ctk_path, "customtkinter"),
    ]
    + tkdnd_datas,
    hiddenimports=[
        # Backend modules
        "backend",
        "backend.service",
        "backend.clip_state",
        "backend.errors",
        "backend.frame_io",
        "backend.job_queue",
        "backend.validators",
        "backend.natural_sort",
        "backend.project",
        # GUI
        "customtkinter",
        # Image / video
        "PIL",
        "PIL.Image",
        "cv2",
        "numpy",
        # ML framework
        "torch",
        "torchvision",
        "timm",
        # HuggingFace (for weight download on first launch)
        "huggingface_hub",
        # Inference deps
        "diffusers",
        "transformers",
        "accelerate",
        "einops",
        "kornia",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim unnecessary modules for smaller bundle
        "matplotlib",
        "notebook",
        "jupyter",
        "IPython",
        "pytest",
        "sphinx",
        "docutils",
        "tkinter.test",
        "unittest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Remove checkpoint files from the bundle (too large)
a.datas = [
    d
    for d in a.datas
    if not d[0].endswith(".pth")
    and not d[0].endswith(".safetensors")
    and not d[0].endswith(".bin")
    and "checkpoints/" not in d[0]
    and "weights/" not in d[0]
]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CorridorKey",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX can cause issues on macOS
    console=False,  # Windowed app — no terminal
    disable_windowed_traceback=False,
    argv_emulation=True,  # macOS: support open-with / drag-to-dock
    target_arch=None,  # Build for current architecture
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CorridorKey",
)

app = BUNDLE(
    coll,
    name="CorridorKey.app",
    icon="assets/CorridorKey.iconset",  # macOS will convert iconset to icns
    bundle_identifier="com.corridordigital.corridorkey",
    info_plist={
        "CFBundleName": "CorridorKey",
        "CFBundleDisplayName": "CorridorKey",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleInfoDictionaryVersion": "6.0",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,  # Support dark mode
        "LSMinimumSystemVersion": "12.3",  # MPS requires macOS 12.3+
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "Video File",
                "CFBundleTypeRole": "Viewer",
                "LSItemContentTypes": [
                    "public.movie",
                    "public.mpeg-4",
                    "com.apple.quicktime-movie",
                ],
            },
            {
                "CFBundleTypeName": "Folder",
                "CFBundleTypeRole": "Viewer",
                "LSItemContentTypes": ["public.folder"],
            },
        ],
    },
)
