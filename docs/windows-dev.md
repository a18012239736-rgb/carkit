# Windows 打包与使用说明（给另一台电脑）

## 一、准备（一次性）

1. 装 **Python 3.12**：https://www.python.org/downloads/ （安装时勾选 *Add python.exe to PATH*）
2. 装 **Git**：https://git-scm.com/download/win
3. 确认已装 **Edge**（Win10/11 自带）或 Chrome —— 抓取用它，程序不下载浏览器
4. WebView2 Runtime：Win10/11 一般自带。若启动 carkit 白屏/报错，装微软官方
   `MicrosoftEdgeWebview2Setup.exe`（evergreen bootstrapper，约 2MB）

## 二、拉代码 + 打包

```powershell
git clone https://github.com/a18012239736-rgb/carkit.git
cd carkit
.\build\build_windows.ps1
```

产物：`dist\carkit\carkit.exe`（**onedir 模式**：整个 `dist\carkit` 文件夹就是一个绿色程序，
拷到任何 Win10/11 机器都能双击运行，无需装 Python）。

> 为什么必须在 Windows 上打包：PyInstaller 不能跨系统编译，且 playwright 的
> node driver 是平台二进制。macOS 只负责开发 engine/CLI。

## 三、日常使用流程

1. 双击 `carkit.exe` → 工作目录默认 `文档\carkit`（数据都存这里）
2. **抓取**：填 seriesId（汽车之家配置页 URL 里的数字）→ ①打开配置页 →
   在弹出的浏览器里勾目标年款、取消其他年款、勾「隐藏相同参数」→ ②确认抓取
   - 被反爬拦截/页面改版：浏览器里 Ctrl+S 保存整页 → 用「导入 HTML」兜底
3. **竞品阶梯**：选 raw → 生成 41 项阶梯 → 检查 [待映射] 高亮格 → 保存
4. **快照**：新建/载入自产品快照 → 填 41 项 × 版型（●值 / ✕ / [待定]）→ 保存
5. **赋值表**：生成 xlsx 模板 → 填金额 → 载入（金额留空 = 待赋值，程序不脑补）
6. **赋值对比**：选快照+阶梯 → **手动指定版型配对**（可多组）→ 运行 →
   BACKUP 表 + 41 项判定明细 → 导出 md

## 四、常见问题

| 现象 | 处理 |
|---|---|
| SmartScreen/杀软拦截未签名 exe | 点「更多信息→仍要运行」；长期方案是买代码签名证书 |
| 抓取 0 行 | 页面没加载完就确认了；等表格出现再点②，或改导入 HTML |
| 白屏 | 缺 WebView2 Runtime，见上文第 4 条 |
| pypi 连不上 | 打包脚本会自动切清华镜像 |
| 规则更新（清单 v1→v2） | 替换 `engine/rules/*.json` 后重打包，或直接改 dist 内 `_internal/engine/rules/`（热更新） |

## 五、开发自检

```powershell
.\.venv\Scripts\Activate.ps1
python -m pytest tests/ -q      # golden 回归：判定词须 100% 命中
python cli.py selftest
```
