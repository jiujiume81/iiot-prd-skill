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

## 11 已知限制

| 限制 | 影响 | 缓解 |
|---|---|---|
| 单文件体积随页面数线性增长 | 36 页以上超过 1.5MB，首次打开变慢 | 超过 36 页时按模块拆成多个 HTML，或只内联当前模块 |
| 无路由，靠 `store.pageId` | 浏览器前进/后退不可用 | 用 `#page=` 直达；评审场景够用 |
| 表单不校验、不提交 | 原型只做交互模拟，不做业务逻辑 | 交给真实前端；`guards` 已在契约里写清校验规则 |
| 无并发与权限的开箱实现 | `userRole` 是手动切换的模拟值 | 契约里 `actor` 已定义，真实系统按它做鉴权 |
| PNG 导出依赖浏览器 | 见 §8 | 降级为打印存 PDF |

---

> 这一节为什么必须存在：容器是"改需求不改 HTML"这条承诺的唯一实现方式，它坏了整个闭环就退回改代码的老路
