# shared/bin — 哪一段跑哪几条命令（唯一索引）

> 所有脚本物理上只此一份。**从任何目录调用都要写绝对路径**：`$SUITE/shared/bin/xxx.py`。
> 五个脚本用 `abspath(__file__)` 推 `shared/schemas`、`shared/assets`；经软链路径调用时会去一个不存在的目录找文件（实测 `FileNotFoundError`）。`IIOT_SUITE_ROOT` 环境变量可覆盖根目录。

## 按段分工

| 段 | 脚本 | 用法 | 什么时候跑 |
|---|---|---|---|
| 01 业务分析 | `check_analysis.py` | `--init <目录> --product "..." --stage 1` / `--status` / `--stage 1` / `--hash` | 起骨架、每次进来、出口 |
| 02 需求分析 | `check_analysis.py` | `--stage 2` / `--stage 2 --seal` / `--stage all` | 出口；`--seal` 全绿才签收并冻结 protoHash + M4/M5/M6 指纹；`--verbose` 展开 A-67 的逐处清单 |
| 02 需求分析 | `check_contract.py` | `--half req <proto>` / `--plan <slices.json>` | 契约需求半边、切片计划 |
| 02 需求分析 | `build_prd.py` | `--proto <proto> --out <PRD.md>`（第 1~6 章有内容） | 给业务方签字的可读件 |
| 03 原型设计 | `check_contract.py` | `<proto>`（不带 `--half`） | 契约成立（全场） |
| 03 原型设计 | `check_parity.py` | `<proto> --html <dist>` | 契约 / 容器 DOM / 导出 MD 三处一致 |
| 03 原型设计 | `check_interact.py` | `--proto <proto> --html <dist>` | 无头浏览器真点一遍 |
| 03 原型设计 | `build_prd.py` + `build_prd_html.py` | `--proto ... --out ...` | 出完整 PRD（md + 单文件 html） |
| 03 原型设计 | `assets/container/src/build.py` | `--proto <abs> --out <abs>` | 重建容器（必须物理绝对路径） |
| 全段 | `harness.py` | `init` / `next` / `step` / `milestone` / `mark-tasks` / `status` / `close` | 每一轮开工前、每做完一个动作、每 2 步、建完任务列表、收工 |

## 谁不该跑什么

- **01 不该跑** `check_contract` / `check_parity` / `check_interact` / `build_prd`：这一段还没有契约。
- **02 不该跑** `check_parity` / `check_interact`：没有组件树，一定红，红了也不代表需求有问题。
- **03 不该跑** `check_analysis --stage 1`：M1~M3 是输入，不是它要改的东西。

## 公共库（不单独调用）

`field_sites.py`（渲染位抽取，`check_contract`/`check_interact`/`check_parity`/`build_prd`/`retired/migrate_fields` 共用）、`render_common.py`（图片内联）、`mdast.py`（md 解析）、`render_figs.py`（mermaid → SVG，需 Chrome）。

## `--half` 与 `--stage` 都不是放宽

| 参数 | 语义 | 跳过什么 | 输出是否声明 |
|---|---|---|---|
| `check_analysis --stage 1` | 只查第 1 段 24 条 + 跨阶段 6 条 | 第 2 段的 21 条 | 标题行打印「第 1 段 24 条 + 跨阶段 6 条」 |
| `check_analysis --stage 2` | 只查第 2 段 20 条 + 跨阶段 6 条 | 第 1 段的 24 条 | 同上 |
| `check_contract --half req` | 02 出口 | 10 条页面/渲染向判据（`SKIP_IN_REQ`） | 结果行上方逐条打印被跳过的编号 |
| `check_contract --half render` | 只查渲染层 | 8 条需求语义判据（`SKIP_IN_RENDER`） | 同上 |
| `check_contract`（默认 `full`） | 一条不跳 | — | — |

**03 交付前必须跑不带 `--half` 的全场。** `--half req` 绿只等于「需求这一半没矛盾」。

## harness：执行状态与链路管控

`harness.py` 管的是**过程**，`check_analysis.py` 管的是**产物**。两层正交，谁也别替谁。

| | `check_analysis.py` | `harness.py` |
|---|---|---|
| 回答什么问题 | 产物到哪一步了、判据过没过（A 系列 50 条） | 这一轮在怎么干：目标是什么、规划几步、每步干了什么、为什么 |
| 读写什么 | `<产品>/_state.json`（+ 六份 M 文件） | `<产品>/_run/`（contract / state / journal / RUNLOG） |
| 数据真值 | 产物进度只认它 | 只认 `_run/journal.jsonl`；**一个字节都不写 `_state.json`** |
| 拦不拦 | 有 ERROR 就拦截（exit 1） | 循环 / 累计偏移 / 非法任务 / 遗漏（exit 2/3/4/5），`close` 对账只 WARN |

它解决的问题是「skill 在产出的时候不知道中间发生了什么」。`_run/` 里能直接看到：

```
analysis/<产品>/
├─ _state.json          ← check_analysis.py 的，别动
└─ _run/
   ├─ contract.json     目标 + 规划 + guardrails，冻结（只有 amend 能加步骤）
   ├─ state.json        当前快照：做到哪、连续同调用几次、有没有被拦
   ├─ journal.jsonl     一步一行，只追加，seq 单调
   └─ RUNLOG.md         journal 的人看渲染，脚本生成
```

### 五个命令就是这个脚本的全部

```bash
python3 shared/bin/harness.py init  --dir <产品目录> --product "新锂想QMS 来料检验" --goal "把来料检验这单需求分析清楚，产出可交给开发的契约与原型" --auto --stage 1
python3 shared/bin/harness.py next  --dir <产品目录>            # 每次开工前：目标原句 + 进度 + 下一步 + 约束 + 上次 + 账本 + 任务列表同步
python3 shared/bin/harness.py mark-tasks --dir <产品目录> --completed-count 2   # 对话里的任务列表按 plan 建好后跑一次
python3 shared/bin/harness.py step  --dir <产品目录> --intent "..." --tool Read --args "M3-scenarios.md" --out "..." --taskId A3
python3 shared/bin/harness.py step  --dir <产品目录> --taskId A1 --intent "..." --tool Write --args M1-problem.md --out M1-problem.md --done
python3 shared/bin/harness.py milestone --dir <产品目录> --gap "还缺什么"   # 每 2 步；只清零计数、记 gap
python3 shared/bin/harness.py close --dir <产品目录> --result "..."        # 复盘 + 与 _state.json 对账
```

其余三个是随手看/改口子：`status --md`（贴给人看的表）、`log --tail N`（原始 journal）、`amend`（往规划里加一步，先校验对不对得上目标）。

### `next` 末尾那行「同步」是什么

对话里的任务列表（WorkBuddy 那套 Task 工具）和 `_run/` 是**两份账本**。定死一条：`_run/` 是真相，任务列表是它的投影，**只许单向投影，不许反写**。反写就是同一件事写两处，必漂。

```
同步  任务列表：A1 应为 in_progress，A2/A3 pending
```

模型照着这一行去 `TaskCreate` / `TaskUpdate`：当前任务 `in_progress`、`done` 里的 `completed`、其余 `pending`。`init` 时 `taskListCreated=false`，这行会变成「先建任务列表」；建完跑一次 `mark-tasks` 置 true，之后不再喊。

`mark-tasks --completed-count N` 会顺手对一次账：`state.done` 的项数和你在列表里勾的项数不一致就打印

```
[账本] 3 项已完，列表勾了 1 项  ← 对不上，去补 TaskUpdate
```

不 exit 非零——它只是提醒。`step` 漏了 `next` 会喊，列表漏勾只有这行会喊。

### 检测：单次出格只记账，累计才拦

| 检测 | 判据 | 退出码 | 处理 |
|---|---|---|---|
| 循环 LOOP | `(tool, argsHash)` 与**前一次**相同，连续 ≥ `maxSameCall`(3) | 2 | 直接 `blocked` |
| 偏移 DRIFT | `--intent` 与 `goalKeywords` 全不重合 | 0 / 3 | 单次记 `goalAligned:false` + WARN 放行；**连续 3 次**才 exit 3 |
| 非法任务 INVALID_TASK | 显式 `--taskId` 不在 plan 里 | 5 | 不记账，直接拒 |
| 遗漏 FORGET | 显式 `--taskId` 不是 plan 里第一个 `pending` | 4 | 记账 + 重放注入块回正 |
| 完成校验 | `--done` 但 `--out` 的文件不存在 / `doneWhen.contains` 缺串 | 6 | 不记账、不标 done |

`argsHash = sha256(tool + "\x1f" + --args 原串)[:8]`。**不解析 JSON、不看"意图相似"**——意图是自述，靠不住。

DRIFT 单次放行是有意的：真实的临场发现（"这个变更要拆成两类"）和跑偏在意图句上长得一样，只有"后面接的都是同一件事"才能把两者分开。所以靠累计，不靠单句判词。真正乱加戏由 `amend` 在源头硬拦。

`blocked` 一旦置位，除 `close` 外所有子命令一律 exit 2 并回显原因，脚本不自己解封；解封只能人看完 `RUNLOG.md` 后跑 `--force-unblock`。

### 完成由产物驱动，不由自述驱动

- `milestone` **不写** `task.status`。它只清零计数、记 gap。早先版本让它顺手把任务标 done，结果 01 段跑满 6 步三个任务全 done、`next` 打印「规划已走完」，而 M1~M3 一个字没写——那是假账本，比没账本更糟。
- 任务记 done 只有一条路：`step --done`，且 `--out` 指向的文件必须真的躺在 `--dir` 下，`doneWhen.contains` 里每个串必须真的出现。缺一样 exit 6，一步都不记。跳步的 `--done` 也不生效（只认第一个 pending）。
- `doneWhen` 是结构化的 `{"file": "...", "contains": ["..."]}`，10 个任务共 3/4/3 个。`{产品}` 在 `init` 时按 `--product` 渲染成真实文件名（不传则取目录名）——常量表里不留占位符，否则 `--done` 永远对不上文件。
- 1.0 的纯文本 `doneWhen` 按兼容处理：只显示，不参与判定（`init --plan` 与 `close` 各打一行说明）。
- `contains` 是子串匹配、没有词边界（`["立场"]` 会被「反对立场」命中），只用来防呆，**不是验收判据**——验收仍以 `check_analysis.py` / `check_contract` / `check_parity` / `check_interact` 为准。

### 校验命令不归 `--done` 管

`C2`（容器构建）的完成前提是 `check_parity` 跑过且 exit 0，`check_interact` 同理。**这条写在 SKILL 里、由模型自己执行，harness 不校验**——`_run/` 里只有意图和参数，没有"某个脚本最近一次真的跑过并返回 0"的可信记录，硬查只能靠模型自述，那正是这套东西一直想避开的。所以 `--done` 只认文件，校验命令靠流程约束。

### 什么时候跑哪条

- **每个动作之后一条 `step`**：不是每改一个文件，是每做一件"能说出意图"的事（读一份纪要、写一节、跑一次校验）。`--intent` 少于 10 字且以「读/看/查/搜/跑/执行/处理」开头会打 WARN：写动作不写判断，复盘时这行字没用。
- **`milestone` 别省**：`--gap` 空着直接 exit 3（空自检等于没自检）。进度靠 `--done` 推进，不靠它。
- **`amend` 是新增步骤的唯一口子**，也是硬拦的地方：`--add` 对不上目标且 `--why` 追溯不到原话/纪要/确认单，直接 exit 3。`--why` 能追到出处时降为 WARN 放行，并记 `goalAligned:false`——理由是人给的，账要留着。
- **`close` 的对账不阻断**：`plan` 说完成的段和 `_state.json` 说完成的段对不上就 WARN 并打印差集，产物真相仍以 `_state.json` 为准。对账只为让人看见"过程记录和产物记录不一致"，不替人做决定。
