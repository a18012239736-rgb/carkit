#!/usr/bin/env python3
"""carkit exe 入口 — pywebview 窗口 + Bridge

用法：python app.py [工作目录]
工作目录缺省 = 用户文档目录/carkit（Windows: Documents\\carkit）
"""
from __future__ import annotations
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)


def default_workdir() -> str:
    if len(sys.argv) > 1:
        return os.path.abspath(sys.argv[1])
    # Windows 交付版默认把原始抓取、阶梯和结果都放在桌面 Codex 文件夹，
    # 便于用户直接找到，也避免和开发目录混在一起。
    return os.path.join(os.path.expanduser("~"), "Desktop", "Codex")


def main():
    import webview
    from api.bridge import Bridge

    workdir = default_workdir()
    bridge = Bridge(workdir)
    ui = os.path.join(BASE, "ui", "index.html")

    window = webview.create_window(
        "carkit — 车型配置对比工具",
        ui,
        js_api=bridge,
        width=1360,
        height=900,
        min_size=(1024, 700),
        background_color="#f6f7f9",
    )
    # Windows 上强制 WebView2（Edge Chromium）；缺失时 pywebview 会报错提示安装
    webview.start(debug=os.environ.get("CARKIT_DEBUG") == "1")


if __name__ == "__main__":
    main()
