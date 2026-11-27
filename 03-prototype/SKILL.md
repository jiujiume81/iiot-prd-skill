---
name: iiot-prototype
version: 0.4.0
agent_created: true
description: 高保真原型设计（三段式第 3 段）：读一份已成立的需求契约，产出可直接交给开发的 Vue 单文件原型（PC 与 PDA 双端同源、离线双击即开、三栏覆盖式容器）、页面目录树、页面标注，以及同源 PRD（md/html 可导出），并用三层脚本验收——契约全场结构、契约/容器/PRD 三处一致、无头浏览器逐条真点。按钮可用性由状态机推导而非手写置灰，组件只用 catalog 里 impl=done 的。只做界面与渲染，不改业务语义、不写 EARS、不重扫场景。当用户说「画原型」「做个高保真」「出 PRD」「PDA 页面长什么样」「页面怎么拆」「把原型交给开发」「这里加个标注」「交互能点吗」，或项目里已有 proto.json 时使用。触发词：原型、高保真、可交互原型、拆页面、页面目录、PDA、工控界面、容器、组件树、标注、PRD 导出、交付开发、三处一致、真点一遍。要改流程或验收条件用 iiot-req-analysis；要从零判断该不该做用 iiot-business-analysis。
---

# 高保真原型设计（第 3 段）

前两段把"做什么"说清楚了，这一段负责"**长什么样、点得动吗、和文档对得上吗**"。三件同源：单文件 HTML、PRD、标注记录。

> **路径约定**：`$SUITE` = 套件根（同时含 `01-business/`、`02-requirement/`、`03-prototype/`、`shared/` 的那一层）。
> 每个会话定位一次：`SUITE=$(cd "$(dirname "<本 SKILL.md 的绝对路径>")/.." && pwd)`。
> 容器与脚本只有一份物理副本（在 `shared/`），**不要复制到自己目录**——改了一处，别处不会知道。

## 一、先判我在哪一段

| 现场 | 判定 | 动作 |
|---|---|---|
| 没有 `{产品}.proto.json`，或 `stages["2"].status != "done"` | 契约没成立 | **拒绝开工**，给 02 的命令。不许"先画个大概" |
| 有 proto 但 `--half req` 红 | 需求半边不成立或被人改过 | 拒绝开工，把红的原样贴给用户，回 02 |
| `stage = 3` 且 `--half req` 绿 | 本段 | 从第一个没做完的步继续 |
| `stages["3"].status = done` | 已完成 | 不重出容器，问要不要加标注或重出 PRD |

**第一条命令不是画图，是复核上游**：`check_contract.py --half req {产品}.proto.json`。绿 = 需求半边没被动过；红 = 要么上游交付本身坏了，要么有人在别处改了语义——**两种情况都不是本段能修的**。

## 二、本段做什么

| 项 | 内容 |
|---|---|
| **入口读** | `{产品}.proto.json` 的需求半边（角色/命令矩阵/状态机/EARS/字段主档/页面骨架）、`slices.json`。**不读上游任何 md** |
| **出口写** | 同一份 proto 上**追加**：`pages[].componentTree`/`interactions`/`prd`、`capabilities[].ui`；另出 `dist/index.html`、`PRD-{产品}.md`/`.html`、`figs/*.svg` |
| **卡点** | ① `--half req` 绿（入场券）② **不带 `--half` 的全场**绿 ③ `check_parity` 三处一致 ④ `check_interact` 真点一遍。四道全过才算交付 |
| **下游** | 人。审核的看容器，开发拿走 HTML 与 PRD，下一轮改需求的回来改 proto 再重建 |

| 步 | 做什么 | 判据落点 |
|---|---|---|
| **P1 切页** | 按功能模块切页面；一张单据只给一个主列表，第二个列表只能是过滤视图 | `L2-74`、`L2-80`~`82`、`L2-90`~`92` |
| **P2 填骨架** | 每页四态齐、组件只选 `impl=done`、字段渲染位与主档双向绑定、每条命令声明 `ui.kind` | `L1-05`、`L2-14`、`L2-51`、`L2-55`、`L2-96`~`101` |
| **P3 出容器** | 重建单文件 HTML（Vue 运行时内嵌、离线可用、三栏覆盖层、不缩放） | 构建成功、无降级组件 |
| **P4 对三处** | 契约 / DOM / 导出 md 同一份事实；PRD 头部指纹等于当前契约 | `C-09`、`C-21`~`25` |
| **P5 真点** | 逐条命令点开弹层、切角色、点目录、点字段、Esc 关闭、标注落位 | `R-06`~`12` |

### 命令

```bash
python3 $SUITE/shared/bin/check_contract.py --half req {产品}.proto.json          # ① 入场券
python3 $SUITE/shared/assets/container/src/build.py \
        --proto $PWD/{产品}.proto.json --out $PWD/dist/index.html                  # ② 重建（必须物理路径）
python3 $SUITE/shared/bin/check_contract.py {产品}.proto.json                     # ③ 全场
python3 $SUITE/shared/bin/check_parity.py {产品}.proto.json --html dist/index.html # ④ 三处一致（需 Chrome）
python3 $SUITE/shared/bin/check_interact.py --proto {产品}.proto.json --html dist/index.html  # ⑤ 真点
python3 $SUITE/shared/bin/build_prd.py --proto {产品}.proto.json --out PRD-{产品}.md          # ⑥ 出 PRD
```

**顺序不能换**：③ 前跑 ②，④ 必须在 ② 之后（否则比的是旧容器 vs 新契约），⑤ 最后。

### 执行留痕（每步必做）

`_state.json` 记**产物真相**，`_run/` 记**这一轮怎么干的**；两层不许合并，都不许手改。完整规则见 `$SUITE/shared/references/08-run-contract.md`，这里只留不能省的五条：

1. **开工先 `next`**：打目标原句 + 当前位置 + 下一步 + 三条约束。不许凭记忆说"上次做到 C2"。`next` 不替代 §一 那张入场券——先 `next`，再 `check_contract --half req`。
2. **每步贴进度块**：`next --brief` 的 3 行**原样贴进回复**，不概括。
3. **有产出才记一步**：读契约得出结论 / 改 `pages[]` 或 `capabilities[]` / 重建容器并看了结果 / 跑 parity 或 interact 并解释红在哪，算一步；连续 rebuild 三遍不看输出不算。`--intent` 写**判断**不写动作。
4. **完成由产物决定**：`step --done --taskId C2 --out dist/index.html`，文件必须真存在且 `doneWhen.contains` 的串真出现，否则 exit 6。C1 交 `{产品}.proto.json`（含 `componentTree`），C3 交 `PRD-<产品>.md`。里程碑自检**只读**，不给任务打勾。
5. **三种异常**：exit 4 跳步 → 读注入块回正；exit 3 偏离 → 单次放行、连 3 次才拦；exit 2 循环 → **立刻停，不许换说法重试**，写清卡点交用户。

**`C2` 有前置，是流程义务、没有脚本替你查**：`--done` 之前先跑 `check_parity` 与 `check_interact`，有红的就不许勾。既然没人验，就把结果写进那一步的 `--out`（如 `parity 0 / interact 0`）——那不是判据，是留痕。

`blocked` 后不许自己 `--force-unblock`——死循环之所以发生，就是模型相信"再试一次就对"。

## 三、可改与不可改（最容易越界的地方）

契约是双向文件：02 写需求半边，03 只**追加**渲染半边。为了页面好看去改 `from`/`to`，等于偷偷改了需求。

| 键 | 能不能动 | 说明 |
|---|---|---|
| `pages[].componentTree`/`interactions`/`prd` | **只能新增细化** | 这是你的活 |
| `capabilities[].ui`（`kind`/`entry`/`title`/`fields`） | **只能新增细化** | `inline` 免录入 / `dialog` ≤6 字段 / `drawer` 要一边看上下文一边填 / `page` 要发链接或字段组 ≥4 |
| `pages[].id/moduleId/target/route/title/layout/entity` | 不许删、不许改语义 | 骨架是 02 定的，改了就与切片对不上 |
| `stateMachines[]`、`capabilities[].from/to/actor/stage` | **禁止修改** | 改了 `--half req` 就红——这是唯一护栏，别绕 |
| `requirements[]`、`fieldCatalog[]`、`slices[]` | **禁止修改** | 要改回 02，让上游重出 |

用户当场说「这个状态不对，应该加一个待复核」——正确反应不是改 JSON，是回一句"这条要回上一段改流程，我记下来"，并把 `stages["2"].status` 标 `stale`。

### 三条渲染硬规则

1. **按钮可用性不写在组件上**：组件只写 `props.capability`，禁止 `disabled:true`；提示语由容器按 `from` + 当前状态拼出：「仅「待审核」可审核（当前为「已归档」）」。
2. **详情页只读**：基本信息 + 各步结论 + 措施清单 + 处理轨迹；推进动作走弹框/抽屉/独立页，详情页里不放可编辑区块。
3. **双端不同源就是错的**：PC 1440（内容区 = 1440 − 侧栏 232，`pc-*`）；PDA 390×844（`pda`，每页有且仅有一个 `BigAction`，必须显式声明 `onlineOnly` 或 `offline`，触控 ≥44px）。PDA 引 `pc-*` 或反过来，`L2-15/16` 红。

容器与视觉各一条：**三栏覆盖式**——左页面目录、右 PRD，展开时压在原型上、**不挤压画布**，原型 1:1，不许 `transform: scale` 糊弄；**令牌不用默认蓝**——深岩青导航 `#0B2028`、主色 `#0A7183`，字号 `{26,16,14,13,12}`（26 只给 KPI 且一屏最多一组），8px 栅格、行高 34、页头 52。

### 验收三层，各管一件事

| 层 | 手段 | 只看 |
|---|---|---|
| L1/L2/P 结构 | `check_contract.py`（全场） | JSON 自不自洽 |
| C 一致 | `check_parity.py` | 契约 / DOM / 导出 md 是不是同一份事实 |
| R 交互 | `check_interact.py` | 点下去之后屏幕发生了什么 |

L3 呈现（覆盖层展开时画布宽度不变、表头不裁切、字号集合、截图非空白）**只能看截图判断**——读不到 DOM 的条款别硬塞进 L1/L2，那只会变成假绿。

## 四、references 索引

| 文件 | 什么时候读 |
|---|---|
| `references/03-page-split.md` | P1 切页：★ 三刀切分、五条硬判据、PRD 十种小节 |
| `references/04-visual-spec.md` | P2/P3 前：令牌全表、PC/PDA 布局、组件选型、8 条可判定标准 |
| `references/06-container.md` | 改容器或加组件时：四层结构、渲染引擎、标注锚点、导出机制 |
| `$SUITE/shared/schemas/proto.schema.json` | 改 proto 前：字段名与必填以 schema 为准 |
| `$SUITE/shared/schemas/catalog.json` | 选组件前：54 个登记、24 个 `impl=done`，只能用 done 的 |
| `$SUITE/shared/bin/README.md` | 不确定跑哪条时：stage → 命令的唯一索引 |
| `$SUITE/shared/samples/` | 写"推进动作成为状态"、无权空态、PRD 章节时对照三份正例 |

## 五、本段不做

| 交给谁 | 什么事 | 为什么不是我 |
|---|---|---|
| `iiot-req-analysis` | 改状态机、加命令、改验收条件、改切片 | 这些是需求不是界面；改了就与上游脱钩，下次重跑被覆盖 |
| `iiot-business-analysis` | 重判该不该做、重扫场景 | 三段里最不该回头的一段；真要回头，整套重来 |

三条自检：为好看把某条命令的 `from` 从两个状态收成一个 → **越界**，`--half req` 会红；详情页放三个可编辑区块 → 动作没成为状态，`L2-54` 红；用了 `catalog.json` 里没有或 `impl=todo` 的组件 → 运行时降级成红色虚线框，原型是残的，`L2-51` 红。

**交接话术**（逐字念）：

> 原型已出（X 页 / Y 命令实测通过）。要不要我导出 PRD？
