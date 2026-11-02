# 容器工程：三栏壳、渲染引擎与迭代闭环

> 容器不是"给原型加个外壳"，它是把 `proto.json` 变成可评审界面的**运行时**。原型和 PRD 都从同一份数据渲染——所以改需求只改 JSON，不改 HTML，不会出现"文档和界面对不上"。

## 1 四层结构

```
assets/container/src/
├─ vue.global.prod.js   ① 运行时   Vue 3.4.38 全量 prod，143KB，内联
├─ runtime.js           ① 兜底     MiniVue shim，Vue 缺失时降级不白屏
├─ components.js        ② 组件库   51 个组件，options API + h()
├─ app.js               ③ 容器壳   三栏、状态机消费、标注、导出
├─ styles.css           ④ 样式     设计令牌 + 布局 + 组件样式
└─ build.py             ⑤ 打包     把 ①~④ + proto.json 内联成单文件
```

依赖方向是单向的：`components.js` 只吃 `props`，不认识 `store`；`app.js` 认识 `store` 和 `DATA`。这样组件可以直接搬进 `.vue` 文件给前端用，不用连带搬容器。

## 2 构建

```bash
cd assets/container/src
python3 build.py --proto ../../../examples/example-01-qms-incoming.proto.json \
                 --out ../dist/index.html
```

产物 `dist/index.html` 约 250KB（Vue 143 + 组件与样式 80 + 数据 25），双击即开、离线可用、可直接发微信。

三个构建期的检查（放在 `build.py` 里，越早越好）：

| 检查 | 为什么 |
|---|---|
| 组件/应用代码里不能出现 `</script` | 内联进 `<script>` 会提前闭合标签，整页白屏且报错指向不明 |
| proto 必须能被 `json.load` | 手改 JSON 多一个逗号就整页白屏，构建期拦住比运行时好 |
| 组件 `type` 必须在 `catalog.json` 白名单内 | 未登记组件在运行时降级成虚线框，构建期就该报出来 |

## 3 三栏布局：覆盖层，不挤压

```
┌───────────────────────────────────────────────┐
│ 容器条：目录 · 页面态 · 单据状态 · 标注 · PRD · 导出 │
├───────────────────────────────────────────────┤
│ ┌────────┐                        ┌──────────┐│
│ │ 目录   │      原型画布 1:1       │  PRD     ││  ← 两者都是浮层
│ │ 264px  │   宽 = 容器宽，不缩放    │ 360~760  ││     压在画布上
│ └────────┘                        └──────────┘│
└───────────────────────────────────────────────┘
```

三条硬约束：

1. **画布宽恒等于容器宽**。目录和 PRD 都是 `position: absolute`，不参与布局，所以展开前后 `stage.offsetWidth` 完全相等。这是"不被挤压"的硬证据，可用 `#test=1` 自检：

   ```bash
   chrome --headless --dump-dom "index.html#test=1" | grep -o '<div id="selftest">[^<]*'
   # {"canvasClosed":1440,"canvasOpen":1440,"notSqueezed":true,...}
   ```

2. **不缩放**。原型就是真实像素，1440 打开就是 1440。早期版本用过 `transform: scale` 适配，代价是：交给开发后前端要反算像素，而且 `getBoundingClientRect` 被缩放磨平，判据会假绿。要看全貌就收起浮层。

3. **PRD 浮层可拖宽 360~760**。拖的是浮层自身宽度，与画布无关。窄于 360 时表格挤成一列，宽于 760 就盖住大半个原型。

## 4 渲染引擎：JSON → UI

核心是 30 行的递归：

```js
function renderNode(node, ctx) {
  var comp = REGISTRY[node.type] || Fallback;         // 未登记组件降级，不白屏
  return h(comp, { key: node.id, p: node.props, n: node, ctx: ctx },
           (node.children || []).map(function (c) { return renderNode(c, ctx); }));
}
```

四个设计要点：

| 要点 | 做法 | 为什么 |
|---|---|---|
| 未登记组件降级 | `Fallback` 渲染虚线框 + 类型名 | 白屏无法定位；虚线框一眼看出哪个漏了 |
| 节点 `id` 作 `key` | `key: node.id` | `id` 分配后不改，diff 稳定，标注锚点也不跑 |
| 只认 `props` 不认全局 | 组件签名 `props: { p, n, ctx }` | 组件可独立搬走 |
| 表格列宽必填 | `table-layout: fixed` + 每列 width | 缺宽度的列在 fixed 下宽度为 0，表现为"列神秘消失" |

## 5 状态：三层，不混

这是整个容器最容易做错的地方。三种"状态"混在一起，按钮可用性就写不出来：

| 层 | 载体 | 例子 | 谁改 |
|---|---|---|---|
| **页面态** | `store.pageState` | default / loading / empty / zero-result / error | 顶部工具条切换（模拟） |
| **业务态** | `store.entityStatus` | created / sampled / reported / approved | 顶部「单据状态」切换；真实系统里由后端返回 |
| **组件态** | 组件内部 | 下拉展开、输入框聚焦 | 组件自己 |

业务态驱动命令可用性，逻辑集中在一个函数里：

```js
function can(capId) {
  var cap = CAPS[capId]; if (!cap) return { ok: true };
  if ((cap.actor || []).indexOf(store.userRole) < 0) return { ok:false, reason:'当前角色无权限' };
  if ((cap.from || []).indexOf(store.entityStatus) < 0) {
    var cur = stateLabel(store.entityStatus);       // 「已归档」
    return { ok:false, reason: (cap.reason || '当前状态不可用') + '（当前为「' + cur + '」）' };
  }
  return { ok: true };
}
```

**提示文案是拼出来的，不是写死的。** 契约里只写「仅「待审核」可审核」，容器补上「（当前为「已归档」）」——否则每加一个状态，就要为每个命令补一句文案。

组件侧只写 `props.capability = "cap-approve"`，**禁止 `disabled: true`**。写了 `disabled` 就绕过了状态机，等于在组件上写死了一个业务规则。

## 6 标注：锚点而不是坐标

```json
{ "id":"an-001", "pageId":"pg-iqc-report", "nodeId":"n-table",
  "anchor": {"x":0.42,"y":0.18}, "body":"...", "severity":"major",
  "affects":["componentTree","capability"], "status":"open" }
```

- `anchor` 是**相对锚定节点**的 0~1 归一化坐标，不是页面绝对像素。所以换页、改栏宽、换窗口大小、重开浏览器，pin 都不跑位。
- `nodeId` 必须在本页组件树内（L2-38 校验）。锚到不存在的节点，pin 会飘到页面左上角。
- 交互流程：点「标注」→ 点页面元素 → 写一句 → 保存。导出为「修改指令」，每条含定位 + 动作 + 现状，可直接喂给下一轮。

## 7 持久化

`localStorage` 按 `iiot:{产品}:{版本}` 分键存三样：

| 键 | 内容 | 重置影响 |
|---|---|---|
| `pageId` / `pageState` / `entityStatus` | 上次看到哪 | 无 |
| `annotations` | 标注（与 `proto.json` 里的初始标注合并） | 会丢人工标注 |
| `prdEdits` | PRD 正文的在线编辑 | 会丢编辑 |

「重置为 AI 版本」= 清这三个键，回到 `proto.json` 的原始状态。版本号进 key 是有意的：换版本时旧标注不会串到新原型上（`nodeId` 可能已经变了）。

## 8 导出

| 导出 | 机制 | 稳定性 |
|---|---|---|
| PRD → Markdown | 遍历 `prd.sections` 拼 md | 稳 |
| 当前页 → 单页 HTML | 抽出该页 DOM + 内联样式，生成独立文件 | 稳，前端可直接用 |
| 标注 → 修改指令 | 拼成结构化文本 | 稳 |
| 当前页 → PNG | SVG `foreignObject` 包 DOM → canvas | **需浏览器实测**，跨域字体和图片会失败 |
| 打印 / 存 PDF | `@media print` 隐藏壳，只留原型 | 稳 |

PNG 那条要留意：`foreignObject` 方案在 Chrome 上通常可行，但页面里有外部字体或图片时会被 tainted canvas 拦住。第一版交互时验证一次，不稳就把 PNG 降级为"打印存 PDF"。

## 9 直达参数

分享某个具体状态给评审，比口头描述省一半时间：

```
index.html#page=pg-iqc-sample-pda            直接打开 PDA 页
index.html#page=pg-iqc-report&status=approved  打开已归档状态（看按钮置灰）
index.html#prd=1&toc=1                       三栏全展开
index.html#test=1                            自检覆盖层是否挤压画布
```

## 10 加一个组件

四步，顺序不能反：

1. **登记** `schemas/catalog.json`：`category`（pc-shell / pc-input / pc-data / pda / common）、`states`、`props` 契约。不登记 → 运行时降级成虚线框 + L2-14 红。
2. **实现** `components.js`：options API + `h()`，`props: { p, n, ctx }`，只用 `p` 里的数据。
3. **加样式** `styles.css`：只能用设计令牌，不写死颜色值。
4. **验证**：改 `example-01` 用上新组件 → `check_contract.py` → `build.py` → 截图看四态。

第 4 步不能省。组件在 `default` 态好看、`empty` 态塌掉，是最常见的问题。

## 11 交互引擎：能点是契约的一部分

老版容器的毛病很典型：`interactions` 在 schema 里有、校验器也查、引擎从来不读。于是"点击行进入详情"只存在于 JSON 里，页面上点下去什么都不发生，评审时没人敢信这台原型。

现在引擎把四件事接上了：

### 11.1 点击由 interactions 驱动

页面根节点上挂一个事件监听：点到的元素往上找到 `[data-node-id]`，拿它的 id 去本页 `interactions` 里找 `on` 相同的条目，执行 `do`。

引擎实现的动作集合是封闭的（L2-59）：`navigate` / `openModal` / `openDrawer` / `setState` / `submit` / `toast` / `reset`。契约里写了别的值，校验器直接红，而不是运行到那一刻才发现没反应。

表格行点击是特例，用 `on: "__row_click"` 表示，由 `RD.selectRow` 处理——它既要记选中行，也要执行交互（通常是 `navigate` 到详情）。

### 11.2 承载层按 `capabilities[].ui` 渲染

`RD.action` 先看命令有没有 `ui`：

| `ui.kind` | 引擎行为 |
|---|---|
| `inline` | 直接执行命令：推进状态、给 toast |
| `dialog` | 打开居中弹框，宽度取 `ui.width`（默认 560） |
| `drawer` | 从右侧滑入，宽度默认 520，贴顶贴底 |
| `page` | `RD.goto(ui.pageId)`，跳独立页面 |

弹层里有三样东西必须有：标题（`ui.title`，缺省用命令名）、字段（`ui.fields` 渲染成表单）、主按钮（`ui.submitLabel`）。没有 `fields` 也没有 `successText` 的命令，弹出来是空壳（L2-63）。

**关闭通道四条都要通**：右上角 `×`、底部「取消」、「Esc」、点遮罩。少一条，评审时就会有人卡在弹层里刷新页面。Esc 监听挂在 `window` 上，所以要判断当前有没有弹层再决定是否拦截。

### 11.3 提交 = 校验 + 状态推进

`submitLayer` 做三件事：

1. 按 `fields[].required` 校验，缺的字段标红并 toast「还有必填项没填：X、Y」，**弹层不关**；
2. 通过后用 `cap.to` 查状态机拿中文标签，推进状态：行级命令（措施单、逐条验证）改 `L.row.status`，单据级命令改 `store.entityStatus`；
3. 关弹层 + toast 结果（`ui.successText` + 新状态）。

### 11.4 数据必须响应式

`var DATA = window.__PROTO__` 是普通对象时，行级命令改了某一行的 `status`，Vue 追不到，表现是"提示提交成功，列表还是旧状态"——比报错更糟，因为用户以为生效了。所以容器初始化时 `DATA = Vue.reactive(window.__PROTO__)`。

配套的：行状态变了，该行的按钮可用性要跟着重算（`can()` 每次渲染时用当前状态求值，不在渲染时算一次就缓存）。

### 11.5 目录必须点得动

`AppShell` 的导航项以前是纯 `<div>`，没有点击处理——看着是菜单，点着没反应。现在：

- 导航项优先用显式 `page` 字段绑定；没写的按 `label` 去匹配页面标题；
- 匹配上了 → `RD.goto(pageId)`，并按当前页高亮（`is-on` 由 `store.pageId` 实时算，不信数据里的 `on`）；
- 匹配不上 → 标 `is-void` + 点击给一句原因（「不在本原型范围」），不做假菜单。

页头标题必须等于页面名（L2-62）。拿某条单据号当页头标题，换一条数据进来就张冠李戴。

### 11.6 实测：别再说"应该能点"

```bash
python3 scripts/check_interact.py \
  --proto examples/example-02-accident.proto.json \
  --html examples/dist-accident.html
```

它从契约里推出用例：每条 dialog/drawer 命令点开一次、看承载形式对不对、按 Esc 看关不关得上；每个目录项点一次、看页面有没有换；每个列表页点一次行、看进不进详情。无头 Chrome 跑，输出逐条 OK/FAIL。

这一层专门抓"契约齐全但引擎不认"：把引擎里 `openLayer` 那行注释掉重跑，9 条命令立刻红。

### 11.7 截图只在验收时截，验完就删

原型核验会反复截同一批页面，很容易留下几十张中间态。约定：

- 每轮截图**覆盖同名文件**，不叠 `r_` / `s_` / `t_` 这种轮次前缀；
- 只保留终版整页图 + 异常态各一张，其余验完即删（进废纸篓，不是硬删）；
- 局部裁切图（看列宽、看间距）用完就删，它只是过程证据。

### 11.8 三个"空块"：契约写了、引擎没读

做事故报告正式交付时连撞三次同一类问题——**JSON 里字段一个不少，页面上那一块是空的**。
三个都不是写错数据，是引擎读的键和契约写的键不是同一个：

| 现象 | 根因 | 修法 |
|---|---|---|
| 详情页顶部「单据状态」只有标题，后面一条空线 | `StatusBar` 只读 `props.steps`，契约给的是 `props.stateMachine` | 组件里补回落：无 `steps` 时按 `stateMachine` 去 `stateMachines` 取 `states` |
| 新建页整张表单显示「暂无字段」 | `FormGrid` 只读 `props.items`，契约写的是 `props.fields`（与命令弹层的 `ui.fields` 同名同义） | `var items = p.items \|\| p.fields \|\| []` |
| 状态条右侧的单据编号 / 发生时间 / 停留天数全不见 | `StatusBar` 只渲染 `props.note`，不认 `props.meta` | 把 `meta` 拼成一段次要文字渲染在右侧 |

三条都补了判据（`L2-64` 状态条必须有 `steps` 或存在的 `stateMachine`；`L2-66` 表单必须有 `items`/`fields`），
因为这类问题**靠看 JSON 永远发现不了**——契约校验全绿，页面却是残的。

推论：新增组件时，props 的键名要么和已有约定一致（表单字段一律 `fields`），要么在组件里同时兼容两种写法。
**"我写了一种、引擎认另一种"是原型返工里最贵的一种错**，它不会报错，只会安静地渲染成空白。

## 12 已知限制

| 限制 | 影响 | 缓解 |
|---|---|---|
| 单文件体积随页面数线性增长 | 36 页以上超过 1.5MB，首次打开变慢 | 超过 36 页时按模块拆成多个 HTML，或只内联当前模块 |
| 无路由，靠 `store.pageId` | 浏览器前进/后退不可用 | 用 `#page=` 直达；交互跳转已可用，浏览器历史栈不记 |
| 表单只校验必填，不校验业务规则 | 前端必填能演示，规则校验（如限值范围）仍要真实后端 | 规则写在 `guards` 里，真实前端按它实现 |
| 无并发与权限的开箱实现 | `userRole` 是手动切换的模拟值 | 契约里 `actor` 已定义，真实系统按它做鉴权 |
| PNG 导出依赖浏览器 | 见 §8 | 降级为打印存 PDF |

---

> 这一节为什么必须存在：容器是"改需求不改 HTML"这条承诺的唯一实现方式，它坏了整个闭环就退回改代码的老路
