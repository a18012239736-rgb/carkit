# Build a macOS app bundle; package it into an architecture-specific DMG in CI.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from pathlib import Path
from engine import __version__

ROOT = Path(SPECPATH).parent

datas = [
    (str(ROOT / "ui"), "ui"),
    (str(ROOT / "engine/rules"), "engine/rules"),
    (str(ROOT / "engine/*.js"), "engine"),
]
datas += collect_data_files("playwright")

hiddenimports = (
    collect_submodules("webview")
    + collect_submodules("engine")
    + ["openpyxl", "lxml"]
)

a = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=["hooks"],
    excludes=["tkinter", "matplotlib", "pandas.tests"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="carkit",
    console=False,
    icon=None,
)
app = BUNDLE(
    exe,
    name="carkit.app",
    icon=None,
    bundle_identifier="com.a18012239736.carkit",
    version=__version__,
    info_plist={"NSHighResolutionCapable": True},
)
