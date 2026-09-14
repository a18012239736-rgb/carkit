# -*- mode: python ; coding: utf-8 -*-
# carkit PyInstaller spec —— 只在 Windows 实机跑（playwright node driver 是平台二进制）
# 用法: pyinstaller build/carkit.spec --noconfirm
#
# 使用 onefile 模式。release/carkit.exe 会被同事单独下载，因此 Python DLL、
# Playwright driver、UI 和规则文件都必须打进同一个 exe，不能依赖旁边的
# _internal 目录。
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from pathlib import Path

ROOT = Path(SPECPATH).parent

datas = [
    (str(ROOT / "ui"), "ui"),
    (str(ROOT / "engine/rules"), "engine/rules"),
    (str(ROOT / "engine/*.js"), "engine"),
]
# playwright 的 node driver 必须整体收集，否则 live 抓取在 exe 内崩溃（最大坑）
datas += collect_data_files("playwright")

hiddenimports = (
    collect_submodules("webview")
    + collect_submodules("engine")
    + ["clr", "clr_loader", "pythonnet", "openpyxl", "lxml"]
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
    console=False,               # GUI 程序不带控制台
    icon=None,
    version=None,
)
