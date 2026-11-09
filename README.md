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
一份 `proto.json` 同时驱动容器渲染、PRD 导出、标注、分批。一致性由 `check_parity.py` 读 DOM 与导出 MD 反查 JSON 来守，抓的是"改了 proto 忘了重建"这类肉眼看不出的漂移。

**三、所有操作都堆进详情页，进去不知道先干什么。**
「过程排查」「原因分析」「措施下发」如果做成详情页里的三个可编辑区块，信息是齐的，但责任、时点、校验全糊在一起。这套把每个推进动作立成**一个单据状态 + 一条命令 + 一个权限点**（待排查→排查、待分析→分析、待下发→下发…），详情页只读，动作由 `capabilities[].ui` 声明用弹框、抽屉还是独立页承载。`check_interact.py` 会把每条命令真点一遍，确认弹得出来、关得上、状态推进后列表跟着变。

## 开工第一件事：先过闸门，再看契约，最后才画页面

```bash
python3 scripts/check_gate.py shaping/ --proto out.proto.json        # ① 澄清走完没有
python3 scripts/check_contract.py out.proto.json                     # ② 契约是否成立
python3 assets/container/src/build.py --proto out.proto.json \
        --out assets/container/dist/index.html                       # ③ 重出容器
python3 scripts/check_parity.py out.proto.json                       # ④ 三处是否一致
python3 scripts/check_interact.py --proto out.proto.json \
        --html assets/container/dist/index.html                       # ⑤ 真点一遍
```

顺序不能换。① 拦"跳步"和"事后补签"，② 拦"契约不自洽"，③ 把已成立的东西渲染出来，④ 确认"契约写的 = 容器显示的 = 导出的 PRD"，⑤ 确认"点下去真的有反应"。

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

`assets/container/dist/index.html` 是单文件、双击即开、离线可用的交付物，内含 Vue 3.4.38 运行时（143KB）、24 个组件、渲染引擎与数据。

- 左侧页面目录、右侧 PRD 都是**覆盖层**，展开时压在原型上，不挤压画布。原型必须是 1:1 真实页面，不能被栏宽压缩成"另一个分辨率"。
- **目录是树**：分组可折叠、当前页分支自动展开、顶部搜索即过滤（命中项带完整路径）。层级上限 3 层。
- **不缩放**。设计宽即真实宽；要看全貌就收起覆盖层，不靠 `transform: scale` 糊弄。
- 顶部：页面态（默认 / 加载 / 空 / 零结果 / 异常）· 单据状态（由状态机驱动）· 标注 · 审核模式 · PRD · 导出。
- **可点击**：命令按 `capabilities[].ui` 打开弹框 / 抽屉 / 独立页，表格行点了进详情，目录项点了换页（未建模模块给原因）。弹层四条关闭通道（× / 取消 / Esc / 遮罩）都通。
- **标注**锚定 `nodeId` + 归一化坐标，换页、改栏宽、重开都不跑位；弹框/抽屉里的字段也能标；存储不按版本分键，**重出一版原型标注还在**；标完成必须写解决方法，落点被删的归到「落点已失效」而不是静默消失。
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

`schemas/catalog.json` 登记 54 个组件，`components.js` 实际实现 24 个，每个带 `impl: done|todo`。契约里只能用 `impl=done` 的组件——用了没实现的，运行时会降级成红色虚线框，原型就是残的。这条把"账实不符"从运行时问题提前到构建前。

要用的组件不在已实现清单里，先实现再写契约。

## 验收：152 条判据 + 交互实测，每条都做过造红验证

| 层 | 手段 | 条数 | 管什么 |
|---|---|---|---|
| G 流程 | `check_gate.py` | 24 | 七步文档齐、三道卡点已确认、非目标 ≥3、量级已量化、异常 11 类、评审四角色各 ≥10 问 |
| L1 结构 | `check_contract.py` | 6 | 顶层必填、schemaVersion、设计宽声明、页面必填字段、route 格式 |
| L2 语义 | `check_contract.py` | 92 | 四态齐、组件白名单且已实现、命令唯一 owner、状态机端点、EARS 非法路径、标注锚点与解决方法、目录树层级与 key 唯一、PDA 策略、角色引用有效、状态条与表单不得渲染成空块；字段主档与渲染位双向绑定、取数链路可解析、录入位规则/展示位空值口径；业务规则形状与拦人必给提示；决策项形状 |
| P 切片 | `check_contract.py --plan` | 11 | 切片上限、依赖成环、可独立验收 |
| C 一致 | `check_parity.py` | 19 | 契约 / 容器 DOM / 导出 MD 三处一致；无降级组件、无 boot-error、无内部标识泄漏；命令 `from` 在表格 mock 数据里必须有对应行；PRD 第 4 章字段字典与主档同集同序；PRD 覆盖每条业务规则/需求/决策；PRD 不得出现占位空节；**产物自证来源**：PRD 头部与 HTML meta 的契约 sha256 必须等于当前契约，没有指纹行同样判红 |
| R 交互 | `check_interact.py` | 用例随契约生成 | 每条 dialog/drawer 命令点了要弹、Esc 要关，且弹层不遮顶部工具条；目录项点了要换页、分组能折叠再展开；弹层里的字段能标注且 pin 落在弹层上；行点了要进详情；**R-06/R-07 逐页逐角色**：切无权角色这批命令一条都不在、格子不留白，切回有权角色命令回来且点得开；**R-08 默认「全部角色（不限）」**：一进来推进命令全可见可点，且 `RD.can` 第三参缺省与顶栏「不限」走同一分支；**R-09 绕过界面调 `RD.action`**：角色不对、状态不对都要拒，断言载体状态没变；**R-10 承载用例三级判定**：入口不在 DOM / 状态到位仍点不开 / 点开却是空壳都记红，"数据里没有落在 from 上的行"降 WARN 交 C-21；**R-11 点字段标签定位到字段块并高亮**；**R-12 字段点击不劫持输入、标注模式优先** |
| L3 呈现 | 容器内 + 截图 | — | 覆盖层展开时画布宽度不变、表头不裁切、短字段不折行、弹层上沿让开 44px 顶栏、字号集合、截图非空白 |

判据的准入门槛只有一条：**答不出「什么输入能让它红」的判据不写**。152 条契约层判据全部做过变异造红：闸门、契约、一致性三层均有命中记录。编号只增不复用，`L2-75/76/78` 是主动删除留下的空号、`L2-87/88` 留给视觉层、`L2-95` 留给 setState、`C-14~C-20` 未实装——**这是实装数，不是规划数**。`L2-40/41/42` 随 `fieldRegistry` 废弃删除、`L2-10/11/12` 随页级 `flow` 移除删除，被判对象不存在，不是放松；休眠判据（对象没了、没有输入能让它红）同样删，不留在条数里充数。R 层另实装 7 条（R-06~R-12），同样造过红：把引擎里开弹层那行去掉，9 条命令立刻失败；把「角色不匹配就不渲染」退化成只置灰，R-06 立刻点名 7 条命令仍在渲染；把 `RD.action` 退回 `can(capId, null)`，R-09 立刻报「执行中直接被改成已完成」；把字段块 id 退回 `field-{页}-{key}`，R-11 立刻报「点列上的 dept 却落在筛选条那块」。

C 层与 R 层需要本机装 Chrome。R 层用例随契约自动生成，除了"每条命令点了要弹、Esc 要关"，还固定带三条守卫：弹层里能标注且 pin 落在弹层上、旧版本存储桶里的标注升版后还在（把存储键前缀改坏就会红）、顶栏「目录」的页面目录是真树（分组能开能合、叶子点了换页并收面板，把折叠那行去掉就报"行数 8→8→8"）。

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
│  ├─ 06-container.md             容器工程与扩展方式
│  └─ 07-report-to-user.md        A1/A2/A3 跟人怎么说（大白话模板）
├─ schemas/                       proto.schema.json · catalog.json · slice.schema.json
├─ scripts/                       check_gate.py · check_contract.py · check_parity.py · check_interact.py
├─ examples/
│  ├─ example-00-minimal.*.json   最小可跑样例
│  ├─ example-01-qms-incoming.proto.json   三页：报告列表 / PDA 取样 / 统计看板
│  ├─ example-02-accident.proto.json       四页：台账 / 我的待办 / 只读详情 / 新建（推进动作样例）
│  └─ shaping-qms/                七份澄清文档 + _gate.json（正向样例）
└─ assets/container/
   ├─ src/                        runtime.js · components.js · app.js · styles.css · build.py
   └─ dist/index.html             交付物（单文件，339KB）
```

## 装到本地

```bash
git clone https://github.com/jiujiume81/iiot-prd-skill.git ~/.workbuddy/skills/IIOT-PRD
```

Claude Code 用户放 `~/.claude/skills/IIOT-PRD`。目录名须为 `IIOT-PRD`，与 `SKILL.md` 里的 `name` 一致。

## 不做

不做像素级设计还原（只做规范还原）；不做后端联调；不做多人实时协同；不做移动端 H5（PDA 与 H5 是两种交互，混做必歪）。

## 依赖

Python 3.8+（四个校验脚本 + 构建脚本，仅标准库）。C 层一致性与 R 层交互实测需 Chrome。容器运行时不依赖网络。

## License

MIT
