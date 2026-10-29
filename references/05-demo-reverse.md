# Demo 逆向：从原型/旧系统里抽出契约

> 场景：业务方给了个 Demo（可能是上一版原型、第三方系统的截图录屏、或者正在用的旧系统源码），要求"照着做一个"。逆向的产出是**现状描述**，不是需求——这一点必须先说清，否则逆向出来的东西会带着旧系统的所有毛病一起进新系统。

## 1 逆向的信任等级

逆向得到的每一条都要标证据等级，规则和 `02-problem.md` 一致：

| 等级 | 含义 | 能用它做什么 |
|---|---|---|
| `measured` | 从源码/接口/数据库直接读到 | 可作为现状事实，可作为新契约的起点 |
| `inferred` | 从界面行为推断 | 必须找人确认，不能直接进 `requirements[]` |
| `stated` | 业务方口述 | 只能作为线索，必须验证 |

**逆向最大的风险是把 `inferred` 当 `measured`。** 看到界面上有个"审核"按钮，推断出"存在审核流程"是合理的；推断出"审核人必须是质量经理"就是编的——后者只能从权限表或代码里的角色判断读到。

## 2 从路由抽模块

### 2.1 抓路由表

按技术栈选一种：

```bash
# vue-router：静态定义
grep -rn "path:\s*['\"]" src/router/ src/**/router*.js

# 后端下发菜单（老系统常见）
curl -s "$BASE/api/menu/tree" -H "Cookie: $C" | python3 -m json.tool > /tmp/menu.json

# 前端打包产物里捞（没源码时）
grep -oE '"/[a-z0-9/_-]{3,40}"' dist/*.js | sort -u | head -200
```

### 2.2 聚合成模块

路由树不能直接当模块清单用，要过四道筛：

| 筛选 | 处理 | 理由 |
|---|---|---|
| 布局路由（`/`、`/layout`、`component: Layout`） | 丢弃 | 它不是页面，是壳 |
| 登录/403/404/500 | 丢弃 | 不属于业务域 |
| 同一 path 前缀 ≥ 3 个路由 | 聚成一个模块 | 1~2 个的别硬聚，容易把不相关的业务绑一起 |
| 只有 `path` 没有 `component`（懒加载外壳） | 下钻到 children | 它只是分组节点 |

```python
# 抽模块的核心逻辑：按 path 第一段聚合，且要求同组路由共享同一个后端资源前缀
from collections import defaultdict
groups = defaultdict(list)
for r in routes:
    seg = r["path"].strip("/").split("/")
    if len(seg) >= 2 and seg[0] not in ("login", "error", "404"):
        groups[seg[0]].append(r)
modules = [{ "id": f"m-{k}", "pages": [to_page_id(r) for r in v] }
           for k, v in groups.items() if len(v) >= 3]
```

### 2.3 路由 → 页面

| 路由特征 | 映射 |
|---|---|
| 列表页（path 以 `list`/`index` 结尾或就是模块根） | `layout: "list"` |
| 详情页（path 含 `:id`） | **不是独立页面**，是列表页的子视图——除非它有自己的权限 |
| `:id/edit` | 同上，通常做成抽屉 |
| 有独立权限码的详情页 | 独立页面 |
| 移动端路由（`/m/`、`/pda/`、`/h5/`） | `target: "pda"`，但要确认是不是真 PDA |

**"`/:id` 全算独立页面"是逆向上最常见的错误**，会凭空多出 30% 的页面数，然后每个页面都要单独设计四态，工作量翻倍而价值为零。

## 3 从分支抽规则

分支是规则的化石。要找的是**条件表达式**，尤其是那些控制"能不能做"的。

### 3.1 四类必抓的分支

| 分支形态 | 代码特征 | 抽出什么 |
|---|---|---|
| 按钮显隐 | `v-if="canApprove"` / `{canApprove && <Btn/>}` | `capabilities[].policy = "hidden"` |
| 按钮禁用 | `:disabled="status !== 'reported'"` | `capabilities[].from = ["reported"]` |
| 提交前校验 | `if (!form.qty) return toast(...)` | `guards[]` 或 `acceptance[illegal]` |
| 字段级条件校验 | `if (type === 'A' && !x) err` | `rule` 里的分情况条款 |

```bash
# 一次把所有"能不能"类分支捞出来
grep -rnE "(v-if|v-show|:disabled|can[A-Z][a-zA-Z]*)" src/views/ | grep -vE "^\s*//" > /tmp/branches.txt
wc -l /tmp/branches.txt
```

### 3.2 分支 → 命令策略

一条 `:disabled="status !== 'reported'"` 能直接翻译成：

```json
{ "id": "cap-approve", "actor": ["u-qa"], "from": ["reported"],
  "policy": "disabled", "reason": "仅「待审核」可审核", "to": "approved", "stage": "verify" }
```

**但 `hidden` 和 `disabled` 的区分要问人。** 代码里写 `v-if` 的，可能在业务上应该是"置灰并说明原因"——隐藏按钮会让用户以为没这个功能，打电话来问。这个判断代码给不了，必须确认。

### 3.3 校验 → 验收用例

```js
if (!form.qty) return toast('请输入数量')
if (form.qty > order.qty) return toast('不能超过到货数量')
```

两行校验，翻译成两条 `illegal` 验收。这类"代码里有、文档里没有"的规则，是逆向最大的收获——它们通常是业务多年踩坑攒出来的，新人不会写进需求文档。

统计一下能看出需求的完整度：

```bash
echo "校验条数: $(grep -cE 'return (toast|message|Message)' /tmp/branches.txt)"
echo "对应非法验收: $(grep -c '"kind": "illegal"' out.proto.json)"
```

后者明显少于前者，就说明逆向漏了规则。

## 4 从状态变化抽状态机

### 4.1 三个抓取点

| 抓取点 | 代码特征 | 得到 |
|---|---|---|
| 状态赋值 | `status = 'sampled'` / `setState({status:'x'})` | 目标状态 |
| store 提交 | `commit('SET_STATUS', x)` / `dispatch('approve')` | 动作名 |
| 接口成功后刷新 | `await api.approve(id); load()` | 状态由后端改，前端只是刷新 |

**第三种最麻烦**：前端代码里完全没有状态值的出现，全靠后端。这种情况必须去抓接口返回的数据，或者直接调一次接口看返回体的 `status` 字段。

```bash
# 抓所有状态字面量
grep -rhoE "status\s*[:=]\s*['\"][a-z_-]{3,20}['\"]" src/ | sort | uniq -c | sort -rn

# 抓动作名（通常是 commit/dispatch 的参数）
grep -rhoE "(commit|dispatch)\(\s*['\"][A-Za-z_]+['\"]" src/ | sort -u
```

### 4.2 合成状态机

得到的状态集合是散点，要按时间顺序连成边。三步：

1. **查初始值**：`initial` 不是"第一个出现的状态"，而是新建记录时的默认值。找 `default:` 分支或数据库列默认值。
2. **连边**：对每个动作（`approve`、`reject`），找它执行前后的状态，得到 `from → to`。
3. **标 system**：没有对应动作、但状态确实会变（定时任务、接口回调、自动计算），标 `"system": true`。

```json
{ "id": "sm-inspection", "entity": "inspection", "initial": "created",
  "states": [{"key":"created","label":"待取样"},{"key":"sampled","label":"已取样"},
             {"key":"reported","label":"待审核"},{"key":"approved","label":"已归档"}],
  "transitions": [
    {"from":"created","to":"sampled","trigger":"cap-submit-sample"},
    {"from":"sampled","to":"reported","system":true},
    {"from":"reported","to":"approved","trigger":"cap-approve"},
    {"from":"reported","to":"created","trigger":"cap-reject"} ] }
```

### 4.3 三个必查的坑

| 坑 | 表现 | 怎么查 |
|---|---|---|
| **有状态没迁移** | `archived`、`cancelled` 出现在代码里但没有任何地方赋这个值 | 状态集合减去迁移端点集合，差集就是孤儿状态（可能是历史遗留，也可能是后端在改） |
| **有迁移没状态** | 赋值 `status='done'` 但状态列表里没有 `done` | 反过来做差集 |
| **迁移不可达** | 从 `initial` 出发走不到某个状态 | 从 `initial` 做 BFS，到不了的标出来——通常是权限分支里的隐藏路径 |

第三条值得单独跑一遍，因为不可达状态意味着有功能是死的，或者权限分支写错了。

```bash
# 校验：所有端点都在 states 内（L2-26 的等价命令）
python3 -c "
import json,sys
d=json.load(open('out.proto.json'))
for sm in d['stateMachines']:
    ks={s['key'] for s in sm['states']}
    for t in sm['transitions']:
        if t['from'] not in ks or t['to'] not in ks:
            print('孤儿端点', sm['id'], t)
"
```

## 5 逆向产出的落位

逆向进来的内容，落到 `proto.json` 的哪个格子，决定它后面怎么被用：

| 逆向得到 | 落到 | 注意 |
|---|---|---|
| 路由树 | `modules[]` + `pages[]` | 布局路由、错误页不进 |
| 权限码 / 角色判断 | `capabilities[].actor` | 角色 id 要重新映射到新系统的 `u-*` |
| 按钮显隐/禁用条件 | `capabilities[].from` + `policy` | `hidden` 还是 `disabled` 要找人确认 |
| 表单校验 | `guards[]` + `acceptance[illegal]` | 这是最有价值的产出 |
| status 字面量 | `stateMachines[].states` | 显示名要重新起，不要照抄英文 key |
| 动作名 | `capabilities[].id` | `cap-` 前缀 + 动词 |
| 列表列定义 | `DataTable.props.columns` | 列宽要按新设计宽重排，不能照抄 |
| 接口字段 | `fieldRegistry[]` | 必须指到真实节点，否则 L2-41 红 |

## 6 逆向的边界：什么不能逆

四种东西代码里有但**不能**逆进新系统：

| 不能逆 | 为什么 | 应该怎么做 |
|---|---|---|
| 界面布局的具体像素 | 旧系统可能就是在错误的分辨率下设计的 | 按 `04-visual-spec.md` 重排，只保留信息结构 |
| 字段的排列顺序 | 通常是历史堆积，不是业务逻辑 | 按业务分组重排 |
| 权限的具体角色名 | 旧角色可能是为绕开限制临时加的 | 回到角色表重新定义，标"是否真实存在" |
| 任何"因为历史原因"的特殊分支 | 逆向会把技术债原样搬过来 | 单独列成 `openQuestions`，问清是否还要保留 |

最后一条最重要。旧系统里 `if (supplierId === 1234) skipValidation` 这种硬编码，逆向进来就是在新系统里埋同一颗雷。**每一条逆向出的规则，都要问一句"这是业务要求还是历史遗留"。**

## 7 逆向的完成判据

四条全满足才算逆向完成，否则只是"抄了个界面"：

1. 每个模块都能说出它对应的后端资源（表或服务），说不出的是界面分组不是模块；
2. 代码里每个"能不能"类分支，要么进了 `capabilities`，要么进了 `guards`，要么被明确记录为"历史遗留，不带入"；
3. 状态机从 `initial` 出发可达所有状态，或有明确的不可达原因；
4. 每条逆向结论都标了 `measured` / `inferred`，`inferred` 的都有对应的 `openQuestions`。

---

> 这一节为什么必须存在：从 Demo 抄界面只能得到皮，抄不出规则和状态机，而这些恰恰是返工的来源
