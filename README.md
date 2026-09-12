# CARKIT 车型配置对比工具

CARKIT 是面向汽车产品和竞品分析工作的 Windows 工具，覆盖两条流程：从汽车之家读取车型配置并整理成配置阶梯，以及导入本品配置后与历史竞品逐项比较并计算配置优势。

## 下载 Windows 程序

同事无需安装 Python 或了解代码，直接点击下面的链接下载并运行：

**[下载 CARKIT Windows 程序](https://github.com/a18012239736-rgb/carkit/raw/refs/heads/master/release/carkit.exe)**

如果直接点击没有开始下载，也可以打开 [`release`](https://github.com/a18012239736-rgb/carkit/tree/master/release) 文件夹，点击 `carkit.exe` 后选择下载。下载后双击 `carkit.exe` 即可启动。

## Windows 使用

直接运行打包后的 `carkit.exe`。程序会在桌面创建 `Codex` 文件夹保存数据和结果。抓取时需要 Edge 或 Chrome；遇到汽车之家验证，在浏览器完成验证后回到程序点击“验证后继续读取”。

## 配置阶梯

在“配置阶梯”页面输入车型名称、车系编号或汽车之家配置页网址，选择年款并抓取完整配置。选择输出版型，为每个后续版型指定比较基准，检查配置后导出 Markdown。

程序保留汽车之家原始数据，阶梯文档只记录相对基准增加或减少的项目。历史车型可以继续编辑、重新导出或删除；删除的数据会移入工作目录的回收站。

## 竞争力对比

1. 导入配置阶梯 PPT，或载入已有本品快照。
2. 在完整清单中校对本品配置。未提及的项目按无配置处理，明确待定的项目不参与比较。
3. 选择历史竞品并检查竞品配置。
4. 在当前页面直接修正本品和竞品配置。修正保存到工作副本，不覆盖原始抓取数据。
5. 手动指定版型配对并运行对比。

结果包含 P21 风格竞争力表、41 项判定明细和逐项赋值计算明细，并可导出 Markdown。程序不会按价格自动配对版型。

## 配置与赋值规则

程序使用完整配置清单进行比较。汽车之家没有该配置行，按无配置处理；选装配置不作为标配；清单中标记 `/` 的项目不参与比较和赋值。

当前内置规则包括续航、高压平台、轮径与轮圈材质、气囊、影像、辅助驾驶、天窗、座椅、音响、车联网和热泵空调等项目。赋值规则可在“赋值规则”页面生成模板、载入修改后的 Excel，或使用内置规则。

计算明细会列出每项差异、计价依据、单项金额、多项合计和少项合计，方便复核。

## 工作目录

| 目录 | 内容 |
|---|---|
| `raw/` | 汽车之家原始抓取数据 |
| `阶梯/` | 竞品配置阶梯和编辑副本 |
| `快照/` | 本品配置快照 |
| `赋值/` | 赋值规则模板和文件 |
| `结果/` | 导出的 Markdown 结果 |
| `回收站/` | 删除后可恢复的历史文件 |

运行数据属于使用者本地资料，不应提交到公共代码仓库。

## 开发与测试

项目使用 Python 3.12。安装依赖后运行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
pytest tests -q
```

Windows 打包：

```powershell
powershell -ExecutionPolicy Bypass -File .\build\build_windows.ps1
powershell -ExecutionPolicy Bypass -File .\build\deploy_desktop.ps1
```

打包产物位于 `dist/carkit/`，桌面部署目录为 `C:\Users\Administrator\Desktop\Codex`。
