# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ProcAI.

Builds a single windowed executable (``ProcAI.exe``) bundling the GUI, the
detection engine and the background-service entry point. The same executable
runs the service when launched with ``--service`` (see procai/__main__.py).

Build:
    pyinstaller installer/procai.spec --noconfirm

Notes
-----
* ``console=False`` -> no console window for the GUI. The service is launched as
  ``ProcAI.exe --service --tray`` by the (visible) startup entry.
* scikit-learn / numpy bring large hidden imports; ``collect_all`` handles them.
* Code-signing is performed AFTER the build (see installer/INSTALLER.md). We do
  NOT bypass SmartScreen/Defender; signing simply establishes legitimate trust.
"""

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = []

# Bundle the SQL schema shipped as package data.
datas += [("../src/procai/data/schema.sql", "procai/data")]

# Pull in heavy optional dependencies if present in the build environment.
for pkg in ("sklearn", "customtkinter", "PIL", "pystray", "reportlab"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

hiddenimports += collect_submodules("procai")

block_cipher = None

a = Analysis(
    ["../src/procai/__main__.py"],
    pathex=["../src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter.test", "test", "tests"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ProcAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                     # UPX disabled: compressed exes trip AV heuristics
    console=False,
    disable_windowed_traceback=False,
    icon="procai.ico" if __import__("os").path.exists("installer/procai.ico") else None,
    version="version_info.txt" if __import__("os").path.exists("installer/version_info.txt") else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="ProcAI",
)
