# PyInstaller spec for PandaSC.
#
# Build with:  pyinstaller build.spec
#
# IMPORTANT: PyInstaller does not cross-compile. Run this ON the target OS:
#   - Run on Windows to get PandaSC.exe
#   - Run on macOS to get a PandaSC.app / mac binary
#   - Run on Linux to get a Linux binary
#
# This spec deliberately does NOT include seller_tools/ (the key generator).
# Never ship that file to customers.

import sys
from PyInstaller.utils.hooks import collect_all

block_cipher = None

datas = []
binaries = []
hiddenimports = []

# pandapower ships a lot of its own data (std_types, network templates) and
# has many optional submodules that PyInstaller's static analysis won't find
# on its own -- collect_all pulls in everything so calc_sc etc. works in the
# frozen build exactly like it does when run from source.
for pkg in ("pandapower", "pandera", "scipy", "networkx", "geojson", "deepdiff"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["backend/app.py"],
    pathex=["backend"],
    binaries=binaries,
    datas=datas + [
        ("backend/templates", "templates"),
        ("backend/static", "static"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="PandaSC",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,     # no console window on Windows; set True while debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    onefile=True,
)
