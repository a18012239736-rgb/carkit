# -*- mode: python ; coding: utf-8 -*-
# carkit PyInstaller spec —— 只在 Windows 实机跑（playwright node driver 是平台二进制）
# 用法: pyinstaller build/carkit.spec --noconfirm
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ("../ui", "ui"),
    ("../engine/rules", "engine/rules"),
    ("../engine/*.js", "engine"),
]
# playwright 的 node driver 必须整体收集，否则 live 抓取在 exe 内崩溃（最大坑）
datas += collect_data_files("playwright")

hiddenimports = (
    collect_submodules("webview")
    + collect_submodules("engine")
    + ["clr", "clr_loader", "pythonnet", "openpyxl", "lxml"]
)

a = Analysis(
    ["../app.py"],
    pathex=[".."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=["hooks"],
    excludes=["tkinter", "matplotlib", "pandas.tests"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="carkit",
    console=False,               # GUI 程序不带控制台
    icon=None,
    version=None,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    name="carkit",                # onedir 模式：dist/carkit/carkit.exe
)
