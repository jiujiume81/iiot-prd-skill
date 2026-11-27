# HARNESS 规格 · 执行状态与链路管控

一句话：`_state.json` 管**产物到哪一步**（真相），`_run/` 管**这一轮在怎么干**（过程）。两层正交，不许合并。

## 1 目录

```
analysis/<产品>/
├─ _state.json          已有，不动
└─ _run/
   ├─ contract.json     顶层目标 + 静态规划，冻结
   ├─ state.json        当前快照，每步覆盖
   ├─ journal.jsonl     追加日志，一步一行，永不重写
   └─ RUNLOG.md         journal 的人看渲染，脚本生成
```

## 2 contract.json（冻结，只有 `amend` 能改）

```json
{
  "runVersion": "1.0",
  "goal": "把来料检验这单需求分析清楚，产出可交给开发的契约与原型",
  "goalKeywords": ["来料检验", "契约", "原型"],
  "plan": [
    {"id": "T1", "stage": 1, "title": "锁定真问题", "doneWhen": "M1 有立场句", "status": "pending"},
    {"id": "T2", "stage": 1, "title": "识别角色",   "doneWhen": "M2 六字段齐",  "status": "pending"},
    {"id": "T3", "stage": 1, "title": "扫场景矩阵", "doneWhen": "M3 82 格 + 确认单", "status": "pending"}
  ],
  "guardrails": {
    "maxSameCall": 3,
    "milestoneEvery": 2,
    "forbidAddingBeyondPlan": true
  },
  "createdAt": "2026-11-17T17:50:00+08:00",
  "frozen": true
}
```

- `goalKeywords` 由 `--goal` 自动切词 + `--keywords` 可覆盖。它是偏离检测的唯一依据，**不许为空**。
- `plan` 由 `--auto` 从 `--stage` 生成（1 → T1..T3，2 → T4..T6，3 → T7..T8），也可 `--plan file.json` 指定。

## 3 state.json（当前快照）

```json
{
  "runVersion": "1.0",
  "current": {"taskId": "T3", "intent": "扫 D2 维度时发现没问过留样", "startedAt": "..."},
  "done": ["T1", "T2"],
  "next": "T3",
  "counters": {"sameCall": 2, "stepsSinceMilestone": 1, "drifts": 0, "loops": 0},
  "blocked": null,
  "lastArgsHash": "a1b2c3d4",
  "lastTool": "Read",
  "updatedAt": "..."
}
```

`blocked` 非 null 时结构：`{"reason":"LOOP","at":"T3","detail":"同一 (Read, a1b2c3d4) 连续 3 次","snapshot":"_run/state.json"}`。

## 4 journal.jsonl（一行一步）

```json
{"seq":7,"ts":"...","taskId":"T3","intent":"扫 D2 维度时发现没问过留样","tool":"Read","argsHash":"a1b2c3d4","argsBrief":"M3-scenarios.md","out":"发现 1 条漏项","verdict":"ok","goalAligned":true,"event":null}
```

- `argsHash`：`sha256(tool + "\x1f" + 参数规范化 JSON)` 前 8 位。
- `argsBrief`：≤ 60 字，给人看。
- `verdict`：`ok` / `drift` / `loop` / `forget` / `fail`。
- `event`：`milestone` / `amend` / `block` / `close` 之一或 null。

## 5 子命令

| 命令 | 作用 | 退出码 |
|---|---|---|
| `init --dir D --goal "..." [--keywords k1,k2] [--auto --stage N \| --plan f.json]` | 起 `_run/`，写 contract + state | 0 / 2（已有 _run 且无 `--force`） |
| `next --dir D` | **输出注入块**：目标 + 已完成 + 下一步 + 禁止事项 | 0 / 2（blocked） |
| `step --dir D --intent "..." --tool T --args "..." [--out "..."] [--verdict ok]` | 记一步，跑三项检测 | 0 正常 / 2 循环 / 3 偏离 / 4 遗忘 |
| `check --dir D` | 只检测不记账 | 同上 |
| `status --dir D [--md]` | 人看视图（终端表格 / markdown） | 0 |
| `amend --dir D --add "..." --why "..."` | 新增步骤，校验对齐 | 0 / 3（不对齐） |
| `milestone --dir D --gap "还缺什么"` | 里程碑自检，清零计数 | 0 / 3（gap 空） |
| `close --dir D [--result "..."]` | 收尾，生成复盘摘要 | 0 |
| `log --dir D [--tail N]` | 原始 journal | 0 |

## 6 检测规则（精确）

**循环 LOOP**：`(tool, argsHash)` 与前一次相同 → `sameCall += 1`；不等则归零。`sameCall >= maxSameCall` → 拦截。
- 判定只认 `(tool, argsHash)`，不认"意图相似"——意图是自述，靠不住。
- 命中时：写 `blocked`、journal 追加 `verdict:"loop"`、exit 2。

**偏离 DRIFT**：`step --intent` 与 `goalKeywords` **全部**不重合，且 `taskId` 不在 plan 里 → 偏离。
- 重合判定：intent 包含任一 keyword 即为重合。
- 命中：exit 3，`drifts += 1`，打印"重注入目标 + 回 <当前 taskId>"。
- `drifts >= 2` 连续 → 升级为 `blocked`（重度漂移）。

**遗忘 FORGET**：`--taskId` 与 plan 里第一个 `pending` 的 id 不符 → 遗忘。
- 命中：exit 4，打印 `next` 的注入块（强制回正），不阻断。
- `forgets >= 2` 连续 → `blocked`。

**里程碑**：`stepsSinceMilestone >= milestoneEvery` 且未跑 `milestone` → `next` 与 `step` 都提示"先做里程碑自检"，不阻断但要打印。

## 7 `next` 的输出（这是"固定初衷"的落点）

模型每次开工前必须跑，输出形如：

```
── 本轮任务 ─────────────────────────────
目标  把来料检验这单需求分析清楚，产出可交给开发的契约与原型
进度  T1 ✓  T2 ✓  T3 ← 现在  （1/3）
下一步 T3 扫场景矩阵：M3 82 格 + 确认单

约束  ① 只做 T3，不碰流程与契约（那是 T4 之后）
      ② 新增动作必须能对上上面那句目标，对不上先 amend 再说
      ③ 同一动作连续 3 次即判死循环

上次  07 扫 D2 维度时发现没问过留样
```

## 8 `status --md` 输出（人看）

```markdown
## 执行记录 · 新锂想QMS 来料检验
目标：… ｜ 进度 2/3 ｜ 已用 7 步 ｜ 告警 0

| # | 任务 | 意图 | 工具 | 结果 | 判定 |
|---|---|---|---|---|---|
| 1 | T1 | 从三份纪要里提原话 | Read | 原话 5 条 | ok |
| 2 | T1 | 写 M1 立场句 | Write | M1 完成 | ok |
```

## 9 与 `_state.json` 的对账

`close` 时校验：`plan` 里 status=done 的 taskId 覆盖的 stage，必须与 `_state.json` 的 `steps[].status=done` 一致。不一致 → WARN，打印差集，**不阻断**（产物真相以 `_state.json` 为准）。

## 10 自测要求（造红，贴原始输出）

| # | 输入 | 期望 |
|---|---|---|
| 1 | `init` 后 `next` | 注入块含 goal / 进度 0/3 / 下一步 T1 |
| 2 | 连续 3 次同 `(tool,args)` | exit 2、`blocked.reason=LOOP`、journal 有 `verdict:loop` |
| 3 | `step --intent "我想先看看页面怎么画"` | exit 3、`drifts=1`、打印重注入目标 |
| 4 | 再跑一次同类偏离 | exit 2、`blocked`（连续 2 次升级） |
| 5 | `--taskId T5`（跳过 T3） | exit 4、打印注入块回正 |
| 6 | `amend --add "顺手加一个登录页" --why "觉得需要"` | exit 3、拒绝（不对齐目标） |
| 7 | `amend --add "补充留样场景" --why "M3 漏项"` | exit 0、plan 多一条 |
| 8 | `milestone --gap ""` | exit 3（空 gap 不算自检） |
| 9 | `status --md` | 表格含每步 intent 与 verdict |
| 10 | `close` | 输出复盘摘要 + 对账结果 |

## 11 不做什么

- 不记录模型内部思维（拿不到，也不该伪造）。
- 不做自动决策：`next` 只给约束，选哪步还是模型定。
- 不替代 `_state.json`：产物进度只有一个真相。
