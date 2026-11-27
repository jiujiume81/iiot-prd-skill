# 技术勘察：IIOT-PRD 三段式拆分的可行性

> 勘察人：老刘　日期：2026-11-16　范围：只读。本轮未修改 `IIOT-PRD/`（v0.9.2）与 `mfg-req-analysis/`（v0.1.0）任何文件；所有实验在 `/tmp` 下用软链复现。
> 本文每条结论都带实测命令与真实输出。凡我拿不准的，一律写成「不建议」，不写「视情况」。

---

## 0 一页结论

| # | 勘察项 | 结论 | 一句话理由 |
|---|---|---|---|
| 1 | 脚本依赖图 | **可拆，但公共库必须留在 `shared/`** | `field_sites.py` 被 5 个脚本共用；`render_common/mdast` 只服务 `build_prd_html`；跨段断点集中在 3 个脚本 |
| 2 | `check_analysis.py --stage` | **改一个脚本加参数**，不要复制两份 | 实测：只交 M1~M3 时 46 条判据里只有 **4 条 A-00 假红**，其余全绿；改动约 45 行 + A-63 换一张表，0 条判据重写 |
| 3 | 5.9MB 资产 | **共享一份物理 `shared/`，所有 SKILL.md 用绝对路径** | 5.2MB 是 mermaid，只有 03 用；软链路径下 `abspath(__file__)` 不解析软链，相对路径**实测必挂** |
| 4 | proto 作为 02→03 唯一接口 | **接口不干净：proto 里有整个组件树，03 必须回写 proto** | 删掉 `componentTree` 实测 **73 条 ERROR**；`check_contract` 有 7 条判据必须有渲染位才能过 |
| 5 | 端到端回归样例 | **用 `qms-incoming`（轻）+ 事故报告（重），但 02 的出口要新造一份 proto** | 现成 proto 与分析产物不是同一次产出，02 的「落契约」环节无样例可对 |
| 6 | 迁移安全 | **先 commit 再 `cp -a`；不要 `git clone`** | IIOT-PRD 有 **4 个未提交改动**（`G-24` 修复），clone 会退回 HEAD，直接假红 |

**总判断：三段可以拆，但 01|02 那条线要付的代价比看上去大（两套规则书打架），02|03 那条线要付的代价被低估了（proto 不是只读接口）。见第 7 节。**

---

## 1 脚本依赖图

### 1.1 谁 import 谁

| 脚本 | import 的本仓库模块 | 角色 |
|---|---|---|
| `check_analysis.py`（mfg，1307 行） | 无 | 独立单体 |
| `check_gate.py` | 无 | 独立单体（但验的是另一套产物格式） |
| `check_contract.py`（1288 行） | `field_sites` | 契约全场校验 |
| `check_interact.py`（1557 行） | `field_sites` | 无头浏览器实测 |
| `check_parity.py`（541 行） | `build_prd`、`field_sites` | 契约/容器/PRD 三处一致 |
| `build_prd.py`（512 行） | `field_sites`、`render_figs`、`build_prd_html`（`main()` 内懒加载） | 生成 PRD md + html |
| `build_prd_html.py`（220 行） | `mdast`、`render_common` | md → 单文件 html |
| `render_figs.py`（288 行） | 无 | mermaid → SVG（需 Chrome） |
| `render_common.py`（93 行） | 无 | 图片内联/转码（公共库） |
| `mdast.py`（165 行） | 无 | md 解析（公共库，可独立 CLI） |
| `field_sites.py`（126 行） | 无 | **渲染位抽取，5 个脚本共用** |
| `migrate_fields.py`（184 行） | `field_sites` | 老契约迁移工具 |
| `assets/container/src/build.py` | 无 | 容器打包（不在 `scripts/`，但属脚本层） |

`field_sites.py` 是唯一真正的公共库：`check_contract` / `check_interact` / `check_parity` / `build_prd` / `migrate_fields` 全依赖它。它一旦分叉，契约与实测会用两套「渲染位」定义，**必然漂**。

`mdast.py` 只有 `build_prd_html.py` 用，跟着 03 走即可，不需要进 `shared` 顶层。

### 1.2 逐脚本读写与断点

| 脚本 | 归属段 | 依赖脚本 | 读 | 写 | 拆走后的断点 |
|---|---|---|---|---|---|
| `check_analysis.py` | 01 + 02（**必须同一份**） | — | 目录下 `M1~M6` 全部、`_gate.json`、`--init` 时读 `../assets/templates/`（`TEMPLATES`，L31）；维度取值表**硬编码在 `DIMS`**（L106），不读 references | `--init` 时写 6 份模板 + `_gate.json` | **硬编码「六份齐全」**（`A-00`）、`A-61` 跨六份比 mtime、`A-32` 要读 M3 才有 P0 编号；`TEMPLATES = dirname(HERE)/assets/templates` → 也要求 `scripts/` 与 `assets/` 同父 → 见 §2 |
| `check_gate.py` | **03 不需要，01/02 也不该用** | — | `01-positioning.md`…`07-review.md`、`_gate.json`（另一套 schema）、可选 proto | `_gate.json`、7 份模板 | 与 mfg 的命名/schema **双份冲突**；`G-10`（proto 比 A3 早写）/`G-23`/`G-24` 三条**无接替者**，直接消失 |
| `check_contract.py` | 02（半场）+ 03（全场） | `field_sites` | proto、`schemas/catalog.json` | — | 7 条判据要求渲染位存在，02 无组件树时**恒红**（实测 68~73 条 ERROR） |
| `check_parity.py` | 03 | `build_prd`、`field_sites` | proto、容器 html、可选 `--prd` md、`figs/*.svg` | 临时 DOM/MD | 默认 html 路径由 `ROOT` 推出 → 目录深度变了就找不到；需 Chrome |
| `check_interact.py` | 03 | `field_sites` | proto、html、Chrome | `/tmp/iiot-interact.html` | 无跨段依赖（最干净） |
| `build_prd.py` | 03 | `field_sites`、`render_figs`、`build_prd_html` | proto、`--shaping` 目录（**只读文件名**） | md、html、figs | `--shaping` 只影响「附录 A 澄清原文」的一串文件名 → 弱依赖，可以不传 |
| `build_prd_html.py` | 03 | `mdast`、`render_common` | md、figs/*.svg | html | 无 |
| `render_figs.py` | 03 | — | `*.mmd`、`ROOT/assets/vendor/mermaid.min.js`、Chrome | svg + `.cache/` | `VENDOR` 由 `__file__` 上溯两级 → 必须与 scripts 同父 |
| `render_common.py` | 03 | — | 图片 | jpg/png | 无 |
| `mdast.py` | 03 | — | md | — | 无 |
| `field_sites.py` | **02 + 03（公共库）** | — | 由调用方传入 proto 对象 | — | 分叉即漂，必须进 `shared/scripts/` |
| `migrate_fields.py` | 03（工具） | `field_sites` | proto | proto / 报告 | 无 |
| `container/src/build.py` | 03 | — | proto + 同目录 `styles.css`/`app.js`/`components.js`/`runtime.js`/`vue.global.prod.js` | html | `--proto` 相对**脚本目录**解析（不是 cwd）；经软链调用找不到 `styles.css`（实测见 §3） |

### 1.3 断点最多的三个脚本

| 排序 | 脚本 | 断点数 | 具体断点 |
|---|---|---|---|
| 1 | `check_contract.py` | 4 | ① 02 无组件树时 7 条判据恒红；② `CATALOG` 由 `ROOT` 推出；③ `field_sites` 公共库位置；④ 与 03 的「全场校验」需要两种模式 |
| 2 | `check_analysis.py` | 3 | ① `A-00` 六份齐全硬编码；② `A-61` 跨六份 mtime；③ `A-32` 读 M3 拿 P0 编号（02 必须能读 01 的产物） |
| 3 | `check_gate.py` | 3 | ① 整套作废（命名 + schema 全不同）；② `G-10` 反补签判据无接替者；③ `G-23/G-24` 契约侧判据无接替者 |

---

## 2 `check_analysis.py` 按 `--stage` 过滤

### 2.1 现状：一个 `main()` 跑全套

`check(d)` 里是**一条直线**：先 `load_gate`，再逐 `STEPS` 查文件与小节，再依次 `check_m1..m6`，最后 `check_common`。没有阶段概念，`STEPS` 是六条硬编码。

### 2.2 实测：只交 M1~M3 会发生什么

```bash
cp -a mfg-req-analysis/examples/qms-incoming /tmp/s1
rm -f /tmp/s1/M4-flows.md /tmp/s1/M5-exceptions.md /tmp/s1/M6-review.md
python3 mfg-req-analysis/scripts/check_analysis.py /tmp/s1
```

第一次（`_gate.json` 里 4~6 步仍是 `done`）：

```
[ERROR] A-60   第 4 步标为 done，但 M4-flows.md 不存在（虚报进度）
[ERROR] A-60   第 5 步标为 done，但 M5-exceptions.md 不存在（虚报进度）
[ERROR] A-60   第 6 步标为 done，但 M6-review.md 不存在（虚报进度）
[ERROR] A-00   六份产物不齐：已有 3 份（M1-problem.md、M2-roles.md、M3-scenarios.md）
结果：ERROR=7  WARN=0  拦截
```

把 4~6 步改成 `pending` 再跑：

```
[ERROR] A-00   第 4 步 业务流程 缺 M4-flows.md
[ERROR] A-00   第 5 步 异常与边界 缺 M5-exceptions.md
[ERROR] A-00   第 6 步 对抗评审 缺 M6-review.md
[ERROR] A-00   六份产物不齐：已有 3 份（M1-problem.md、M2-roles.md、M3-scenarios.md）
结果：ERROR=4  WARN=0  拦截
```

**这 4 条全是「六份齐全」这一个前提造出来的假红**，46 条判据里没有一条真的不过。这决定了改法：不是改判据，是改「本阶段需要哪几份」。

### 2.3 最小改法

| 改动点 | 位置 | 行数 | 内容 |
|---|---|---|---|
| ① `STEPS` 加 `stage` 字段 | `STEPS` 定义处（L38-53） | 6 | 每条加 `"stage": 1` 或 `2`，1~3 步为 1，4~6 步为 2 |
| ② 缺文件循环按阶段过滤 | `check()` 里 `for st in STEPS`（约 L1155） | +3 | `if stage and st["stage"] != stage: continue` |
| ③ 齐全检查改成本阶段份数 | `if len(existing) < 6`（约 L1180） | 3 | 分母换成 `len([s for s in STEPS if s["stage"] == stage])` |
| ④ `A-60b` / `A-61` 只比本阶段 | `check_common` 两处循环 | +4 | 同一过滤；`A-61` 只在同阶段内比 mtime |
| ⑤ `--stage` 参数 | `main()` | +8 | 解析 `--stage 1\|2\|all`，默认 `all`（**向后兼容，旧命令一行都不用改**） |
| ⑥ **`A-63` 换越界表** | `OUT_OF_SCOPE`（L146）+ `check_common`（L1052） | +5 | stage 2 换成 `["componentTree","pages[]"]`：`proto.json`/`capabilities[]` 在 02 里是**合法产物**，沿用现表 02 必红 |

合计约 **45 行 + 换一张 4 项的表，6 处，0 条判据重写**。

> ⑥ 不是「过滤」，是**改规则**：mfg v0.1.0 的 `A-63` 原意是「分析 skill 不许碰原型层」，02 落契约后这句话不成立了。这张表换不换，得幻神拍板——我不能自己发挥。

### 2.4 46 条的 stage 归属（huanshen 实抓，我已复核编号与总数对齐）

> 抓法：`re.findall(r'"A-[0-9]{2}[b-z]?"')` 去重 = 46，与 SKILL.md 声称一致。`A-1x` 是小节族（按文件查必需二级标题），不计入 46，但实现上也要按阶段过滤。

| 归属 | 条数 | 编号 | 说明 |
|---|---|---|---|
| stage 1 | **24** | `A-00`、`A-01~06`、`A-10~14`、`A-20~26`（含 `A-25`）、`A-24b`、`A-25b/c/d/e` | M1/M2/M3 + M3 五重闸门 |
| stage 2 | **16** | `A-30~34`、`A-40~44`、`A-50`、`A-50b`、`A-51~54` | M4/M5/M6 |
| **跨阶段（两段都要跑）** | **6** | `A-60`、`A-60b`、`A-61`、`A-62`、`A-63`、`A-64` | 进度/分步/含糊词/越界/空话，按「本阶段已有文件」跑 |
| 不计入 | — | `A-1x` | 小节族，按文件查 |

**实现禁令：不许按「编号数组切片」实现 `--stage`。** 两段都必须跑那 6 条跨阶段判据（`A-62/63/64` 按本阶段已有文件遍历），否则它们掉进缝里——stage 1 绿、stage 2 也绿，全量一跑才红。

### 2.5 跨阶段判据清单（不能一刀切）

| 判据 | 性质 | 处理 |
|---|---|---|
| `A-00` 六份齐全 | 阶段前提 | 按阶段改分母（②③） |
| `A-25` 第⑤重（M3 未确认但 M4 已存在） | 01 判据读 02 文件 | **留在 stage 1**。M4 不存在时恒绿，02 写完后回跑一次就能抓到「先写第 4 步再补签」 |
| `A-32`（P0 场景必须上流程） | 02 判据读 01 产物 | **留在 stage 2**，02 必须能只读 M3。M3 是输入不是产物，允许读 |
| `A-25d`（openQuestions 与 M3 待确认清单逐字一致） | 02 读 M3 | 留在 `--stage all`；M3 存在才跑，缺就跳过 |
| `A-60` 虚报进度 | 按步查，天然可分 | 过滤即可 |
| `A-61` 分步痕迹 | 需 ≥2 份同阶段文件 | 分阶段比：01 内比 M1..M3，02 内比 M4..M6。**跨段先后（M3 vs M4）由 `A-25` 第⑤重兜住**，不会两边都不跑 |
| `A-60b` 行数登记偏差 | 按步查 | 过滤即可 |
| `A-62/63/64` 含糊词 / 越界 / 空话 | 按文件查 | 两段都跑（见 2.4 禁令）。`A-63` 在 stage 2 要换表（⑥） |

**「两边都不跑」的兜底方案**：`--stage 1` / `--stage 2` 用于日常推进，**02 交付前必须再跑一次 `--stage all`**（默认值），把所有跨阶段判据重新过一遍。这样任何一个判据都有唯一的「最终责任人」，不是靠人去记得跑哪个模式。

### 2.6 结论

**改一个脚本加参数，不复制两份。**

- 复制两份：1307 行 ×2，46 条判据 ×2，改一条判据要改两处，`qms-incoming` 样例也要维护两套通过基线。**漂是必然的，不是风险。**
- 加参数：一份代码，一个基线，`--stage all` 就是今天的完整语义，老命令零改动。

---

## 3 5.9MB 资产怎么共享

### 3.1 体积真相

| 目录 | 体积 | 谁用 |
|---|---|---|
| `assets/vendor/mermaid.min.js` | **5.2 MB** | 只有 `render_figs.py`（03 出图时） |
| `assets/container/` | 720 KB | 03（`build.py` + 5 个源文件 + `dist/index.html`） |
| `schemas/` | 68 KB | `check_contract.py`（02 半场 + 03 全场） |
| `scripts/` | 340 KB | 02 + 03 |
| `mfg-req-analysis/scripts/check_analysis.py` | 64 KB | 01 + 02 |
| `mfg-req-analysis/{references,templates}` | 108 KB | 01 + 02 |

**01 和 02 根本不需要那 5.9MB**：01 只要 `check_analysis.py` + templates + references；02 再加 `check_contract.py`/`field_sites.py`/`catalog.json`（92 KB）。需要容器的只有 03。

### 3.2 路径解析的硬约束（源码级）

| 脚本 | 路径来源 | 实际含义 |
|---|---|---|
| `check_contract.py:20` | `ROOT = dirname(dirname(abspath(__file__)))`，`CATALOG = ROOT/schemas/catalog.json` | 要求 `scripts/` 与 `schemas/` **同父** |
| `render_figs.py:27` | `VENDOR = ROOT/assets/vendor/mermaid.min.js` | 要求 `scripts/` 与 `assets/` **同父** |
| `check_parity.py:509` | 默认 html = `ROOT/assets/container/dist/index.html` | 同上 |
| `build_prd.py:25` | `ROOT`（读 proto 相对路径与 `schemas`） | 同上 |
| `container/src/build.py:17` | `HERE = dirname(abspath(__file__))`，`--proto` 非绝对时 `join(HERE, proto)` | proto **相对脚本目录**，不是 cwd；`--out` 相对 cwd |

结论：**`scripts/`、`assets/`、`schemas/` 必须三件同父**。所以「共享」只能是共享一个 `shared/` 目录，不能只软链 `assets`。

补一条容易漏的：`check_analysis.py` 也受同一个约束——`TEMPLATES = os.path.join(os.path.dirname(HERE), "assets", "templates")`（L31）。所以它进 `shared/scripts/` 之后，`--init` 会去 `shared/assets/templates/` 找模板。这**不冲突**：`shared/assets/` 下同时放 `templates/`（01/02）、`container/`、`vendor/`（03）即可，三个子目录名不重。

再补一条更硬的：**`build.py` 不能进统一脚本目录**。它 `HERE = 自己目录`、同级读 `styles.css`/`app.js`/`components.js`/`runtime.js`/`vue.global.prod.js`（`build.py:17` + `read()` 全部 `join(HERE, p)`）。也就是说「所有 py 放一处（`bin/`）」这个方案**对 `build.py` 不成立**——它必须留在 `assets/container/src/`。真正需要统一的只是 `scripts/` 那 11 个；`build.py` 天然跟着容器走，容器只有一份，所以不存在复制两份的问题。

### 3.3 软链实测：三条全挂

搭一个和提案一致的布局（`shared/` 下三件软链到 IIOT-PRD，`03/` 是物理目录，`/tmp/fakeskills/iiot-t03` 模拟 `~/.workbuddy/skills/` 里的软链）：

```bash
# T1 物理绝对路径 → 通过
python3 /tmp/suite/shared/scripts/check_contract.py .../example-00-minimal.proto.json
# 结果：ERROR=0  WARN=0  PASS

# T2 经软链 skill 用 ../shared → 挂
python3 /tmp/fakeskills/iiot-t03/../shared/scripts/check_contract.py ...
# FileNotFoundError: '/tmp/fakeskills/shared/schemas/catalog.json'

# T3 在 03 内放 scripts 软链，经 skill 路径调用 → 同样挂
python3 /tmp/fakeskills/iiot-t03/scripts/check_contract.py ...
# FileNotFoundError: '/tmp/fakeskills/iiot-t03/schemas/catalog.json'

# T5 build.py 经软链路径 → 挂
python3 /tmp/fakeskills/iiot-t03/scripts/../assets/container/src/build.py ...
# FileNotFoundError: '/tmp/fakeskills/iiot-t03/assets/container/src/styles.css'

# T6 build.py 物理绝对路径 → 通过
python3 /tmp/suite/shared/assets/container/src/build.py ...
# size : 352 KB (vue 143KB / css 48KB / data 12KB)
```

**根因**：`os.path.abspath(__file__)` **不解析软链**（只有 `realpath` 会）。所以脚本一旦被「带软链的路径」调用，它推出的 `ROOT` 是软链所在的假目录。11 个脚本里有 5 个用这个模式，改脚本等于改封版资产，**不动**。

### 3.4 结论

**共享一份物理 `shared/`，四份 SKILL.md 一律写绝对路径。**

```
iiot-prd-suite/
├─ SKILL.md                 路由（见 §7.1，我不建议它是第 4 个软链）
├─ 01-业务分析/SKILL.md
├─ 02-需求分析与契约/SKILL.md
├─ 03-原型设计/SKILL.md
└─ shared/                  ← 唯一物理副本，5.9MB 只此一份
   ├─ scripts/              11 个 py + check_analysis.py（加 --stage 后）
   ├─ assets/
   │  ├─ templates/         M1~M6 骨架（01/02 的 --init 用）
   │  ├─ container/         720KB（03）
   │  └─ vendor/            5.2MB mermaid（03 出图时）
   ├─ schemas/
   └─ samples/              qms-incoming + 4 份 proto（回归用，见 §5）
```

- 每份 SKILL.md 第二行写死：`SUITE=<套件根>`，之后所有命令用 `$SUITE/...`。**不用相对路径，不用 `../`，不依赖软链怎么解。**
- 不要给 01/02 复制 `assets/`：它们用不到，白占 700KB 还会让人误以为 01 能出原型。
- 不要为了「看起来自包含」复制 `vendor/mermaid.min.js`：5.2MB×3，且它是唯一会随版本升级的二进制，三份必然不同步。

---

## 4 契约（proto.json）作为 02→03 唯一接口

### 4.1 proto 里到底装了什么

```
example-02-accident.proto.json（125 KB）
├─ meta / modules / capabilities(12) / stateMachines(2) / dataModel
├─ requirements(4) / fieldCatalog(51) / dataSources / guards / decisions
└─ pages[4]
   ├─ id / moduleId / target / route / title / layout / entity / states
   ├─ prd{goal, …}          ← ★ PRD 十种小节，属 03 的活
   ├─ componentTree{…}      ← ★ 整个页面结构，属 03 的活
   └─ interactions{…}       ← ★ 属 03 的活
```

**proto 不是「需求契约」，它是「需求 + 原型」的合订本。** 拆 02/03 时这是最容易被忽略的一条。

### 4.2 实测：02 交得出「只要需求」的 proto 吗

```bash
# 删掉每页的 componentTree / interactions / prd
python3 scripts/check_contract.py /tmp/no-tree.proto.json
# 结果：ERROR=68  FAIL

# 只删 componentTree（留 prd）
# 结果：ERROR=73  FAIL

# 只删 prd（留组件树）
# 结果：ERROR=8   FAIL   → L1-05 ×4（页必填字段）、L2-09 ×4（PRD 缺 goal）
```

68 条的构成：

| 判据 | 条数 | 管什么 | 属谁的活 |
|---|---|---|---|
| `L2-97` | 23 | 主档字段没有任何渲染位引用 | 03（画页面） |
| `L2-91` | 12 | 命令被谁认领（按钮挂哪） | 03 |
| `L2-55` | 12 | 命令未声明 `ui.kind` / `ui.entry` | 03 |
| `L1-05` | 12 | 页面缺必填字段（含 `prd`） | 03 |
| `L2-14` | 4 | 组件 type 不在白名单 | 03 |
| `L2-09` | 4 | 页面 PRD 缺 goal 小节 | 03 |
| `L2-81` | 1 | 状态条无内容 | 03 |

**7 条判据、68 个错误，全部落在 03 的工种上。** 这就是「只读 proto」这句话不成立的地方。

### 4.3 那 02 怎么自证契约成立

实测：把上面 **7 条**判据屏蔽掉，同一份「无组件树」的 proto 立刻全绿：

```bash
python3 - <<'EOF'
import sys; sys.path.insert(0,'scripts')
import check_contract as cc
skip={'L1-05','L2-09','L2-14','L2-55','L2-81','L2-91','L2-97'}
o=cc.add; cc.add=lambda l,c,m: None if c in skip else o(l,c,m)
sys.argv=['x','/tmp/no-tree.proto.json']; cc.main()
EOF
# 结果：ERROR=0  WARN=0  PASS
```

也就是说：`check_contract.py --half req` 只需一个**跳过表 + 参数解析**（约 30 行），不需要重写任何判据。

> **实施修正（2026-11-16，落地时实测）**：用「pages 只给骨架」的 02 出口样例跑，7 条不够，还要加 3 条：`L2-07`（页面四态）、`L2-48`（PDA 在线策略）、`L2-49`（PDA 必须 BigAction）。其中 `L2-49` 直接查 `componentTree`，02 结构上不可能满足。**最终跳过集 = 10 条**，见 `shared/bin/check_contract.py` 的 `SKIP_IN_REQ`。剩下的 90 多条判据（状态机端点、命令 owner、四眼原则、字段主档、数据源、EARS、切片依赖）**全部照跑**，02 的契约强度不降。

### 4.4 「只有 M4/M5 才能提供」的字段

| 契约字段 | 来源 | 02 能否独立产出 |
|---|---|---|
| `stateMachines[].transitions[]` | M4 状态机表 | 能（M4 就在 02 手里） |
| `capabilities[].from/to/actor/stage` | M4 主流程 + M3 角色 | 能 |
| `guards[]` | M5 异常/降级 | 能 |
| `requirements[].acceptance[kind:"illegal"]` | M5 异常清单 | 能，但**只能靠人写**——`L2-34` 只检查「有没有一条 illegal」，不校验它与状态机是否矛盾 |
| `fieldCatalog[]` | M1/M3 点名的字段 | 能（编号），但**target 表/字段要靠 dataModel** |
| `pages[].componentTree` | 无（M4/M5 都不含页面） | **不能** |
| `pages[].prd` | 无 | **不能** |

`L2-34` 是个薄判据：它只要求「存在非法路径」，不要求非法路径真的与状态机冲突。所以「stateMachine 的非法路径」这条看似必须 M4，实际是**作者自觉**，脚本不卡。这既说明 02 能独立过检，也说明这条判据本身偏弱——记在这里，不属本轮修。

### 4.5 `check_parity` / `check_interact` 要不要读 md

| 脚本 | 参数 | 读 md 吗 |
|---|---|---|
| `check_parity.py` | `proto --html [--prd]` | **不读**。不给 `--prd` 时用 `build_prd.build(..., render=False)` 在内存里生成 md 比对指纹（`C-22/C-23/C-24`） |
| `check_interact.py` | `proto --html --chrome` | **不读**。用例全部从 proto 的 `capabilities[].from/to` 推出 |

实测 `check_parity` + `check_interact` 在只有 proto 与 html 时都能过（见 §5.3）。**这两个脚本是干净的。**

### 4.6 结论

**这个接口不够干净，必须改两处，缺一不可：**

1. **`check_contract.py` 加 `--half req|render`**（约 25 行，7 个编号的跳过表）。不加，02 永远过不了检，只能「不跑校验直接交付」——那是把闸门拆了。
2. **明确 proto 是双向文件，不是只读接口**：02 起草 `requirements/capabilities/stateMachines/dataModel/fieldCatalog/guards/decisions` + `pages` 的骨架（`id/moduleId/target/route/title/layout/entity`）；03 只**追加** `pages[].componentTree/interactions/prd`，**不许改 02 写的业务语义**（这条要写进 03 的 SKILL.md 与自测脚本，否则 03 会为了让页面好看偷偷改 `from/to`）。

**不能放宽的**：03 交付前必须跑不带 `--half` 的全场 `check_contract`。02 的半场绿灯不等于契约成立，只等于「需求这一半没矛盾」。

---

## 5 现有样例能不能做三段端到端验证

### 5.1 候选盘点

| 样例 | 内容 | 三段覆盖 | 结论 |
|---|---|---|---|
| `mfg-req-analysis/examples/qms-incoming/` | M1~M6 六份 + `_gate.json`（19 场景/8 流程/14 异常/40 问），`ERROR=0` | 01 完整、02 只有文档没有 proto | **当 01 的基线** |
| `IIOT-PRD/examples/example-01-qms-incoming.proto.json` | 3 页 / 4 命令 / 2 需求，`PASS` | 03 完整 | **当 03 的轻样例**（同一产品，能接上） |
| `IIOT-PRD/examples/shaping-qms/` | `01-positioning`…`07-review` 七份 + `_gate.json`（旧格式），`check_gate` 放行 | 01（旧格式） | 只能当**旧产物兼容**测试 |
| `IIOT-PRD/examples/example-02-accident.proto.json` | 4 页 / 12 命令 / 2 状态机 / 51 字段，`PASS` | 03 完整 | **当 03 的重样例**（状态机四眼原则、推进动作拆分都在这里） |
| `example-00-minimal` / `example-03-role-empty` | 边界样例（最小、角色空） | 03 边界 | 保留，测「降级不崩」 |
| `QMS-事故报告-正式交付/` | 真实交付：proto + shaping(旧格式) + PRD.md/html + 原型 html + **脚本快照**（`build_prd.py`/`build_proto.py`） | 03 重样例 | **不要当回归样例**，当「历史交付不可回归破坏」的保护对象 |

### 5.2 缺口（必须补）

| 缺口 | 影响 | 补法 |
|---|---|---|
| 没有一份「从 M4/M5 落出来的 proto」 | 02 的出口无样例可对，`--half req` 没有正向基线 | 用 `qms-incoming` 的 M4/M5 新落一份 `qms-incoming.proto.json`（3 页，复用 `example-01` 的页面骨架，**业务字段按 M4/M5 重写**），让 02 跑到 `ERROR=0` |
| `qms-incoming` 与 `example-01` 不是同一次产出 | 场景编号/流程步对不上，`A-32`（P0 上流程）无法交叉验证 | 同上：落 proto 时用 M3 的真实 S 编号，`A-32` 才有意义 |
| 旧格式（`01..07`）只有一份 | 03 的「读旧交付」兼容性没有断言 | 用 `QMS-事故报告-正式交付/shaping/` 做只读回归（只测 `--shaping` 列文件名不报错） |

### 5.3 最小可验证命令序列（三段各一条）

```bash
SUITE=<套件根>
S=$SUITE/shared/samples
```

**01（业务分析，出口 M1/M2/M3 + `_gate.json`）**

```bash
python3 $SUITE/shared/scripts/check_analysis.py $S/qms-incoming --stage 1
# 期望：ERROR=0  WARN=0  放行
```

**02（需求分析 + 落契约，出口 M4/M5/M6 + `qms-incoming.proto.json`）**

```bash
python3 $SUITE/shared/scripts/check_analysis.py $S/qms-incoming --stage all \
 && python3 $SUITE/shared/scripts/check_contract.py --half req $S/qms-incoming.proto.json
# 期望：两条都 ERROR=0
```

**03（原型，只读 proto）**

```bash
python3 $SUITE/shared/assets/container/src/build.py \
    --proto $S/qms-incoming.proto.json --out /tmp/qms.html \
 && python3 $SUITE/shared/scripts/check_contract.py $S/qms-incoming.proto.json \
 && python3 $SUITE/shared/scripts/check_parity.py $S/qms-incoming.proto.json --html /tmp/qms.html \
 && python3 $SUITE/shared/scripts/check_interact.py \
    --proto $S/qms-incoming.proto.json --html /tmp/qms.html
# 期望：契约 PASS / 一致 / 实测 PASS
```

**今天就能跑通的三条基线（我实测过）**：

```
check_analysis  qms-incoming                    → ERROR=0  WARN=0  放行（判据 46 条）
check_gate      shaping-qms + example-01        → ERROR=0  WARN=0  放行
check_contract  example-00/01/02/03             → 四份全 PASS
check_parity    example-01 + /tmp/e01.html      → ERROR=0  WARN=0  一致
check_interact  example-00 + /tmp/t3.html       → 5 项，通过 5  PASS
```

### 5.4 两个环境坑（写进 README，别让人踩）

| 坑 | 现象 | 处理 |
|---|---|---|
| Chrome 冷启动超 40s | `check_parity` 第一次跑：`subprocess.TimeoutExpired ... --virtual-time-budget=3500 ... timed out after 40 seconds`；重跑同一条命令 `ERROR=0` | 回归脚本要**允许重试一次**，或先 `open -a "Google Chrome" --args --headless` 预热。判红前先看是不是超时 |
| `build.py --proto` 相对脚本目录 | 在仓库根跑 `build.py --proto examples/xxx` 报 `.../src/examples/xxx: No such file` | 一律用**绝对路径**；`SKILL.md`/`README.md` 里现有的 `--proto out.proto.json` 写法在根目录下是错的（`references/06-container.md` 的 `../../../examples/...` 才对） |

---

## 6 迁移安全

### 6.1 先看一个坏消息：IIOT-PRD 工作区不干净

```bash
git -C IIOT-PRD status --short
 M assets/container/src/app.js
 M assets/container/src/components.js
 M scripts/check_gate.py
 M scripts/check_interact.py
# 4 files changed, 29 insertions(+), 12 deletions(-)
```

这 4 个改动是**真修复**，不是垃圾。例如 `check_gate.py` 的 `G-24`：

```diff
-        if not (proto.get("fieldRegistry") or []):
+        if not (proto.get("fieldCatalog") or proto.get("fieldRegistry") or []):
```

`fieldRegistry` 自 v2 起已被 `fieldCatalog` 取代。**`git clone` 拿到的是 HEAD（没有这个修复），对任何新契约都会误报 `G-24`「字段没落位」。** 所以「v0.9.2 封版」这句话目前只对 HEAD 成立，工作区是 v0.9.2+。

### 6.2 `cp -a` 还是 `git clone`

| 方式 | 保住 .git | 保住 4 个未提交改动 | 结论 |
|---|---|---|---|
| `git clone` | ✅ | ❌ | **不可用**（回退到有假红的版本） |
| `git clone` + `git apply patch` | ✅ | 需手工 | 次优：多一步，且 patch 会随文件漂 |
| `cp -a` | ✅（连 `.git` 一起） | ✅ | **推荐**，但会带进 `__pycache__`（`.gitignore` 已忽略，可后删） |
| `git archive HEAD \| tar -x` | ❌ | ❌ | 只适合「确定要纯 HEAD」的场合 |

**推荐顺序**：

```bash
# ① 先让工作区可复现（不改封版资产内容，只记录）
git -C IIOT-PRD diff > /tmp/iiot-prd-wip.patch          # 备份改动本身
git -C IIOT-PRD add -A && git -C IIOT-PRD commit -m "chore: 存档 v0.9.2 工作区（拆分为三段前的快照）"
# ② 再复制（连 .git 一起，历史保得住）
cp -a IIOT-PRD <套件根>/shared/upstream-iiot
```

注：`commit` 会改 `IIOT-PRD/.git`（历史变了），但**不改技能文件内容**。若「一个字节都不许改」被理解为连提交也不许，则退化为只 `cp -a` + 保留 `/tmp/iiot-prd-wip.patch`，并明确接受「新目录里 .git 是脏的」。

### 6.3 旧的两个 skill 目录怎么处置

| 对象 | 处置 | 理由 |
|---|---|---|
| `原型PRD/IIOT-PRD/`（物理） | **原地不动** | 封版资产；03 的 `shared/` 需要从它复制，保留原始可随时对照 |
| `原型PRD/mfg-req-analysis/`（物理） | **原地不动** | v0.1.0 封版；01/02 用 `cp` 出来的副本 + `--stage`，原件留作对照 |
| `~/.workbuddy/skills/IIOT-PRD`（软链） | **移出 skills 目录**：`mv ~/.workbuddy/skills/IIOT-PRD ~/.workbuddy/skills-disabled/` | 软链是安装状态不是资产。不移走，它会和 03 抢「画原型」的触发，模型随机选一个 |
| `~/.workbuddy/skills/mfg-req-analysis`（软链） | 同上移走 | 不移走，01/02 与它三个抢「需求分析」 |
| 删不删？ | **不删，只移** | `mv` 回一行就能恢复；`rm` 恢复不了 |

> 这一步是**用户可见的行为变更**（用户已经习惯说「画个原型」触发 IIOT-PRD），必须由 team-lead 和俞秀福确认后再执行。

### 6.4 迁移前必须备份的清单

| # | 对象 | 为什么不能只靠 git | 备份方式 |
|---|---|---|---|
| 1 | `IIOT-PRD` 4 个未提交改动 | HEAD ≠ 工作区，clone 会丢 | `git diff > wip.patch` **+** `cp -a` |
| 2 | `IIOT-PRD/.git`（13 commits，`origin` = github） | 本地分支/远端状态 | `cp -a`；远端已 push 则另有保险 |
| 3 | `mfg-req-analysis/.git`（11 commits，**无远端**） | 只在本地，唯一副本 | `cp -a`（这条最不能省） |
| 4 | `~/.workbuddy/skills/{IIOT-PRD,mfg-req-analysis}` 软链的 target | 记下原 target 才知道怎么恢复 | `ls -l ~/.workbuddy/skills/ > /tmp/skills-links.txt` |
| 5 | `QMS-事故报告-正式交付/`（含 `build_prd.py`/`build_proto.py` 脚本快照、`figs/`、`shaping/` 旧格式） | 交付物，不在任何 git 里 | `cp -a` 或 tar 到 `/tmp` |
| 6 | `IIOT-PRD/examples/*.proto.json` + `dist-*.html` | `.gitignore` 忽略 `*.proto.json`（`!examples/*` 例外，但产物 html 没保护） | `cp -a` |
| 7 | 用户工程 用户工程（本地路径从略） | 角色定义里点了名：重建过它的 `dist/事故报告管理.html` | 至少备份 `accident.proto.json` + `dist/` |

---

## 7 我建议不要这么拆的地方

这一节是本文的重点。**下面每一条我都给了替代方案，不是反对拆，是反对按现在这个切法拆。**

### 7.1 不建议把 router 做成第 4 个 softlink

**问题**：四个软链挂在 `~/.workbuddy/skills/` 下，靠 description 竞争触发。router 的 description 必然包含「需求分析 / 原型 / PRD」这些词，**它会和 01/02/03 抢同一句话**，而不是「先被调用再分发」。技能触发不是函数调用，没有可靠的「先执行 router」保证。

**替代**：不建 router skill。把「该进哪一段」的判定表写进**三份 SKILL.md 各自的开头 5 行**：

```
进来先看目录里有没有 _gate.json / {产品}.proto.json：
  只有需求原话            → 01
  _gate.json 里 1~3 步 done → 02
  proto.json 存在且 1~6 步 done → 03
```

三段各自都能判断「我是不是该在这里」，比一个抢触发的 router 靠谱。若 lead 坚持要 router，就把它做成**只回答「我该用哪个」的纯路由**，description 里禁止出现「分析」「原型」「PRD」这类工种词，只留「不知道从哪开始 / 下一步做什么 / 这套怎么用」。

### 7.2 不建议把 `check_gate.py` 搬进任何一段

**问题**：它验的是 `01-positioning.md`…`07-review.md` + `A1/A2/A3` schema，与 mfg 的 `M1~M6` + `M1/M3/M6` schema **完全不兼容**（实测：拿 mfg 样例喂它 → `ERROR=11`；拿 IIOT 样例喂 `check_analysis` → `ERROR=9`）。搬进 03 是死代码（03 不读 md），留在 01/02 是第二套规则书。

**它有 3 条独占语义，但只有 1 条真需要移植**（我第一版写「搬 2 条」，复核后改口）：

| 判据 | 管什么 | 现有接替者 | 结论 |
|---|---|---|---|
| `G-01` | 有原型但没有澄清（跳步） | `A-00`「`_gate.json` 不存在：分析未启动」同义 | **可删** |
| `G-10` | proto 的写入时间早于 A3 确认时间 → 事后补签 | **无**。`A-25` 第⑤重只比 M4 vs M3，没有一句比 proto | **必须移植**到 `--stage 2`：新增「`{产品}.proto.json` 的 mtime ≥ M6 确认时间」 |
| `G-23` | proto 里 P0 openQuestion 未 resolved/assumed 不许冻结契约 | `A-24`（L1125）**更严**：只要 M4 存在，任何 open 的 openQuestion 都报 ERROR，不限 P0 | **可删**（`A-24` 已覆盖且更强） |
| `G-24` | `fieldCatalog` 为空 → 需求点名的字段没落位 | `L2-96/97` | **可删** |

净结论：`check_gate.py` **整体退役**，只搬 `G-10` **一条**进 `check_analysis.py --stage 2`（约 12 行）。这一条如果漏了，拆分后的闸门比现在**弱**——这是我最担心的一处。

> 更正记录：我原先写「`G-23` 必须移植」，复核 `check_analysis.py:1125` 后发现 `A-24` 的触发条件更宽（不限 P0、只要 M4 已开写），`G-23` 属被覆盖。少搬一条，少一处漂的机会。

### 7.2b 一个不是「拆不拆」的问题是设计缺口：P1 没有去向判据

`A-30~A-34` 只卡 P0：`A-32` 是「**P0** 场景必须出现在主流程或分支流程」。P1 场景没有任何判据要求它出现在某处，也没有判据要求「P1 可以在本批不做，但要写清后置到哪」。脚本里查不到 P1 去向，这是**新增判据**的活，不是改判据，也不属本轮拆分。

落法（给 02 的实现者）：新增 `A-35`「每个 P1 场景必须落在主流程/分支流程，或在 M6 结论里写明后置批次」，造红方式 = 删掉某个 P1 在 M4 里的引用且不写后置 → 必须红。**不做这条，02 的出口对 P1 是完全放行的**，而用户最容易被 P1 的「以后再说」糊弄。

### 7.3 不建议拆 01|02 那条线（成本 > 收益）

**证据**：

| 维度 | 事实 |
|---|---|
| 共享代码 | 同一个 `check_analysis.py`（1307 行、46 条判据 + `A-1x` 小节族） |
| 共享状态 | 同一个 `_gate.json`（`gateVersion 1.0`、`skill` 字段写死 `mfg-req-analysis`、`steps` 必须 6 条、`confirmations` 必须含 M1/M3/M6） |
| 共享文档 | 同一套 `M1~M6` 命名、同一套 `references/`（76 KB） |
| 边界位置 | M3 硬闸门（`A-25` 五重校验）正好落在切口上 |
| 02 必须读 01 | `A-32`（P0 场景必须上流程）必须读 M3；`A-25d` 必须读 M3 |
| 规则冲突 | 异常类：IIOT 11 类 vs mfg 12 类（多了「工艺与配方」，且「历史兼容/历史数据兼容」等命名不同）；场景门槛：IIOT 只要「频次+兜底」，mfg 要 11 维 82 格 + ≥15 条 |

拆开之后你要付出：

1. 一份脚本服务两个 skill（可以，`--stage` 已解决）；
2. **两套 description 必须互斥**，否则用户说「分析下这个需求」两个都亮；
3. 11 类 vs 12 类必须统一（我建议统一到 12 类，因为 mfg 是后写的、更严）；
4. `_gate.json` 的 `skill` 字段写死 `mfg-req-analysis`，01 和 02 共用一个目录时**不能有两个值** → 02 不能声明自己是另一个 skill；
5. 用户在 01 和 02 之间切换会丢上下文（每个 skill 冷启动都要 `--status` 恢复，多一次读盘与一次解释）。

换来的只有一件事：**用户能单独触发「只做前三步」**。而这件事用 `--stage 1` 一条命令就能做到，不需要拆 skill。

**替代方案（首选）**：01 和 02 合为一个 skill（就叫「需求分析」，v0.2），内部两段由 `--stage` 控制；出口是 `M1~M6 + _gate.json + {产品}.proto.json`。这样：

- 六步一个 skill，一套规则书，一个 `_gate.json`，零冲突；
- 「只做前三步」= `--stage 1`，用户随时可以停；
- M3 硬闸门天然在中间，不需要跨 skill 传状态。

**如果 lead 一定要三段**：把切口从「前三步/后三步」改成「**分析 / 契约**」——01+02 合成「分析」（M1~M6），02 只做「落契约」（M1~M6 → proto）。这样 02 是纯粹的「翻译器」，`check_contract --half req` 就是它的唯一闸门，`_gate.json` 归 01 独有，命名冲突消失。**这个切法的代码改动量比现在这个切法小一半。**

### 7.4 不建议给 02 再造一份「需求契约」格式

**问题**：为了让 02 有独立出口，很容易想到「02 出一份 `req.proto.json`，03 再转成 `proto.json`」。**不要。** 那会变成三份格式（md / req.proto / proto），每次改需求要改两处 JSON，`check_parity` 的「三处一致」会变成「四处一致」，而 `C-24` 的指纹链（proto sha → PRD sha → 容器 meta sha）必须重写。

**替代**：02 直接写 `{产品}.proto.json`，只写需求半边（`pages` 只给骨架）。03 在同一份文件上追加 `componentTree/interactions/prd`。用 `--half req` 卡 02，用不带参数的全场卡 03。一份文件，一条指纹链，不动。

### 7.5 不建议把 03 做成「IIOT-PRD 的软链」

**问题**：`03/SKILL.md` 若只是一个软链指回 `IIOT-PRD/`，那 03 的任何修改都会落到封版资产上（`check_contract` 要加 `--half`，就会改 `IIOT-PRD/scripts/check_contract.py`）——直接违反「一个字节都不许改」。

**替代**：`shared/` 是**物理复制**（`cp -a`），`IIOT-PRD/` 只作为「原始参照 + git 历史源」。改 `--half`/`--stage` 改在 `shared/` 的副本上。代价：两份 `check_contract.py` 共存（`IIOT-PRD` 的冻结、`shared` 的演进），必须在 `IIOT-PRD/README.md` 之外的地方（本轮不能改它）写清「`IIOT-PRD/` 已冻结，改动一律进 `iiot-prd-suite/shared/`」。

### 7.6 一句话总账

| 切法 | 代码改动 | 规则冲突 | 闸门损失 | 我的判断 |
|---|---|---|---|---|
| 三段（01 前三步 / 02 后三步+契约 / 03 原型） | `--stage` 45 + `A-63` 换表 5 + 移植 `G-10` 12 + `--half` 25 ≈ **87 行** | 11 vs 12 类需统一；`_gate.skill` 字段冲突；两套 description 要互斥；`A-63` 越界表要 02 专用 | 无（前提是 `G-10` 移植） | **可做，但 01|02 那条线性价比最低** |
| 两段（分析 M1~M6 / 契约 + 原型） | `--half` 25 + 移植 `G-10` 12 ≈ **37 行** | 无 | 无 | **我更推荐** |
| 不拆（IIOT-PRD 内部加 `--stage`） | 45 行 | 无 | 无 | 最省，但用户仍只有一个「大」skill |

我按 lead 定的三段写完了勘察，也把「三段怎么拆才不塌」的补丁点列清楚了（§2/§3/§4/§7.2）。但**如果只问工程上哪条路最不容易漂：两段 > 三段 > 不拆**。这个判断我不改口。
