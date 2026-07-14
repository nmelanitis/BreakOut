# -*- mode: python ; coding: utf-8 -*-
"""Cross-platform one-file package for the local BreakOut desktop beta."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / "scripts" / "breakout_launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(ROOT / "src" / "breakout" / "templates"), "breakout/templates"),
        (str(ROOT / "src" / "breakout" / "static"), "breakout/static"),
        (str(ROOT / "src" / "breakout" / "schemas"), "breakout/schemas"),
    ],
    hiddenimports=collect_submodules("uvicorn"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BreakOut",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
