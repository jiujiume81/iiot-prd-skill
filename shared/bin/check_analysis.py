#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""iiot-prd-suite · 三段式分析产物校验（A 系列 46 条判据，不拆文件）

用法：
  python3 shared/bin/check_analysis.py <产品目录>/ --stage 1      # 第 1 段：只查 M1~M3
  python3 shared/bin/check_analysis.py <产品目录>/ --stage 2      # 第 2 段：只查 M4~M6
  python3 shared/bin/check_analysis.py <产品目录>/                # = --stage all，46 条全跑
  python3 shared/bin/check_analysis.py <产品目录>/ --status       # 跨会话恢复视图
  python3 shared/bin/check_analysis.py <产品目录>/ --hash         # 算 M3 场景表 hash
  python3 shared/bin/check_analysis.py --init <产品目录>/ --product "..." --stage 1
  python3 shared/bin/check_analysis.py <产品目录>/ --upgrade      # 只做 _gate.json → _state.json
  python3 shared/bin/check_analysis.py <产品目录>/ --stage 2 --seal   # 签收第 2 段出口
                                        #   零 ERROR 且零 A-67 才落盘；已有签收需 --force
                                        #   --force 只覆盖「已签收」，不覆盖判据

退出码：0 = 放行，1 = 拦截（有 ERROR），2 = 用法错误。

--stage 的分工（24 + 21 + 6 = 51；原 mfg 46 条 + A-35 + A-36 + A-67 + A-68 + A-69）：
  stage 1 = A-00 / A-01~06 / A-10~14 / A-20~26 / A-24b / A-25b~e        （24 条）
  stage 2 = A-30~34 / A-35 / A-36 / A-40~44 / A-50~54 / A-67 / A-68 / A-69   （21 条）
  跨阶段  = A-60 / A-60b / A-61 / A-62 / A-63 / A-64                   （6 条，两段都跑）
  A-1x 是小节族（按文件查必需二级标题），不计入 46，但同样按 stage 过滤。

两条纪律（来自 IIOT-PRD 的教训，别再犯）：
  1. 判据只读产物文件，不读模型说的话；
  2. 判据不读模板里的解释文字 —— sections() 剔除 `>` 引用块，否则模板自带的说明会把判据喂饱。
"""
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone

E, W = "ERROR", "WARN"
OK = "OK"
issues = []

# --seal 时 A-67 走严格模式：签收动作本身不允许把渲染键降级成 WARN。
STRICT = False
# --verbose 时把聚合掉的逐处清单放这里，默认可不打印（23 条红说的是同一件事）
VERBOSE_HITS = []

HERE = os.path.dirname(os.path.abspath(__file__))
SUITE = os.environ.get("IIOT_SUITE_ROOT") or os.path.dirname(HERE)
TEMPLATES = os.path.join(SUITE, "assets", "templates")

# 跨阶段判据：--stage 1 与 --stage 2 都必须跑，否则掉缝里
CROSS_STAGE = {"A-60", "A-60b", "A-61", "A-62", "A-63", "A-64"}

# A-63 越界词表：stage 1 不许碰原型层；stage 2 已落到契约，proto.json / capabilities 是合法产物
# 语义：02 可以提「页面骨架」，不许提「页面怎么画」。
# 表里只放**结构键名**，一个中文词都不许加。三条理由（2026-11-16 裁定，别再动摇）：
#   1. 中文「组件树」在 02 的产物里绝大多数是**正确写法**——「组件树与交互由第 3 段补」
#      正是我们想让 02 说的话。加进去等于惩罚正确行为，人会换个说法绕过去，判据形同虚设。
#   2. A-63 判的是「有没有把渲染层**结构**写进来」，不是「有没有**提到**渲染层的词」。
#      结构可判（键名 / JSON 片段），词不可判。
#   3. 反例可证：写「页面组件树与交互由第 3 段补」→ 必须放行；
#      写「componentTree 按状态拆三块」→ 必须红。加中文词会同时杀前一句。
# 见 shared/references/09-pitfalls.md 案例 3（判据能验形，验不了义）。
OUT_OF_SCOPE = {
    1: ["componentTree", "pages[]", "capabilities[]", "proto.json"],
    2: ["componentTree", "interactions", "ui.kind", "pages[].prd"],
}



def add(level, code, msg):
    issues.append((level, code, msg))


# ---------------------------------------------------------------- 六步与标题
# stage: 1 = 01-business 的出口（M1~M3），2 = 02-requirement 的出口（M4~M6）
STEPS = [
    {"no": 1, "stage": 1, "key": "problem", "file": "M1-problem.md", "title": "真问题",
     "secs": ["原话", "边界与非目标", "问题与方案分离", "真问题陈述", "替代路径", "我的立场"]},
    {"no": 2, "stage": 1, "key": "roles", "file": "M2-roles.md", "title": "角色",
     "secs": ["角色表", "角色现实性核对", "角色关系", "缺席的角色"]},
    {"no": 3, "stage": 1, "key": "scenarios", "file": "M3-scenarios.md", "title": "场景",
     "secs": ["场景表", "覆盖矩阵", "优先级口径", "待确认清单", "确认记录"]},
    {"no": 4, "stage": 2, "key": "flows", "file": "M4-flows.md", "title": "业务流程",
     "secs": ["主流程", "分支流程", "泳道", "状态机", "断点"]},
    {"no": 5, "stage": 2, "key": "exceptions", "file": "M5-exceptions.md", "title": "异常与边界",
     "secs": ["异常清单", "影响量化口径", "降级路径汇总"]},
    {"no": 6, "stage": 2, "key": "review", "file": "M6-review.md", "title": "对抗评审",
     "secs": ["评审口径", "资深研发", "测试负责人", "业务负责人", "现场使用者",
              "最大 5 个风险", "结论"]},
]

STEPS_BY_FILE = {s["file"]: s for s in STEPS}


def steps_of(stage):
    """该阶段该查哪几步。stage=0 表示全量。"""
    return [s for s in STEPS if not stage or s["stage"] == stage]


# --status 里每步看哪张主表（其余表只在判据里用）
MAIN_TABLE = {1: "原话", 2: "角色表", 3: "场景表", 4: "主流程", 5: "异常清单",
              6: ("资深研发", "测试负责人", "业务负责人", "现场使用者")}


def primary_rows(secs, step_no):
    """该步主表的数据行数。M6 的主表是四个角色的问题表（合起来才是它的主体）。"""
    target = MAIN_TABLE.get(step_no)
    if target is None:
        return 0
    if isinstance(target, tuple):
        return sum(table_rows(find_sec(secs, t) or "") for t in target)
    return table_rows(find_sec(secs, target) or "")


def pad(text, width):
    """按终端显示宽度补空格：中文占 2 列，否则表会歪。"""
    import unicodedata
    w = sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)
    return text + " " * max(1, width - w)

# 表头（逐字）。列名漂移是本类文档最常见的腐化方式，只认逐字 + 顺序。
COLS = {
    "M1_QUOTE": ["#", "原话（逐字，不许改写）", "出处", "谁说的", "时间"],
    "M1_SEP": ["原话编号", "判定（问题/方案/混合）", "背后的损失（量化）", "证据等级",
               "命中的判据（词性/三问/可替换）"],
    "M1_PATH": ["编号", "路径", "具体做法", "治不了什么", "成本量级", "是否需要改系统"],
    "M2_ROLE": ["角色名称", "角色目标", "使用频率", "关注的信息", "可能的操作权限",
                "和其他角色的关系"],
    "M2_REAL": ["角色名称", "是否真实存在", "与其他角色是否同一人", "由此产生的系统约束"],
    "M2_ABSENT": ["角色", "为什么不在系统里", "他会怎么影响系统", "系统必须为他留什么出口"],
    "M3_SCEN": ["#", "场景名称", "触发时机", "用户当前状态", "用户想完成什么",
                "系统应该提供什么帮助", "优先级", "发生频次", "失败兜底", "受影响角色"],
    "M3_MATRIX": ["维度", "取值", "归属", "理由"],
    "M3_PENDING": ["#", "我拿不准的一件事", "我给的建议", "你不定会怎样", "你的回答"],
    "M4_FLOW": ["步", "步骤", "触发者（角色/系统/设备）", "系统判断（规则或 guard）",
                "输入", "输出", "状态变化", "批量粒度", "对应场景"],
    "M4_BRANCH": ["分支", "从第几步分叉", "条件", "去向", "对应场景"],
    "M4_STATE": ["状态", "谁触发", "触发动作", "→ 目标状态", "条件", "是否系统自动"],
    "M4_BREAK": ["断点位置（第几步）", "现在没系统时靠什么完成", "上线后用户可能怎么绕过"],
    "M5_EXC": ["类别", "异常场景", "触发条件", "影响（量化）",
               "产品处理建议（必须含降级路径）", "对应场景/流程步"],
    "M5_DEGRADE": ["异常类", "降级做法", "谁执行", "恢复后怎么补数据"],
    "M6_Q": ["#", "问题", "他为什么会问", "现在缺什么", "补到哪"],
    "M6_RISK": ["#", "风险", "上线后多久会爆", "爆了什么样", "现在能不能解", "处理结论"],
}

# 十一个维度与取值（DESIGN C.3.1，唯一源）。
# 族名必须是短词：场景与矩阵里写的是 `族:值`，`生命周期阶段:` 这种长名会把表格挤爆。
DIMS = [
    ("D1",  "阶段", ["创建前", "创建", "待处理", "处理中", "待确认", "已完成", "已作废", "归档后"]),
    ("D2",  "触发", ["计划", "异常", "手工", "接口", "扫码", "定时", "导入", "设备信号"]),
    ("D3",  "批量", ["单条", "一批", "多批混选", "全量", "拆批", "并批", "分批到货"]),
    # D4 只放中性的「来路」。`先入后检 / 先检后入` 是结论（谁先谁后），
    # 写进词表等于把答案塞进题目 —— 它们靠 Step 2.5 跨系统时序与场景库 SC-11 产出。
    ("D4",  "来路", ["正常入库", "退货再入", "让步接收", "转库调拨", "委外回收",
                      "返工返修", "试制", "客户供料", "紧急放行"]),
    ("D5",  "角色", ["发起", "执行", "审核", "下游等待", "监管", "外部方", "班组长", "替班"]),
    ("D6",  "结果", ["通过", "部分成功", "全失败", "超时", "重复", "越权", "数据不全", "断网"]),
    ("D7",  "连续", ["编号连续", "断号", "重号", "跨月跨年", "一物多码", "多物一码", "人为改号"]),
    ("D8",  "版本", ["首建", "标准换版", "主数据变更", "作废重开", "历史迁移"]),
    ("D9",  "时间", ["白班", "夜班", "交接班", "峰谷", "跨天", "月末", "停产检修"]),
    ("D10", "现场", ["产线", "工位", "车间", "仓库", "在途", "无网", "戴手套", "噪音", "光线"]),
    ("D11", "形态", ["粉体", "液体", "卷材", "结构件", "气体", "其他"]),
]
DIM_NAMES = {code: name for code, name, _ in DIMS}
DIM_VALUES = {code: vals for code, _, vals in DIMS}

# 制造业异常 11 类（E.5 / A-40）。类别列必须在第一列。
EXC_CLASSES = [
    ("用户操作", ["用户操作"]),
    ("系统状态", ["系统状态", "系统"]),
    ("数据", ["数据"]),
    ("权限", ["权限"]),
    ("网络接口", ["网络", "接口"]),
    ("并发重复", ["并发", "重复"]),
    ("历史数据兼容", ["历史", "兼容"]),
    ("运营后台", ["运营", "后台"]),
    ("设备与硬件", ["设备与硬件", "设备", "硬件", "外设", "扫码枪", "打印机", "电子秤", "PDA", "网关"]),
    ("工艺与配方", ["工艺", "配方", "参数", "首件"]),
    ("追溯断链", ["断链", "追溯"]),
    ("标准与版本", ["标准与版本", "标准", "版本"]),
]
EXC_ORDER = [name for name, _ in EXC_CLASSES]

# 结论型取值黑名单：把「答案」写进维度词表，扫出来的只是自己的假设
CONCLUSION_VALUES = ["先入后检", "先检后入", "先做后审", "先审后做", "事后补录"]

FORBIDDEN_PHRASES = ["待定", "TBD", "建议考虑", "可以酌情", "视情况", "（待填）", "(待填)"]
# 越界词表按 stage 换表，见文件头 OUT_OF_SCOPE（1 = 分析段，2 = 落契约段）
EMPTY_WORDING = ["参考行业最佳实践", "提升易用性", "优化体验"]

IMPLEMENT_NOUNS = ["页面", "按钮", "弹框", "弹窗", "字段", "接口", "菜单", "标签页"]
DELIVERY_HINTS = ["交", "给", "审", "导出给"]


# ---------------------------------------------------------------- 基础解析
def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def sections(md):
    """抓二级标题，返回 {标题原文: 该节正文}。

    剔除 `>` 引用块：模板里的说明文字若被算进正文，判据会被自己喂饱（IIOT-PRD 踩过）。
    判据不读自己的注释。
    """
    out, cur, buf = {}, None, []
    for line in md.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if cur is not None:
                out[cur] = "\n".join(buf)
            cur, buf = m.group(1), []
        elif cur is not None:
            if line.lstrip().startswith(">"):
                continue
            buf.append(line)
    if cur is not None:
        out[cur] = "\n".join(buf)
    return out


def find_sec(secs, kw):
    for k, v in secs.items():
        if kw in k:
            return v
    return None


def find_secs(secs, kw):
    return [v for k, v in secs.items() if kw in k]


def is_sep(line):
    return bool(re.match(r"^\|[\s:\-|]+\|$", line.strip()))


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_table(block):
    """返回 (表头 cells, 数据行 list[cells])。

    数据行过滤：整行全空、或全格都是占位符，不算数据（模板骨架不能拿来充数）。
    """
    if not block:
        return [], []
    lines = [ln.strip() for ln in block.splitlines() if ln.strip().startswith("|")]
    if not lines:
        return [], []
    header = cells(lines[0])
    rows = []
    for ln in lines[1:]:
        if is_sep(ln):
            continue
        cs = cells(ln)
        if all((not c) or c in ("（待填）", "(待填)", "—", "-") for c in cs):
            continue
        rows.append(cs)
    return header, rows


def grab(sec_text, cols_key, code, what):
    """取表并把列名逐字校验一遍。列名不对，后续判据全是假绿，所以在这里拦。"""
    header, rows = parse_table(sec_text)
    want = COLS[cols_key]
    if not header:
        add(E, code, "%s 里没找到表格（应为 %d 列：%s）" % (what, len(want), " | ".join(want)))
        return [], []
    if header != want:
        miss = [c for c in want if c not in header]
        extra = [c for c in header if c not in want]
        detail = []
        if miss:
            detail.append("缺「%s」" % "、".join(miss))
        if extra:
            detail.append("多「%s」" % "、".join(extra))
        if not detail:
            detail.append("顺序不对")
        add(E, code, "%s 列名与规范不一致：%s（规范：%s）" % (what, "；".join(detail), " | ".join(want)))
        return header, rows
    return header, rows


def col(header, name):
    return header.index(name) if name in header else -1


def cell(row, idx):
    if idx < 0 or idx >= len(row):
        return ""
    return row[idx].strip()


def table_rows(block):
    """数表格数据行（排除表头与分隔线）。"""
    _, rows = parse_table(block)
    return len(rows)


def list_items(block):
    """数 Markdown 列表项。要求标记后有空格，否则 `---` 会被算成一条。"""
    return len(re.findall(r"^\s*(?:\d{1,2}[.、)]|[-*+]\s)\s*\S", block or "", re.M))


def parse_time(s):
    """ISO8601 → aware datetime；不带时区按本地时区。"""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def mtime_aware(path):
    return datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)


def norm_value(v):
    """维度取值比对：去掉括号补充说明后再比，`归档后（≥30 天）` 与 `归档后` 视为同一格。"""
    return re.sub(r"（.*?）|\(.*?\)", "", v or "").strip()


def digest12(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def scene_hash(md_text):
    """M3 场景表 hash：整份文件剔除「## 确认记录」节后取 sha256 前 12 位。

    只对正文算，避免"记录一写就把自己判红"；同时确认后用 touch 改 mtime 也糊弄不过去。
    """
    lines = md_text.replace("\r\n", "\n").split("\n")
    out, skipping = [], False
    for ln in lines:
        m = re.match(r"^##\s+(.+?)\s*$", ln)
        if m:
            skipping = "确认记录" in m.group(1)
        if not skipping:
            out.append(ln)
    return digest12("\n".join(out).rstrip() + "\n")


# ---------------------------------------------------------------- 闸门
STATE_FILE = "_state.json"
LEGACY_FILE = "_gate.json"
STATE_VERSION = "2.0"


def artifact_hash(path):
    """产物指纹：前 12 位。缺文件返回 None。"""
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]


def _scene_ids_by_priority(d, pri):
    """从 M3 场景表取某优先级的场景编号（导出给 02 用，不让它重扫场景）。"""
    p = os.path.join(d, "M3-scenarios.md")
    if not os.path.isfile(p):
        return []
    blk = find_sec(sections(read(p)), "场景表")
    if blk is None:
        return []
    header, body = parse_table(blk)
    if not header:
        return []
    i_id, i_pri = col(header, "#"), col(header, "优先级")
    return [cell(r, i_id) for r in body if pri in cell(r, i_pri).upper()]


def _roles(d):
    p = os.path.join(d, "M2-roles.md")
    if not os.path.isfile(p):
        return []
    blk = find_sec(sections(read(p)), "角色表")
    if blk is None:
        return []
    header, body = parse_table(blk)
    if not header:
        return []
    i_name = col(header, "角色名称")
    return [cell(r, i_name) for r in body if cell(r, i_name)]


def derive(state, d):
    """把 steps 汇总成 stages，并导出 01→02 的机读交接块。纯派生物，不写盘。

    stages 只建 1 和 2 —— 第 3 段没有对应的 M 文件，硬给它一个 status 只会得到一个
    永远算不出真值的字段（原来那个恒 pending 就害过人：照它写 if 判断，等于没写）。
    03 的状态一律由产物推断，见 status() 与 check_stage3_stale()。
    proto 是 02 的出口产物，指纹记在 stages["2"].artifacts 里，不挂在 03 名下。
    """
    steps = state.get("steps") or []
    prev2 = ((state.get("stages") or {}).get("2") or {})
    sealed = prev2.get("sealed")             # 只由 --seal 写，derive 不覆盖
    stages = {}
    for n in (1, 2):
        mine = [s for s in steps if s.get("stage") == n]
        st = [s.get("status") for s in mine]
        if mine and all(x == "done" for x in st):
            status = "done"
        elif any(x in ("done", "in_progress") for x in st):
            status = "in_progress"
        else:
            status = "pending"
        stages[str(n)] = {
            "status": status,
            "artifacts": {s["file"]: artifact_hash(os.path.join(d, s["file"])) for s in mine},
        }
    proto = state.get("protoFile") or ""
    if not proto:
        found = sorted(f for f in os.listdir(d) if f.endswith(".proto.json")) if os.path.isdir(d) else []
        if len(found) == 1:
            proto = found[0]
            state["protoFile"] = proto
    if proto:
        stages["2"]["artifacts"][proto] = artifact_hash(os.path.join(d, proto))
    if sealed:
        stages["2"]["sealed"] = sealed
    # 第 3 段只记产物，不记状态（没有写入通道的状态必然恒假，见 09-pitfalls 案例 5）
    if os.path.isdir(d):
        outs = [f for f in os.listdir(d) if f.endswith(".html")]
        dist = os.path.join(d, "dist")
        if os.path.isdir(dist):
            outs += [os.path.join("dist", f) for f in os.listdir(dist) if f.endswith(".html")]
        stages["3"] = {"artifacts": {f: artifact_hash(os.path.join(d, f)) for f in outs}}
    # 只导三件。P1 不进来：它已经在 M3 的优先级列里，再复制一份进 export 就是两份事实，
    # M3 改一处、export 忘一处必漂（A-35 直接从 M3 的 P1 行找下落）。
    # demandType 由脚本从 M1 原文算出来，不继承人写的值：
    # 本函数每次都会重写 export，人写的字段必被覆盖（cleanHash 就是这么丢的）。
    # 事实源头是 M1 那一行，derive 只负责把它搬到 export 给 02 用。
    _dt = ""
    _m1 = os.path.join(d, "M1-problem.md")
    if os.path.isfile(_m1):
        _mm = re.search(r"需求类型[:：]\s*(AI\s*型|非\s*AI\s*型)", read(_m1))
        _dt = _mm.group(1) if _mm else ""
    stages["1"]["export"] = {"p0": _scene_ids_by_priority(d, "P0"),
                             "roles": _roles(d),
                             "openQuestions": [q.get("id") for q in (state.get("openQuestions") or [])],
                             "demandType": _dt}
    if proto:
        stages["2"]["export"] = {"proto": proto,
                                 "artifacts": {s["file"]: artifact_hash(os.path.join(d, s["file"]))
                                               for s in steps if s.get("stage") == 2}}
    state["stages"] = stages
    state["protoFile"] = proto
    # 当前段：第一个没 done 的段；1、2 都 done 且没有容器产物时算第 3 段
    cur_stage = next((n for n in (1, 2) if stages[str(n)]["status"] != "done"), 3)
    state["stage"] = cur_stage
    nxt = next((s for s in steps if s.get("status") != "done"), None)
    state["current"] = {"stage": cur_stage,
                        "step": (nxt or (steps[-1] if steps else {})).get("no"),
                        "file": (nxt or (steps[-1] if steps else {})).get("file"),
                        "status": (nxt or {}).get("status", "done")}
    return state


def upgrade_gate(gate):
    """_gate.json (v1.0) → _state.json (v2.0)。

    只做字段搬家，不动任何业务值；不写盘（写盘在 load_state 里）。
    """
    steps = []
    for st in (gate.get("steps") or []):
        spec = STEPS_BY_FILE.get(st.get("file") or "")
        steps.append({
            "no": st.get("no"),
            "stage": (spec or {}).get("stage", 1),
            "key": st.get("key") or (spec or {}).get("key"),
            "file": st.get("file"),
            "status": st.get("status") or "pending",
            "doneAt": st.get("doneAt"),
            "rows": st.get("rows") or 0,
        })
    for spec in STEPS:
        if not any(s["no"] == spec["no"] for s in steps):
            steps.append({"no": spec["no"], "stage": spec["stage"], "key": spec["key"],
                          "file": spec["file"], "status": "pending", "doneAt": None, "rows": 0})
    steps.sort(key=lambda s: s["no"] or 0)

    return {
        "stateVersion": STATE_VERSION,
        "product": gate.get("product") or "",
        "createdAt": gate.get("createdAt"),
        "updatedAt": datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "protoFile": gate.get("protoFile") or "",
        "stage": 1,
        "current": {},
        "steps": steps,
        "confirmations": gate.get("confirmations") or {},
        "artifacts": {},
        "matrix": gate.get("matrix") or {},
        "nonGoals": gate.get("nonGoals") or [],
        "scale": gate.get("scale") or {},
        "waived": gate.get("waived") or {},
        "openQuestions": gate.get("openQuestions") or [],
        "upgradedFrom": "gateVersion:%s" % (gate.get("gateVersion") or "?"),
    }


def load_state(d, write_upgrade=True):
    """优先读 _state.json；没有就读 _gate.json 并升级（打印一行，不静默）。"""
    sp = os.path.join(d, STATE_FILE)
    gp = os.path.join(d, LEGACY_FILE)
    if os.path.isfile(sp):
        try:
            state = json.loads(read(sp))
        except ValueError as exc:
            add(E, "A-00", "_state.json 不是合法 JSON：%s" % exc)
            return None
        state["artifacts"] = {s["file"]: artifact_hash(os.path.join(d, s["file"]))
                              for s in (state.get("steps") or [])}
        derive(state, d)
        if write_upgrade:
            _sync(sp, state)
        return state
    if os.path.isfile(gp):
        try:
            legacy = json.loads(read(gp))
        except ValueError as exc:
            add(E, "A-00", "_gate.json 不是合法 JSON：%s" % exc)
            return None
        state = upgrade_gate(legacy)
        state["artifacts"] = {s["file"]: artifact_hash(os.path.join(d, s["file"]))
                              for s in state["steps"]}
        derive(state, d)
        if write_upgrade:
            _sync(sp, state)
            print("[state] 检测到旧格式 _gate.json（gateVersion %s）→ 已生成 _state.json（%s）；"
                  "原文件保留未动" % (legacy.get("gateVersion") or "?", STATE_VERSION))
        return state
    add(E, "A-00", "%s / %s 都不存在：分析未启动，先跑 --init 起骨架" % (STATE_FILE, LEGACY_FILE))
    return None


def _sync(path, state):
    """只在内容真的变了时才写，避免每次读都改 mtime。"""
    body = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=False)
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            if f.read() == body:
                return
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)



def load_gate(d):
    """旧名保留：所有调用点改为 load_state 的薄包装。"""
    return load_state(d)



def gate_confirm(gate, mid):
    return ((gate or {}).get("confirmations") or {}).get(mid) or {}


def check_matrix_counts(gate, header, rows, confirmed_m3):
    """A-24：总格数按取值表算，空格 0，待确认 ≤7，排除 ≤40%。"""
    for code, name, vals in DIMS:
        bad = [v for v in vals if v in CONCLUSION_VALUES]
        if bad:
            add(E, "A-24", "维度 %s（%s）的取值表里有结论型取值：%s —— 答案写进题目，"
                           "扫出来的是循环论证" % (code, name, "、".join(bad)))

    enabled = ((gate.get("matrix") or {}).get("enabledDims")) or [c for c, _, _ in DIMS]
    unknown = [d for d in enabled if d not in DIM_VALUES]
    if unknown:
        add(E, "A-24", "matrix.enabledDims 里有未知维度：%s" % "、".join(unknown))
        enabled = [d for d in enabled if d in DIM_VALUES]

    expected = [(d, v) for d in enabled for v in DIM_VALUES[d]]
    total = len(expected)

    i_dim, i_val, i_own = col(header, "维度"), col(header, "取值"), col(header, "归属")
    i_why = col(header, "理由")
    seen, mapped, excluded, pending, bad_own = {}, 0, 0, 0, []
    for r in rows:
        raw_dim, raw_val = cell(r, i_dim), cell(r, i_val)
        m = re.match(r"^(D\d+)", raw_dim)
        if not m or m.group(1) not in DIM_VALUES:
            add(E, "A-24", "覆盖矩阵行「%s / %s」的维度不是 D1~D10" % (raw_dim, raw_val))
            continue
        d = m.group(1)
        if d not in enabled:
            add(E, "A-24", "覆盖矩阵扫了未启用的维度 %s（%s）" % (d, raw_val))
            continue
        hit = [v for v in DIM_VALUES[d] if norm_value(v) == norm_value(raw_val)]
        if not hit:
            add(E, "A-24", "%s 的取值「%s」不在取值表里（取值表见 references/03-scenarios.md，共 %d 维）"
                % (d, raw_val, len(DIMS)))
            continue
        key = (d, norm_value(hit[0]))
        if key in seen:
            add(E, "A-24", "覆盖矩阵重复登记：%s / %s" % (d, hit[0]))
            continue
        seen[key] = r
        own = cell(r, i_own)
        if re.match(r"^S\d+", own):
            mapped += 1
        elif own == "排除":
            excluded += 1
            why = cell(r, i_why)
            if any(w in why for w in ("不适用", "业务上不需要", "业务不需要", "概率低", "不需要")):
                add(E, "A-24b", "排除理由不能是空话：%s / %s → 「%s」" % (d, hit[0], why))
            elif not (re.search(r"\d", why) or
                      re.search(r"ERP|MES|WMS|QMS|LIMS|SPC|SRM|EAM|PLC|SCADA|APS|PLM|ANDON", why) or
                      re.search(r"S\d|第\s*\d+\s*步", why)):
                add(E, "A-24b", "排除理由要含具体事实（数字/系统名/单据名/场景号/步号）：%s / %s → 「%s」"
                    % (d, hit[0], why))
        elif own == "待确认":
            pending += 1
        else:
            bad_own.append("%s/%s=%s" % (d, hit[0], own or "(空)"))

    for b in bad_own:
        add(E, "A-24", "矩阵归属只能是 S 编号 / 排除 / 待确认，实际是 %s" % b)

    missing = [(d, v) for d, v in expected if (d, norm_value(v)) not in seen]
    if missing:
        show = "、".join("%s/%s" % (d, v) for d, v in missing[:8])
        add(E, "A-24", "覆盖矩阵有 %d 个空格（总格数 %d）：%s%s"
            % (len(missing), total, show, " …" if len(missing) > 8 else ""))

    got = mapped + excluded + pending
    if got != total:
        add(E, "A-24", "矩阵归属合计 %d ≠ 总格数 %d（已映射 %d / 排除 %d / 待确认 %d）"
            % (got, total, mapped, excluded, pending))
    if pending > 7:
        add(E, "A-24", "矩阵待确认 %d 格 > 7：这不是穷举，是没拍板" % pending)
    if total and excluded / float(total) > 0.40:
        add(E, "A-24", "排除 %d 格占 %.0f%% > 40%%：把该做的场景「排除」掉了"
            % (excluded, excluded * 100.0 / total))
    if confirmed_m3 and pending:
        assumed = len([q for q in ((gate.get("openQuestions") or []))
                       if q.get("status") == "assumed"])
        if assumed < pending:
            add(E, "A-24", "M3 已确认但矩阵还有 %d 格待确认，openQuestions 里只有 %d 条 assumed 兜底："
                           "每一格待确认都要有一条假定的默认值" % (pending, assumed))

    claimed = (gate.get("matrix") or {})
    for k, actual in (("totalCells", total), ("mapped", mapped),
                      ("excluded", excluded), ("pending", pending)):
        if k in claimed and claimed[k] != actual:
            add(E, "A-24", "matrix.%s 写的是 %s，实际按文件算是 %s（_gate.json 与产物不一致）"
                % (k, claimed[k], actual))
    return total, mapped, excluded, pending


def check_gate_m3(d, gate):
    """A-25：五重校验。这是全 skill 唯一一个人工硬闸门。"""
    c = gate_confirm(gate, "M3")
    if not c.get("confirmed"):
        add(E, "A-25", "M3（第 3 步闸门）未确认：场景没被用户确认，M4 及之后一律不许写。"
                       "拦截句式：请回我一句「场景没遗漏，可以继续」")
        if os.path.isfile(os.path.join(d, "M4-flows.md")):
            add(E, "A-25", "第⑤重（未跳步）：M3 未确认但 M4-flows.md 已存在——先写第 4 步再补签")
        return False

    # ① 有人
    by = (c.get("by") or "").strip()
    if not by:
        add(E, "A-25", "第①重（有人）：confirmations.M3.by 为空——无签署人的确认等于没确认")
    elif re.search(r"AI|模型|助手|Claude|GPT|assistant", by, re.I):
        add(E, "A-25", "第①重（有人）：签署人写的是「%s」——模型不许替用户签字" % by)

    # ② 有时
    at = parse_time(c.get("at"))
    now = datetime.now(tz=timezone.utc)
    if at is None:
        add(E, "A-25", "第②重（有时）：confirmations.M3.at 不是合法 ISO8601：%r" % c.get("at"))
    elif at > now:
        add(E, "A-25", "第②重（有时）：确认时间 %s 在未来，任何 mtime 都比它早，判据会恒绿"
            % c.get("at"))

    # ③ 有据
    quote = (c.get("quote") or "").strip()
    ok3, why3 = quote_ok(quote)
    if not ok3:
        add(E, "A-25", "第③重（有据）：quote「%s」不足以证明是用户说的——%s" % (quote, why3))

    # ④ 对版
    m3 = os.path.join(d, "M3-scenarios.md")
    cur = scene_hash(read(m3)) if os.path.isfile(m3) else ""
    claimed = (c.get("contentHash") or "").strip().lower()
    if not claimed:
        add(E, "A-25", "第④重（对版）：confirmations.M3.contentHash 为空——"
                       "没有版本指纹，确认后偷偷改场景表没人知道")
    elif claimed != cur:
        add(E, "A-25", "第④重（对版）：确认的是旧版。contentHash=%s，当前场景表是 %s"
                       "（确认后改过内容，或 hash 没重算）" % (claimed, cur))

    # ⑤ 未跳步
    m4 = os.path.join(d, "M4-flows.md")
    if at and os.path.isfile(m4):
        if mtime_aware(m4) < at:
            add(E, "A-25", "第⑤重（未跳步）：M4-flows.md 的写入时间早于 M3 确认时间，"
                           "属先写第 4 步再回头补签")
    return ok3 and bool(by) and at is not None and claimed == cur


def check_gate_vs_m3(d, gate):
    """A-25d：gate.openQuestions 必须与 M3 待确认清单逐字一致。

    形对义错是最难抓的一类：status 和 decision 都在，文本却是模板默认值。
    下游只读 _gate.json，看到的就是「问交接班、答不能合并」。
    """
    p = os.path.join(d, "M3-scenarios.md")
    if not os.path.isfile(p):
        return
    sec = find_sec(sections(read(p)), "待确认清单")
    header, rows = parse_table(sec)
    if not header:
        return
    i_id, i_text = col(header, "#"), col(header, "我拿不准的一件事")
    i_sug = col(header, "我给的建议")
    table = {cell(r, i_id): (cell(r, i_text), cell(r, i_sug)) for r in rows}
    qs = gate.get("openQuestions") or []
    for q in qs:
        qid = str(q.get("id") or "")
        if qid not in table:
            add(E, "A-25d", "openQuestions 的 %s 在 M3 待确认清单里找不到同号行" % qid)
            continue
        text, sug = table[qid]
        if (q.get("text") or "").strip() != text:
            add(E, "A-25d", "%s 的 text 与 M3 待确认清单不一致：gate「%s」/ 表「%s」"
                % (qid, (q.get("text") or "")[:18], text[:18]))
        if (q.get("suggest") or "").strip() != sug:
            add(E, "A-25d", "%s 的 suggest 与 M3 待确认清单不一致：gate「%s」/ 表「%s」"
                % (qid, (q.get("suggest") or "")[:18], sug[:18]))
    for qid in table:
        if qid not in [str(q.get("id") or "") for q in qs]:
            add(E, "A-25d", "M3 待确认清单的 %s 没写进 openQuestions，机器可读的那份缺一条" % qid)


# decision 里写死的条数 → 必须等于 steps[].rows
COUNT_WORDS = {"原话": 1, "角色": 2, "场景": 3, "流程": 4, "异常": 5, "风险": 6}


# 业务计数：三种语序都要认。「19 条场景」在中文里比「场景 19 条」更常见，
# 只认一种就等于允许一半的复述漏过去，这条判据的意义就没了。
COUNT_PATTERNS = [
    r"(原话|角色|场景|流程|异常|风险|P0)(?:表)?[^\d，。；]{0,4}\d+\s*(?:条|个)",  # 场景表 19 条 / P0 有 6 条
    r"\d+\s*(?:条|个)\s*(原话|角色|场景|流程|异常|风险|P0)",   # 19 条场景
    r"(?:共|合计|总计)\s*\d+\s*(?:条|个)",                      # 共 19 条
]


def check_decision_counts(gate):
    """A-25e：decision 里只要命中业务计数就 WARN，不比对数字。

    为什么删掉比对：比对只能拦「写错」，拦不住「当时写对、后来改了场景忘了改 decision」——
    后者才是真会发生的。禁写第二处从根上消掉了这个腐化形态，也省掉一张会腐化的映射表。
    所以这里只认「有没有写」，不认「写得对不对」；级别因此只能是 WARN，误报成本必须为零。
    「另外 2 条按默认值」这类表述不带主体词、也不带共/合计/总计，不会误伤。
    """
    c = (gate.get("confirmations") or {}).get("M3") or {}
    dec = c.get("decision") or ""
    for pat in COUNT_PATTERNS:
        for m in re.finditer(pat, dec):
            add(W, "A-25e", "M3.decision 里写了「%s」：条数只该活在 steps[].rows；"
                            "要写就写成「见 M3 场景表」，别写死数字" % m.group(0))


def quote_ok(quote):
    r"""③ 的判据（主控修正版）：≥4 字，且命中任一具体性条件。

    命中即通过：
      - 含场景编号 `S\d`
      - 含维度编号 `D\d` 或维度名（生命周期阶段/触发方式/…）
      - 含「没遗漏 / 没有遗漏 / 无遗漏」
      - 去掉口头语后仍有 ≥2 个业务实词（≥2 字的词段）
    仅「确认 / 好的 / ok / 可以」这类无信息量的回执，判不通过。
    """
    q = (quote or "").strip()
    if len(q) < 4:
        return False, "quote 少于 4 字"
    if re.search(r"S\d", q) or re.search(r"D\d{1,2}\b", q):
        return True, ""
    for name in DIM_NAMES.values():
        if name in q:
            return True, ""
    if re.search(r"没遗漏|没有遗漏|无遗漏", q):
        return True, ""
    stop = ["确认", "好的", "可以", "没问题", "继续", "同意", "行", "嗯", "对的", "是的",
            "ok", "OK", "收到", "知道"]
    text = q
    for w in stop:
        text = text.replace(w, " ")
    words = [w for w in re.split(r"[^\u4e00-\u9fa5A-Za-z0-9]+", text) if len(w) >= 2]
    if len(words) >= 2:
        return True, ""
    return False, "只有一个无信息量的回执，没有具体对象或结论"


# ---------------------------------------------------------------- 各文件判据
def check_m1(path):
    txt = read(path)
    secs = sections(txt)
    if find_sec(secs, "原话") is None:
        add(E, "A-01", "M1 缺「## 原话」节")
    else:
        header, rows = grab(find_sec(secs, "原话"), "M1_QUOTE", "A-01", "M1 原话表")
        if rows:
            if len(rows) < 3:
                add(E, "A-01", "M1 原话表只有 %d 行，至少 3 行（转述不算，要逐字）" % len(rows))
            i_q, i_src = col(header, "原话（逐字，不许改写）"), col(header, "出处")
            for r in rows:
                q = cell(r, i_q)
                if len(q) < 8:
                    add(E, "A-01", "M1 原话「%s」少于 8 字：这是转述不是原话" % (q or "(空)"))
                if not cell(r, i_src):
                    add(E, "A-01", "M1 原话「%s」的出处为空（会话/会议/微信/文档名）" % q[:12])
        elif header:
            add(E, "A-01", "M1 原话表没有数据行")

    if find_sec(secs, "问题与方案分离") is None:
        add(E, "A-02", "M1 缺「## 问题与方案分离」节")
    else:
        header, rows = grab(find_sec(secs, "问题与方案分离"), "M1_SEP", "A-02", "M1 问题与方案分离表")
        if header and not rows:
            add(E, "A-02", "M1 问题与方案分离表没有数据行")
        plan_like = 0
        for r in rows:
            empties = [COLS["M1_SEP"][i] for i, c in enumerate(r) if i < 5 and not c]
            if empties:
                add(E, "A-02", "M1 问题与方案分离表有一行缺格：%s" % "、".join(empties))
            level = cell(r, col(header, "证据等级"))
            if level and not re.search(r"stated|inferred|measured", level):
                add(E, "A-02", "证据等级必须标 stated / inferred / measured（可分行标），实际写的是「%s」" % level)
            verdict = cell(r, col(header, "判定（问题/方案/混合）"))
            if "方案" in verdict or "混合" in verdict:
                plan_like += 1
        if rows and plan_like < 2:
            add(E, "A-03", "判定为『方案』或『混合』的只有 %d 条（要求 ≥2）——"
                           "全部判成问题，说明没做分离，直接把方案当需求" % plan_like)

    if find_sec(secs, "替代路径") is None:
        add(E, "A-04", "M1 缺「## 替代路径」节")
    else:
        header, rows = grab(find_sec(secs, "替代路径"), "M1_PATH", "A-04", "M1 替代路径表")
        if header:
            if len(rows) < 3:
                add(E, "A-04", "M1 替代路径只有 %d 条，至少 3 条" % len(rows))
            i_sys = col(header, "是否需要改系统")
            if not any("否" in cell(r, i_sys) for r in rows):
                add(E, "A-04", "M1 替代路径里没有一条『是否需要改系统 = 否』——"
                               "三条都在讲怎么改产品，说明没考虑过更省钱的路")

    stand = find_sec(secs, "我的立场")
    if stand is None:
        add(E, "A-05", "M1 缺「## 我的立场」节：分析文档必须给结论")
    else:
        if "看情况" in stand:
            add(E, "A-05", "「我的立场」出现『看情况』：这就是不给结论")
        if not re.search(r"不做|先做别的|做", stand):
            add(E, "A-05", "「我的立场」没有出现『做 / 不做 / 先做别的』三者之一")

    stmt = find_sec(secs, "真问题陈述") or ""
    if stmt and not re.search(r"\d", stmt):
        add(W, "A-06", "真问题陈述里没有数字：{谁} 在 {什么场合} 因为 {什么机制} 损失 {多少}，"
                       "「多少」必须量化")


def check_m2(path):
    secs = sections(read(path))
    roles, real_rows, absents = [], [], []
    if find_sec(secs, "角色表") is None:
        add(E, "A-10", "M2 缺「## 角色表」节")
    else:
        header, rows = grab(find_sec(secs, "角色表"), "M2_ROLE", "A-10", "M2 角色表")
        roles = rows
        if header and len(rows) < 3:
            add(E, "A-10", "M2 角色表只有 %d 行，至少 3 行" % len(rows))
        i_freq = col(header, "使用频率")
        for r in rows:
            f = cell(r, i_freq)
            if not re.search(r"(次|批)", f) or not re.search(r"[天周月]", f):
                add(E, "A-11", "使用频率要写成「N 次/天」这种可算的数，实际写的是「%s」" % (f or "(空)"))

    if find_sec(secs, "角色现实性核对") is None:
        add(E, "A-12", "M2 缺「## 角色现实性核对」节")
    else:
        header, rows = grab(find_sec(secs, "角色现实性核对"), "M2_REAL", "A-12", "M2 角色现实性核对表")
        real_rows = rows
        if header and len(rows) != len(roles):
            add(E, "A-12", "现实性核对 %d 行 ≠ 角色表 %d 行：每个角色都要核一遍"
                % (len(rows), len(roles)))
        i_name = col(header, "角色名称")
        i_exist = col(header, "是否真实存在")
        i_constraint = col(header, "由此产生的系统约束")
        names = set(cell(r, 0) for r in roles) if roles else set()
        for r in rows:
            name = cell(r, i_name)
            if names and name not in names:
                add(E, "A-12", "现实性核对里的「%s」在角色表里找不到（两张表角色名要逐字一致）" % name)
            if "否" in cell(r, i_exist) and len(cell(r, i_constraint)) < 4:
                add(E, "A-12", "角色「%s」标了『不存在』，却没写由此产生的系统约束" % name)

    if find_sec(secs, "缺席的角色") is None:
        add(E, "A-13", "M2 缺「## 缺席的角色」节")
    else:
        header, rows = grab(find_sec(secs, "缺席的角色"), "M2_ABSENT", "A-13", "M2 缺席的角色表")
        absents = rows
        if header and len(rows) < 2:
            add(E, "A-13", "缺席的角色只有 %d 行，至少 2 行" % len(rows))
        i_out = col(header, "系统必须为他留什么出口")
        for r in rows:
            if not cell(r, i_out):
                add(E, "A-13", "缺席角色「%s」没写系统要给他留什么出口" % cell(r, 0))

    rel = find_sec(secs, "角色关系") or ""
    # 硬约束里点名「缺席的角色」（供应商/客审方）也算点名——它们同样是关系的一环
    names = [cell(r, 0) for r in roles if cell(r, 0)]
    names += [cell(r, 0).split("/")[0].strip() for r in absents if cell(r, 0)]
    numbered = re.findall(r"^\s*\d\.\s*(.+)$", rel, re.M)
    if len(numbered) < 3:
        add(W, "A-14", "角色关系下方只有 %d 条硬约束，至少 3 条" % len(numbered))
    else:
        vague = [x for x in numbered if not any(n in x for n in names)]
        if vague:
            add(W, "A-14", "硬约束里没点名具体角色：%s" % vague[0][:24])


def check_m3(path, gate, confirmed_m3):
    txt = read(path)
    secs = sections(txt)
    scen_rows, p0 = [], []
    if find_sec(secs, "场景表") is None:
        add(E, "A-20", "M3 缺「## 场景表」节")
    else:
        header, rows = grab(find_sec(secs, "场景表"), "M3_SCEN", "A-20", "M3 场景表")
        scen_rows = rows
        i_name = col(header, "场景名称")
        i_trig = col(header, "触发时机")
        i_state = col(header, "用户当前状态")
        i_want = col(header, "用户想完成什么")
        i_help = col(header, "系统应该提供什么帮助")
        i_pri = col(header, "优先级")
        i_freq = col(header, "发生频次")
        i_fall = col(header, "失败兜底")
        i_who = col(header, "受影响角色")

        if header and len(rows) < 15:
            add(E, "A-20", "M3 场景表只有 %d 行，至少 15 行（十一维扫完不可能只有这么点）" % len(rows))
        p0 = [r for r in rows if cell(r, i_pri).upper().startswith("P0")]
        if header and len(p0) < 5:
            add(E, "A-20", "P0 场景只有 %d 条，至少 5 条——没分主次等于没排优先级" % len(p0))

        for r in rows:
            name = cell(r, i_name)
            bad = [w for w in IMPLEMENT_NOUNS if w in name]
            reportish = [w for w in ("报表", "报告") if w in name]
            if bad:
                add(E, "A-21", "场景名「%s」含实现名词「%s」：这是方案不是场景" % (name, bad[0]))
            elif reportish:
                want = cell(r, i_want)
                if any(h in want for h in DELIVERY_HINTS):
                    add(W, "A-21", "场景名「%s」含「%s」，但『想完成什么』是交付语义（%s），"
                                   "按业务对象放行" % (name, reportish[0], want[:16]))
                else:
                    add(E, "A-21", "场景名「%s」含实现名词「%s」：这是方案不是场景"
                        % (name, reportish[0]))

            miss = [n for n, v in (("场景名称", name), ("触发时机", cell(r, i_trig)),
                                   ("用户当前状态", cell(r, i_state)),
                                   ("用户想完成什么", cell(r, i_want)),
                                   ("系统应该提供什么帮助", cell(r, i_help)),
                                   ("发生频次", cell(r, i_freq))) if not v]
            if miss:
                add(E, "A-22", "场景「%s」有 %d 个字段是空的：%s"
                    % (name or "(无编号)", len(miss), "、".join(miss)))
            trig = cell(r, i_trig)
            # 空话黑名单：包含匹配、命中即 ERROR、不看长度。
            # 反向用白名单会误杀「换版生效日」「交接班前 10 分钟」这类真时间，所以只拦空话。
            VAGUE_TRIG = ("需要时", "需要的时候", "视情况", "看情况", "随时", "合适的时",
                          "必要时", "按需", "待定", "业务需要", "计划安排", "有异常时")
            hit = [w for w in VAGUE_TRIG if w in trig]
            if trig and hit:
                add(E, "A-22", "场景「%s」的触发时机是空话「%s」（命中「%s」）：要写时间点或事件"
                    % (name, trig, hit[0]))
            elif trig and len(trig) < 6:
                add(E, "A-22", "场景「%s」的触发时机只有 %d 字：「%s」看不出什么时候发生"
                    % (name, len(trig), trig))
            elif trig and not re.search(r"当|后|时|每|\d|接到|到货|建单|换版|发版|生效|盘点|结账|交接|扫码|停线", trig):
                add(W, "A-22", "场景「%s」的触发时机「%s」看不出是时间还是事件" % (name, trig))
            state = cell(r, i_state)
            if state in ("正常", "在工位上", "良好", "一般", "常态"):
                add(E, "A-22", "场景「%s」的用户当前状态「%s」是空话：要写手部状态/信号/姿势/光线"
                    % (name, state))

        for r in p0:
            name = cell(r, i_name)
            fall = cell(r, i_fall)
            if not fall or fall in ("提示用户", "提示", "—", "-", "无"):
                add(E, "A-23", "P0 场景「%s」的失败兜底是「%s」——上线后现场一定用纸条绕过" % (name, fall))
            if not cell(r, i_who):
                add(E, "A-23", "P0 场景「%s」没写受影响角色：谁在等这个结果" % name)

    total = mapped = excluded = pending = 0
    if find_sec(secs, "覆盖矩阵") is None:
        add(E, "A-24", "M3 缺「## 覆盖矩阵」节——穷举的判定就是这张矩阵")
    else:
        header, rows = grab(find_sec(secs, "覆盖矩阵"), "M3_MATRIX", "A-24", "M3 覆盖矩阵")
        if header:
            total, mapped, excluded, pending = check_matrix_counts(gate, header, rows, confirmed_m3)

    if find_sec(secs, "待确认清单") is None:
        add(E, "A-26", "M3 缺「## 待确认清单」节")
    else:
        header, rows = grab(find_sec(secs, "待确认清单"), "M3_PENDING", "A-26", "M3 待确认清单")
        if header and len(rows) > 7:
            add(E, "A-26", "待确认清单 %d 条 > 7：倒 20 条给用户，他一条都不会回" % len(rows))
        i_sug, i_con, i_ans = (col(header, "我给的建议"), col(header, "你不定会怎样"),
                               col(header, "你的回答"))
        for r in rows:
            if not cell(r, i_sug):
                add(E, "A-26", "待确认项「%s」没给建议：只给问题不给建议，是把判断推回给用户" % cell(r, 1))
            if not cell(r, i_con):
                add(E, "A-26", "待确认项「%s」没写『你不定会怎样』" % cell(r, 1))
            if confirmed_m3 and not cell(r, i_ans):
                add(E, "A-26", "M3 已确认，但待确认项「%s」的『你的回答』是空的" % cell(r, 1))
    return scen_rows, p0


def check_m4(path, p0_ids):
    secs = sections(read(path))
    states_used, machine_states = set(), set()
    flow_rows, branch_rows = [], []
    if find_sec(secs, "主流程") is None:
        add(E, "A-30", "M4 缺「## 主流程」节")
    else:
        header, rows = grab(find_sec(secs, "主流程"), "M4_FLOW", "A-30", "M4 主流程表")
        flow_rows = rows
        if header and len(rows) < 6:
            add(E, "A-30", "主流程只有 %d 行，至少 6 行" % len(rows))
        i_change = col(header, "状态变化")
        i_batch = col(header, "批量粒度")
        for r in rows:
            empties = [COLS["M4_FLOW"][i] for i, c in enumerate(r) if i < 9 and not c]
            if empties:
                add(E, "A-30", "主流程第 %s 步有空格：%s" % (cell(r, 0) or "?", "、".join(empties)))
            ch = cell(r, i_change)
            if ch and not re.match(r"^\S+\s*→\s*\S+$", ch):
                add(E, "A-30", "主流程第 %s 步的状态变化「%s」不是 `X → Y`（写「提交后状态更新」推不出按钮可用性）"
                    % (cell(r, 0), ch))
            for part in re.split(r"\s*→\s*", ch) if ch else []:
                if part.strip():
                    states_used.add(part.strip())
        if header and rows:
            i_batch = col(header, "批量粒度")
            if not any("批" in cell(r, i_batch) for r in rows):
                add(E, "A-33", "主流程没有任何一步是「批」粒度：制造业流程必然有批量环节")
            empty_batch = [cell(r, 0) for r in rows if not cell(r, i_batch)]
            if empty_batch:
                add(E, "A-33", "主流程第 %s 步的批量粒度为空" % "、".join(empty_batch))

    if find_sec(secs, "分支流程") is not None:
        header, rows = grab(find_sec(secs, "分支流程"), "M4_BRANCH", "A-32", "M4 分支流程表")
        branch_rows = rows

    if find_sec(secs, "状态机") is None:
        add(E, "A-31", "M4 缺「## 状态机」节")
    else:
        header, rows = grab(find_sec(secs, "状态机"), "M4_STATE", "A-31", "M4 状态机表")
        if header and len(rows) < 3:
            add(E, "A-31", "状态机只有 %d 行，至少 3 个状态迁移" % len(rows))
        i_state, i_to = col(header, "状态"), col(header, "→ 目标状态")
        src, dst = set(), set()
        for r in rows:
            if cell(r, i_state):
                src.add(cell(r, i_state))
            if cell(r, i_to):
                dst.add(cell(r, i_to))
        machine_states = src | dst
        for s in sorted(states_used - machine_states):
            add(E, "A-31", "主流程里出现状态「%s」，但状态机表里没有——状态集必须闭合" % s)
        if src - dst and not (src & dst):
            add(E, "A-31", "状态机存在只进不出的死状态：%s" % "、".join(sorted(src - dst)))

    # A-32：P0 场景必须落在流程里
    if flow_rows or branch_rows:
        covered = set()
        for r in flow_rows + branch_rows:
            for c in r:
                covered.update(re.findall(r"S\d+", c))
        miss = [s for s in p0_ids if s not in covered]
        if miss:
            add(E, "A-32", "P0 场景 %s 没有出现在主流程或分支流程里：P0 不上流程，等于没做"
                % "、".join(miss))

    if find_sec(secs, "断点") is None:
        add(E, "A-34", "M4 缺「## 断点」节")
    else:
        header, rows = grab(find_sec(secs, "断点"), "M4_BREAK", "A-34", "M4 断点表")
        if header and not rows:
            add(E, "A-34", "断点表是空的：没有一个断点的流程，说明没想上线后现场怎么绕过")
        i_bypass = col(header, "上线后用户可能怎么绕过")
        for r in rows:
            if not cell(r, i_bypass):
                add(E, "A-34", "断点第 %s 步没写用户会怎么绕过" % cell(r, 0))


def check_m5(path):
    secs = sections(read(path))
    if find_sec(secs, "异常清单") is None:
        add(E, "A-40", "M5 缺「## 异常清单」节")
        return
    header, rows = grab(find_sec(secs, "异常清单"), "M5_EXC", "A-40", "M5 异常清单")
    if not header:
        return
    if len(rows) < 12:
        add(E, "A-40", "异常清单只有 %d 行，12 类每类至少 1 行" % len(rows))

    covered, orphan = set(), []
    for r in rows:
        cls = cell(r, 0)
        hit = classify(cls)
        if hit:
            covered.add(hit)
        else:
            orphan.append(cls or "(空类别)")
    miss = [c for c in EXC_ORDER if c not in covered]
    if miss:
        add(E, "A-40", "异常清单未覆盖 %d/12 类：%s" % (len(miss), "、".join(miss)))
    for o in orphan:
        add(W, "A-40", "异常行类别「%s」归不进 12 类，确认是否重复归类或漏了类别" % o)

    i_impact = col(header, "影响（量化）")
    i_fix = col(header, "产品处理建议（必须含降级路径）")
    i_trace = col(header, "对应场景/流程步")
    vague = 0
    for r in rows:
        impact = cell(r, i_impact)
        if not re.search(r"\d|无法量化", impact):
            vague += 1
            if vague <= 3:
                add(E, "A-41", "影响必须量化（条/分钟/小时/百分数），「%s」不算" % (impact or "(空)"))
        elif "无法量化" in impact and len(impact) < 12:
            add(E, "A-41", "写「无法量化」必须在同一格写明原因")
        fix = cell(r, i_fix)
        if fix and not re.search(r"手工|手输|先存|暂存|后补|补录|电话|打印|纸质|接受后果|人工|留痕|降级", fix):
            add(E, "A-42", "处理建议「%s…」没有降级动作：只写「提示用户」等于没设计" % fix[:12])
    if vague > 3:
        add(E, "A-41", "共有 %d 行影响没量化" % vague)

    traced = 0
    for r in rows:
        trace = cell(r, i_trace)
        if re.search(r"S\d+|第\s*\d+\s*步", trace):
            traced += 1
    if traced < 3:
        add(E, "A-43", "异常清单里只有 %d 行能追到具体场景或流程步（至少 3 行）" % traced)

    if find_sec(secs, "降级路径汇总") is None:
        add(W, "A-44", "M5 缺「## 降级路径汇总」节")
    else:
        header, drows = grab(find_sec(secs, "降级路径汇总"), "M5_DEGRADE", "A-44", "M5 降级路径汇总表")
        if header and len(drows) < 3:
            add(W, "A-44", "降级路径汇总只有 %d 行，至少 3 行" % len(drows))
        i_fill = col(header, "恢复后怎么补数据")
        for r in drows:
            if not cell(r, i_fill):
                add(W, "A-44", "降级「%s」没写恢复后怎么补数据（补数是研发最关心的）" % cell(r, 0))


def check_m6(path, gate):
    secs = sections(read(path))
    roles = ["资深研发", "测试负责人", "业务负责人", "现场使用者"]
    waived = ((gate or {}).get("waived") or {}).get("reviewRoles") or {}

    missing = [r for r in roles if find_sec(secs, r) is None]
    if missing:
        add(E, "A-50", "M6 缺角色小节：%s（删节要在该节写 waived + 原因，不许直接删）"
            % "、".join(missing))
    any_waived = False
    for r, cfg in waived.items():
        if isinstance(cfg, dict) and cfg.get("waived"):
            any_waived = True
            if not cfg.get("reason"):
                add(E, "A-50", "角色「%s」被 waived 但没写原因" % r)
    for role in roles:
        blk = find_sec(secs, role)
        if blk is None:
            continue
        if "waived" in blk:
            any_waived = True
            if len(re.sub(r"waived.*", "", blk).strip()) < 8:
                add(E, "A-50", "「%s」被 waived，但没写原因" % role)
            continue
        header, rows = grab(blk, "M6_Q", "A-51", "M6 %s 问题表" % role)
        if not header:
            continue
        if len(rows) < 10:
            add(E, "A-51", "「%s」只有 %d 个问题，要求 ≥10" % (role, len(rows)))
        i_q = col(header, "问题")
        for row in rows:
            q = cell(row, i_q)
            if not re.search(r"[？?]", q):
                add(E, "A-51", "「%s」的问题「%s」不是疑问句" % (role, q[:18]))
            if not (re.search(r"S\d+", q) or re.search(r"P[012]", q) or
                    re.search(r"待|已|状态", q) or len(q) >= 12):
                add(E, "A-51", "「%s」的问题「%s」没点名具体对象" % (role, q[:18]))
            if re.search(r"建议|优化|提升|加强|注意|关注", q) and not re.search(r"[？?]", q):
                add(E, "A-52", "「%s」写成结论了：「%s」" % (role, q[:18]))
    if any_waived:
        add(W, "A-50b", "存在 waived 的角色：已记录在案，风险表里要有对应风险")

    risk = find_sec(secs, "最大 5 个风险")
    if risk is None:
        add(E, "A-53", "M6 缺「## 最大 5 个风险」节")
    else:
        header, rows = grab(risk, "M6_RISK", "A-53", "M6 风险表")
        if header and len(rows) != 5:
            add(E, "A-53", "风险表恰好 5 行，实际 %d 行" % len(rows))
        i_when = col(header, "上线后多久会爆")
        for r in rows:
            w = cell(r, i_when)
            if not re.search(r"第\s*[\d一二三四五六七八九十]+\s*(次|天|周|个月|批)|上线即爆|"
                             r"\d+\s*(天|周|个月|小时)|第一次|首次", w):
                add(E, "A-53", "「上线后多久会爆」必须是时间量（第 N 次 / N 天 / 第一次月结），"
                               "实际写「%s」" % (w or "(空)"))

    concl = find_sec(secs, "结论")
    if concl is None:
        add(E, "A-54", "M6 缺「## 结论」节")
    else:
        if not re.search(r"不能开工|能开工", concl):
            add(E, "A-54", "结论必须是「能开工 / 不能开工」二选一，不许写「基本可行，注意风险」")
        items = list_items(concl)
        if items != 3:
            add(E, "A-54", "结论下的前置事项要恰好 3 条，实际 %d 条" % items)


def classify(cls):
    cls = (cls or "").strip()
    for name in EXC_ORDER:          # 先精确，避免「历史数据兼容」被判成「数据」
        if cls == name:
            return name
    for name in EXC_ORDER:
        if name in cls:
            return name
    best = None
    for name, kws in EXC_CLASSES:
        for kw in kws:
            if kw in cls and (best is None or len(kw) > best[1]):
                best = (name, len(kw))
    return best[0] if best else None


# ---------------------------------------------------------------- 通用判据
def check_common(d, gate, files, stage=0):
    """跨阶段 6 条：A-60 / A-60b / A-61 / A-62 / A-63 / A-64。

    --stage 1 与 --stage 2 都必须调用本函数（否则这 6 条掉缝里）；
    内部只按 stage 收窄「查哪几步」，不跳过任何一条判据。
    """
    want = {s["no"] for s in steps_of(stage)}
    declared = {x.get("no"): x for x in (gate.get("steps") or [])}

    # A-60 虚报进度
    for no in sorted(want):
        st = declared.get(no) or {}
        if st.get("status") in ("done", "skipped") and not os.path.isfile(
                os.path.join(d, st.get("file") or "")):
            add(E, "A-60", "第 %s 步标为 %s，但 %s 不存在（虚报进度）"
                % (no, st.get("status"), st.get("file")))

    # A-60b 主表行数登记是否与文件一致（偏差 >20% 才报，容忍手工调整）
    for st in steps_of(stage):
        p = os.path.join(d, st["file"])
        n = (declared.get(st["no"]) or {}).get("rows")
        if not os.path.isfile(p) or not isinstance(n, int) or n <= 0:
            continue
        real = primary_rows(sections(read(p)), st["no"])
        if real and abs(n - real) / float(real) > 0.20:
            add(W, "A-60b", "%s 登记 %d 行，实际主表 %d 行（偏差 >20%%）：rows 是给人快速判断进度的，"
                             "差太远就失去参考价值" % (st["file"], n, real))

    # A-61 分步痕迹（只在本段内比：跨段先后由 A-25 第⑤重兜）
    mt = [(no, mtime_aware(os.path.join(d, (declared.get(no) or {}).get("file") or "")))
          for no in sorted(want)
          if os.path.isfile(os.path.join(d, (declared.get(no) or {}).get("file") or ""))]
    mt.sort()
    for i in range(1, len(mt)):
        if mt[i][1] < mt[i - 1][1]:
            add(W, "A-61", "第 %s 步的文件比第 %s 步更早落盘：一次写完，等于没分步"
                % (mt[i][0], mt[i - 1][0]))
            break

    # A-62/63/64 按本段已有文件遍历；A-63 的词表按 stage 换表
    table = OUT_OF_SCOPE[stage] if stage in OUT_OF_SCOPE else OUT_OF_SCOPE[1]
    for f in files:
        txt = read(os.path.join(d, f))
        hits = [w for w in FORBIDDEN_PHRASES if w in txt]
        if hits:
            add(E, "A-62", "%s 出现含糊词：%s" % (f, "、".join(hits)))
        hits = [w for w in table if w in txt]
        if hits:
            add(E, "A-63", "%s 越界到本段不该碰的层：出现 %s（本段词表：%s）"
                % (f, "、".join(hits), "/".join(table)))
        hits = [w for w in EMPTY_WORDING if w in txt]
        if hits:
            add(E, "A-64", "%s 出现空话：%s" % (f, "、".join(hits)))


# ---------------------------------------------------------------- 主流程
def check(d, stage=0):
    """stage=0 全量；1 = M1~M3；2 = M4~M6。跨阶段 6 条始终跑（见 check_common）。"""
    want = steps_of(stage)
    files = [s["file"] for s in want]
    gate = load_state(d)
    if gate is None:
        return

    if gate.get("stateVersion") != STATE_VERSION:
        add(E, "A-60", "stateVersion 必须为 %s，实际 %r" % (STATE_VERSION, gate.get("stateVersion")))

    declared = {st.get("no"): st for st in (gate.get("steps") or [])}
    for st in want:
        if st["no"] not in declared:
            add(E, "A-60", "_state.json 的 steps 未登记第 %d 步（%s）" % (st["no"], st["file"]))
        p = os.path.join(d, st["file"])
        if not os.path.isfile(p):
            if (declared.get(st["no"]) or {}).get("status") in ("done", "skipped"):
                add(E, "A-60", "第 %d 步标为 done，但 %s 不存在（虚报进度）" % (st["no"], st["file"]))
            else:
                add(E, "A-00", "第 %d 步 %s 缺 %s" % (st["no"], st["title"], st["file"]))
            continue
        secs = sections(read(p))
        for kw in st["secs"]:
            if find_sec(secs, kw) is None:
                add(E, "A-1x", "%s 缺必需小节「## %s」" % (st["file"], kw))
            elif len(find_secs(secs, kw)) > 1:
                add(W, "A-1x", "%s 有多个小节命中「%s」：解析只取第一个" % (st["file"], kw))

    existing = [f for f in files if os.path.isfile(os.path.join(d, f))]
    if len(existing) < len(want):
        label = {0: "六份", 1: "第 1 段三份（M1~M3）", 2: "第 2 段三份（M4~M6）"}[stage]
        add(E, "A-00", "%s 产物不齐：已有 %d/%d 份（%s）"
            % (label, len(existing), len(want), "、".join(existing) or "无"))

    # 卡点 M1 / M6（WARN 级）；M1 属第 1 段，M6 属第 2 段
    gates = [("M1", "M1（第 1 步：真问题方向）"), ("M6", "M6（第 6 步：结论被业务方看过）")]
    if stage == 1:
        gates = gates[:1]
    elif stage == 2:
        gates = gates[1:]
    for mid, label in gates:
        c = gate_confirm(gate, mid)
        if not c.get("confirmed"):
            add(W, "A-25b" if mid == "M1" else "A-25c", "%s 未确认（不拦，但要在交付里说明）" % label)
        elif not c.get("by") or not c.get("at"):
            add(W, "A-25b" if mid == "M1" else "A-25c", "%s 已确认但缺 by/at：无签署人的确认等于没确认" % label)

    if stage in (0, 1):
        if os.path.isfile(os.path.join(d, "M1-problem.md")):
            check_m1(os.path.join(d, "M1-problem.md"))
        if os.path.isfile(os.path.join(d, "M2-roles.md")):
            check_m2(os.path.join(d, "M2-roles.md"))

    confirmed_m3 = check_gate_m3(d, gate) if stage in (0, 1) else False

    if stage in (0, 1):
        check_prd_stage1(d, gate)

    # M3 是第 2 段的输入：p0_ids 必须读到，否则 A-32 无从判
    p0_ids = []
    if os.path.isfile(os.path.join(d, "M3-scenarios.md")):
        scen, p0 = check_m3(os.path.join(d, "M3-scenarios.md"), gate, confirmed_m3) \
            if stage in (0, 1) else (None, scenarios_p0(d))
        p0_ids = [cell(r, 0) for r in p0 if cell(r, 0)]

    if stage in (0, 2):
        if os.path.isfile(os.path.join(d, "M4-flows.md")):
            check_m4(os.path.join(d, "M4-flows.md"), p0_ids)
        if os.path.isfile(os.path.join(d, "M5-exceptions.md")):
            check_m5(os.path.join(d, "M5-exceptions.md"))
        if os.path.isfile(os.path.join(d, "M6-review.md")):
            check_m6(os.path.join(d, "M6-review.md"), gate)
        check_p1_disposition(d)
        check_prd_stage2(d, gate)

    if stage in (0, 1):
        check_gate_vs_m3(d, gate)
        check_decision_counts(gate)
    check_common(d, gate, existing, stage)

    # A-36（移植自 check_gate 的 G-10）：proto 的写入时间早于出口确认 = 事后补签。
    # 这条挡不住「改了内容」（那是 hash 的活），专挡「先画完原型再回头补分析文档」。
    if stage in (0, 2):
        check_handoff_time(d, gate)
        check_semantic_only(d, gate)
        check_stage3_stale(d, gate)

    # 未解决待确认项（M4 存在即判，两段都会跑到）
    for q in (gate.get("openQuestions") or []):
        if q.get("status") == "open" and confirmed_m3 and os.path.isfile(os.path.join(d, "M4-flows.md")):
            add(E, "A-24", "openQuestions 的「%s」还开着，M4 已经开写：确认前必须 resolved 或 assumed"
                % q.get("id"))


# ---------------------------------------------------------------- A-69 PRD 正文十节
# 02 的对外交付物是 PRD.md（评审/开发/测试看这一份），M4/M5/M6 是底稿。
# 十节骨架取自《AI-PRD 模板拆解》，另加制造业三件套——那份模板自己承认缺这三样。
PRD_KIT = [("5.1", "权限矩阵"), ("5.2", "状态机"), ("5.3", "字段字典")]
PRD_SECS = "一二三四五六七八九十"
PRD_PLACEHOLDER = "第 2 段填"


def _prd_section(text, num):
    """取某一节的正文（不含标题行）。按编号前缀切，容忍标题文字被改。"""
    i = PRD_SECS.find(num)
    nxt = PRD_SECS[i + 1] if i + 1 < len(PRD_SECS) else ""
    pat = (r"^#{1,4}\s*%s、.*?(?=^#{1,4}\s*%s、|\Z)" % (num, nxt)) if nxt \
        else (r"^#{1,4}\s*%s、.*" % num)
    m = re.search(pat, text, re.M | re.S)
    if not m:
        return None
    seg = m.group(0)
    return seg.split("\n", 1)[1] if "\n" in seg else ""


def check_prd_stage1(d, gate):
    """A-69（01 出口）：骨架齐、前三节写实、四~十 必须留占位、需求类型已声明。

    第四~十节由 01 写实是越界：01 手里没有 proto，写流程/功能/字段只能是猜，
    而 02 会把猜出来的结构当既定事实继承——这和 A-67 管的是同一类病。
    """
    p = os.path.join(d, "PRD.md")
    if not os.path.isfile(p):
        add(E, "A-69", "01 出口缺 PRD.md：它是两段共同的对外交付物——01 起骨架、02 补全")
        return
    text = read(p)
    for sec in PRD_SECS:
        if not re.search(r"^#{1,4}\s*%s、" % sec, text, re.M):
            add(E, "A-69", "PRD.md 缺第「%s」节标题：十节要一次建齐，否则 02 以为只有前面几节" % sec)
    for sec in "一二三":
        body = _prd_section(text, sec) or ""
        if PRD_PLACEHOLDER in body or len(body.strip()) < 30:
            add(E, "A-69", "PRD.md 第「%s」节没写实：这是 01 该交的三节之一（内容 <30 字或仍是占位）" % sec)
    # 时点开关：02 已签收的项目回跑 --stage 1，四~十 写实是合法的（那是 02 补的）。
    # 和 A-67 同一条规矩——同一个文件在不同时点有两种合法形态，判据必须知道"现在轮到谁"。
    sealed2 = ((gate.get("stages") or {}).get("2") or {}).get("sealed")
    if not sealed2:
        for sec in "四五六七八九十":
            body = _prd_section(text, sec) or ""
            if body.strip() and PRD_PLACEHOLDER not in body:
                add(E, "A-69", "PRD.md 第「%s」节被 01 写实了：四~十 是 02 的活（流程/功能/数据/"
                    "异常/指标/阶段/待确认），01 手里没有 proto，写了只能是猜" % sec)
                break
    m1 = os.path.join(d, "M1-problem.md")
    if os.path.isfile(m1) and not re.search(r"需求类型[:：]\s*(AI\s*型|非\s*AI\s*型)", read(m1)):
        add(E, "A-69", "M1 没写「需求类型：AI 型 / 非 AI 型」：02 靠它决定第六节写评测集还是数据校验")


def check_prd_stage2(d, gate):
    """A-70（02 出口）：四~十 全部写实、无占位残留、七列齐、三件套在、命令不造假、类型口径对。"""
    p = os.path.join(d, "PRD.md")
    if not os.path.isfile(p):
        add(E, "A-70", "02 出口缺 PRD.md：01 起的骨架必须在同一个文件上补完，不许另写一份")
        return
    text = read(p)

    for sec in PRD_SECS:
        if not re.search(r"^#{1,4}\s*%s、" % sec, text, re.M):
            add(E, "A-70", "PRD.md 缺第「%s」节" % sec)

    # 占位没补 = 02 交的是空壳
    stub = [s for s in "四五六七八九十" if PRD_PLACEHOLDER in (_prd_section(text, s) or "")]
    if stub:
        add(E, "A-70", "PRD.md 还有占位没补：第 %s 节仍是「第 2 段填」——02 的活没干完"
            % "、".join(stub))

    # 第五节七列：必须剔掉标题行再判（`## 五、功能需求与验收标准` 标题里就有「验收标准」）
    body5 = _prd_section(text, "五") or ""
    for col in ("触发条件", "输入", "输出", "异常", "验收标准"):
        if col not in body5:
            add(E, "A-70", "PRD.md 第五节缺列「%s」：七列缺一列，测试就转不成用例" % col)

    for k, name in PRD_KIT:
        if k not in text and name not in text:
            add(W, "A-70", "PRD.md 未写「%s」：中后台评审必问；确实没有就在 M6 写明理由" % name)

    # 命令编号回查 proto：PRD 不许凭空编命令
    proto = gate.get("protoFile") or ""
    if not proto:
        found = sorted(f for f in os.listdir(d) if f.endswith(".proto.json")) if os.path.isdir(d) else []
        proto = found[0] if len(found) == 1 else ""
    ppath = os.path.join(d, proto) if proto else ""
    if proto and os.path.isfile(ppath):
        try:
            ids = {c.get("id") for c in (json.loads(read(ppath)).get("capabilities") or [])}
        except Exception:
            ids = None
        if ids is not None:
            ghost = sorted(set(re.findall(r"cap-[a-z0-9][a-z0-9-]*", text)) - ids)
            if ghost:
                add(E, "A-70", "PRD.md 提到契约里没有的命令：%s。PRD 不许凭空编命令——先加进 "
                    "proto.capabilities 再写" % "、".join(ghost[:6]))

    # 类型口径：AI 型要有评测，非 AI 型不许出现评测集（WARN，两向都只提醒）
    # 类型从 M1 原文解析，不读 stages["1"].export.demandType——
    # 那个字段由 derive() 从产物重算，人写的值会被冲掉（与 cleanHash 被覆盖同一个坑）。
    # 事实的源头是 M1 里那行声明，判据只认源头。
    dt = ""
    m1 = os.path.join(d, "M1-problem.md")
    if os.path.isfile(m1):
        mm = re.search(r"需求类型[:：]\s*(AI\s*型|非\s*AI\s*型)", read(m1))
        dt = mm.group(1) if mm else ""
    body6 = _prd_section(text, "六") or ""
    if "AI" in dt and "非" not in dt:
        if "评测" not in body6 and "样本" not in body6:
            add(W, "A-70", "需求类型是 AI 型，第六节却没写评测集与通过条件：上线后无法验收")
    elif "非" in dt:
        if "评测集" in body6:
            add(W, "A-70", "需求类型是非 AI 型，第六节却写了评测集：评审会问模型在哪、谁训的")

    # 已知边界（不实现）：proto.capabilities 没有 priority 字段，做不了
    # "P0 命令必须全部出现在 PRD" 的正向检查。要补得先给 capability 加 priority。


# ---------------------------------------------------------------- A-67 语义半边纯净度
# 02 只许写语义半边，渲染半边（组件树/交互/页面 PRD/页面态/命令承载）是 03 的活。
# 用白名单不用黑名单：黑名单只拦得到想得到的键，03 以后加 chartHints / annotationAnchors，
# 02 就可能跟着写进去。白名单让「02 能写什么」成为封闭集合，扩集要改常量、写理由。
#
# 【白名单必须从真实产物反推】顶层 17 个键 = shared/schemas/proto.schema.json 的 properties；
# 页面键 = 四个样例 pages[] 的并集；contract 子键 = 四个样例 contract 的并集
# （实跑：actor / doneWhen / entryFrom / owns / submitBoundary / task）。
# 凭「02 该写什么」正推必漏——第一版漏了 contract，02 连命令归属都交不出来。
TOP_ALLOWED = {
    "schemaVersion", "meta", "actors", "modules", "pages", "capabilities",
    "stateMachines", "dataModel", "dataSources", "requirements", "decisions",
    "fieldCatalog", "guards", "openQuestions", "slices", "components", "annotations",
}
# 不在 schema 里、属 03 的容器扩展
TOP_FORBIDDEN = {"nav", "skinTokens"}

PAGE_ALLOWED = {"id", "moduleId", "target", "route", "title", "layout", "entity",
                "listRole", "parentId", "subtitle", "notApplicableStates", "contract"}
PAGE_FORBIDDEN = {"componentTree", "interactions", "prd", "states", "pda"}

CONTRACT_ALLOWED = {"owns", "actor", "doneWhen", "entryFrom", "submitBoundary", "task"}

# 从四个样例 capabilities[] 的并集反推。label 少了会让 L2-52（命令必须有用户可见动作名）
# 与 A-67 直接打架：一个说必须有，一个说写了就错。
CAP_ALLOWED = {"id", "name", "label", "actor", "entity", "from", "to", "policy",
               "reason", "guard", "stage", "sameActorOk", "target", "placement", "pageIds"}
CAP_FORBIDDEN = {"ui"}

# 这两个键在 schema 的 required 里（L1-01 要它们存在），但值只能为空——
# 组件登记与标注都是 03 的产物。允许空数组、非空即红，这样 02 不会过不了自己的闸门。
MUST_BE_EMPTY = {"components", "annotations"}


def check_semantic_only(d, gate):
    """A-67：02 交出的 proto 不许含渲染半边。

    判定只有两维：**内容里有没有渲染键** × **这份内容是不是 02 交的那一版**。
    不问"谁干的"——同一个文件会被 02 和 03 先后写，出处本来不可知；问出处就会得到
    一个可以被"03 构建过"洗白的判据（那样 02 越界写完让 03 build 一次就过关了）。

        无渲染键                     → 不报（干净，与出处无关）
        有渲染键 + 无 sealed                          → ERROR：02 从没交过一份纯净契约
        有渲染键 + sealed 但 M4/M5/M6 变了            → ERROR（**聚合一条**）：签收已失效，该重做
        有渲染键 + sealed 且 hash 不等、md 未变        → WARN：签收后文件被改过（03 追加的就是这类）
        有渲染键 + sealed 且 hash 相等、md 未变        → ERROR：签收那版就含渲染键，sealed 不可信
        --seal 时一律不降级（STRICT）：签收前契约必须干净

        签收只在「契约和 md 都没动过」时有效。md 一改，旧签收失效——
        否则会与 A-68 形成"双 WARN"，而双 WARN 在流程里就是静默放行。
        md 变了这一支聚合成一条：判据的条数应该等于用户要做的事的数量，不是被检查的键的数量。
    """
    proto = gate.get("protoFile") or ""
    if not proto:
        found = sorted(f for f in os.listdir(d) if f.endswith(".proto.json")) if os.path.isdir(d) else []
        proto = found[0] if len(found) == 1 else ""
    ppath = os.path.join(d, proto) if proto else ""
    if not (proto and os.path.isfile(ppath)):
        return
    try:
        doc = json.loads(read(ppath))
    except ValueError as exc:
        add(E, "A-67", "%s 不是合法 JSON：%s" % (proto, exc))
        return

    hits = []

    # ① 顶层键
    for k in doc:
        if k in TOP_FORBIDDEN:
            hits.append("%s 写了容器级键 %s：这是第 3 段的活，02 只交语义半边" % (proto, k))
        elif k not in TOP_ALLOWED:
            hits.append("%s 顶层键 %s 不在 02 的白名单里（schema 只有 %d 个键）："
                        "渲染半边由 03 在同一个文件上追加" % (proto, k, len(TOP_ALLOWED)))

    # ② 页面项
    for i, pg in enumerate(doc.get("pages") or []):
        if not isinstance(pg, dict):
            continue
        for k in pg:
            if k in PAGE_FORBIDDEN:
                hits.append("%s 写了渲染半边（pages[%d].%s）：这是第 3 段的活。"
                            "02 只交语义半边；页面结构由 03 在同一个文件上追加" % (proto, i, k))
            elif k not in PAGE_ALLOWED:
                hits.append("%s 的 pages[%d] 出现 %s：02 的页面项只允许 %s"
                            % (proto, i, k, "/".join(sorted(PAGE_ALLOWED))))
        c = pg.get("contract")
        if isinstance(c, dict):
            for k in c:
                if k not in CONTRACT_ALLOWED:
                    hits.append("%s 的 pages[%d].contract 出现 %s：只允许 %s"
                                % (proto, i, k, "/".join(sorted(CONTRACT_ALLOWED))))

    # ③ modules：目录分组是 03 的活。02 手里只有页面骨架，写分组只能是猜，
    #    猜完 03 会当既定结构继承。要表达「这几页是一组」，用 pages[].parentId。
    #    （注：L2-74 不是空判据——它校验空壳组/跨模块挂载/同页两次，只是没有 pageGroups 时不遍历。）
    for i, m in enumerate(doc.get("modules") or []):
        if isinstance(m, dict) and "pageGroups" in m:
            hits.append("%s 的 modules[%d] 写了 pageGroups（页面目录分组）：02 只给页面骨架，"
                        "目录怎么组织是 03 按 parentId 归并出来的，不由 02 猜" % (proto, i))

    # ④ 命令：承载形式是 03 的决策
    for c in (doc.get("capabilities") or []):
        if not isinstance(c, dict):
            continue
        for k in c:
            if k in CAP_FORBIDDEN:
                hits.append("%s 的命令 %s 写了 ui（承载形式）：按钮弹框还是抽屉是 03 的决策"
                            % (proto, c.get("id") or "(无 id)"))
            elif k not in CAP_ALLOWED:
                hits.append("%s 的命令 %s 出现 %s：只允许 %s"
                            % (proto, c.get("id") or "(无 id)", k, "/".join(sorted(CAP_ALLOWED))))

    # ⑤ 组件登记与标注：键必须在（L1-01 要），值必须空
    for k in MUST_BE_EMPTY:
        v = doc.get(k)
        if isinstance(v, list) and v:
            hits.append("%s 的 %s 有 %d 条：组件登记与标注是第 3 段的活，02 交空数组"
                        % (proto, k, len(v)))

    if not hits:
        return

    # 先判内容，再判出处。出处只有一个客观依据：--seal 签收时记下的 protoHash。
    # 「谁写的」本身不可知（同一文件 02/03 先后写），拿它当开关必被洗白——
    # 用 html 指纹或 stage3 标记都会变成"02 越界写完让 03 跑一遍就过关"。
    cur = _proto_sha16(ppath)
    sealed = ((gate.get("stages") or {}).get("2") or {}).get("sealed") or {}
    sh = sealed.get("protoHash") or ""
    md_frozen = sealed.get("mdHashes") or {}
    md_changed = [f for f, h in md_frozen.items()
                  if h and artifact_hash(os.path.join(d, f)) != h]

    if not sh:
        # 【有意逐键，不是漏改】未签收时每个渲染键都是一处独立的越界，用户要逐个删，
        # 所以逐键报；而 md_changed 那一支报的是"契约整体过期"，是一件事，所以那边聚合成一条。
        # 两个分支粒度不同是有意的：条数应该等于用户要做的事的数量。
        # 下一轮若要统一粒度，先回答"未签收时用户要做几件事"——别直接当 bug 改掉。
        for m in hits:
            add(E, "A-67", m + "（02 还没签收过一份纯净契约：先用 --stage 2 --seal 签收）")
        return

    if md_changed:
        # 签收只在「契约和 md 都没动过」时有效。md 一改，旧签收失效，
        # 含渲染键就不再是"03 追加的"，而是"该重做了"。
        # 但这件事只有一件，所以聚合成一条——判据的条数应该等于用户要做的事的数量，
        # 不是被检查的键的数量（满配契约会一次报 20 多条，全是同一件事）。
        def cat_of(m):
            if ".prd" in m:
                return "pages[].prd"
            if "componentTree" in m:
                return "componentTree"
            if "interactions" in m:
                return "interactions"
            if "pageGroups" in m:
                return "pageGroups"
            if "写了 ui" in m or "capabilities" in m and "ui" in m:
                return "ui"
            if "components" in m or "annotations" in m:
                return "components/annotations"
            if "顶层键" in m:
                return "顶层键"
            return "其他"
        cats, order = {}, []
        for m in hits:
            k = cat_of(m)
            if k not in cats:
                cats[k] = 0
                order.append(k)
            cats[k] += 1
        detail = " / ".join("%s×%d" % (k, cats[k]) for k in order)
        VERBOSE_HITS.extend(hits)
        add(E, "A-67", "%s 契约在签收后被改过，且含 %d 处渲染键（%s）：签收已失效。"
                       "先清掉渲染键 → 重出契约（--stage 2）→ 重签（--stage 2 --seal）。"
                       "逐处清单见 --verbose。"
            % (proto, len(hits), detail or "见 --verbose"))
        return

    if STRICT:
        for m in hits:
            add(E, "A-67", m + "（签收模式：签收前契约必须干净，不允许带渲染键）")
        return

    if sh == cur:
        # 理论上不可能：--seal 拒绝带病签收，所以"签收那版就含渲染键"意味着 sealed 被手改
        for m in hits:
            add(E, "A-67", m + "（当前契约与签收指纹一致却含渲染键：sealed 记录不可信，"
                               "清干净后重签）")
        return

    for m in hits:
        add(W, "A-67", m + "（签收后文件被改过：%s → %s。03 追加渲染键就是这一类；"
                           "若这是你自己回改契约，清干净后重签 --stage 2 --seal）" % (sh[:8], cur[:8]))


def _proto_sha16(path):
    """与 check_parity/C-24 同一算法、同一长度（16 位）。别再造一套 12 位的。"""
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def check_stage3_stale(d, gate):
    """A-68：02 签收之后，M4/M5/M6 又被改过 → 契约需重出重签。WARN。

    触发依据只有 sealed.mdHashes —— 和 A-67 用同一个 sealed 快照。判据守的时点只能有一个开关，
    两个就是两个真相（这也是 --mark / upstream / html 指纹三套方案被否掉的原因）。

    已知边界（不实现）：若有人直接改 proto 不动 md，A-68 不响，只有 A-67 的 WARN 会说"文件被改过"。
    02 的规矩是 proto 从 md 推，为这条加 proto 语义子集 hash 等于把"两区"再做一遍，不值。
    """
    sealed = ((gate.get("stages") or {}).get("2") or {}).get("sealed") or {}
    frozen = sealed.get("mdHashes") or {}
    if not frozen:
        return
    changed = []
    for f, h in sorted(frozen.items()):
        cur = artifact_hash(os.path.join(d, f))
        if cur and h and cur != h:
            changed.append(f)
    if changed:
        # 文案只说「共同事实导致的后果」，不说别的判据的等级或行为：
        #   ✅ "签收已失效：残留的渲染键现在算越界"（事实，不随判据调）
        #   ❌ "A-67 会把残留的渲染键按 ERROR 处理"（等级会变——这一轮就调了三次）
        add(W, "A-68", "第 2 段产物在签收后被改过（%s）：契约需重出并重签 —— "
                       "清掉渲染键 → --stage 2 重出 → --stage 2 --seal 重签。"
                       "签收已失效：残留的渲染键现在算越界，不再视作第 3 段追加的产物"
            % "、".join(changed))


def check_handoff_time(d, gate):
    """A-36（移植自 check_gate 的 G-10）：产物先写完、确认时间后补 = 事后补签。

    与 A-25 第④重（hash）方向相反，谁也替代不了谁：
      hash 挡「签了之后改内容」；A-36 挡「先写完再补签」。
    """
    proto = gate.get("protoFile") or ""
    if not proto:
        found = sorted(f for f in os.listdir(d) if f.endswith(".proto.json")) if os.path.isdir(d) else []
        proto = found[0] if len(found) == 1 else ""
    ppath = os.path.join(d, proto) if proto else ""
    if not (proto and os.path.isfile(ppath)):
        return
    # 新版没有 A3（切片与契约确认就是 02 自己的出口），对标点是 A2 评审签署 → 落到 M6 确认。
    # 兼容旧格式里叫 A2 的写法。
    c = gate_confirm(gate, "M6") or gate_confirm(gate, "A2")
    at = parse_time(c.get("at"))
    pm = mtime_aware(ppath)
    if not at:
        if not c.get("confirmed"):
            add(W, "A-36", "%s 的签署点未确认：无法判断契约是不是在确认之后落的（不拦，但交付里要说）" % proto)
    elif pm < at:
        add(E, "A-36", "%s 的写入时间早于签署时间 %s：属事后补签（契约先写完，再把确认补到它后面）"
            % (proto, c.get("at")))
    m6 = os.path.join(d, "M6-review.md")
    if os.path.isfile(m6) and pm < mtime_aware(m6):
        add(E, "A-36", "%s 的写入时间早于 M6-review.md：契约先写、评审后补" % proto)


def check_p1_disposition(d):
    """A-35：每个 P1 场景必须有下落。

    两条合法去向：进 M4 流程；或进 M6 的「后置批次」节（要写理由与兜底）。
    找不到才红。P1 清单只从 M3 的优先级列取，不从 export 复制（两份事实必漂）。
    """
    ids = _scene_ids_by_priority(d, "P1")
    if not ids:
        return
    m4p, m6p = os.path.join(d, "M4-flows.md"), os.path.join(d, "M6-review.md")
    m4txt = read(m4p) if os.path.isfile(m4p) else ""
    later, later_ids = "", set()
    if os.path.isfile(m6p):
        secs = sections(read(m6p))
        for k, v in secs.items():
            if "后置" in k or "下一批" in k:
                later = v
                break
        if later:
            header, rows = parse_table(later)
            i_fb = next((i for i, h in enumerate(header) if "兜底" in h), -1)
            for r in rows:
                sid = cell(r, 0)
                if not sid:
                    continue
                later_ids.add(sid)
                if i_fb < 0 or len(cell(r, i_fb)) < 4:
                    add(E, "A-35", "P1 场景 %s 进了后置批次，但没写兜底「今天先怎么过」" % sid)
    miss = []
    for sid in ids:
        if sid in later_ids:
            continue
        if re.search(r"(?<![A-Za-z0-9])%s(?![0-9])" % re.escape(sid), m4txt):
            continue
        miss.append(sid)
    if miss:
        add(E, "A-35", "P1 场景 %s 没有下落：既不在 M4 流程里，也没进 M6 的「后置批次」"
                       "（后置要写为什么不进本批 + 兜底）" % "、".join(miss))


def scenarios_p0(d):
    """第 2 段只读 M3 的 P0 编号，不重复跑 M3 的判据（那是第 1 段的闸门）。"""
    p = os.path.join(d, "M3-scenarios.md")
    if not os.path.isfile(p):
        return []
    secs = sections(read(p))
    blk = find_sec(secs, "场景表")
    if blk is None:
        return []
    header, rows = grab(blk, "M3_SCEN", "A-32", "M3 场景表")
    i_pri = col(header, "优先级")
    return [r for r in rows if cell(r, i_pri).upper().startswith("P0")]



def _stage3_line(d, gate):
    """第 3 段没有 M 文件，也就没有可推导的 status。这里不编一个假状态，
    只把能看到的产物如实说出来：未构建 / 已构建（指纹一致） / 产物过期。"""
    proto = gate.get("protoFile") or ""
    ppath = os.path.join(d, proto) if proto else ""
    if not (proto and os.path.isfile(ppath)):
        return "契约还没有，第 3 段无从开始"
    cur = _proto_sha16(ppath)
    cands = []
    if os.path.isdir(d):
        cands += [os.path.join(d, f) for f in os.listdir(d) if f.endswith(".html")]
        dist = os.path.join(d, "dist")
        if os.path.isdir(dist):
            cands += [os.path.join(dist, f) for f in os.listdir(dist) if f.endswith(".html")]
    seen = []
    for p in cands:
        try:
            head = open(p, encoding="utf-8", errors="ignore").read(3000)
        except OSError:
            continue
        m = re.search(r'name="prd-source" content="sha256:([0-9a-f]{16})"', head)
        if m:
            seen.append((os.path.basename(p), m.group(1)))
    if not seen:
        return "未构建（没有带 prd-source 指纹的容器）"
    hit = [n for n, h in seen if h == cur]
    if hit:
        return "已构建（%s 指纹与当前契约一致 %s）" % ("、".join(hit[:2]), cur)
    return "产物过期（%s 指纹 %s ≠ 当前契约 %s）→ 重出容器" % (seen[0][0], seen[0][1], cur)


def status(d):
    gate = load_state(d)
    if gate is None:
        return 2
    print("分析进度：%s（%s）" % (gate.get("product") or "(未命名)", d))
    cur = gate.get("current") or {}
    print("stateVersion %s · 当前第 %s 段 · 当前步 %s（%s）"
          % (gate.get("stateVersion"), gate.get("stage", "?"),
             cur.get("step", "?"), cur.get("file", "?")))
    print("=" * 64)
    print(pad("段", 4) + pad("步", 4) + pad("主题", 12) + pad("文件", 20)
          + pad("状态", 11) + pad("行数", 6) + "sha256")
    print("-" * 64)
    for st in STEPS:
        g = next((x for x in (gate.get("steps") or []) if x.get("no") == st["no"]), {})
        p = os.path.join(d, st["file"])
        rows = 0
        if os.path.isfile(p):
            rows = primary_rows(sections(read(p)), st["no"])
        h = (gate.get("artifacts") or {}).get(st["file"]) or artifact_hash(p) or "—"
        print(pad(str(st["stage"]), 4) + pad(str(st["no"]), 4) + pad(st["title"], 12)
              + pad(st["file"], 20) + pad(g.get("status") or "?", 11)
              + pad(str(rows) if rows else "—", 6) + str(h))
    print("-" * 64)
    print("第 3 段：%s" % _stage3_line(d, gate))
    print("-" * 64)

    conf = gate.get("confirmations") or {}
    for mid, label, strict in (("M1", "第 1 步 真问题方向", False),
                               ("M3", "第 3 步 场景与流程（硬闸门）", True),
                               ("M6", "第 6 步 结论交付", False)):
        c = conf.get(mid) or {}
        if mid == "M3":
            m3 = os.path.join(d, "M3-scenarios.md")
            cur = scene_hash(read(m3)) if os.path.isfile(m3) else ""
            stale = (c.get("contentHash") or "") and c.get("contentHash") != cur
            state = "已确认" if c.get("confirmed") else "未确认"
            if stale:
                state = "已确认，但场景表已改（hash 对不上）"
        else:
            state = "已确认" if c.get("confirmed") else "未确认"
        tail = "" if strict else "（不拦）"
        print("卡点 %-3s %-26s %s%s" % (mid, label, state, tail))

    opens = [q for q in (gate.get("openQuestions") or []) if q.get("status") == "open"]
    print("-" * 64)
    print("待确认 %d 条：%s" % (len(opens), "、".join(q.get("id", "?") for q in opens) or "无"))

    nxt = next((st for st in STEPS
                if (next((x for x in (gate.get("steps") or []) if x.get("no") == st["no"]), {})
                    .get("status") not in ("done",))), None)
    if not (conf.get("M3") or {}).get("confirmed") and nxt and nxt["no"] > 3:
        print("下一步：M3 未过，回第 3 步让用户确认场景（不许写 M4）")
    elif nxt:
        print("下一步：做第 %d 步 %s（%s）" % (nxt["no"], nxt["title"], nxt["file"]))
    else:
        print("下一步：六步已走完，跑一次校验再交付")
    return 0


def print_spec():
    """把 SPEC 打成 markdown 表：文档里的数字以这里为准，别手抄。"""
    total = sum(len(v) for _, _, v in DIMS)
    print("## 维度（%d 维 / 总格数 %d）\n" % (len(DIMS), total))
    print("| 编号 | 族名 | 格数 | 取值 |")
    print("|---|---|---|---|")
    for code, name, vals in DIMS:
        print("| %s | `%s` | %d | %s |" % (code, name, len(vals), " / ".join(vals)))
    print("\n## 异常（%d 类）\n" % len(EXC_CLASSES))
    print("、".join(n for n, _ in EXC_CLASSES))
    print("\n## 表格列名（逐字，顺序敏感）\n")
    for k, cols in COLS.items():
        print("- `%s`：%s" % (k, " | ".join(cols)))
    return 0


def do_hash(d):
    p = os.path.join(d, "M3-scenarios.md")
    if not os.path.isfile(p):
        print("找不到 %s" % p)
        return 2
    print(scene_hash(read(p)))
    return 0


def init(d, product, stage=0):
    """起骨架。stage=1 只出 M1~M3，stage=2 只出 M4~M6，0 出六份。"""
    if not os.path.isdir(TEMPLATES):
        print("找不到模板目录：%s" % TEMPLATES)
        return 2
    os.makedirs(os.path.join(d, "_draft"), exist_ok=True)
    for st in steps_of(stage):
        src = os.path.join(TEMPLATES, st["file"])
        dst = os.path.join(d, st["file"])
        if os.path.isfile(dst):
            continue
        if os.path.isfile(src):
            shutil.copyfile(src, dst)
        else:
            with open(dst, "w", encoding="utf-8") as f:
                f.write("# M%d %s\n\n" % (st["no"], st["title"]))
                for kw in st["secs"]:
                    f.write("## %s\n\n（待填）\n\n" % kw)
    sp = os.path.join(d, STATE_FILE)
    gp = os.path.join(d, LEGACY_FILE)
    if not os.path.isfile(sp) and os.path.isfile(gp):
        load_state(d)                       # 触发一次升级，打印提示
    elif not os.path.isfile(sp):
        now = datetime.now().astimezone().replace(microsecond=0).isoformat()
        state = {
            "stateVersion": STATE_VERSION,
            "product": product or "（待填）",
            "createdAt": now,
            "updatedAt": now,
            "stage": stage or 1,
            "current": {"step": 1, "file": "M1-problem.md", "status": "pending"},
            "steps": [{"no": s["no"], "stage": s["stage"], "key": s["key"], "file": s["file"],
                       "status": "pending", "doneAt": None, "rows": 0} for s in STEPS],
            "nonGoals": [],
            "scale": {"records": 0, "dailyNew": 0, "batchSize": [1, 1], "note": ""},
            "confirmations": {
                "M1": {"confirmed": False, "by": None, "at": None, "quote": None,
                       "contentHash": None, "decision": None},
                "M3": {"confirmed": False, "by": None, "at": None, "quote": None,
                       "contentHash": None, "decision": None},
                "M6": {"confirmed": False, "by": None, "at": None, "quote": None,
                       "contentHash": None, "decision": None},
            },
            "waived": {"reviewRoles": {"fieldUser": {"waived": False, "reason": None}}},
            "matrix": {"enabledDims": [c for c, _, _ in DIMS], "totalCells": 0,
                       "mapped": 0, "excluded": 0, "pending": 0},
            "openQuestions": [],
            "artifacts": {},
        }
        derive(state, d)
        with open(sp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    n = len(steps_of(stage))
    print("已生成骨架：%s（%d 份文档 + _state.json + _draft/）" % (d, n))
    print("填完后跑：python3 %s %s --stage %d"
          % (os.path.join(SUITE, "bin", "check_analysis.py"), d, stage or 1))
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2

    stage = 0
    if "--stage" in argv:
        i = argv.index("--stage")
        if i + 1 >= len(argv):
            print("--stage 需要一个值：1 / 2 / all")
            return 2
        v = argv[i + 1].lower()
        stage = 0 if v == "all" else int(v) if v in ("1", "2") else -1
        if stage < 0:
            print("--stage 只认 1 / 2 / all")
            return 2

    if argv[0] == "--init":
        prod = ""
        if "--product" in argv:
            i = argv.index("--product")
            if i + 1 < len(argv):
                prod = argv[i + 1]
        skip = {prod} | ({argv[argv.index("--stage") + 1]}
                         if "--stage" in argv and argv.index("--stage") + 1 < len(argv) else set())
        rest = [a for a in argv[1:] if not a.startswith("--") and a not in skip]
        d = rest[0] if rest else "analysis/new"
        return init(d, prod, stage)

    if "--spec" in argv:
        return print_spec()

    args = [a for a in argv if not a.startswith("--")]
    # 跳过 --stage / --product 的取值，别把它当成目录
    vals = set()
    for flag in ("--stage", "--product"):
        if flag in argv:
            i = argv.index(flag)
            if i + 1 < len(argv):
                vals.add(argv[i + 1])
    args = [a for a in args if a not in vals]
    if not args:
        print(__doc__)
        return 2
    d = args[0]
    if not os.path.isdir(d):
        print("目录不存在：%s" % d)
        return 2

    global STRICT
    if "--seal" in argv:
        STRICT = True

    if "--status" in argv:
        return status(d)
    if "--hash" in argv:
        return do_hash(d)
    if "--upgrade" in argv:
        state = load_state(d)
        return 0 if state else 2

    check(d, stage)
    if "--verbose" in argv and VERBOSE_HITS:
        print("逐处清单（%d 条，默认聚合为一条；--verbose 才展开）：" % len(VERBOSE_HITS))
        for m in VERBOSE_HITS:
            print("  ‣ " + m)
        print("-" * 72)
    errors = [i for i in issues if i[0] == E]
    warns = [i for i in issues if i[0] == W]
    if "--quiet" not in argv:
        scope = {0: "全量 50 条", 1: "第 1 段 24 条 + 跨阶段 6 条",
                 2: "第 2 段 21 条 + 跨阶段 6 条"}[stage]
        print("分析校验：%s（%s）" % (d, scope))
        print("-" * 72)
        for level, code, msg in issues:
            print("[%s] %-6s %s" % (level, code, msg))
        if not issues:
            print("[OK   ] PASS   %s产物齐全，判据全绿"
                  % {0: "六份", 1: "第 1 段三份", 2: "第 2 段三份"}[stage])
        print("-" * 72)
    print("结果：ERROR=%d  WARN=%d  %s"
          % (len(errors), len(warns), "放行" if not errors else "拦截"))

    if "--seal" in argv:
        return do_seal(d, issues, stage, force="--force" in argv)
    return 1 if errors else 0


def do_seal(d, issues, stage, force=False):
    """--seal：全绿才签收，写 stages["2"].sealed = {at, protoHash, mdHashes}。

    能带病签收的签收等于没有签收，所以有 ERROR 一律拒绝，且不写盘。

    --force 只覆盖「已签收」这个状态，不覆盖判据。
    让 --force 能跳过判据，等于给判据开了一个 --force 形状的后门，
    和 A-25e 被"换个语序就过"是同一个病。
    所以顺序是：先判据（含 A-67 严格判定）→ 再判是否要 --force → 最后才写盘。
    """
    if stage != 2:
        print("--seal 只能在 --stage 2 用（签收的是第 2 段的出口）")
        return 2
    errors = [i for i in issues if i[0] == E]
    if errors:
        print("拒绝签收：还有 %d 条 ERROR。带病签收等于没签收，先全部修绿再跑 --seal"
              "（--force 不能绕过判据）。" % len(errors))
        return 1

    # A-67 在"已签收且 hash 不等"时只报 WARN，不能靠 ERROR 拦住。
    # 签收的语义是"我确认这份是纯净的"，所以有 hits 也一律拒绝——否则
    # 越界版会被 --force 签收，下一次跑立刻变第四行红，用户只会觉得判据疯了。
    hits = [i for i in issues if i[1] == "A-67"]
    if hits:
        print("拒绝签收：契约还不干净（%d 条 A-67）。签收前必须先清掉渲染键——"
              "契约一改，第 3 段本来就要重做。" % len(hits))
        return 1

    state = load_state(d)
    if state is None:
        return 2
    proto = state.get("protoFile") or ""
    ppath = os.path.join(d, proto) if proto else ""
    if not (proto and os.path.isfile(ppath)):
        print("拒绝签收：找不到当前契约（%s）。第 2 段的出口必须是一份 {产品}.proto.json" % (proto or "?"))
        return 1

    ph = _proto_sha16(ppath)
    old = ((state.get("stages") or {}).get("2") or {}).get("sealed") or {}
    if old.get("protoHash") and old.get("protoHash") != ph and not force:
        print("契约在签收后被改过（%s → %s）。确认要重新签收请加 --force"
              % (old["protoHash"][:8], ph[:8]))
        return 1

    now = datetime.now().astimezone().replace(microsecond=0).isoformat()
    sealed = {"at": now, "protoHash": ph,
              "mdHashes": {f: artifact_hash(os.path.join(d, f))
                           for f in ("M4-flows.md", "M5-exceptions.md", "M6-review.md")}}
    state.setdefault("stages", {}).setdefault("2", {})["sealed"] = sealed
    _sync(os.path.join(d, STATE_FILE), state)

    if old:
        print("旧 sealed 已作废：at=%s / protoHash=%s" % (old.get("at"), (old.get("protoHash") or "?")[:4]))
    print("已签收第 2 段出口：at=%s  protoHash=%s" % (now, ph))
    print("已冻结 M4/M5/M6 指纹：%s" % " / ".join(
        "%s=%s" % (f.split("-")[0], h) for f, h in sealed["mdHashes"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
