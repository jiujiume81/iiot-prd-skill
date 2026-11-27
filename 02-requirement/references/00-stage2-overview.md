# 第 2 段总览：S4~S7（需求分析 + 落契约）

> 输入是第 1 段签过闸门的 `M1`/`M2`/`M3`。这一段把「多少个场景」变成「系统怎么接」：流程、状态机、异常、评审，最后落成 `{产品}.proto.json` 的**需求半边**。
> 编号对照见 `$SUITE/shared/references/00-method-map.md`。

## 三步 + 一次落契约

| 步 | 做什么 | 产物 | 判据 |
|---|---|---|---|
| **S4** | 主流程（分步/触发者/系统判断/输入输出/状态 `X → Y`/批量粒度）、分支、泳道、状态机、断点 | `M4-flows.md` | `A-30`~`A-34` |
| **S5** | 异常 12 类（按行首类别判定）+ 影响量化 + 降级动作 + 可追溯 + 补数口径 | `M5-exceptions.md` | `A-40`~`A-44` |
| **S6** | 四角色各 ≥10 问、5 个风险（带「上线后多久会爆」）、结论二选一 + 恰好 3 条前置 | `M6-review.md` | `A-50`~`A-54` |
| **S7** | 命令矩阵、状态机编译、字段主档、EARS 六字段、分批切片 | `{产品}.proto.json`（语义区）+ `slices.json` | `check_contract --half req` |

## 20 条判据 + 6 条跨阶段

| 组 | 编号 | 管什么 |
|---|---|---|
| M4 | `A-30`~`A-34` | `X → Y`、状态集闭合、P0 上流程、批量粒度、断点与「用户会怎么绕过」 |
| M5 | `A-40`~`A-44` | 12 类覆盖（行首列）、影响量化、降级动作、可追溯、补数口径 |
| M6 | `A-50`、`A-50b`、`A-51`~`A-54` | 四角色 ≥10 问、疑问句、风险恰 5 条、结论二选一 |
| 跨段 | `A-60`、`A-60b`、`A-61`、`A-62`、`A-63`、`A-64` | 两段都跑：进度真伪、分步痕迹、含糊词、越界、空话 |
| 反补签 | `A-36` | `{产品}.proto.json` 的写入时间早于 M6 确认时间、或早于 `M6-review.md` = 事后补签（移植自旧 `check_gate` 的 `G-10`） |
| 纯净度 | `A-67` | 先判内容再判出处：无键不报；无 sealed → ERROR；sealed 但 md 变了 → ERROR（聚合一条）；hash 不等且 md 未变 → WARN；hash 相等 → ERROR。签收只在「契约与 md 都没动过」时有效 |
| 签收过期 | `A-68` | 签收后 M4/M5/M6 又变 → WARN「契约需重出并重签」，与 A-67 共用同一个 `sealed` |

`A-63` 的越界词表在这一段**换过表**：`proto.json` / `capabilities[]` 是合法产物，只禁 `componentTree` / `pages[]`。

## 落契约的六条硬线

| # | 硬线 | 怎么写 | 谁判红 |
|---|---|---|---|
| 1 | 一个动作 = 一个状态 = 一条命令 | 每个推进动作各自一条 `capability`，各自带 `actor` | `L2-54`~`L2-58` |
| 2 | 状态机端点不许悬空 | 每条 `from`/`to` 在状态集里；非终态必须有出向命令 | `L2-25`~`L2-27`、`L2-57` |
| 3 | 四眼原则 | `stage=submit` 与 `stage=verify` 的 `actor` 交集必须为空，否则显式 `sameActorOk` | `L2-30` |
| 4 | 每条需求要有非法路径 | `acceptance` 至少一条 `kind:"illegal"` | `L2-34` |
| 5 | 合同不许冻结带 P0 未决问题 | `openQuestions` 有 `open` 就不许往下走 | `A-24`（分析侧） |
| 6 | 切片的依赖不许成环 | `slices.json` 用 `--plan` 单独判 | `P-01`~`P-11` |

## 这一段不做什么

- **不重扫场景**：`p0` / `p1` / `roles` 从 `_state.json` 的 `stages["1"].export` 读，不从 M3 再推一遍。
- **不画页面**：`pages` 只给骨架（`id` / `moduleId` / `target` / `route` / `title` / `listRole`），`componentTree` 交给 03。
- **不写 `ui.kind` / `ui.entry`**：按钮挂哪是 03 的事。`--half req` 会跳过这 10 条页面/渲染向判据，跳了哪几条脚本会打印。

## 出口怎么自证

```bash
python3 $SUITE/shared/bin/check_analysis.py analysis/<产品>/ --stage 2
python3 $SUITE/shared/bin/check_analysis.py analysis/<产品>/ --stage all   # 出口再跑一次，跨段不漏
python3 $SUITE/shared/bin/check_contract.py --half req analysis/<产品>/<产品>.proto.json
```

三条全绿才算交出去，再用 `--stage 2 --seal` 签收。`--half req` 绿只等于「需求这一半没矛盾」，不等于契约成立 —— 那是 03 交付前不带 `--half` 的全场。
