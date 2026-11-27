---
name: iiot-prototype
version: 0.3.0
agent_created: true
description: 高保真原型设计（三段式第 3 段）：读一份已成立的需求契约（{产品}.proto.json 的需求半边），产出可直接交给开发的 Vue 单文件原型（PC 与 PDA 双端同源、离线双击即开、三栏覆盖式容器）、页面目录树、页面标注，以及同源 PRD（md/html 可导出可打印），并用三层脚本验收——契约全场结构、契约/容器/PRD 三处一致、无头浏览器逐条真点一遍。按钮可用性由状态机推导而非手写置灰，推进动作各自成为单据状态，组件只用已实现的白名单。只做界面与渲染，不改业务语义、不写 EARS、不重扫场景。当用户说「画原型」「做个高保真」「出 PRD」「PDA 页面长什么样」「页面怎么拆」「把原型交给开发」「这里加个标注」「交互能点吗」，或项目里已有 proto.json 时使用。触发词：原型、高保真、可交互原型、原型设计、页面、拆页面、页面目录、PDA、工控界面、容器、组件、组件树、标注、PRD 导出、导出 PRD、交付开发、审核模式、截图、三处一致、真点一遍、已有 proto。要改流程、异常或验收条件用 iiot-req-analysis；要从零判断该不该做用 iiot-business-analysis。
---

# iiot-prototype — 高保真原型设计（第 3 段）

前两段把"做什么"说清楚了，这一段负责"**长什么样、点得动吗、和文档对得上吗**"。交付物三件同源：一份单文件 HTML（双击即开）、一份 PRD、一份标注记录。

> **路径约定**：`$SUITE` = `/Users/yuxiufu/WorkBuddy/原型PRD/iiot-prd-suite`，进来先设一次：
>
> ```bash
> SUITE=/Users/yuxiufu/WorkBuddy/原型PRD/iiot-prd-suite
> ```
>
> 容器与脚本都只有一份物理副本（在 `shared/` 下），四段共用。**不要复制一份到自己目录**，改了一处另外三处不会知道。

## 一、进来先判断我在哪一段

| 现场 | 判定 | 动作 |
|---|---|---|
| 项目里没有 `{产品}.proto.json`，或 `stages["2"].status != "done"` | 契约还没成立 | **拒绝开工**。回一句"契约还没落"，给出 02 的命令。不许"先画个大概" |
| 有 proto，但 `check_contract --half req` 红 | 需求半边不成立或被人改过 | 拒绝开工，把红的那几条原样贴给用户，回 02 |
| `stage = 3` 且 `--half req` 绿 | 是我的段 | 从第一个没做完的步继续 |
| `stages["3"].status = done` | 已完成 | 不重出容器。问一句要不要加标注、要不要重出 PRD |

判定的第一条命令不是画图，是复核上游：

```bash
python3 $SUITE/shared/bin/check_contract.py --half req {产品}.proto.json
```

绿 = 需求半边没被动过；红 = 要么上游交付本身就坏，要么有人在别处改了语义。**两种情况都不是本段能修的。**

## 二、本段做什么

| 项 | 内容 |
|---|---|
| **入口读什么** | `{产品}.proto.json`（需求半边：角色/命令矩阵/状态机/EARS/字段主档/页面骨架）、`slices.json`。**不读上游任何 md** |
| **出口写什么** | 同一份 proto 上**追加**：`pages[].componentTree` / `pages[].interactions` / `pages[].prd` / `capabilities[].ui`；另出 `dist/index.html`、`PRD-{产品}.md`、`PRD-{产品}.html`、`figs/*.svg` |
| **卡点** | ① `check_contract --half req` 绿（入场券）；② **不带 `--half` 的全场** `check_contract` 绿；③ `check_parity` 三处一致；④ `check_interact` 真点一遍。四道全过才算交付 |
| **下游拿它干什么** | 人。审核的人看容器，开发拿走 HTML 与 PRD，下一轮改需求的人回来改 proto 再重建 |

### 五步

| 步 | 做什么 | 判据落点 |
|---|---|---|
| **P1 切页** | 按功能模块切页面；一张单据只给一个主列表，第二个列表只能是过滤视图 | `L2-74`、`L2-80`~`L2-82`、`L2-90`~`L2-92` |
| **P2 填骨架** | 每页四态齐、组件只选 `impl=done`、字段渲染位与主档双向绑定、每条命令声明 `ui.kind` | `L1-05`、`L2-14`、`L2-51`、`L2-55`、`L2-96`~`L2-101` |
| **P3 出容器** | 重建单文件 HTML（Vue 运行时内嵌、离线可用、三栏覆盖层、不缩放） | 构建成功、无降级组件 |
| **P4 对三处** | 契约 / 容器 DOM / 导出 md 三处同一份事实；PRD 头部指纹等于当前契约 | `C-09`、`C-21`~`C-25` |
| **P5 真点** | 逐条命令点开弹层、切角色、点目录、点字段、Esc 关闭、标注落位 | `R-06`~`R-12` |

### 命令

```bash
# ① 入场券（复核需求半边，见 §一）
python3 $SUITE/shared/bin/check_contract.py --half req {产品}.proto.json

# ② 重建容器（build.py 必须用物理路径，它靠自身目录找 styles.css 等）
python3 $SUITE/shared/assets/container/src/build.py \
        --proto $PWD/{产品}.proto.json --out $PWD/dist/index.html

# ③ 全场契约（不带 --half，这才是"契约成立"）
python3 $SUITE/shared/bin/check_contract.py {产品}.proto.json

# ④ 三处一致（需 Chrome）
python3 $SUITE/shared/bin/check_parity.py {产品}.proto.json --html dist/index.html

# ⑤ 真点一遍（需 Chrome）
python3 $SUITE/shared/bin/check_interact.py --proto {产品}.proto.json --html dist/index.html

# ⑥ 出 PRD
python3 $SUITE/shared/bin/build_prd.py --proto {产品}.proto.json --out PRD-{产品}.md
```

**顺序不能换。** ③ 前跑 ②，④ 必须在 ② 之后（否则比的是旧容器 vs 新契约），⑤ 最后。

### 执行留痕（每一步都要留，不是可选项）

`_state.json` 记**产物真相**（六步做到哪、谁签的字）；`_run/` 记**这一轮怎么干的**（目标原句、规划、每步意图）。两层不许合并，两个都不许手改——只经 `harness.py` 改。命令与字段以 `$SUITE/_design/HARNESS.md` §5 为准，本文不抄第二份。

两个词别混用：`step` 记的是一**步**，`plan` 里的一项是**子任务**（`C1`~`C3`）。一个子任务动辄十几步，**步数不等于进度**——别拿步数当勾数。

**① 对话可见：进度块贴进回复正文，不依赖任何界面**

用户要在对话里看见跑到哪了。**Task 工具在 skill 被调用时通常不显示**（依赖宿主 UI），所以进度的落点只能是文字：

1. 每次 `next` / `step` 之后，跑一次 `next --brief`，把返回的 3 行**原样贴进回复**，不概括、不省略：

```
── 1/3 ──────────────────────────────
A1 ✓  A2 ← 现在  A3
做 A2 角色 → M2-roles.md｜内含「角色表」 ｜ 账本 4 步
```

2. 开工贴一次、每完成一步再贴一次。用户看的是这个块，不是你的总结段落。
3. Task 工具（`TaskCreate`/`TaskUpdate`）能用就用，**不能用也不影响**——它是锦上添花，不是这套机制的落点。别因为它不显示就跳过进度块。
4. 块里的「← 现在」与「账本 N 步」是自检：`_run/` 推进了而块没变，就是你漏跑了 `next --brief`。
5. 进度块不是证据。做完没做完看产物文件与 `_state.json`；块只负责让人看见。

**② 开工前跑 `next`，这是固定初衷的唯一入口**

项目还没有 `_run/` 时先 `init --dir analysis/<产品>/ --goal "<目标原句>" --auto --stage 3`；之后每次会话第一件事、以及每完成一个子任务之后，都跑一次 `next --dir analysis/<产品>/`。它打目标原句 + 当前位置 + 下一步 + 三条约束。不许凭记忆说"上次做到 C2"——`--status` 管判据，`next` 管目标和链路，谁也替不了谁。`next` 不替代 §一 那张入场券：先 `next`，再 `check_contract --half req`，后者仍是"能不能开工"的唯一判据。

**③ 每完成一个有产出的动作，跑 `step`**

| 算一步 | 不算一步 |
|---|---|
| 读契约或截图并**得出结论**、改了一个 `pages[]` / `capabilities[]`、重建了一次容器并**看了结果**、跑了一次 `check_parity` / `check_interact` 并**解释了红在哪里** | 纯检索、grep 找位置、翻目录、再跑一遍 `--status`、连续 rebuild 三遍不看输出 |

`--intent` 写**判断**不写动作：「列表页的 commands 挂错了页面，同一 entity 的命令进了两个 `layout=list`」，而不是「读了 03-page-split」。将来复盘全靠这一列。
`--tool` / `--args` 必填（填你真跑的那个工具和关键参数，它同时是循环检测的依据），`--verdict` 默认 `ok`；产物不满足 `doneWhen`（比如 `check_parity` 还红）记 `fail`；做了本段不该做的事（比如为了好看改 `from`/`to`）记 `drift`。

子任务要标完成，**四样一起给，缺一样就等于没给**：`--done --taskId C2 --out dist/index.html`，且该文件必须真的存在、`doneWhen.contains` 里的串必须真的出现。缺文件或缺串都 exit 6，但那是**防呆**，不是验收——验收仍是 `check_contract` / `check_parity` / `check_interact` 那三层。只给 `--taskId` 也会 exit 6，那不是"工具不好用"，是这步还没做完。另两个同理：C1 交 `{产品}.proto.json`（要含 `componentTree`），C3 交 `PRD-<产品>.md`。

**C2 有前置，是流程义务、没有脚本替你查**：`--done` 之前先跑 `check_parity` 与 `check_interact`，有红的就不许勾。既然没人验，就把结果写进那一步的 `--out`（例如 `parity 0 / interact 0`）。那不是判据，是留痕：`log` 一翻就能看出这一步到底跑没跑。三处一致不占任务位：校验是前置条件，不是产物。

**④ 每积累 2 步做一次里程碑自检**

`milestoneEvery` 到了就跑 `milestone --gap "..."`。`--gap` 写**这一轮产出对顶层目标还差什么**，"暂无""已对齐"算空话，判 exit 3、不计自检。自检只回答"偏没偏"，**不回答"完没完"**——它不给任何子任务打勾，别指望跑它把 C2 标完。本段的真例子：

> 三处一致过了，但 PDA 详情页还没有 `BigAction`，`R-06`~`R-12` 有 3 条点不过——离"能交给开发"差 PDA 那半条主线。

**⑤ 跳步、偏离、循环，三种动作**

| 情况 | 退出码 | 动作 |
|---|---|---|
| 遗忘（跳步） | 4 | 读 `next` 的注入块，回到它说的那步，**不要重开** |
| 偏离（意图与目标不沾） | 0 / 3 | 单次只记 `goalAligned:false` 并 WARN、**放行**（真实发现常常一开始看着不沾），第 2 次仍放行，**第 3 次**才判偏离 exit 3；那时停手，把当前动作和目标原句各念一遍。真要加步骤 → `amend --add ... --why ... [--stage N] [--done-file <产物>]`，对不齐目标会被硬拒；没给 `--done-file` 的新步骤，完成时只认 `--out` 指向的文件存在 |
| 循环（同一动作第 3 次） | 2 | **立刻停**，不许换措辞重试。读 `log --tail 10`，判断是工具用错还是这步本来就做不了，写进 `blocked` 交给用户 |

**禁令**：`blocked` 之后不许自己 `--force-unblock`，必须用户确认过才能解。死循环之所以发生，就是因为模型相信"再试一次就对"。

## 三、可改与不可改（这一段最容易越界的地方）

契约是双向文件：02 写需求半边，03 只**追加**渲染半边。为了让页面好看去改 `from`/`to`，等于偷偷改了需求。

| 键 | 本段能不能动 | 说明 |
|---|---|---|
| `pages[].componentTree` / `interactions` / `prd` | **只能新增和细化** | 这是你的活 |
| `capabilities[].ui`（`kind`/`entry`/`title`/`fields`） | **只能新增和细化** | `inline` 无需录入 / `dialog` ≤6 字段 / `drawer` 要一边看上下文一边填 / `page` 要发链接或字段组 ≥4 |
| `pages[].id/moduleId/target/route/title/layout/entity` | 不许删、不许改语义 | 骨架是 02 定的，改了就与切片对不上 |
| `stateMachines[]`、`capabilities[].from/to/actor/stage` | **禁止修改** | 改了 `--half req` 就红——这是唯一的护栏，别去绕过它 |
| `requirements[]`（EARS）、`fieldCatalog[]`、`slices[]` | **禁止修改** | 要改就回 02，让上游重出 |

用户当场说「这个状态不对，应该加一个待复核」——正确反应不是改 JSON，是回一句"这条要回上一段改流程，我把它记下来"，并把 `_state.json.stages["2"].status` 标 `stale`。

### 三条渲染硬规则

1. **按钮可用性不写在组件上。** 组件只写 `props.capability`，禁止 `disabled:true`；提示语由容器按 `from` + 当前状态拼出来：「仅「待审核」可审核（当前为「已归档」）」。
2. **详情页只读。** 基本信息 + 各步结论 + 措施清单 + 处理轨迹；推进动作走弹框/抽屉/独立页，不在详情页里放可编辑区块。
3. **双端不同源就是错的。** PC 1440（内容区 = 1440 − 侧栏 232，`pc-*`）；PDA 390×844（`pda`，每页有且仅有一个 `BigAction`，必须显式声明 `onlineOnly` 或 `offline`，触控 ≥44px）。PDA 引 `pc-*` 或反过来，`L2-15/16` 红。

### 容器与视觉，各一条不能忘

- **三栏覆盖式**：左页面目录、右 PRD，展开时压在原型上，**不挤压画布**。原型必须 1:1 真实页面，不许 `transform: scale` 糊弄。
- **令牌不用默认蓝**：深岩青导航 `--ink-900 #0B2028`、主色 `--brand-600 #0A7183`；字号 `{26,16,14,13,12}`，26 只给 KPI 数字且一屏最多一组；8px 栅格、行高 34、页头 52。

### 验收三层，各管一件事，不许互相顶替

| 层 | 手段 | 只看 |
|---|---|---|
| L1/L2/P 结构 | `check_contract.py`（全场） | JSON 自不自洽 |
| C 一致 | `check_parity.py` | 契约 / DOM / 导出 md 是不是同一份事实 |
| R 交互 | `check_interact.py` | 点下去之后屏幕上发生了什么 |

L3 呈现（覆盖层展开时画布宽度不变、表头不裁切、字号集合、截图非空白）**只能看截图判断**，读不到 DOM 的条款不要硬塞进 L1/L2，那只会变成假绿。

## 四、references 索引

| 文件 | 什么时候读 |
|---|---|
| `references/03-page-split.md` | P1 切页时；★ 三刀切分、五条硬判据、PRD 十种小节、切片上限 |
| `references/04-visual-spec.md` | P2/P3 之前；设计令牌全表、PC/PDA 布局规范、组件选型决策、审美的 8 条可判定标准 |
| `references/06-container.md` | 改容器或加组件时；四层结构、渲染引擎、三层状态、标注锚点、导出机制 |
| `$SUITE/shared/schemas/proto.schema.json` | 每次改 proto 前；字段名与必填以 schema 为准 |
| `$SUITE/shared/schemas/catalog.json` | 选组件前；54 个登记、24 个 `impl=done`，只能用 done 的 |
| `$SUITE/shared/bin/README.md` | 不确定该跑哪条时；哪个 stage 跑哪几条命令的唯一索引 |
| `$SUITE/shared/samples/example-02-accident.proto.json` | 写"推进动作成为状态"时；4 页 / 12 命令 / 7 状态的完整范例 |
| `$SUITE/shared/samples/example-03-role-empty.proto.json` | 写无权角色空态时；`R-06/R-07` 的正例 |
| `$SUITE/shared/samples/PRD-accident.md` | 出 PRD 前；章节结构参照，`C-22`~`C-25` 的正例 |

## 五、本段不做

| 交给谁 | 什么事 | 为什么不是我 |
|---|---|---|
| `iiot-req-analysis` | 改状态机、加命令、改验收条件、改切片 | 这些是需求，不是界面。改了就与上游脱钩，下次重跑被覆盖 |
| `iiot-business-analysis` | 重新判断该不该做、重扫场景 | 三段里最不该回头的一段；真要回头，整套重来 |

三条自检：

1. 为了页面好看，把某条命令的 `from` 从两个状态收成一个——**越界**，`--half req` 会红，别绕过。
2. 详情页里放了三个可编辑区块——动作没有成为状态，`L2-54` 红。
3. 契约里出现不在 `catalog.json` 或 `impl=todo` 的组件——运行时降级成红色虚线框，原型是残的，`L2-51` 红。

**交接话术**（逐字念）：

> 原型已出（X 页 / Y 命令实测通过）。要不要我导出 PRD？
