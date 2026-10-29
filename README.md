# IIOT-PRD — 工业互联网需求分析与高保真原型工作台

一个给工业互联网产品经理用的 skill（面向 Claude Code / WorkBuddy 等支持 skill 的 agent）。

把「一句话需求」或「一段压缩的 Demo」展开成三件同源的东西：

| 产物 | 形态 | 给谁 |
|---|---|---|
| 需求契约 | `{产品}.proto.json` | 校验器、渲染引擎、PRD 导出——单一真源 |
| 高保真原型 | Vue 3 单文件 HTML，双击即开 | 直接交给前端开发 |
| PRD | 容器内可编辑，可导出 Markdown | 评审、存档、对外 |

三者读的是同一份 JSON，所以改需求只改数据、不改 HTML，不会出现"原型和文档对不上"。

## 它解决的两个老问题

**一、按钮为什么是灰的，说不清。**
按钮可用性不写在组件上，由状态机 + 命令矩阵推导。组件只写 `props.capability = "cap-approve"`，禁止 `disabled: true`；容器自动拼出完整提示「仅「待审核」可审核（当前为「已归档」）」。提交与审核两条命令的角色交集必须为空（四眼原则），要一人多角色必须显式 `sameActorOk`。

**二、原型与 PRD 各写一遍，然后对不上。**
一份 `proto.json` 同时驱动容器渲染、PRD 导出、标注、切片。一致性由 `check_parity.py` 读 DOM 与导出 MD 反查 JSON 来守，抓的是"改了 proto 忘了重建"这类肉眼看不出的漂移。

## 开工第一件事：先过闸门，再看契约，最后才画页面

```bash
python3 scripts/check_gate.py shaping/ --proto out.proto.json        # ① 澄清走完没有
python3 scripts/check_contract.py out.proto.json                     # ② 契约是否成立
python3 assets/container/src/build.py --proto out.proto.json \
        --out assets/container/dist/index.html                       # ③ 重出容器
python3 scripts/check_parity.py out.proto.json                       # ④ 三处是否一致
```

顺序不能换。① 拦"跳步"和"事后补签"，② 拦"契约不自洽"，③ 把已成立的东西渲染出来，④ 确认"契约写的 = 容器显示的 = 导出的 PRD"。

首次使用先起骨架，七份澄清模板自动生成：

```bash
python3 scripts/check_gate.py --init shaping/ --product "产品名 · 模块名"
```

正向样例在 `examples/shaping-qms/`（七份澄清文档 + `_gate.json`），可直接对照写法。

## 流程：七步，三道确认卡点

| 步 | 做什么 | 产物 | 卡点 |
|---|---|---|---|
| 0 | 边界：目标 / 非目标 / 数据量与频次 | `01-positioning.md` | — |
| 1 | 真问题：问题与方案分离、三条替代路径 | `02-problem.md` | **A1 确认** |
| 2 | 角色（含"是否真实存在""是否同一人"） | `03-roles.md` | — |
| 3 | 场景（含频次、失败兜底） | `04-scenarios.md` | — |
| 4 | 泳道流程，状态变化写 `from → to` | `05-user-flows.md` | — |
| 5 | 异常 11 类（软件 8 + 外设 / 追溯断链 / 标准版本） | `06-exceptions.md` | — |
| 6 | 四角色对抗评审（研发 / 测试 / 业务 / **现场使用者**） | `07-review.md` | **A2 确认** |
| 7 | 落契约：命令矩阵、状态机、EARS、切片 | `*.proto.json` + `slices.json` | **A3 确认** |

首轮回复只允许澄清问题（5~7 个，尽量给选项）+ 我的假设 + 非目标，不得出现 JSON 或组件树。

## EARS：六个字段，一个都不能省

```
REQ-00X  标题
角色 actor          谁，用岗位不用人名
触发 trigger        何时 / 何事触发
规则 rule           约束与前置校验，无主观词
状态机 stateMachine sm-xxx：from → to（挂哪条命令）
预期 expectation    系统响应，单一响应
验收 acceptance     至少 1 条 kind:"illegal"（状态不符 / 权限不足 / 并发冲突）
```

`acceptance` 缺非法路径直接报错——只测成功路径的需求等于没写验收。

## 双端同源

| 端 | 设计宽 | 组件前缀 | 硬约束 |
|---|---|---|---|
| PC | 1440（内容区 = 1440 − 侧栏 232） | `pc-*` | 作业型列表页 = 全宽表格 + 行内操作；顶部 0 个指标卡 |
| PDA | 390 × 844 | `pda` | 每页有且仅有一个 `BigAction`；必须声明 `onlineOnly` 或 `offline`；触控 ≥ 44px |

PDA 页不得引用 `pc-*` 组件，反之亦然，校验器会红。

## 容器：三栏，覆盖式，不缩放

`assets/container/dist/index.html` 是单文件、双击即开、离线可用的交付物，内含 Vue 3.4.38 运行时（143KB）、23 个组件、渲染引擎与数据。

- 左侧页面目录、右侧 PRD 都是**覆盖层**，展开时压在原型上，不挤压画布。原型必须是 1:1 真实页面，不能被栏宽压缩成"另一个分辨率"。
- **不缩放**。设计宽即真实宽；要看全貌就收起覆盖层，不靠 `transform: scale` 糊弄。
- 顶部：页面态（默认 / 加载 / 空 / 零结果 / 异常）· 单据状态（由状态机驱动）· 标注 · 审核模式 · PRD · 导出。
- 标注锚定 `nodeId` + 归一化坐标，换页、改栏宽、重开都不跑位；导出为「修改指令」可直接喂给下一轮。
- 直达参数：`#page=pg-xxx&status=approved&prd=1&toc=1`，方便把某个状态分享给评审。

## 视觉令牌

深岩青导航 + 青蓝主色 + 暖中性状态色，为车间长时间盯屏设计（不是 AntD 默认蓝）：

| 令牌 | 值 | 用途 |
|---|---|---|
| `--ink-900` | `#0B2028` | 导航主体 |
| `--brand-600` | `#0A7183` | 主按钮、选中态 |
| `--brand-400` | `#2AA3B3` | 导航活动指示、进度点 |
| `--page` / `--surface` | `#F2F6F7` / `#FFFFFF` | 工作区 / 卡片 |
| `--ok-600` / `--warn-600` / `--danger-600` | `#1B7A57` / `#9A6508` / `#B23A31` | 合格 / 待处理 / 不合格 |
| 字号 | `{26, 16, 14, 13, 12}` | 标题 16、区块 14、正文 13、表格 12；26 只给 KPI 数字，一屏最多一组 |
| 栅格 | 8px 基准；行高 34；页头 52；工具栏 44 | 密度优先 |

## 组件：登记 ≠ 实现

`schemas/catalog.json` 登记 54 个组件，`components.js` 实际实现 23 个，每个带 `impl: done|todo`。契约里只能用 `impl=done` 的组件——用了没实现的，运行时会降级成红色虚线框，原型就是残的。这条把"账实不符"从运行时问题提前到构建前。

要用的组件不在已实现清单里，先实现再写契约。

## 验收：110 条判据，每条都做过造红验证

| 层 | 手段 | 条数 | 管什么 |
|---|---|---|---|
| G 流程 | `check_gate.py` | 26 | 七步文档齐、三道卡点已确认、非目标 ≥3、量级已量化、异常 11 类、评审四角色各 ≥10 问 |
| L1 结构 | `check_contract.py` | 6 | 顶层必填、schemaVersion、设计宽声明、页面必填字段、route 格式 |
| L2 语义 | `check_contract.py` | 53 | 四态齐、组件白名单且已实现、命令唯一 owner、状态机端点、EARS 非法路径、标注锚点、PDA 策略、角色引用有效 |
| P 切片 | `check_contract.py --plan` | 11 | 切片上限、依赖成环、可独立验收 |
| C 一致 | `check_parity.py` | 14 | 契约 / 容器 DOM / 导出 MD 三处一致；无降级组件、无 boot-error、无内部标识泄漏 |
| L3 呈现 | 容器内 + 截图 | — | 覆盖层展开时画布宽度不变、表头不裁切、短字段不折行、字号集合、截图非空白 |

判据的准入门槛只有一条：**答不出「什么输入能让它红」的判据不写**。110 条全部做过变异造红：闸门 12 条、契约 8 条、一致性 3 条，全部命中预期报错。

C 层需要本机装 Chrome。

## 目录

```
IIOT-PRD/
├─ SKILL.md                       技能主文件（触发词、流程、判据总表）
├─ references/
│  ├─ 01-requirements-method.md   七步澄清的判据与盲区
│  ├─ 02-ear-spec.md              EARS 六字段逐字段写法
│  ├─ 03-page-split.md            模块/页面切分与结构统一
│  ├─ 04-visual-spec.md           令牌、布局规范、组件选型、审美判据
│  ├─ 05-demo-reverse.md          从 Demo 抽模块 / 规则 / 状态机
│  └─ 06-container.md             容器工程与扩展方式
├─ schemas/                       proto.schema.json · catalog.json · slice.schema.json
├─ scripts/                       check_gate.py · check_contract.py · check_parity.py
├─ examples/
│  ├─ example-00-minimal.*.json   最小可跑样例
│  ├─ example-01-qms-incoming.proto.json   三页：报告列表 / PDA 取样 / 统计看板
│  └─ shaping-qms/                七份澄清文档 + _gate.json（正向样例）
└─ assets/container/
   ├─ src/                        runtime.js · components.js · app.js · styles.css · build.py
   └─ dist/index.html             交付物（单文件，291KB）
```

## 装到本地

```bash
git clone https://github.com/jiujiume81/iiot-prd-skill.git ~/.workbuddy/skills/IIOT-PRD
```

Claude Code 用户放 `~/.claude/skills/IIOT-PRD`。目录名须为 `IIOT-PRD`，与 `SKILL.md` 里的 `name` 一致。

## 不做

不做像素级设计还原（只做规范还原）；不做后端联调；不做多人实时协同；不做移动端 H5（PDA 与 H5 是两种交互，混做必歪）。

## 依赖

Python 3.8+（三个校验脚本 + 构建脚本，仅标准库）。C 层一致性检查需 Chrome。容器运行时不依赖网络。

## License

MIT
