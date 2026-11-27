# references 归属表

> 范围：两份旧 skill 的 **18 份 references**（`mfg-req-analysis` 11 份 + `IIOT-PRD` 7 份）。
> 结论：旧 18 份 → 新 18 份。**退役 1 份、合并 2→1、拆分 1→3、其余 14 份原样搬**。
> 没有一份"其他"，没有一份进 `retire/` 是因为"没想好"——只有 `01-requirements-method.md` 因与 mfg 六步三处重叠而退役。

## 一、逐份归属（18 行）

| 文件 | 去处 | 改什么 | 为什么 |
|---|---|---|---|
| `mfg/00-method.md` | **拆三份**：`shared/references/00-method-map.md` + `01/references/00-stage1-overview.md` + `02/references/00-stage2-overview.md` | 总览表（S1~S8 与两套旧编号对照）进 shared；1~3 步"做什么/防什么/输入从哪来"进 01；4~6 步 + S7 进 02 | 它是唯一同时讲"六步 + 判据索引 + 输入从哪来"的文件。三段都要看总览，但都不该看全文——一个字不改地搬进哪一段，都会让那一段多读 40 行无关内容 |
| `mfg/01-problem.md` | `01/references/01-problem.md` | 不改 | S1 的写法细则，`A-01`~`A-06` 逐条对着它写 |
| `mfg/02-roles.md` | `01/references/02-roles.md` | 不改 | S2 的六字段与实性核对，判据按表头抓，动了就红 |
| `mfg/03-scenarios.md` | `01/references/03-scenarios.md` | **不改（一个字节都不能动）** | ★ 脚本按它的取值表**实时求和**算 82 格（`Σ 启用维度的取值数`），改了分母就变，`A-24` 全部失准 |
| `mfg/04-flow.md` | `02/references/04-flow.md` | 加一节「状态机交接」：M4 的每行 `X → Y` 要带 `F-编号`，供契约 `srcRef` 回指 | 状态机的唯一源在 M4，契约里那份是它的编译产物。没有编号，两边对不上时无法定位 |
| `mfg/05-exceptions.md` | `02/references/05-exceptions.md` | 每类异常加一列「能推出哪条非法验收」 | EARS 的 `acceptance.kind=illegal` 从这里来。不建立这条链，02 写非法路径时就只能编 |
| `mfg/06-review.md` | `02/references/06-review.md` | 不改 | S6 的四角色问法与风险排序，`A-50`~`A-54` 对着它 |
| `mfg/07-domain-map.md` | `shared/references/07-domain-map.md` | 17 个交接断点每条标 `用于 M1 边界` 或 `用于 M4 交接` | **一份两用**：01 拿 13 个系统的"管什么/不管什么"划非目标，02 拿 17 个断点写 M4 的交接点表。拆成两份必然变成两份互相补不齐的清单 |
| `mfg/08-scenario-library.md` | `01/references/08-scenario-library.md` | 不改 | 31 条起手式只服务 S3 扫描，对 02/03 无用 |
| `mfg/09-pitfalls.md` | `shared/references/09-pitfalls.md` | 每条加 `stage: 1\|2`，并保留原有"归到哪一步没做" | 19 条跨 1~6 步。**标 stage 是为了让每段只读自己那几条**——01 读到"评审写成夸奖"会困惑，那是 02 的坑 |
| `mfg/10-talk-to-user.md` | **合并**进 `shared/references/talk-to-user.md` | 与 IIOT 的 `07-report-to-user.md` 合成一本，按"什么时候说"分节：第一轮 / M3 确认单 / A2 汇报 / A3 分批 / 术语对照 | 两份讲的是同一件事的两种写法（一份管开场、一份管汇报）。分开留，术语表就有两套，用户会听到两种说法 |
| `IIOT/01-requirements-method.md` | **`retire/`** | 不迁 | 七步逐条判据与盲区，与 `mfg/01`~`06` **三处直接重叠**（替代路径 ≥3、角色现实性、异常类别）。两套并存必然一边绿一边红。吸收两处：每步"最常见错在哪"→ 两份 overview；A1/A2/A3 的"业务方最多拍 5 个板"→ `talk-to-user.md` |
| `IIOT/02-ear-spec.md` | `02/references/02-ear-spec.md` | 加两节：`stateMachine` 字段必须引用 M4 的 `F-编号`；`acceptance.illegal` 必须引用 M5 的异常类 | EARS 是 S7 的唯一写法。不加这两节，六字段会写成"看起来齐、实际悬空" |
| `IIOT/03-page-split.md` | `03/references/03-page-split.md` | 不改 | `L2-74/80/81/82/90~92` 直接引它的节号，动了判据就指错 |
| `IIOT/04-visual-spec.md` | `03/references/04-visual-spec.md` | 不改 | 令牌全表与 PC/PDA 布局规范的唯一定义处，容器 CSS 与它同源 |
| `IIOT/05-demo-reverse.md` | `02/references/05-demo-reverse.md` | 「从路由抽模块」那节改成"抽出的模块登记进 `proto.modules[].sourceRef`"，并明写 03 不得直接读本文 | 它解决的是"输入不是口述而是 Demo"，属 S4/S7 的输入形态。03 需要的是**已登记的模块**，不是抽取方法 |
| `IIOT/06-container.md` | `03/references/06-container.md` | 路径示例全部改成 `$SUITE/shared/assets/container/` | 容器只有一份物理副本，文档里写相对路径会让人以为该复制 |
| `IIOT/07-report-to-user.md` | **合并**进 `shared/references/talk-to-user.md`，原件不留 | 与 `mfg/10` 合成一本 | 见上 |

## 二、三处特殊处理的细节

| 处理 | 涉及 | 落地规则 |
|---|---|---|
| **合并 2→1** | `mfg/10-talk-to-user.md` + `IIOT/07-report-to-user.md` → `shared/references/talk-to-user.md` | 分五节：① 第一轮只许四件事（01）② M3 确认单 ≤7 条（01）③ A2 汇报"我过了 48 个疑问，只剩 2 条你定不了"（02）④ A3 分批交付（02）⑤ 术语对照（切片→分批交付、命令→一个操作、状态机→单据状态流转、契约→需求清单、四眼→提交的人不能同时是审核的人）。**第 ⑤ 节全段共用**，这是合并的唯一理由 |
| **一份两用** | `shared/references/07-domain-map.md` | 01 读「一、系统边界」；02 读「二、17 个交接断点」。文件头的三条原则改成"哪一段读哪一节"的指路 |
| **标 stage** | `shared/references/09-pitfalls.md` | 19 条逐条加 `stage`。第 1、2 条是方法级（矩阵把答案写进题目 / 拿现状当结论），两段都读，标 `stage: 0`；其余 17 条按"归到哪一步"分到 1 或 2 |

## 三、谁能读谁（防越段引用）

| references | 01 业务分析 | 02 需求分析 | 03 原型设计 |
|---|---|---|---|
| `01-problem` / `02-roles` / `03-scenarios` / `08-scenario-library` | 主 | — | — |
| `04-flow` / `05-exceptions` / `06-review` / `02-ear-spec` / `05-demo-reverse` | — | 主 | — |
| `03-page-split` / `04-visual-spec` / `06-container` | — | — | 主 |
| `shared/00-method-map` | 引 | 引 | 引 |
| `shared/07-domain-map` | 引（系统边界） | 引（交接断点） | — |
| `shared/09-pitfalls` | 引（`stage:1`） | 引（`stage:2`） | — |
| `shared/talk-to-user` | 引（第一轮 / M3 单） | 引（A2 / A3） | — |
| `IIOT/01-requirements-method` | 退役 | 退役 | 退役 |

**硬约束：03 一份 01/02 的 references 都不许读。** 它要的一切都在 `{产品}.proto.json` 里；读不到就说明契约缺东西，该做的是回 02 补，不是自己去文档里找答案。这是"三段不退化成一长条流程"的唯一防线。

## 四、净增与净减

| 项 | 文件 | 说明 |
|---|---|---|
| 净增 1 | `shared/references/00-method-map.md` | 旧两份资产都没有"统一编号对照表"，这是新造的 |
| 拆出 2 | `01/references/00-stage1-overview.md`、`02/references/00-stage2-overview.md` | 由 `mfg/00-method.md` 切 |
| 合并出 1 | `shared/references/talk-to-user.md` | 由两份合并 |
| 退役 1 | `IIOT/01-requirements-method.md` | 重叠，进 `retire/` |

旧 18 → 新 18，数量守恒是巧合，不是目标；目标是**同一件事只有一份**。

## 五、一个待你定的命名

段目录名两份设计文档不一致：`ARCH.md` 写 `01-business / 02-requirement / 03-prototype`，`TECH.md §3.4` 写 `01-业务分析 / 02-需求分析与契约 / 03-原型设计`。

三份 SKILL.md 正文**没有写死段目录名**——本段 references 一律写 `references/xxx.md`（相对当前 skill 目录），共享的一律写 `$SUITE/shared/…`（绝对路径）。所以这个命名**不影响任何一条命令**，只影响建目录那一步。建议按 `TECH.md` 的中文名（老刘已在按它勘察），但需要你一句话确认，避免两人各建一套。
