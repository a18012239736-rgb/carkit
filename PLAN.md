# 车型配置对比工具（carkit）——独立 Windows exe + GUI 实现计划

## Context

pjy 现有两个高频工作流（5C 配置抓取、赋值对比）完全依附于 Claude 的记忆文件、Playwright MCP 和本机环境。目标：把确定性环节沉淀为**独立 Windows exe（带 GUI）**，在无 Claude、无 MCP 的电脑上也能跑完整链路；同时 engine 层与 UI 解耦，本机 Claude 工作流未来可直接调用同一套引擎。

**pjy 已拍板的决策**：
- UI：pywebview + HTML 前端（Windows 自带 WebView2 渲染），**侧边栏导航**布局
- 抓取：程序驱动目标机已装 Edge/Chrome **自动抓 + 手动另存 HTML 导入兜底**
- 功能范围：**赋值对比全链 + 5C 五段制导出**（不做 car-kb 入库）
- **奇瑞 PVA 赋值表废弃不作参考**；41 项配置的赋值金额由 pjy 单独规定 → 程序设计「赋值表」编辑器 + xlsx 导入模板
- 自产品快照：目标机无 Claude 读 PPT → 程序内置快照编辑器（41项×版型），存 JSON 可导入导出

## 交付方式（护栏）

- 代码只落**本地目录**（默认 `~/Desktop/carkit/`），本地 git 版本管理；**不创建任何远端仓库、不推 GitHub**——golden 夹具含 T19NG 敏感产品数据，除非 pjy 明确要求
- Windows 迁移方式：本地拷贝（U盘/网盘由 pjy 自选），打包在 Windows 实机跑 `build_windows.ps1`

## 架构：三层分离

```
~/Desktop/carkit/                    # 项目根（macOS 开发，Windows 实机打包）
├── engine/                          # 纯 Python，零 GUI 依赖，Claude/CLI/exe 共用
│   ├── models.py                    # dataclass：RawTable/Ladder/Snapshot/DiffResult/Valuation
│   ├── rawschema.py                 # 两种既有 raw JSON schema + HTML → canonical RawTable
│   ├── scrape.py                    # playwright channel 驱动系统 Edge/Chrome + 生产级 EVALUATE_JS（内嵌常量）
│   ├── checklist.py                 # 加载 rules/ 41项清单+豁免规则
│   ├── mapper.py                    # raw 行名→41项 三层匹配（精确/别名/模糊）+ 值归一化
│   ├── ladder.py                    # RawTable → 竞品阶梯(41×N)
│   ├── snapshot.py                  # 快照模型 + 「同基础」继承展开 + 复合子项拆分
│   ├── differ.py                    # 判定词引擎（多/少/同/豁免/不计）
│   ├── valuer.py                    # 赋值表 + 分段计价 + 配置优势/拉平/综合竞争力
│   ├── render_backup.py             # deck BACKUP 表 + 41项判定明细 md
│   ├── render_5c.py                 # 五段制 md 模板渲染
│   └── rules/                       # 随包数据文件（唯一事实源，热更新不重打 exe）
│       ├── checklist_v1.json        # 41项+填写规则（从 对比配置清单-v1.md 结构化）
│       ├── exemptions.json          # 6条豁免规则结构化（头枕/KTV/续航微差/内后视镜/选装○/[待定]）
│       ├── aliases.json             # raw行名↔41项 别名映射（可扩充）
│       └── valuation_template.xlsx  # pjy 填的赋值表模板（预填41项，支持三种计价）
├── api/bridge.py                    # pywebview js_api 薄桥：JSON进→engine→JSON出
├── ui/                              # HTML/CSS/JS 前端（index.html + 6 页面）
├── app.py                           # exe 入口（pywebview 窗口）
├── cli.py                           # 同引擎命令行入口（macOS 开发/回归/Claude 调用）
├── tests/golden/                    # Q05+T19NG 回归夹具（拷现有产物）
└── build/                           # carkit.spec + build_windows.ps1（一键打包）
```

## GUI 页面（侧边栏导航，6 页）

| 页 | 功能 | 关键交互 |
|---|---|---|
| 🌐 抓取 | 填 seriesId → 打开真实 Edge 窗口抓取；或导入已存 HTML/raw JSON | 年款勾选+「隐藏相同参数」由 pjy 在弹出的浏览器里手动确认后点「抓取」；抓取状态/行数实时显示 |
| 📋 竞品阶梯 | RawTable → 41项映射 → 41×N 可编辑表格 | 「无该行=✕」自动；映射不中的行标 `[待映射]` 高亮，pjy 点击指定归属；导出 md/xlsx |
| ✏️ 快照 | 自产品编辑器：版型+价格管理、41项×版型填 ●值/✕/[待定] | 「继承自基础型」按钮；复合项（座椅功能）按子项拆分填写；导入/导出 JSON |
| 💰 赋值 | 41项金额编辑：单值 / 分段(每km×元) / 分档(band) / 按颗 | 导入 xlsx 模板；缺项标 `[待赋值]`；金额由 pjy 规定，程序不脑补 |
| ⚔️ 对比 | 选快照+竞品阶梯 → **pjy 下拉指定版型配对**（绝不自动配对）→ 出 BACKUP 表 + 41项判定明细 | 判定词着色（多=绿/少=红/豁免=灰）；导出 md/xlsx；无赋值表时金额行显示「待赋值明细表」 |
| ⚙️ 设置 | 数据目录、浏览器选择(Edge/Chrome)、规则文件版本、golden 自检 | 清单 v1→v2 换 rules 文件即可 |

## 关键设计点

**1. 抓取（scrape.py）**：`playwright channel="msedge"` headful 驱动系统浏览器，不捆绑浏览器二进制。EVALUATE_JS 用已验证的生产版（行 `div[class*="style_row"]`；列=行**直接子级** filter `/style_col/i`，绝不用 `querySelectorAll` 防列数膨胀；双子项 `style_col_sub` 拆分；`i[class*="solid"]`=●、`i[class*="outline"]`=○ 部分匹配防 hash 变更）。降级链：自动抓 → 手动另存 HTML 导入（lxml 跑同款选择器）→ 直接导入 raw JSON（两种既有 schema 都吃）。

**2. canonical RawTable**：统一两种现存 raw JSON（Q05 紧凑双重编码版 / 重抓数据富结构版）+ HTML 解析结果，含 series_id、trims（短名/全称/指导价，价格行自动解析）、rows（name/group/cells[dot/text/subs]）。

**3. 41项映射**：精确→别名→模糊(token重叠+编辑距离,阈值0.6)→命不中标 `[待映射]` 问人。值归一化规则代码化：轮胎只写R值+合并轮圈材质、气囊合成数量、540影像直写、氛围灯多色=256色、○=选装不计有、无行=✕。

**4. diff 引擎**：豁免规则先行（exemptions.json 6条）→ 归一化比较 → 输出 `判定词 自值(对方值)`（格式对齐现有 `赋值对比-T19NGvs启源Q05-2026-09-11.md`）。续航微差/跨档的档距口径做成可配参数。

**5. 赋值引擎**（金额来自 pjy 赋值表，非 PVA）：
- 配置优势 = Σ(多项赋值) − Σ(少项赋值)
- 拉平指导价优势 = 配置优势 + (竞品指导价 − 自产品指导价)×10000 【此公式已从你 Sheet2 手工草稿验证吻合，待你最终确认】
- 综合竞争力 = **公式待 pjy 提供**，做成可插拔；未提供前 GUI/导出显示 `[待公式]`
- 计价类型支持：flat 单值 / segmented 每km×元 / band 分档查表 / per_unit 按颗

**6. 五段制导出（render_5c.py）**：模板化渲染（基本配置段 + `较X +Y万:(Z版)` 升档段 + `>` 选装引用块），遵守既有写法禁令（无emoji/无●○符号/增项不加括号/升档双列增减）。本机 Claude 工作流仍可拿 engine 数据自行灵活措辞。

**7. 与本机 Claude 工作流关系**：skill（5c-car-trim、赋值对比）改为调 `cli.py`/engine；Claude 保留确认门、配对指定、?项补答、灵活写作。rules/ 与算法两端共享同一份。

## 打包与分发（Windows）

- `build/build_windows.ps1` 一键脚本，**必须在 Windows 实机跑**（PyInstaller 不能跨系统编译，playwright node driver 平台相关）：venv → pip install → `pyinstaller carkit.spec`（onedir 模式，`collect_data_files('playwright')` 捆 driver，EVALUATE_JS 内嵌防漏）
- WebView2：Win10/11 一般自带；安装包内置微软官方 evergreen bootstrapper（~2MB）首启检测补装
- 分发：绿色 zip 或 Inno Setup 安装包；未签名 exe 会触发 SmartScreen 警告，建议后续购代码签名证书（不阻塞首版）
- 目标机需已装 Edge 或 Chrome（Win10/11 默认有 Edge）

## 分期里程碑

**P0 — engine 核心 + 回归基线（macOS，CLI 验证，无 GUI）**
- 交付：rules/ 结构化、rawschema、mapper、ladder、snapshot、differ、render_backup、cli.py
- 验证（golden 回归）：吃现有 Q05 raw JSON + T19NG 快照（转 JSON）→ 跑 diff → 与现有 `赋值对比-T19NGvs启源Q05-2026-09-11.md` 的 41 项判定明细**逐项比对，判定词+值 100% 命中**；BACKUP 表多/少两行一致（金额行留空）

**P1 — GUI 整链 + 赋值 + 首版 exe（Windows 实机打包）**
- 交付：pywebview 6 页、快照编辑器、赋值表编辑器、valuer、HTML/JSON 导入兜底、打包脚本
- 验证：Windows 实机打出 exe，导入 Q05 数据 + T19NG 快照 + pjy 填的赋值表 → GUI 出 BACKUP 表；配置优势/拉平公式用你确认的赋值金额抽验；综合竞争力显 `[待公式]`

**P2 — live 抓取 + 五段制导出 + 综合竞争力**
- 交付：抓取页（channel 驱动系统 Edge）、年款确认流程、render_5c、综合竞争力公式接入（待 pjy 给公式）
- 验证：Windows 实机抓 Q05(8241)，输出与现有 raw JSON 逐行 diff（229行/headers/关键值一致）；失败自动落 HTML 兜底；五段制 md 与现有 `5C-看竞争-启源Q05.md` 结构比对

## 需要 pjy 提供/确认的（实现中逐条问，不阻塞开工）

1. **综合竞争力公式**（P2 前）：手工草稿的 −2609/−1249/1741 无法唯一反推，需你给完整公式
2. **拉平指导价公式确认**：`配置优势 + 价差×10000` 是否就是最终口径
3. **续航「微差 vs 跨档」口径**：500vs506 不计、500vs405 计——分档标准（差值阈值？固定档位表？）
4. **41 项赋值金额表**：程序出 xlsx 模板后由你填（P1 验证前需要）

## 主要风险与缓解

| 风险 | 缓解 |
|---|---|
| PyInstaller 漏 playwright driver → exe 内抓取崩溃 | spec 里 collect-all；Windows 实机早验证；HTML 导入兜底 P1 即可用，抓取失败不断链 |
| 汽车之家反爬/改版 | channel+headful 真实浏览器降检测；选择器集中一处可改；三层降级链 |
| 年款 checkbox 难自动化 | 弹出真实浏览器由 pjy 手动勾选确认（本就对应原工作流人工步骤）；或抓全表按 headers 年款过滤 |
| 41项映射歧义 | 三层匹配+`[待映射]`人工裁决，绝不脑补；aliases.json 可扩充 |
| 杀软/SmartScreen 拦未签名 exe | 文档说明+后续代码签名；绿色 zip 分发 |
| 规则版本漂移 | rules/ 带 version，结果 md 记录所用规则版本 |

## 验证方式（端到端）

1. macOS：`python cli.py diff --snapshot T19NG.json --ladder Q05.json --pairs ...` 输出与现有对比结果 md 逐项一致（P0 锚点）
2. Windows 实机：双击 exe → 导入 Q05 raw JSON → 快照 → 填赋值 → 配对 → 出 BACKUP 表 → 导出 md，全程无 Claude
3. Windows 实机：seriesId 8241 live 抓取 → 与既有 raw JSON 逐行 diff
4. 五段制导出与 `5C-看竞争-启源Q05.md` 结构比对
