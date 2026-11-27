# examples 索引

这个目录里混着两类东西，**读者不同**：

| 你是谁 | 看哪些 | 别碰哪些 |
|---|---|---|
| **只是用这套 skill**（写需求、画原型） | `qms-incoming/` 的 `M1`~`M6` + `PRD.md` + `example-03-incoming.proto.json` —— 照着它判断"我这份该写到什么程度" | 其余全部 |
| **在改这套东西**（判据、容器、脚本） | 下面第一、二、三节全部 | —— |

给用户的那几份**是样本不是模板**：它示范的是"一份合格的 M1 长什么样""PRD 十节各写多长"，不是让你往里面填内容。照结构写，内容用自己的。

下面按"改这套东西的人"的视角说明每个文件的依赖关系。

## 一、被脚本直接点名（删了文档里的命令就跑不通）

| 文件 | 谁在用 | 用途 |
|---|---|---|
| `example-01-qms-incoming.proto.json` | `check_parity.py`、`build.py`、`03-prototype/references/06-container.md` | 命令示例里的默认契约；`build.py` 的重建示范 |
| `example-02-accident.proto.json` | `check_interact.py`、`06-container.md` | 真点一遍的示范契约（4 页 / 12 命令 / 7 状态） |
| `dist-accident.html` | `check_interact.py`、`06-container.md` | 与上面配套的容器 |
| `qms-incoming/` | 回归基准 | 见下 |

## 二、回归基准：`qms-incoming/`

**这是整套东西唯一的端到端正向样例**，所有判据的"全绿"靠它证明：

```bash
python3 shared/bin/check_analysis.py examples/qms-incoming/ --stage 1   # 应 exit 0
python3 shared/bin/check_analysis.py examples/qms-incoming/ --stage 2   # 应 exit 0
```

没有它，判据只能跑反例，**无法证明"全绿"是可能的状态**——那就成了只会报红的机器。改动任何判据后，先跑这两条。

| 文件 | 是什么 |
|---|---|
| `M1`~`M6` | 六步产物，示范"每一步该写多长、写到什么程度" |
| `PRD.md` | 十节正文的正向样例（含权限矩阵 / 状态机 / 字段字典） |
| `example-03-incoming.proto.json` | 02 出口的契约（语义半边已签收，渲染半边为空） |
| `_draft/M3-candidates.md` | 候选场景的中间产物，示范"先落草稿再裁决"这一步留痕 |
| `_gate.json` + `_state.json` | 旧格式与新格式并存，用于验证自动升级 |

## 三、容器改动的对照基准（**不能重建，重建就失效**）

`dist-accident.html`、`dist-role-empty.html` 的价值不是"能打开看"，是**"改容器之前长什么样"的物证**。

改 `shared/assets/container/` 之后重建，得到的是"改之后"的产物——拿它跟自己比，永远看不出改坏了什么。**要看有没有改坏，只能跟这两个旧文件比。**

所以它们不能删，也不该随手重建覆盖。

## 四、只在设计稿里被提到

`example-00-minimal.proto.json`（最小合法契约）、`example-03-role-empty.proto.json`（角色空态）、`PRD-accident.md`（PRD 章节参照）——只在 `_design/` 里被引用，属"形态边界样本"：写契约卡住时，对照最小形态判断"哪些字段其实可以省"。

## 五、什么时候该动它们

| 场景 | 动作 |
|---|---|
| 改了判据 | **必须**先跑 `qms-incoming` 两段，全绿才算没改坏 |
| 改了容器或样式 | 重建到 `dist/`（别覆盖这里的旧文件），与旧文件并排比 |
| 新增一种契约形态 | 加 `example-0X-*.proto.json`，并在本表登记谁在用 |
| 想清理仓库体积 | 先看"三"——那两个 HTML 是基准，删了就没法自证 |

总体积 1.2M，其中 73% 是三个可重建的 HTML + SVG。**但它们的价值就在"不是重建出来的"，体积可以忍。**
