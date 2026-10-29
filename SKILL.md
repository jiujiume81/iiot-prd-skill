---
name: IIOT-PRD
version: 0.3.0
description: 工业互联网产品经理的需求分析与高保真原型工作台。把口头需求收敛成「可校验的需求契约 + 可直接交给开发的 Vue 高保真原型 + 同源 PRD」，PC 与 PDA 双端同源，配色与组件库面向车间长时间作业场景。流程带闸门（澄清、命令策略、切片清单必须确认，由脚本校验），需求表达遵循 EARS，按钮可用性由状态机推导而非手写 disabled。当用户要做需求分析、需求澄清、写 PRD、画原型、做可交互原型、PDA 页面、工业软件界面、QMS/LIMS/MES 需求、需求评审、Demo 逆向、或要把原型直接交给开发时使用。触发词：需求分析、需求澄清、PRD、原型、高保真原型、可交互原型、PDA、工控、QMS、LIMS、MES、EARS、状态机、按钮置灰、命令策略、用户流、模块清单、页面清单、标注、评审、Demo 逆向、交付开发。
---

# IIOT-PRD — 工业互联网需求分析与高保真原型

把「一句话需求 / 压缩的 Demo」展开成三件同源的东西：**可校验的需求契约（JSON）+ 高保真原型（Vue，直接给开发）+ 同源 PRD（可编辑、可导出）**。

三者读的是同一份 `{产品}.proto.json`——所以改需求只改数据，不改 HTML，不会出现"原型和文档对不上"。

## 开工第一件事：先过闸门，再看契约，最后才画页面

```bash
python3 scripts/check_gate.py shaping/ --proto out.proto.json        # ① 澄清走完没有
python3 scripts/check_contract.py out.proto.json                     # ② 契约是否成立
python3 assets/container/src/build.py --proto out.proto.json \
        --out assets/container/dist/index.html                       # ③ 重出容器
python3 scripts/check_parity.py out.proto.json                       # ④ 三处是否一致
```

**顺序不能换。** ①拦"跳步"和"补签"，②拦"契约不自洽"，③把已成立的东西渲染出来，④确认"契约写的 = 容器显示的 = 导出的 PRD"。

④ 是唯一需要真实浏览器的检查（读 DOM 与导出 MD），它抓的是"改了 proto 忘了重建"这类漂移——契约 11 列、容器还是 10 列，肉眼看不出来，`C-09` 一跑就红。

- ① 出 ERROR：回到对应的澄清步骤，**不许写 `componentTree`**。最硬的一条是 `G-10`：原型的文件写入时间早于 A3 确认时间，直接判定"事后补签"。
- ② 出 ERROR：契约不自洽（命令没人 owns、状态机端点悬空、需求缺非法路径…），画出来的原型一定是错的。
- ③ 前两步都绿了才跑。
- ④ 必须在 ③ 之后跑，否则比的是旧容器 vs 新契约。

首次使用先起骨架，七份模板会自动生成：

```bash
python3 scripts/check_gate.py --init shaping/ --product "新锂想QMS · 来料检验"
```

完整的正向样例在 `examples/shaping-qms/`（七份文档 + `_gate.json`），可直接对照写法。

## 流程：七步，三道卡点

| 步 | 做什么 | 产物 | 卡点 |
|---|---|---|---|
| 0 | 边界：目标 / 非目标 / 数据量与频次 | `shaping/01-positioning.md` | — |
| 1 | 真问题：问题与方案分离、三条替代路径 | `shaping/02-problem.md` | **A1 必须确认** |
| 2 | 角色（含"是否真实存在""是否同一人"） | `shaping/03-roles.md` | — |
| 3 | 场景（含频次、失败兜底） | `shaping/04-scenarios.md` | — |
| 4 | 泳道流程，状态变化写 `from → to` | `shaping/05-user-flows.md` | — |
| 5 | 异常 11 类（软件 8 + 外设/追溯断链/标准版本） | `shaping/06-exceptions.md` | — |
| 6 | 四角色对抗评审（研发/测试/业务/**现场使用者**） | `shaping/07-review.md` | **A2 必须确认** |
| 7 | 落契约：命令矩阵、状态机、EARS、切片 | `{产品}.proto.json` + `slices.json` | **A3 必须确认** |

每步的写法见 `references/01-requirements-method.md`；`check_gate.py` 会逐项检查文档里的小节、表格列、以及 `_gate.json` 里的非目标与量级。**首轮回复只允许澄清问题（5~7 个，尽量给选项）+ 我的假设 + 非目标**，不得出现 JSON 或组件树。

## references 索引

| 文件 | 什么时候读 |
|---|---|
| `01-requirements-method.md` | 澄清阶段全程；七步的判据与盲区 |
| `02-ear-spec.md` | 写 `requirements[]` 时；EARS 六字段逐字段写法、五句式映射、常见写错五类 |
| `03-page-split.md` | 拆模块与页面时；三刀切分、五条硬判据、PRD 十种小节、切片上限 |
| `04-visual-spec.md` | 画原型前；设计令牌全表、PC/PDA 布局规范、组件选型决策、审美的 8 条可判定标准 |
| `05-demo-reverse.md` | 业务方给的是 Demo / 旧系统时；从路由抽模块、从分支抽规则、从状态变化抽状态机 |
| `06-container.md` | 改容器或加组件时；四层结构、渲染引擎、三层状态、标注锚点、导出机制 |

## EARS：六个字段，一个都不能省

```
REQ-00X  标题
角色 actor        谁，用岗位不用人名
触发 trigger      何时/何事触发
规则 rule         约束与前置校验，无主观词
状态机 stateMachine  sm-xxx：from → to（挂哪条命令）
预期 expectation  系统响应，单一响应
验收 acceptance   至少 1 条 kind:"illegal"（状态不符/权限不足/并发冲突）
```

`acceptance` 缺非法路径是 ERROR（`L2-34`），因为只测成功路径的需求等于没写验收。

## 按钮可用性：不写在组件上

```json
{ "id":"cap-approve", "actor":["u-qa"], "from":["reported"],
  "policy":"disabled", "reason":"仅「待审核」可审核", "to":"approved", "stage":"verify" }
```

- 组件只写 `props.capability = "cap-approve"`，**禁止 `disabled:true`**；
- 容器自动拼出完整提示：「仅「待审核」可审核（当前为「已归档」）」；
- `stage` 为 `submit` 与 `verify` 的命令，`actor` 交集必须为空（四眼原则），要一人多角色必须显式 `sameActorOk`。

## 双端同源

| 端 | 设计宽 | 组件前缀 | 硬约束 |
|---|---|---|---|
| PC | 1440（内容区 = 1440 − 侧栏 232） | `pc-*` | 作业型列表页 = 全宽表格 + 行内操作；顶部 0 个指标卡 |
| PDA | 390×844 | `pda` | 每页必须有且仅有一个 `BigAction`；必须显式声明 `onlineOnly` 或 `offline`；触控 ≥44px |

PDA 页不得引用 `pc-*` 组件，反之亦然（`L2-15/16` 会红）。

## 组件：登记 ≠ 实现

`catalog.json` 登记 **54 个**组件，`components.js` 实际实现 **23 个**，每个组件带 `impl: done|todo`。

契约里只能用 `impl=done` 的组件（`L2-51` 会红）——因为用了没实现的组件，运行时会降级成红色虚线框，原型就是残的。这条把"账实不符"从运行时问题提前到构建前。

已实现的是这 23 个，覆盖作业型列表页、详情页、统计页、PDA 取样的全部常见形态：

| 类别 | 已实现 |
|---|---|
| PC 骨架 | `AppShell` `PageShell` `TabStrip` `FilterBar` `StatusBar` `ToolBar` `SectionCard` `Grid` `StatStrip` `Pager` |
| PC 数据 | `DataTable` `Chart`（line/bar/pie/control/pareto）`KpiCard` `ProgressList` `DescList` `Timeline` `StatusFlow` |
| PDA | `PdaShell` `SyncBadge` `ScanBar` `PdaCardList` `NumpadInput` `BigAction` |

要用的组件不在上表里，先实现再写契约；不要先在契约里写上再指望运行时能画出来。

## 容器（三栏，覆盖式）

`assets/container/dist/index.html` 是**单文件、双击即开、离线可用**的交付物，内含 Vue 3.4.38 运行时（143KB）、组件库、渲染引擎、数据。

- **左：页面目录**、**右：PRD**，都是**覆盖层**——展开时压在原型上，不挤压画布。这是硬约束：原型必须是 1:1 真实页面，不能被栏宽压缩成"另一个分辨率"。
- **不缩放**。设计宽即真实宽；要看全貌就收起覆盖层，不靠 `transform: scale` 糊弄。
- 顶部：页面态（默认/加载/空/零结果/异常）· 单据状态（由 stateMachine 驱动）· 标注 · 审核模式 · PRD · 导出。
- 标注：点「标注」→ 点页面元素 → 写一句 → 保存。标注锚定 `nodeId` + 归一化坐标，**换页、改栏宽、重开都不跑位**；导出为「修改指令」可直接喂给下一轮。
- 审核模式：隐藏标注与过程控件，只留原型与 PRD，给评审用。
- 保存：`localStorage` 按 `iiot:{产品}:{版本}` 分键，可一键「重置为 AI 版本」。
- 导出：PRD→Markdown、当前页→单页 HTML（可直接给前端）、当前页→PNG、标注→修改指令、打印/存 PDF。
- 直达参数：`#page=pg-xxx&status=approved&prd=1&toc=1`，方便分享某个状态给评审。

## 视觉令牌

深岩青导航 + 青蓝主色 + 暖中性状态色，专为车间长时间盯屏设计（不是 AntD 默认蓝）：

| 令牌 | 值 | 用途 |
|---|---|---|
| `--ink-900` | `#0B2028` | 导航主体 |
| `--brand-600` | `#0A7183` | 主按钮、选中态 |
| `--brand-400` | `#2AA3B3` | 导航活动指示、进度点 |
| `--page` / `--surface` | `#F2F6F7` / `#FFFFFF` | 工作区 / 卡片 |
| `--ok-600` / `--warn-600` / `--danger-600` | `#1B7A57` / `#9A6508` / `#B23A31` | 合格 / 待处理 / 不合格 |
| 字号 | `{26, 16, 14, 13, 12}` | 标题 16、区块 14、正文 13、表格与标签 12；**26 只给 KPI 数字**，一屏最多一组 |
| 栅格 | 8px 基准；行高 34；页头 52；工具栏 44 | 密度优先 |

## 验收：三层，缺一层就白干

| 层 | 手段 | 判据 |
|---|---|---|
| G 流程 | `check_gate.py`（26） | 七步文档齐、三道卡点已签、非目标 ≥3、量级已量化、异常 11 类、评审四角色各 ≥10 问 |
| L1 结构 | `check_contract.py`（6） | 顶层必填、schemaVersion、设计宽声明、页面必填字段、route 以 `/` 开头 |
| L2 语义 | `check_contract.py`（53） | 四态齐、组件白名单**且已实现**、命令唯一 owner、状态机端点、EARS 非法路径、标注锚点、PDA 策略、角色引用有效 |
| P 切片 | `check_contract.py --plan`（11） | 切片上限、依赖成环、可独立验收 |
| C 一致 | `check_parity.py`（14） | 契约 / 容器 DOM / 导出 MD 三处一致；无降级组件、无 boot-error、无内部标识泄漏 |
| L3 呈现 | 容器内 + 截图 | 覆盖层展开时画布宽度不变、表头不裁切、短字段不折行、字号集合、截图非空白 |

五层各管一件事，**不许互相顶替**：

- G 只读 Markdown 与 `_gate.json`——管"有没有想清楚"，不碰 JSON 结构；
- L1/L2/P 只读 JSON——管"想清楚的东西有没有落成自洽的结构"，看不到渲染结果；
- C 读 DOM 与导出 MD，但以 JSON 为基准——管"三处是否同一份事实"；
- L3 只读 DOM 的度量值（宽度、行数、字号）——读不到 DOM 的条款写进 L1/L2 只会变成"假绿"。

判据的准入门槛只有一条：**答不出「什么输入能让它红」的判据不写**。`scripts/` 三个脚本共 **110 条判据**（G 26 / L1 6 / L2 53 / P 11 / C 14），每条都做过造红验证：闸门 12 条变异、契约 8 条、一致性 3 条，全部命中预期报错。

## 目录

```
IIOT-PRD/
├─ SKILL.md
├─ references/
│  ├─ 01-requirements-method.md   七步澄清的判据与盲区
│  ├─ 02-ear-spec.md              EARS 六字段逐字段写法
│  ├─ 03-page-split.md            模块/页面切分与四类结构统一
│  ├─ 04-visual-spec.md           令牌、布局规范、组件选型、审美判据
│  ├─ 05-demo-reverse.md          从 Demo 抽模块/规则/状态机
│  └─ 06-container.md             容器工程与扩展方式
├─ schemas/proto.schema.json · catalog.json · slice.schema.json
├─ scripts/check_gate.py          流程闸门（G 26）
├─ scripts/check_contract.py      契约校验（L1 6 + L2 53 + P 11）
├─ scripts/check_parity.py        三处一致（C 14，需 Chrome）
├─ examples/
│  ├─ example-00-minimal.proto.json · example-00-slices.json
│  ├─ example-01-qms-incoming.proto.json   三页：报告列表 / PDA 取样 / 统计看板
│  └─ shaping-qms/                七份澄清文档 + _gate.json（正向样例）
└─ assets/container/
   ├─ src/{runtime.js, components.js, app.js, styles.css, build.py, vue.global.prod.js}
   └─ dist/index.html          ← 交付物（单文件）
```

## 不做

不做像素级设计还原（只做规范还原）；不做后端联调；不做多人实时协同；不做移动端 H5（PDA 与 H5 是两种交互，混做必歪）。
