# Windows 打包与使用说明（给另一台电脑）

## 一、准备（本地开发与打包）

1. 装 **Python 3.12**：https://www.python.org/downloads/ （安装时勾选 *Add python.exe to PATH*）
2. 装 **Git**：https://git-scm.com/download/win
3. 确认已装 **Edge**（Win10/11 自带）或 Chrome —— 抓取用它，程序不下载浏览器
4. WebView2 Runtime：Win10/11 一般自带。若启动 carkit 白屏/报错，装微软官方
   `MicrosoftEdgeWebview2Setup.exe`（evergreen bootstrapper，约 2MB）
5. 装 **Node.js** 并确认 `node` 可在终端运行，前端回归测试需要它。

日常使用只需从 [GitHub 最新发布页](https://github.com/a18012239736-rgb/carkit/releases/latest)
下载 `carkit.exe`，无需安装 Python、Git 或 Node.js；仍需 Edge / Chrome 和 WebView2 Runtime。

## 二、拉代码 + 打包

```powershell
git clone https://github.com/a18012239736-rgb/carkit.git
cd carkit
.\build\build_windows.ps1
```

产物：`dist\carkit.exe`（**onefile 模式**：Python DLL、Playwright driver、UI 和规则文件都在
一个 exe 中，无需另带 `_internal` 文件夹）。构建脚本还会把该文件复制到
`release\carkit.exe`，供本地使用。对外下载以 [GitHub Release 最新的 carkit.exe](https://github.com/a18012239736-rgb/carkit/releases/latest/download/carkit.exe)
为准，仓库 `release/` 中的历史程序不随每次发布更新。

推送 `v*` 标签（如 `v0.2.2`）后，GitHub Actions 会在 Windows 上自动运行全部测试、
打包单文件程序，并在独立目录验证窗口启动，通过后将 `carkit.exe` 上传到该标签的 GitHub Release。

> 为什么必须在 Windows 上打包：PyInstaller 不能跨系统编译，且 playwright 的
> node driver 是平台二进制。macOS 只负责开发 engine/CLI。

## 三、日常使用流程

1. 双击 `carkit.exe`，工作目录默认是桌面的 `Codex` 文件夹，历史数据和结果保存在这里。
2. **配置阶梯**：输入车型名称、车系编号或汽车之家配置页网址，点击“搜索车型”，按提示选择车型和年款。
   遇到网站验证时，在弹出的浏览器完成验证，再回到程序点击“验证后继续读取”。
   读取时保留完整配置表，关闭“隐藏相同参数”和“隐藏暂无内容”，避免缺行。
   也可展开“导入本地配置数据”导入保存的完整 HTML 或 raw JSON。
3. **配置阶梯**：选择输出版型、基本版型和各版型比较基准，检查配置，在“预览与导出”区查看阶梯、导出 Markdown 或 Excel。
   再次使用时可点击“打开历史车型”。
4. **本品配置**：导入配置阶梯 PPT 或手动添加本品，核对版型、价格口径、继承关系及完整配置表，勾选确认后保存。
   未提及或明确没有的配置填 `✕`，尚未确认的配置保留 `[待定]`。
5. **赋值规则**：修改金额、档位和阈值，点击“保存并立即应用”。也可从 Excel / JSON 导入，再保存应用；缺赋值时程序提示待赋值。
6. **竞争力对比**：选择“本品 vs 竞品”或“竞品 vs 竞品”，检查两侧配置，**手动指定版型配对**（可多组），
   可选填双方底价后点击“开始对比”。在结果区检查待核清单、竞争力表和配置项明细，导出 Markdown / Excel，或填写方案名称并“保存当前方案”。
   继续之前的工作可展开页面上方的“打开已保存方案”。

## 四、常见问题

| 现象 | 处理 |
|---|---|
| SmartScreen/杀软拦截未签名 exe | 点「更多信息→仍要运行」；长期方案是买代码签名证书 |
| 抓取 0 行 | 等完整配置表加载并完成网站验证，再点击“验证后继续读取”；也可导入完整 HTML |
| 白屏 | 缺 WebView2 Runtime，见上文第 4 条 |
| pypi 连不上 | 打包脚本会自动切清华镜像 |
| `Failed to load Python DLL ... _internal\python312.dll` | 这是旧目录版只复制了 exe；改用 GitHub 最新发布页的单文件 `carkit.exe` |
| 规则更新（清单 v1→v2） | 替换 `engine/rules/*.json` 后重新打包；单文件版不支持直接修改 `_internal` 热更新 |

## 五、开发自检

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest tests/ -q      # golden 回归：判定词须 100% 命中
python cli.py selftest
```
