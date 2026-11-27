# iiot-prd-suite · 架构设计

> 一句话：把 `mfg-req-analysis`（六步分析）与 `IIOT-PRD`（七步澄清 + 契约 + 容器）压成三段——**01 业务分析 / 02 需求分析 / 03 原型设计**——四份 SKILL.md 挂在**同一个物理目录**下，靠 `~/.workbuddy/skills/` 的四根软链变成四个可独立触发的 skill。
>
> 本文只定架构，不写实现。作者：幻神。日期：2026-11-16。

---

## 0 先解决两张流程表的对号（否则三段的分界线是随口划的）

两份资产的步骤编号不同源，必须先合并成一套，三段的分界才有依据。

| 统一编号 | `mfg-req-analysis` 六步 | `IIOT-PRD` 七步 | 归到哪段 |
|---|---|---|---|
| **S1 真问题与边界** | 步1（原话、边界、非目标、方案分离、替代路径、立场） | 步0（边界/量级）+ 步1（真问题） | 01 |
| **S2 角色** | 步2（六字段 + 现实性核对 + 缺席角色） | 步2（角色，含"是否真实存在""是否同一人"） | 01 |
| **S3 场景** | 步3（十一维矩阵 + 优先级 + 待确认） | 步3（场景 + 频次 + 失败兜底） | 01 |
| **S4 流程与状态机** | 步4（主流程/分支/泳道/状态机/断点） | 步4（泳道 + `from → to`） | 02 |
| **S5 异常与边界** | 步5（12 类 + 影响量化 + 降级） | 步5（11 类 = 软件 8 + 外设/追溯断链/标准版本） | 02 |
| **S6 对抗评审与结论** | 步6（四角色 ≥10 问 + 5 风险 + 结论二选一） | 步6（同上，卡点 A2） | 02 |
| **S7 落契约（语义层）** | 无 | 步7 的**语义半**：命令矩阵、状态机、字段主档、EARS、切片 | 02 |
| **S8 页面与容器（渲染层）** | 无 | 步7 的**页面半** + 容器/视觉/一致性/交互实测 | 03 |

三条结论：

1. **IIOT 的步 0 被并进 S1，不单独成步**。它的三个小节（一句话目标 / 非目标 / 数据量与频次）本来就是 M1 的表头，`A-04`/`A-05` 已经在管；`check_gate` 的 `G-06/G-07` 是同一件事的第二套阈值。
2. **IIOT 的步 7 必须切成两半**，这是整个重组的**唯一外科手术**。原来它一口气产出 `proto.json` 的语义（capabilities / stateMachine / requirements）和渲染（pages / componentTree / ui.kind），所以"分析"与"原型"焊死在一步里——这正是拆不动的根因。切法见 §3：**一个文件、两个区、两个写入者**。
3. **对外只说三段，不暴露 8 步**。用户在 `01→02→03` 之间移动；S1~S8 只活在 `_state.json` 的 `current.step` 里，用来回答"从哪继续"。

---

## 1 物理形态

### 1.1 结论

**一个物理目录，四个一级子目录，四根软链。** 不是四个并列目录。

```
<套件根>/     ← 唯一物理根，唯一 git 仓
```

理由（WorkBuddy 的加载规则直接决定了这个形态）：

| 约束 | 后果 |
|---|---|
| 只扫 `~/.workbuddy/skills/<name>/SKILL.md` 这一层，子目录里的 SKILL.md 不单独加载 | 把 4 个 SKILL.md 平铺进 `skills/` 下面不行；`skills/suite/01/SKILL.md` 也不会被加载 |
| `skills/` 里已存在指向仓库的**软链**（现有 `IIOT-PRD`、`mfg-req-analysis` 都是软链），实测可用 | 可以"一个物理目录、多个触发名"——软链指的是**子目录**，不是根 |
| 脚本内部按 `ROOT = dirname(dirname(__file__))` 找 `schemas/`、`assets/container/dist` | 脚本必须住在一个 `xxx/bin/` 下，且 `xxx/` 里同时有 `schemas/` 与 `assets/`。这决定了下面 `shared/` 的位置（§1.3） |

**结论：软链挂到 4 个子目录，不是挂到根。** 挂根只能得到一个名字；挂子目录能得到四个名字，且每个名字有独立的 `name`/`description`，互不抢词。

### 1.2 目录树（精确到文件名）

```
iiot-prd-suite/
├─ README.md                     装法、四根软链、状态文件、回滚到旧版（一行命令）
├─ LICENSE                       MIT（两份资产 LICENSE md5 相同，只留一份）
├─ .gitignore
├─ _design/
│  └─ ARCH.md                    本文件
│
├─ 01-business/                  ← 软链名 iiot-biz-analysis
│  ├─ SKILL.md
│  ├─ references/
│  │  ├─ 00-stage1-overview.md   （原 mfg 00-method.md 的 1~3 步半）
│  │  ├─ 01-problem.md
│  │  ├─ 02-roles.md
│  │  ├─ 03-scenarios.md         ★ 十一维矩阵、8 组配对、五步扫描协议
│  │  └─ 08-scenario-library.md  31 条起手式
│  └─ assets/templates/
│     ├─ M1-problem.md
│     ├─ M2-roles.md
│     └─ M3-scenarios.md
│
├─ 02-requirement/               ← 软链名 iiot-req-spec
│  ├─ SKILL.md
│  ├─ references/
│  │  ├─ 00-stage2-overview.md   （原 mfg 00-method.md 的 4~6 步半 + S7 落契约）
│  │  ├─ 04-flow.md
│  │  ├─ 05-exceptions.md
│  │  ├─ 06-review.md
│  │  ├─ 02-ear-spec.md          ★ EARS 六字段逐字段写法
│  │  └─ 05-demo-reverse.md      输入是 Demo/旧系统时怎么抽规则与状态机
│  └─ assets/templates/
│     ├─ M4-flows.md
│     ├─ M5-exceptions.md
│     ├─ M6-review.md
│     └─ proto.core.skeleton.json   02 的出口骨架（只有语义区）
│
├─ 03-prototype/                 ← 软链名 iiot-prototype
│  ├─ SKILL.md
│  ├─ references/
│  │  ├─ 03-page-split.md        三刀切分、五条硬判据、PRD 十种小节
│  │  ├─ 04-visual-spec.md       设计令牌、PC/PDA 布局、组件选型、审美 8 条
│  │  └─ 06-container.md         容器四层结构、渲染引擎、标注、导出
│  └─ assets/templates/
│     └─ proto.render.skeleton.json 渲染区骨架（pages/modules/pageGroups 空壳）
│
├─ suite/                        ← 软链名 iiot-suite（调度器，不含业务判据）
│  └─ SKILL.md
│
└─ shared/                       ← 唯一一份，谁都不复制
   ├─ bin/                       全部 12 个脚本，一份
   │  ├─ check_analysis.py       --stage 1|2（46 条不拆文件）
   │  ├─ check_contract.py       --stage core|render|full
   │  ├─ check_parity.py
   │  ├─ check_interact.py
   │  ├─ build_prd.py            --stage core|full
   │  ├─ build_prd_html.py
   │  ├─ render_figs.py
   │  ├─ render_common.py
   │  ├─ mdast.py
   │  ├─ field_sites.py
   │  └─ README.md               「哪个 stage 跑哪几条命令」的唯一索引
   ├─ schemas/
   │  ├─ _state.schema.json      ★ 由 _gate.schema.json 升级
   │  ├─ proto.schema.json       全量（core ∪ render）
   │  ├─ proto.core.schema.json  02 出口的必填集
   │  ├─ proto.render.schema.json 03 出口的必填集
   │  ├─ catalog.json
   │  └─ slice.schema.json
   ├─ assets/
   │  ├─ container/              5.9MB，唯一一份（src/ + dist/index.html）
   │  └─ vendor/mermaid.min.js
   ├─ references/
   │  ├─ 00-method-map.md        ★ S1~S8 与三段、与两份旧编号的对照表（§0 的表）
   │  ├─ 07-domain-map.md        13 系统边界 + 17 交接断点（01 用边界，02 用断点）
   │  ├─ 09-pitfalls.md          19 条坑，每条标「哪一步没做」
   │  └─ talk-to-user.md         ★ mfg 10-talk-to-user + IIOT 07-report-to-user 合并
   └─ examples/
      ├─ qms-incoming/           mfg 的 M1~M6 + _state.json（端到端正向样例）
      ├─ example-00-minimal.proto.json
      ├─ example-01-qms-incoming.proto.json
      ├─ example-02-accident.proto.json
      ├─ example-03-role-empty.proto.json
      ├─ example-00-slices.json
      ├─ PRD-accident.md / PRD-accident.html
      ├─ dist-accident.html / dist-role-empty.html
      └─ figs/                   sm-accident.svg · sm-measure.svg
```

### 1.3 为什么脚本全进 `shared/bin/`（这条决定后面所有路径写法）

现有脚本硬编码了两种相对定位：

| 脚本 | 假设 |
|---|---|
| `check_contract.py:20` | `ROOT/schemas/catalog.json` |
| `check_parity.py:509` | `ROOT/assets/container/dist/index.html` |
| `build.py:16` | `HERE`（自己所在目录）下找 `runtime.js` 等 |

如果脚本跟着段走（`01-business/scripts/`、`03-prototype/scripts/`），容器与 schema 就得各复制一份，5.9MB × 4。如果脚本全进 `shared/bin/`，则 `ROOT = shared/`，`shared/schemas/` ✓、`shared/assets/container/` ✓、`build.py` 的 `HERE = shared/assets/container/src/` ✓——**三个既有假设一个都不用改**。

代价：02 能看见 `check_interact.py`（它不该跑）。防法是文档而不是权限：`shared/bin/README.md` 是唯一索引，各段 SKILL.md 只写自己那几条命令。**不做目录级隔离**——四个段本来就共享同一批判据实现，靠目录墙隔出来的"独立"是假独立。

### 1.4 四根软链

```bash
ln -s <套件根>/01-business    ~/.workbuddy/skills/iiot-biz-analysis
ln -s <套件根>/02-requirement  ~/.workbuddy/skills/iiot-req-spec
ln -s <套件根>/03-prototype   ~/.workbuddy/skills/iiot-prototype
ln -s <套件根>/suite          ~/.workbuddy/skills/iiot-suite
```

| 软链 | 定位 |
|---|---|
| `iiot-biz-analysis` | 动手前想清楚：这需求该不该做、谁在用、有多少种情况 |
| `iiot-req-spec` | 想清楚之后写成机器能校验的语义契约（含 EARS） |
| `iiot-prototype` | 契约已经成立，画成能点、能审、能导 PRD 的 Vue 容器 |
| `iiot-suite` | 不产出业务内容，只回答"现在到哪了、下一步跑哪条命令" |

---

## 2 资产归属表

规则：**同一个事实只允许存在一份**。能拆成两半的（如 `00-method.md`）按 S 编号切开；拆开会变成两份互相矛盾的副本的（术语表、坑库、端到端样例），整份进 `shared/`。

### 2.1 来源 A：`mfg-req-analysis`

| 文件 | 去处 | 为什么 | 要不要改写（改什么） |
|---|---|---|---|
| `SKILL.md` | `01-business/SKILL.md` | 六步的前三步正好是 01 的全部内容 | **重写**：删步 4~6、删 M3 之后所有内容；判据索引只留 24 条；加"出口交 02 的三样东西" |
| `README.md` | `iiot-prd-suite/README.md` + `01-business/` 无 | 装法/命令/造红清单要跟着"四根软链 + 一套状态文件"重写，不能两段各写一份 | **重写**：软链装法、`--stage` 命令、造红清单按 stage 分组、回滚命令 |
| `LICENSE` | 根目录 `LICENSE` | 与 IIOT-PRD 的 LICENSE md5 相同（`0c17f7d1…`），只需一份 | 不改 |
| `.gitignore` | 根 `.gitignore` | 合并两份 ignore（加 `__pycache__`、`dist/*.html`、`examples/figs/.cache`） | 合并 |
| `.git/` | `retire/mfg-req-analysis-0.1.0/.git` | 新套件开新仓；旧历史舍不得丢就整目录归档，可 `git log` 查 | 不改，只 `git clone` 归档 |
| `_design/DESIGN.md` | `retire/mfg-0.1.0-design/` | 已被本 ARCH 覆盖，留着会与新架构打架 | 不改，加一个 `SUPERSEDED-BY-ARCH.md` 一行指针 |
| `_design/DIFF-huanshen.md` | 同上 | 0.1.0 的设计评审记录，历史价值 | 不改 |
| `_design/DRYRUN-qms-incoming.md` | `shared/examples/qms-incoming/DRYRUN.md` | 实跑记录，是"矩阵怎么用"的最佳教材，01 引用它 | **改写**：补一句"这是 0.1.0 单段实跑，结论仍有效" |
| `_design/IMPL-NOTES.md` | `retire/mfg-0.1.0-design/` | 实现笔记，含已作废的取舍 | 不改 |
| `_design/LEAD-REVIEW.md` | 同上 | 同上 | 不改 |
| `_design/TECH-SCAFFOLD.md` | 同上 | 同上 | 不改 |
| `assets/_gate.schema.json` | `shared/schemas/_state.schema.json` | 状态文件升级的唯一载体（§5） | **必改**：加 `stateVersion`、`stages{1,2,3}`、`handoff`、`current`、每产物 `sha256`；保留 `confirmations`/`matrix`/`openQuestions` 原结构不动 |
| `assets/templates/M1-problem.md` | `01-business/assets/templates/` | 01 的产物模板 | 不改 |
| `assets/templates/M2-roles.md` | 同上 | 同上 | 不改 |
| `assets/templates/M3-scenarios.md` | 同上 | 同上 | 不改 |
| `assets/templates/M4-flows.md` | `02-requirement/assets/templates/` | 02 的产物模板 | **改写**：加一行"状态机的唯一源在本文件，proto.stateMachine 是它的编译产物" |
| `assets/templates/M5-exceptions.md` | 同上 | 同上 | 不改 |
| `assets/templates/M6-review.md` | 同上 | 同上 | 不改 |
| `examples/qms-incoming/M1~M3` | `shared/examples/qms-incoming/` | 端到端样例不能拆：`_state.json` 的 hash 链要能一次跑通 | 不改内容，**只把 `_gate.json` 升级成 `_state.json`**（加 stage/hash 字段，M1~M6 原有内容不动） |
| `examples/qms-incoming/M4~M6` | 同上（整包不拆） | 同上 | 同上 |
| `examples/qms-incoming/_gate.json` | `shared/examples/qms-incoming/_state.json` | 同上 | **必改**：按 §5 的字段设计重写；原 6 步登记改成 3 段 + 8 步双视图 |
| `examples/qms-incoming/_draft/M3-candidates.md` | `shared/examples/qms-incoming/_draft/` | 扫描草稿，是"矩阵怎么扫"的实物证据 | 不改 |
| `scripts/check_analysis.py` | `shared/bin/check_analysis.py` | 46 条判据**绝不拆文件**（拆必漂：A-25 与 A-24 共用同一套矩阵解析） | **必改**：每条判据登记处加 `stage` 字段（`1`/`2`/`0`=跨阶段）；`--stage 1|2` 过滤；`A-63` 的越界词表按 stage 换表（§2.4）；`--status` 改读 `_state.json` |
| `references/00-method.md` | 拆成三份：`shared/references/00-method-map.md` + `01/references/00-stage1-overview.md` + `02/references/00-stage2-overview.md` | 它是唯一同时讲清"六步 + 判据索引 + 输入从哪来"的文件，三段都要看总览但都不该看全文 | **必拆**：总览表（§0 那张）进 shared；1~3 步"做什么/防什么/输入从哪来"进 01；4~6 步 + S7 进 02 |
| `references/01-problem.md` | `01-business/references/` | S1 | 不改 |
| `references/02-roles.md` | `01-business/references/` | S2 | 不改 |
| `references/03-scenarios.md` | `01-business/references/` | S3，矩阵取值表的唯一源（脚本实时求和读它） | 不改（**判据依赖它的表头，一个字节都不能动**） |
| `references/04-flow.md` | `02-requirement/references/` | S4 | **改写**：末尾加"状态机交接"小节——M4 的 `X → Y` 每行要有 `F-编号`，供 proto 的 `srcRef` 回指 |
| `references/05-exceptions.md` | `02-requirement/references/` | S5 | **改写**：每类异常加"能推出哪条非法验收"，因为 EARS 的 `acceptance.kind=illegal` 从这里来（§3） |
| `references/06-review.md` | `02-requirement/references/` | S6 | 不改 |
| `references/07-domain-map.md` | `shared/references/` | 01 用它定边界（M1 非目标），02 用它接断点（M4 交接点表） | **改写**：17 个断点每条标 `用于 M1 边界 / 用于 M4 交接` |
| `references/08-scenario-library.md` | `01-business/references/` | 31 条起手式只服务 S3 扫描 | 不改 |
| `references/09-pitfalls.md` | `shared/references/` | 19 条跨 1~6 步（每条自带"哪一步没做"），拆开就变成两份坑库 | **改写**：每条加 `stage: 1\|2`，`--status` 按当前段只提示本段的坑 |
| `references/10-talk-to-user.md` | `shared/references/talk-to-user.md`（与 IIOT 07 合并） | 第一轮话术（01）、M3 确认单（01）、A2/A3 汇报（02）三处要同一套术语对照，拆开必然漂成三份 | **合并改写**：mfg 的"第一轮四件事 + M3 确认单" + IIOT 的"A1/A2/A3 三段汇报 + 术语对照表"合成一本，按"什么时候说"分节 |

### 2.2 来源 B：`IIOT-PRD`

| 文件 | 去处 | 为什么 | 要不要改写（改什么） |
|---|---|---|---|
| `SKILL.md` | 拆成 `02-requirement/SKILL.md` + `03-prototype/SKILL.md`，七步表进 `shared/references/00-method-map.md` | 它的前半是 01/02 的流程，后半（页面/容器/视觉/验收六层）是 03 的全部 | **必拆**：02 只留 S4~S7 与"三个卡点"；03 只留 S8、组件白名单、容器、视觉令牌、验收六层；七步表原件进 shared 作对照 |
| `README.md` | 合并进根 `README.md`，原件 `retire/` | 两份 README 讲的是同一件事（怎么装、怎么跑） | 合并后归档 |
| `LICENSE` | 根 `LICENSE` | 与 mfg 相同，一份 | 不改 |
| `.gitignore` | 根 `.gitignore` | 合并 | 合并 |
| `references/01-requirements-method.md`（175 行） | `retire/`，其中两段被吸收 | 七步逐条判据与盲区，与 mfg 的 `01~06` 三处重叠（替代路径 ≥3、角色现实性、异常 11 类 vs 12 类），并存必红绿打架 | **退役**。吸收两处：① 每步"最常见错在哪"→ 01/02 的 `00-stage*-overview.md`；② A1/A2/A3 三卡点的"业务方要拍几个板"→ `talk-to-user.md` |
| `references/02-ear-spec.md`（157） | `02-requirement/references/` | EARS 是 S7 的唯一写法，属 02 | **改写**：加"`stateMachine` 字段必须引用 M4 的 `F-编号`"与"`acceptance.kind=illegal` 必须引用 M5 的异常类"两节 |
| `references/03-page-split.md`（325） | `03-prototype/references/` | 页面切分是 S8 的第一道刀 | 不改（`L2-74/80/81/82` 判据直接引它的节号） |
| `references/04-visual-spec.md`（217） | `03-prototype/references/` | 令牌与布局只服务渲染 | 不改 |
| `references/05-demo-reverse.md`（218） | `02-requirement/references/` | 它解决的是"输入不是口述而是 Demo"，抽出来的是规则与状态机（S4/S7）；页面结构的抽取结果最终由 02 写进 `proto.modules`，03 不需要读它 | **改写**：把"从路由抽模块"那节改成"抽出的模块登记进 `proto.modules[].sourceRef`"，明确 03 不得直接读本文 |
| `references/06-container.md`（475） | `03-prototype/references/` | 容器工程，只服务 S8 | **改写**：路径示例全部改成 `../shared/assets/container/` |
| `references/07-report-to-user.md`（170） | 合并进 `shared/references/talk-to-user.md`，原件退役 | 与 mfg 10 是同一件事的两种写法 | 合并（见 A 表 10 那条） |
| `schemas/proto.schema.json` | `shared/schemas/proto.schema.json`（全量）+ 新拆 `proto.core` / `proto.render` | 单文件 schema 会把"语义未完成"判成"格式非法"，02 出口永远过不了 | **必改**：顶层分 `core`（entities/roles/capabilities/stateMachine/requirements/fieldCatalog/slices）与 `render`（pages/modules/pageGroups/designTokens）；`proto.schema.json` 只是两者的 `allOf` |
| `schemas/catalog.json` | `shared/schemas/` | 54 个组件的 `impl` 登记，判据 `L2-51` 直接读 | 不改（`L2-51` 依赖其结构） |
| `schemas/slice.schema.json` | `shared/schemas/` | 切片由 02 产出，判据 `P-01~11` 读它 | 不改 |
| `scripts/check_gate.py`（452，G-01~G-24） | `retire/` | 与 `check_analysis.py` **大面积重复且阈值不同**（异常 11 类 vs 12 类、四角色 ≥10 问 vs ≥10 问但小节名不同、"非目标 ≥3"两处各判一遍）。两套判据管同一件事，必然一边绿一边红 | **退役，但迁移 3 条语义**：`G-01`（有原型无澄清）→ `_state.json` 的 `handoff["2→3"]` 必须存在；`G-10`（原型早于 A3）→ 由阶段 hash 链 + `mtime ≥ 上游 doneAt` 判；其余全部由 A 系判据接管 |
| `scripts/check_contract.py`（1288；L1 6 + L2 92 + P 11） | `shared/bin/` | 唯一能判"契约自不自洽"的脚本，拆开必漂 | **必改**：加 `--stage core|render|full`；`core` 只跑依赖于语义区的判据（见 §2.4 表）；`P` 组进 `core`（切片在 02 出口就要定） |
| `scripts/check_parity.py`（541；C 19） | `shared/bin/` | 三处一致，只有 03 会跑 | 不改逻辑；`--stage` 参数不需要（它天然属 full） |
| `scripts/check_interact.py`（1557；R 层） | `shared/bin/` | 只有 03 会跑（需 Chrome） | 不改 |
| `scripts/build_prd.py`（512） | `shared/bin/` | 02 要用它出"只到需求章的 PRD"给业务方审，03 要用它出完整 PRD | **必改**：`--stage core` 只出第 1~6 章（范围/角色/场景/流程/异常/需求），跳过页面/字段字典/图 |
| `scripts/build_prd_html.py`（220） | `shared/bin/` | 同属 PRD 导出 | 跟随 `--stage` |
| `scripts/render_figs.py`（288） | `shared/bin/` | 状态机 SVG，03 用；02 出 core PRD 时也要画状态机图 | 不改 |
| `scripts/render_common.py`（93） | `shared/bin/` | 被 build_prd / render_figs 共用 | 不改 |
| `scripts/mdast.py`（165） | `shared/bin/` | 同上 | 不改 |
| `scripts/field_sites.py`（126） | `shared/bin/` | 字段主档与渲染位双向绑定（`L2-96~101`），03 用 | 不改 |
| `scripts/migrate_fields.py`（184） | `retire/` | 一次性迁移工具（`fieldRegistry`→`fieldCatalog`），旧结构在新套件里不存在了 | 退役 |
| `scripts/__pycache__/`（6 个 pyc） | 不复制 | 编译缓存 | 删 |
| `assets/container/`（5.9MB，src 6 文件 + dist/index.html） | `shared/assets/container/` | 一份，四段共用；`build.py` 用 `HERE` 定位，位置无关 | **小改**：`build.py` 的 `--out` 默认值从 `dist/index.html` 改为提示用户显式传 `--out <项目>/dist/index.html`（避免往共享目录写产物） |
| `assets/vendor/mermaid.min.js` | `shared/assets/vendor/` | 图渲染依赖 | 不改 |
| `examples/example-00-minimal.proto.json` | `shared/examples/` | 最小契约，02 的 core 样例 + 03 的 render 样例都能用它 | 不改 |
| `examples/example-00-slices.json` | `shared/examples/` | 02 出口的切片样例 | 不改 |
| `examples/example-01-qms-incoming.proto.json` | `shared/examples/` | 三页样例（列表/PDA/看板） | 不改 |
| `examples/example-02-accident.proto.json` | `shared/examples/` | 推进动作范例（4 页/12 命令/7 状态），`L2-54~58` 的正例 | 不改 |
| `examples/example-03-role-empty.proto.json` | `shared/examples/` | 无权角色空态样例（R-06/R-07 的正例） | 不改 |
| `examples/shaping-qms/`（7 份 + `_gate.json`） | `retire/` | 它是七步形态的旧样例（`01-positioning`…`07-review` + A1/A2/A3），与 mfg 的 M1~M6 是**两份同构事实**。样例只能有一份，否则用户不知道照哪份写 | 退役（保留在 `retire/` 供对照） |
| `examples/PRD-accident.md` / `.html` | `shared/examples/` | PRD 产物样例，03 的验收参照（`C-22~C-25` 的正例） | 不改 |
| `examples/dist-accident.html` / `dist-role-empty.html` | `shared/examples/` | 容器产出样例 | 不改 |
| `examples/figs/sm-accident.svg` / `sm-measure.svg` | `shared/examples/figs/` | 状态机图产物 | 不改 |
| `examples/figs/.cache/`（12 个 svg） | 不复制 | 渲染缓存，可再生 | 删 |

### 2.3 净增文件（只有 4 个）

| 文件 | 为什么必须新增 |
|---|---|
| `02-requirement/assets/templates/proto.core.skeleton.json` | 02 要能 `--init` 出一个"只有语义区"的 proto 骨架；直接给完整 proto 会让模型顺手把 pages 也填了 |
| `03-prototype/assets/templates/proto.render.skeleton.json` | 03 要能"只补渲染区"；给完整 proto 会让模型重写语义区 |
| `shared/references/00-method-map.md` | 三段各说各话时，只有一张共同的步骤对照表能让"我从 01 交付给 02"有明确编号 |
| `shared/bin/README.md` | "哪个 stage 跑哪几条命令"的唯一索引，防 02 误跑 `check_interact` |

### 2.4 `check_analysis.py` 46 条的 stage 归属（不拆文件）

逐条编号（脚本实抓 46 个唯一编号），**不拆文件，只加 `stage` 字段**：

| 组 | 编号 | 条数 | stage | 备注 |
|---|---|---|---|---|
| 骨架 | `A-00` | 1 | **0（跨）** | 目录与状态文件合法性，两段每次都要查 |
| M1 | `A-01`~`A-06` | 6 | 1 | |
| M2 | `A-10`~`A-14` | 5 | 1 | |
| M3 | `A-20`~`A-26`、`A-24b` | 8 | 1 | 矩阵覆盖、排除理由、待确认 ≤7 |
| M3 闸门 | `A-25b`、`A-25c`、`A-25d`、`A-25e` | 4 | 1 | 与 `A-25` 合计五重；`A-25d`（`openQuestions` 与 M3 逐字一致）**只在 stage 1 跑**，因为 02 只允许改 `resolved` 字段、不许改 `text`/`suggest`，改了就靠 `A-25` 第④重 hash 拦 |
| M4 | `A-30`~`A-34` | 5 | 2 | |
| M5 | `A-40`~`A-44` | 5 | 2 | |
| M6 | `A-50`、`A-50b`、`A-51`~`A-54` | 6 | 2 | |
| 通用 | `A-60`、`A-60b`、`A-61`、`A-62`、`A-63`、`A-64` | 6 | **0（跨）** | 见下 |
| 合计 | | **46** | | 1 段 24 / 2 段 16 / 跨 6 |

**跨阶段 6 条的执行规则（防"两边都不跑"）：**

| 编号 | stage 1 语义 | stage 2 语义 | 防漏跑 |
|---|---|---|---|
| `A-60`/`A-60b` 虚报进度 | 检查 M1~M3 是否声称完成而实际为空 | 检查 M4~M6 | `--stage 2` 默认**先跑一遍 stage 1 的 A-00 + A-60**，再跑自身 |
| `A-61` 分步痕迹 | 检查 M1~M3 是否残留"待补充/稍后" | 同 | 同上 |
| `A-62` 含糊词 | 全文 | 全文 | 同上 |
| `A-63` 越界 | 禁 `componentTree`/`pages[]`/`capabilities[]`/`proto.json` 全部 | 禁 `componentTree`/`pages[]`/`modules`/`pageGroups`/`ui.kind`（`capabilities`/`stateMachine`/`requirements` **合法**） | 词表按 stage 切换，**两段都必须跑**，因为它的定义随 stage 变 |
| `A-64` 空话 | 六份 | 六份 | 同上 |

结论：`--stage 2` 的退出条件不是"16 条全绿"，而是"16 条 + 6 条跨阶段"全绿。`--stage 1` 的退出条件是"24 条 + 6 条跨阶段"全绿。两段都必须让跨阶段组跑，**不许只按数组切片**。

`check_contract.py` 的 stage 切法（对应 §3 的两区设计）：

| 组 | 编号范围 | `--stage core` | `--stage render` | `--stage full` |
|---|---|---|---|---|
| L1 结构 | 6 条 | 只校 core 区必填 | 只校 render 区必填 | 全 |
| L2 语义 | 92 条 | 命令 owner、状态机端点、EARS 非法路径、角色引用、字段主档定义、业务规则形状、决策项 | 四态、组件白名单且 `impl=done`、页面必填、目录树、PDA 策略、字段主档与渲染位双向绑定、取数链路 | 全 |
| P 切片 | 11 条 | **全跑**（切片在 02 出口定） | — | 全 |
| C/R/L3 | 19 + R 层 | — | 全跑 | 全 |

---

## 3 三阶段的交接契约

### 3.1 一行说清

| 段 | 入口读什么 | 出口写什么 | 卡点 | 下游拿它干什么 |
|---|---|---|---|---|
| **01 业务分析** | 用户原话 / 会议纪要 / 现有单据 / Demo（不读任何上游 md） | `M1-problem.md` `M2-roles.md` `M3-scenarios.md` + `_state.json.stages[1].export` | **M3 五重硬闸门**（ERROR）；M1 方向确认（WARN） | 02 从 `export.p0[]` 拿要建模的场景，从 `export.roles[]` 拿 actor 候选，从 `openQuestions[]` 拿未定项 |
| **02 需求分析** | `M1~M3`（引用不重抄）+ `_state.json.stages[1].export` | `M4-flows.md` `M5-exceptions.md` `M6-review.md` + `{产品}.proto.json` 的 **core 区** + `slices.json` + `_state.json.stages[2]` | **A2 评审签署** + `check_analysis --stage 2` 全绿 + `check_contract --stage core` 全绿 | 03 只读 `proto.json` 的 core 区（不读任何 md） |
| **03 原型设计** | **只有** `{产品}.proto.json`（core 已冻结）+ `slices.json` | `proto.json` 的 **render 区** + `dist/index.html` + `PRD-{产品}.md/html` + `_state.json.stages[3]` | `check_contract --stage render` + `check_parity` + `check_interact` 三层绿 | 人（评审、交付开发） |

### 3.2 01 的出口：M1/M2/M3 + `_state.json`，**M3 确认单必须带 P0 清单**

只交三份 md 不够——02 会退化成"把 M3 的场景表再读一遍再抄一遍"，这就是上次来料模块大改的根因（02 抄了一份 P0 清单，01 改了场景，02 那份没变，最后两份都对不上）。

所以 01 的出口是**三段**：

```json
"stages": { "1": { "export": {
   "p0":   [ {"id":"S-03","name":"…","why":"…","srcRef":"M3-scenarios.md#场景表"} ],
   "roles":[ {"id":"u-qa","name":"检验员","exists":true,"srcRef":"M2-roles.md#R-02"} ],
   "openQuestions": [ {"id":"Q-01","text":"…","assumed":"…","resolvedBy":null} ]
}}}
```

| 字段 | 02 怎么用 | 硬约束 |
|---|---|---|
| `p0[]` | **只给 P0 建流程**，P1 场景在 M4 里登记为"本批不做流程"并给出理由 | 数量必须等于 M3 场景表 P0 行数（`A-25f` 新增：`export.p0.len` ≠ M3 P0 行数即红） |
| `roles[]` | 直接映射成 `proto.roles[].id`，**不许另建一套 actor 命名** | `proto.roles[].srcRef` 必须指向 `M2-roles.md#R-xx`（`A-70` 新增：找不到即红） |
| `openQuestions[]` | 02 只许改 `resolved`/`resolvedBy`，不许改 `text`/`suggest` | 改了 → `A-25` 第④重 hash 失配（已签的 M3 被偷偷改）→ 直接红 |

**M3 确认单要不要带 P0 清单给 02：要。** 但它同时是给用户看的东西，所以分两处：给人看的是 `M3-scenarios.md` 的「确认单」节（≤7 条），给 02 的是 `_state.json.export.p0`。**同一份事实两个投影，靠 `srcRef` 拴在一起**，不是两份。

### 3.3 02 的出口：M4/M5/M6 + `proto.json` 的 core 区

`proto.json` **一个文件、两个区、两个写入者**。这是整个架构的关键点，也是"03 不许依赖 01/02 的 markdown"能成立的唯一办法。

| 区 | 键 | 写入者 | 从哪推导 |
|---|---|---|---|
| `core` | `entities[]` `roles[]` `capabilities[]` `stateMachine[]` `requirements[]`（EARS） `fieldCatalog[]` `dataSources[]` `decisions[]` `businessRules[]` `slices[]` | **02** | 见下表 |
| `render` | `pages[]` `modules[]` `pageGroups[]` `menu[]` `designTokens` `components[]`（引用） | **03** | 从 `core.capabilities`（谁在哪个页面 owns 什么）+ `core.requirements`（每页要满足哪些）+ `slices[]` |

`core` 各键的推导来源：

| core 键 | 唯一来源 | 说明 |
|---|---|---|
| `roles[]` | M2 角色表（经 `export.roles`） | 只准引用 id，不准重写六字段 |
| `stateMachine[].transitions[]` | **M4 的 `from → to` 行** | 每条 transition 带 `srcRef: "M4-flows.md#F-04"` |
| `capabilities[]` | M4 的推进动作（一个动作 = 一个状态 = 一条命令）+ M6 风险的处置结论 | `actor` 来自 `roles[]`，`from` 来自 `stateMachine` |
| `requirements[]`（EARS） | **在 02 的 S7 写**，不在 03 | `rule` 来自 M5 的降级路径与 M6 的疑问；`stateMachine` 字段引用 `transitions[].id`；`acceptance.kind=illegal` 必须引用 M5 的异常类编号（`A-71` 新增：`illegal` 用例的 `srcRef` 指不到 M5 具体行即红） |
| `fieldCatalog[]` | M5 的影响量化 + M6 的疑问里点名的业务字段 | 只登记"被人点名过的字段"，不臆造 |
| `slices[]` | M6 结论 + 依赖关系 | P 组判据（11 条）在 `--stage core` 就跑 |

**EARS 在哪一步写：02 的 S7，且必须是 02 的最后一步。** 因为 EARS 的 `stateMachine` 要引用 M4 的迁移、`acceptance.illegal` 要引用 M5 的异常类、`rule` 要引用 M6 的风险——放在 03 写，就等于让"画页面的人"去补"需求"。原来 IIOT 的步 7 把两者混在一起，是因为容器和 EARS 在同一个 `proto.json` 里；现在用两区隔开，EARS 归 02，页面归 03。

### 3.4 03 的入口只有 `proto.json`：M4 与 `stateMachine` 是否重复

**重复。定唯一源：`M4-flows.md` 是唯一源，`proto.stateMachine` 是 02 出口时编译出的产物，03 只读产物。**

| 判据 | 内容 |
|---|---|
| 方向 | M4 → proto，单向。02 出口前跑 `A-72`：M4 每条 `X → Y` 在 `proto.stateMachine` 有对应 transition，且 `proto` 每条 transition 在 M4 有对应行（**双向一一对应**，缺一边就红） |
| 03 的可见性 | 03 只读 `proto`。它能看到 `transitions[].srcRef = "M4-flows.md#F-04"`，**知道回哪里找，但不需要读** |
| 改需求时的规矩 | 用户口头改流程 → 03 **不许**直接改 `proto.stateMachine`（那会让 M4 与 proto 脱钩，下次 02 重跑就覆盖掉）；03 必须报"这条要回 02 改 M4"，并把 `_state.json.stages[2].status` 标 `stale` |
| 为什么不让 03 读 M4 | 一旦 03 能读 M4，模型就会拿 M4 的散文去补 proto 里缺的东西，于是"proto 是唯一事实"破功，`check_parity` 也就失去意义（它比的是 proto vs DOM，不是 M4 vs DOM） |

`M4-flows.md` 里的状态机**图**（`render_figs.py` 出的 svg）也归 02：02 出 core PRD 时要给人看状态机。03 复用同一张图，不重画。

### 3.5 02 出口的人读件

02 的出口如果只有 JSON，业务方没法审。所以 02 出口**允许且建议**跑一次：

```bash
python3 ../shared/bin/build_prd.py --stage core {产品}.proto.json --out REQ-{产品}.md
```

产出只到需求章（范围 / 角色 / 场景 / 流程 / 异常 / 需求清单），**不含页面、字段字典、图**。完整 PRD 由 03 出。这样"02 的产物能被人签字"，同时不把页面的事情提前到 02。

---

## 4 四份 SKILL.md 的分工与触发词

### 4.1 逐份定义

#### ① `iiot-suite`（调度器）

- **name**：`iiot-suite`
- **description**（逐字，可直接用）：

> 三段式需求与原型流水线的调度入口：01 业务分析、02 需求分析、03 原型设计。**只做状态判断与转交，不做分析、不写文档、不画原型。** 当用户说「继续」「到哪一步了」「接着上次做」「我上次做到哪了」「这个项目还差什么」，或在一个已有 `_state.json` 的项目上说「往下做」「下一步」时使用。触发词：继续、接着做、上次做到哪、进度、状态、下一步、恢复、三段式、iiot 套件、流水线调度。要真正做分析或画原型时，本 skill 会转给 `iiot-biz-analysis` / `iiot-req-spec` / `iiot-prototype`。
- **什么时候进来**：用户没说要做什么、只说"继续"；或跨会话回来，模型不确定上下文。
- **进来第一件事**：

```bash
python3 ../shared/bin/check_analysis.py <项目目录>/ --status
```
读 `_state.json`，输出「走到第几段第几步 / 下一步该跑哪条命令 / 哪些产物 hash 漂了」。**然后转交，不自己做。**
- **出口**：一句转交指令 + 一条可复制的命令。不写任何产物。

#### ② `iiot-biz-analysis`（01）

- **name**：`iiot-biz-analysis`
- **description**（逐字）：

> 制造业业务分析（三段流水线第 1 段）：把口头需求、会议纪要、「领导说要个看板」拆成三份可验收的产物——真问题（分清问题与方案、还原真实目标、给替代路径）、角色（六字段 + 现实性核对 + 缺席角色）、场景（十一维覆盖矩阵 82 格，第 3 步是硬闸门必须用户本人确认）。**只做业务分析，不出原型、不写 PRD、不写需求契约。** 当用户说「分析一下这个需求」「业务方到底想要什么」「值不值得做」「这个需求是真的吗」「帮我拆一下场景」「明天开评审会怎么讲」「需求澄清」时使用。触发词：业务分析、需求分析、需求澄清、真问题、需求真伪、值不值得做、角色分析、场景拆解、场景穷举、矩阵、六步法第 1 到 3 步、MES 需求、QMS 需求、LIMS 需求、WMS 需求。要写需求契约用 `iiot-req-spec`；要画原型用 `iiot-prototype`；要一次跑完分析加原型用 `IIOT-PRD`。
- **什么时候进来**：只有一段零散信息、还没定"要不要做"；或场景没扫穷举。
- **进来第一件事**：

```bash
python3 ../shared/bin/check_analysis.py <项目目录>/ --status --stage 1
```
从第一个非 `done` 的步继续；没有项目就先 `--init`。
- **出口**：`M1/M2/M3` + `_state.json.stages[1]`（含 `export.p0/roles/openQuestions`），并明确告诉用户「下一步是 02，命令我给你」。

#### ③ `iiot-req-spec`（02）

- **name**：`iiot-req-spec`
- **description**（逐字）：

> 需求规格化（三段流水线第 2 段）：把已确认的真问题、角色、场景写成机器能校验的语义契约——流程与状态机（`from → to`）、异常 12 类与降级路径、四角色对抗评审，最后落成 EARS 需求（角色/触发/规则/状态机/预期/验收，含非法路径）与分批交付切片。产物是 `M4`~`M6` 加 `{产品}.proto.json` 的语义区，可用脚本判红。**只写语义契约，不画页面、不做组件树、不做视觉。** 当用户说「把流程画一下」「梳理状态机」「异常怎么处理」「开评审会」「写需求清单」「写 EARS」「分批上线怎么切」「需求规格」时使用。触发词：需求分析、需求规格、流程梳理、状态机、异常梳理、异常 12 类、对抗评审、需求评审、EARS、需求清单、契约、切片、分批交付、验收条件、非法路径。要画原型用 `iiot-prototype`；要从零分析用 `iiot-biz-analysis`。
- **什么时候进来**：01 的 M3 已签；或用户手里已有确认过的场景表要往下走。
- **进来第一件事**：

```bash
python3 ../shared/bin/check_analysis.py <项目目录>/ --status --stage 2
```
若 `_state.json` 里 stage 1 不是 `done` → **拒绝开工**，回 01。
- **出口**：`M4/M5/M6` + `proto.json` 的 core 区 + `slices.json`；`check_analysis --stage 2` 与 `check_contract --stage core` 全绿；可选 `build_prd --stage core` 出一份给人审的 `REQ-{产品}.md`。

#### ④ `iiot-prototype`（03）

- **name**：`iiot-prototype`
- **description**（逐字）：

> 高保真原型设计（三段流水线第 3 段）：读一份已经成立的需求契约（`{产品}.proto.json` 的语义区），产出可直接交给开发的 Vue 单文件原型（PC 与 PDA 双端同源、离线可用、三栏覆盖式容器）、同源 PRD（可编辑可导出），并用脚本过三层验收（契约结构 / 三处一致 / 无头浏览器真点一遍）。按钮可用性由状态机推导、推进动作各自成为单据状态、组件只用已实现的白名单。**只做原型与渲染，不改需求语义、不写 EARS、不做业务分析。** 当用户说「画个原型」「做个高保真」「出 PRD」「PDA 页面长什么样」「这个页面怎么拆」「把原型交给开发」「交互能点吗」「标注一下这里」时使用。触发词：原型、高保真原型、可交互原型、PRD、页面拆解、PDA、工控界面、组件、容器、标注、交付开发、截图、评审模式。要改需求语义先回 `iiot-req-spec`；要重做分析回 `iiot-biz-analysis`。
- **什么时候进来**：`proto.json` 的 core 区已冻结（`_state.json.handoff["2→3"]` 存在）。
- **进来第一件事**：

```bash
python3 ../shared/bin/check_contract.py {产品}.proto.json --stage render
```
缺 core 或 core 不自洽 → **拒绝开工**，报"回 02"。core 在、render 空 → 从 `proto.render.skeleton.json` 起。
- **出口**：`proto.json` 的 render 区 + `dist/index.html` + `PRD-{产品}.md/html`，`check_contract --stage render` / `check_parity` / `check_interact` 三层绿。

### 4.2 抢词矩阵

| 用户说的话 | 谁接 | 为什么不给别人 |
|---|---|---|
| 「帮我分析这个需求」 | **01** | 02 的 description 里"需求分析"是 `需求规格` 的别名，但 01 有"需求澄清 / 值不值得做"这些更强的锚；且 01 的入口不需要任何前置产物，02 需要 M3 已签 |
| 「做原型」 | **03** | 只有 03 的 description 含"原型/PRD/PDA/容器"；01、02、suite 三份都不许出现"原型" |
| 「继续」 | **suite** | 只有 suite 的 description 含"继续/上次做到哪/进度"；三段各自的 description 都不许出现这几个词 |
| 「需求分析」单独一词 | **01**（默认），若项目里 stage 1 已 done → suite 提示可跳 02 | 01 在 description 里对"需求分析"占位更靠前；02 用"需求规格/需求清单"做区分 |
| 「先分析，分析完再画」 | **01**，做完转 02，再转 03 | 01 的 SKILL.md 里写明"出口必须给下一段的命令"，不许一口气做到底 |
| 「一次做完」/「直接出 PRD 和原型」 | **`IIOT-PRD`（旧版）** | 旧版是七步一体，新套件的三段不追求一次跑完。01/02/03 的 description 里都写了"要一次跑完用 IIOT-PRD"，把这条路指回去 |

### 4.3 与旧 `IIOT-PRD` 的处理

旧版的 description 里同时含"需求分析 / 原型 / PRD / PRD / 状态机 / 评审"，**必然与 01+02+03 三方抢词**，这不是措辞能解决的。所以分两段式：

| 阶段 | 动作 | 理由 |
|---|---|---|
| 迁移期（第 1~4 周） | 保留 `~/.workbuddy/skills/IIOT-PRD` 软链；四份新 description 里都加一句「要一次跑完分析加原型用 `IIOT-PRD`」作为**显式指回** | 用户还在用旧版交付，硬切断会打断在跑的项目 |
| 切换期（第 5 周起） | **摘掉软链**（不是删目录）：`rm ~/.workbuddy/skills/IIOT-PRD` | 软链是安装态，删它不算"改封版资产"；摘掉后抢词消失 |
| 回滚 | `ln -s .../IIOT-PRD ~/.workbuddy/skills/IIOT-PRD` | 一条命令 |

`mfg-req-analysis` 的软链在新套件上线当天就摘——它的内容 100% 被 01/02 吸收，留着只会与 01 抢"需求分析 / 六步法"。

---

## 5 阶段状态与断点恢复

### 5.1 结论：`_gate.json` 升级为 `_state.json`，`gateVersion 1.0` 升 `stateVersion 2.0`

不能留在 `_gate.json`：它现在只记"六步各做了什么 + 三个签署 + 矩阵统计"，**没有阶段概念、没有产物 hash、没有交接记录**，所以回答不了"三天后从哪继续"。名字也得换——叫 `_gate` 会让人以为只有一个闸门，实际它要记三段的状态。

旧项目（`analysis/*/`）靠 `check_analysis.py --migrate` 转换：`_gate.json` 的**所有现有字段原样搬入 `stages[1]`**，`stateVersion` 置 2.0，其余段标 `not_started`。**不丢任何字段**，`confirmations.M3` 的 `contentHash` 必须原样保留（否则已签的闸门会被判成"未签"）。

### 5.2 字段设计

```jsonc
{
  "stateVersion": "2.0",
  "suite": "iiot-prd-suite",
  "product": "新锂想QMS · 来料检验",
  "createdAt": "2026-11-16T10:00:00+08:00",
  "updatedAt": "2026-11-16T18:20:00+08:00",

  "current": { "stage": 2, "step": "S5", "status": "in_progress" },
  "// current 的作用": "回答'现在在哪'。step 用统一编号 S1~S8（§0），stage 用 1|2|3 给人看",

  "stages": {
    "1": {
      "status": "done",                    // not_started | in_progress | done | stale
      "startedAt": "...", "doneAt": "...",
      "confirmed": { "by": "俞秀福", "at": "…", "quote": "场景没遗漏，可以继续" },
      "artifacts": {
        "M1-problem.md":   { "sha256": "9f2c…", "bytes": 4210, "mtime": "…" },
        "M2-roles.md":     { "sha256": "71ab…", "bytes": 3890, "mtime": "…" },
        "M3-scenarios.md": { "sha256": "0d44…", "bytes": 9120, "mtime": "…" }
      },
      "checks": { "tool": "check_analysis --stage 1", "errors": 0, "warns": 2, "ranAt": "…" },
      "export": {
        "p0": [ { "id": "S-03", "name": "…", "why": "…", "srcRef": "M3-scenarios.md#场景表" } ],
        "roles": [ { "id": "u-qa", "name": "检验员", "exists": true, "srcRef": "M2-roles.md#R-02" } ],
        "openQuestions": [ { "id": "Q-01", "text": "…", "suggest": "…",
                             "resolved": null, "resolvedBy": null, "srcRef": "…" } ]
      },
      "legacy": { "nonGoals": [], "scale": {}, "matrix": {}, "waived": {} }
      // legacy 只放从 _gate.json 原样搬来的字段，保证 --migrate 无损
    },

    "2": {
      "status": "in_progress",
      "artifacts": { "M4-flows.md": {...}, "M5-exceptions.md": {...}, "M6-review.md": {...} },
      "contract": {
        "file": "{产品}.proto.json",
        "coreHash": "a1b2…",        // core 区的规范化 sha256（排序键 + 去空白）
        "renderHash": null          // 03 填
      },
      "checks": { "tool": ["check_analysis --stage 2", "check_contract --stage core"],
                  "errors": 0, "warns": 1, "ranAt": "…" }
    },

    "3": {
      "status": "not_started",
      "artifacts": { "dist/index.html": null, "PRD-{产品}.md": null },
      "contract": { "renderHash": null, "parityPassed": false, "interactPassed": false }
    }
  },

  "handoff": {
    "1->2": { "at": "2026-11-16T15:00:00+08:00", "exportHash": "…", "consumedBy": ["M4-flows.md"] },
    "2->3": { "at": null, "coreHash": "a1b2…", "consumedBy": ["pages[]", "modules[]"] }
  },

  "openQuestions": [ /* 全项目唯一一份，阶段间只改 resolved 字段 */ ]
}
```

### 5.3 回答"三天后回来说继续"

`check_analysis.py <dir>/ --status` 按这个顺序判定，**规则固定，不靠模型记忆**：

| 情况 | 判定 | 动作 |
|---|---|---|
| `current.status = in_progress` 且当前步产物 hash 与磁盘一致 | 真的在做，没变过 | 从 `current.step` 继续，报"上次在 S5 写到一半" |
| 当前步产物 hash 与磁盘**不一致** | 有人（可能是用户手改/另一个会话）改过 | 该步标 `stale`，**从该步重跑**，并打印哪几个文件变了（不猜变了什么） |
| 上游 `stages[n].status = done` 但 `artifacts.*.sha256` 全部一致 | 已确认部分可信 | **跳过，一个字都不重写**；只读 `export` 取下游输入 |
| 上游某产物 hash 变了 | 已签的东西被改过 | 上游标 `stale`，下游连锁标 `stale`；提示"01 的 M3 变了，02 的 proto 需要重出"，并给出**不要**自动重写的理由（重写会丢 02 人工判断） |
| `stages[1].status = in_progress` 且无 `confirmed` | 01 还没过闸门 | 回 01；03 若被直接唤起，**拒绝** |
| `stages[2].contract.coreHash` 存在且与当前 proto 的 core 区 hash 一致 | 02 已交付 | 03 可开工；不一致 → 03 拒绝（说明有人在 03 阶段改了语义区） |

**关键：hash 是"是否需要重做"的唯一依据，mtime 只用于 `A-25` 第⑤重（防跳步）和 `G-10` 的替代品。** 理由已在 0.1.0 里验证过：`touch` 能改 mtime，但改不了 hash；用户确认后追加一行说明会改 mtime，但 hash 只对正文算，不误伤。

**`--status` 的输出必须包含一条可以直接复制的命令**，例如：

```
当前：02 需求分析 · S5 异常与边界（写到一半）
上一步产物 hash 全部一致，M1~M4 不会重做。
下一步：python3 ../shared/bin/check_analysis.py analysis/新锂想QMS/ --stage 2
未决：Q-01 检验批超期是否允许回退（assumed：允许，需你确认）
```

---

## 6 废弃与共存

| 资产 | 处置 | 理由 | 迁移期怎么提示用户 |
|---|---|---|---|
| `mfg-req-analysis`（整个 skill） | **空壳转发，4 周后删** | 46 条判据与 11 份 references 已 100% 迁进 01/02；但用户手里的 `analysis/*/` 项目还要能跑 `--status`。删太早会让他"分析做到一半打不开" | `SKILL.md` 只留 6 行：一句"已拆成 `iiot-biz-analysis`（1~3 步）与 `iiot-req-spec`（4~6 步）"，一条 `--migrate` 命令，一条新命令。**不保留任何业务内容**，否则模型会读它而不读新版 |
| `mfg-req-analysis/.git` 与 `_design/` | 归档到 `retire/mfg-req-analysis-0.1.0/`，只读 | 设计史有复盘价值；`.git` 留着能查 0.1.0 每次改动的原因 | README 里一行"历史设计在 retire/，不要照它实现" |
| `IIOT-PRD`（整个 skill） | **原地不动，一个字节不改；只摘/挂软链** | 封版资产是用户当前交付在用的东西。改它 = 改交付基线 | 第 5 周摘软链前一周，在 `iiot-prototype/SKILL.md` 开头写一行"本段替代 IIOT-PRD 的步 7 后半；旧版仍可整跑"。**不在 IIOT-PRD 里加 README**——那是改资产 |
| `IIOT-PRD/examples/shaping-qms/` | 不删，随封版资产一起冻着 | 它与新套件的 M1~M6 是两份同构样例，但它是封版的一部分，动它等于改版 | 新 `shared/examples/` 里只放 mfg 那一套；README 注明"shaping-qms 是 0.9.x 形态，已不作为样例" |
| `check_gate.py` 的 G 系列 24 条 | **退役**（不迁进新套件） | 与 A 系大面积重叠且阈值不一致（11 类 vs 12 类）。两套并存时必然出现"check_gate 绿、check_analysis 红"，用户只会认为工具坏了 | 01/02 的 SKILL.md 里删掉所有 `check_gate` 命令；`shared/bin/README.md` 写一行"G 系列已退役，语义迁到 `_state.json` 的 handoff 与 A 系判据" |
| `migrate_fields.py` | 退役 | 它迁的是 `fieldRegistry`→`fieldCatalog`，新 schema 里 `fieldRegistry` 不存在 | 无提示（旧项目不需要它） |
| `examples/figs/.cache/`、`scripts/__pycache__/` | 删 | 可再生，占体积 | 无 |

**不做"保留并行"。** 并行期一长，用户会在旧 skill 里提需求、在新 skill 里被拒，两份判据各自演化，最后又回到"两个 skill 说两套话"。空壳转发 + 4 周窗口是唯一能收敛的做法。

---

## 7 风险清单

| # | 风险 | 为什么会发生 | 怎么防 |
|---|---|---|---|
| **R1** | 用户以为三段会自动连起来，实际每段都要他重新说一句 | 三个 skill 是三个独立触发；模型在 01 收尾时不会主动去调 02（它不是一个进程里的两个函数）。用户心智是"一条流水线"，实际是"三个工具" | ① 01 的出口**强制**输出一段"下一步：复制这条命令"，把跨段变成复制粘贴而不是思考；② `iiot-suite` 兜住"继续"这一类说法；③ 01/02 的 `_state.json` 里 `current` 指向下一步，用户说任何一句含糊的话都能被 suite 接住 |
| **R2** | `proto.json` 成为单点：02 写错，03 全错，而 03 的人看不到 02 的推理 | 这正是"03 只依赖 proto"的代价。03 只看到 `capabilities[].reason="仅「待审核」可审核"`，看不到 M4 里为什么是这个状态、M5 里为什么这个异常要拦 | ① 每个 core 元素强制 `srcRef`（`A-70`），03 能被指回出处；② 02 出口建议出 `REQ-{产品}.md`（只到需求章），这是 03 能读的"推理摘要"，且它是 proto 的投影不是新事实；③ 03 发现语义可疑时，规矩是"标 stale 回 02"，不是就地改 |
| **R3** | 判据按 stage 过滤后，跨阶段判据（尤其 `A-63` 越界）两边都不跑 | `--stage 1` 只跑 24 条、`--stage 2` 只跑 16 条，若实现成"按数组切片"，那 6 条跨阶段的就掉进缝里 | ① 跨阶段组用 `stage: 0` 显式标记，`--stage 1/2` **都**跑；② `--stage 2` 开机先跑 `A-00 + A-60/A-60b`（虚报进度与骨架），防"只查自己那段"；③ `A-63` 的越界词表**按 stage 分两张**（stage 2 允许 `capabilities/stateMachine/requirements`），否则 02 一写契约就红、模型会去关判据 |
| **R4** | 5.9MB 容器在四个 skill 之间被复制四份 | 每段都想"自包含"，复制是最省事的做法；一旦复制，`build.py`、`styles.css` 就有四份，改一处三处不知道 | ① 物理上只有 `shared/assets/container/` 一份，四段都写 `../shared/assets/container/`；② `README.md` 写明"禁止把 container 复制进段目录"；③ 加一条 CI 检查（可选）：`find . -name "components.js" | wc -l` 必须为 1 |
| **R5** | 两套判据风格并存（G 24 条 vs A 46 条），一边绿一边红 | `check_gate` 没被立即删，用户/老刘仍会跑它；它对"异常 11 类"判绿，而 `A-40` 对"12 类"判红 | ① `check_gate.py` 在切换当天从 `shared/bin/` 移走（不留在能被找到的地方）；② 段 SKILL.md 里一条 `check_gate` 命令都不许出现；③ 旧脚本留在 `retire/`，需要时人去找，不进入自动路径 |
| **R6** | 六个 skill 抢"需求分析"一个词 | 旧 `IIOT-PRD`、旧 `mfg-req-analysis`、新 01/02/03、suite 共六份 description 都含需求相关词。模型选哪个是概率行为 | ① 四份新 description 用**互斥锚点**（01=真问题/值不值得做；02=需求规格/EARS/契约；03=原型/PRD/PDA；suite=继续/进度）；② 第 5 周摘旧软链，这是唯一彻底的办法；③ 迁移期四份新 description 都写"要一次跑完用 IIOT-PRD"，把冲突变成显式路由 |
| **R7** | hash 链太严，改一个字整段作废，用户干脆绕过（删 `_state.json`、或直接说"别管状态了重做"） | 已签文件被改 → 下游全 `stale`。用户觉得"我只是改了个错别字" | ① `stale` 只**提示**不**阻断**（除 02→03 的 coreHash，那个必须阻断）；② `--status` 明确打印"变了哪几个文件、变了多少字节"，让用户判断；③ `_state.json` 丢了也不致命：`--init --adopt` 从现有产物重建（hash 重算、签署置为"需重签"） |
| **R8** | 03 只读 proto，用户口头改需求时模型就地改 `proto.stateMachine`，语义区与渲染区错位 | 03 里模型手里有文件写权限，改一行 JSON 比"回 02"省事得多；而 `check_contract --stage render` 看不出语义区被动过 | ① `stages[2].contract.coreHash` 由 02 写、03 只读；03 每次开工先算 core 区 hash，与记录不符 → **拒绝开工**；② 在 03 的 SKILL.md 里把"改语义区"写成明确的禁止项（不是建议）；③ `check_parity` 增加"core hash 与 `_state.json` 一致"一条 |
| **R9** | 02 只给 P0 建流程，P1 场景永远没有流程与异常，覆盖缺口静默 | 01 出口只传 `p0[]`，02 天然只想做 P0；`A-30~A-34` 也只查"P0 上流程"，不查 P1 的去向 | ① M4 模板强制有一节「本批不做的场景」，每条 P1 必须登记"为什么不做、什么时候做"（`A-35` 新增：M3 里 P1 场景数 ≠ M4 登记数即红）；② 02 出口的 `REQ-{产品}.md` 里这一节必须出现（`build_prd --stage core` 强制渲染） |
| **R10** | 物理目录改名/搬家，四根软链全断，用户看到四个"空 skill" | 软链是绝对路径；用户换机器、移动 `原型PRD/` 目录都会断 | ① README 顶部给出重建软链的 4 行命令（可直接粘贴）；② `iiot-suite` 的 SKILL.md 第一条写"若四段中任意一段打不开，先跑这条重建命令"；③ 建议把 suite 目录固定在 `~/WorkBuddy/原型PRD/` 下并在 README 里写"不要移动" |
| **R11** | 旧项目（只有 M1~M3 的 `analysis/*/`）在新脚本下 `--stage 2` 跑不通，报一堆"缺 M4" | `_gate.json` 转成 `_state.json` 时 stage 2 是 `not_started`，但用户会直接跑 `--stage 2` 校验 | ① `--stage 2` 先读 `_state.json`，上游 `status != done` 直接给一句人话"01 还没过闸门，先跑 `--stage 1`"，不是刷 5 条 ERROR；② `--migrate` 后自动跑一次 `--status` 打印"你现在在 01 的哪一步" |

---

## 附：与旧两版的差异一览（给老刘实现时对照）

| 维度 | `mfg-req-analysis` 0.1.0 | `IIOT-PRD` 0.9.2 | 新套件 |
|---|---|---|---|
| 触发 | 1 个 | 1 个 | 4 个（01/02/03/suite） |
| 步骤 | 6 步（M1~M6） | 7 步（0~7）+ 六层验收 | 8 步（S1~S8）+ 03 内部 5 步（P1~P5） |
| 判据 | A 系 46 条（1 个脚本） | G 24 + L1 6 + L2 92 + P 11 + C 19 + R 层 | A 系 46 条（按 `--stage` 过滤）+ L1/L2/P/C/R（`--stage core\|render\|full`），**G 系退役** |
| 状态文件 | `_gate.json`（无阶段概念） | `_gate.json`（无 hash） | `_state.json` 2.0（三段 + 产物 hash + 交接记录） |
| 契约 | 明文禁止出现 `proto.json`（`A-63`） | 一个 `proto.json` 装语义 + 渲染 | 一个 `proto.json`，`core` 区归 02、`render` 区归 03，`A-63` 词表按 stage 换 |
| 脚本位置 | 各 skill 自带 | 各 skill 自带 | 全部进 `shared/bin/`，一份 |
| 容器 | — | 5.9MB 自带 | `shared/assets/container/`，一份 |
| 样例 | `examples/qms-incoming`（六份） | `examples/shaping-qms`（七份）+ 4 个 proto | 只用 `shared/examples/qms-incoming`（六份 + `_state.json`）+ 4 个 proto；`shaping-qms` 归档 |
