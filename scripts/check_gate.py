#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IIOT-PRD 流程闸门（G 系列判据）

用法：
  python3 scripts/check_gate.py shaping/                    # 只查澄清阶段是否走完
  python3 scripts/check_gate.py shaping/ --proto out.proto.json   # 连"顺序倒挂"一起查
  python3 scripts/check_gate.py --init shaping/ --product "QMS 来料检验"   # 生成骨架

它查的不是"文档写得漂不漂亮"，是三件会让整件事作废的事：

  1. 跳步：没做澄清就出组件树（G-01 / G-08）
  2. 补签：原型先画完，澄清文档后补，时间戳不自洽（G-09）
  3. 空壳：文件在、小节在，但关键列（证据等级 / 是否同一人 / 失败兜底）没有（G-10~G-16）

退出码：0 = 放行，1 = 拦，2 = 用法错误。
"拦"不是建议，是「不许继续写 componentTree」。
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

E, W = "ERROR", "WARN"
issues = []


def add(level, code, msg):
    issues.append((level, code, msg))


# ---------------------------------------------------------------- 七步定义
# need: (小节关键词, 是否必需, 会在缺时报什么)
STEPS = [
    {
        "no": 0, "key": "positioning", "file": "01-positioning.md",
        "title": "边界与非目标",
        "need": ["一句话目标", "非目标", "数据量与频次"],
        "why": "没有非目标，后面每拆一个场景都会顺手扩边界；没有量级，9407 条和 47 条会被当成同一个产品做",
    },
    {
        "no": 1, "key": "problem", "file": "02-problem.md",
        "title": "真问题",
        "need": ["原话拆解", "真问题陈述", "替代路径"],
        "why": "直接接受业务方给的方案，是这类需求返工的第一原因",
    },
    {
        "no": 2, "key": "roles", "file": "03-roles.md",
        "title": "角色",
        "need": ["角色表", "角色关系"],
        "why": "给不存在的角色设计权限，上线后一半按钮没人点",
    },
    {
        "no": 3, "key": "scenarios", "file": "04-scenarios.md",
        "title": "场景",
        "need": ["场景表", "优先级"],
        "why": "不写失败兜底的场景，上线后现场会用纸条绕过系统",
    },
    {
        "no": 4, "key": "flows", "file": "05-user-flows.md",
        "title": "流程",
        "need": ["泳道", "状态变化"],
        "why": "「提交后状态更新」是废话，待取样→已取样才能推按钮可用性",
    },
    {
        "no": 5, "key": "exceptions", "file": "06-exceptions.md",
        "title": "异常",
        "need": ["异常清单", "追溯与版本"],
        "why": "外设、追溯断链、标准改版这三类在办公室测不出来，全在现场爆",
    },
    {
        "no": 6, "key": "review", "file": "07-review.md",
        "title": "对抗评审",
        "need": ["研发", "测试", "业务", "现场使用者", "风险"],
        "why": "工业系统最常见的死法不是功能不对，是上线后现场不用",
    },
]

GATES = [
    ("A1", "真问题确认", ["problem"], "未确认真问题就开始拆场景，等于把方案当需求做"),
    ("A2", "评审通过", ["problem", "roles", "scenarios", "flows", "exceptions", "review"], "评审未过就落契约，风险未收敛"),
    ("A3", "切片与契约确认", [s["key"] for s in STEPS], "切片未确认就写组件树，页面结构会反复推翻"),
]

# 异常 11 类：8 软件 + 3 工业
EXC_CLASSES = [
    ("用户操作", ["用户操作"]),
    ("系统状态", ["系统状态"]),
    ("数据", ["数据异常", "数据"]),
    ("权限", ["权限"]),
    ("网络接口", ["网络", "接口"]),
    ("并发重复", ["并发", "重复"]),
    ("历史兼容", ["历史", "兼容"]),
    ("运营后台", ["运营", "后台"]),
    ("外设硬件", ["外设", "硬件", "扫码枪", "打印机", "电子秤"]),
    ("追溯断链", ["断链", "追溯"]),
    ("标准版本", ["版本", "标准变更", "改版"]),
]

REVIEW_ROLES = ["研发", "测试", "业务", "现场"]


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def sections(md):
    """抓二级标题，返回 {标题原文: 该节正文}。

    剔除 `>` 引用块：模板里每节末尾都有一句「这一节为什么必须存在：待取样→已取样…」，
    若不剔除，判据会被自己的解释文字满足（写模板的人顺手写了个合格示例，脚本就读到"合格"了）。
    判据不能读自己的注释，这是闸门类脚本最容易出的假绿。
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


def table_rows(block):
    """数表格数据行（排除表头与分隔线）。"""
    if not block:
        return 0
    n = 0
    for line in block.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        if re.match(r"^\|[\s:\-|]+\|$", s):      # 分隔线
            continue
        n += 1
    return max(0, n - 1)                          # 减表头


def list_items(block):
    """数 Markdown 列表项。要求 `-` 后带空格，否则 `---` 水平线会被算成一条。"""
    return len(re.findall(r"^\s*(?:\d{1,2}[.、)]|[-*+]\s)\s*\S", block or "", re.M))


def header_of(block):
    """取表格首行（表头）。"""
    if not block:
        return ""
    for line in block.splitlines():
        if line.strip().startswith("|"):
            return line
    return ""


def parse_time(s):
    """ISO8601 → aware datetime；不带时区按本地时区。"""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


# ---------------------------------------------------------------- 主检查
def check(shaping_dir, proto_path=None):
    gate_file = os.path.join(shaping_dir, "_gate.json")
    proto_exists = bool(proto_path) and os.path.isfile(proto_path)

    # ---- G-01 跳步：有原型，没有澄清 ----
    if not os.path.isfile(gate_file):
        if proto_exists:
            add(E, "G-01", f"存在 {os.path.basename(proto_path)} 但 shaping/_gate.json 不存在："
                           "属「跳过澄清直接画组件树」，必须回到第 0 步")
        else:
            add(E, "G-01", "shaping/_gate.json 不存在：澄清阶段未启动（先 --init 生成骨架）")
        return

    gate = json.loads(read(gate_file))
    product = gate.get("product") or "(未命名产品)"

    if gate.get("gateVersion") != "1.0":
        add(E, "G-02", f"gateVersion 必须为 1.0，实际 {gate.get('gateVersion')}")

    # ---- G-03 步骤覆盖 ----
    steps = {s.get("no"): s for s in (gate.get("steps") or [])}
    missing_steps = [s["no"] for s in STEPS if s["no"] not in steps]
    if missing_steps:
        file_missing = [s["file"] for s in STEPS if s["no"] not in steps]
        add(E, "G-03", f"gate.steps 未登记第 {missing_steps} 步（缺 {', '.join(file_missing)}）")

    # ---- 逐步：文件 + 小节 ----
    for spec in STEPS:
        no, fn = spec["no"], spec["file"]
        path = os.path.join(shaping_dir, fn)
        declared = steps.get(no) or {}
        if not os.path.isfile(path):
            if declared.get("status") in ("done", "skipped"):
                add(E, "G-04", f"第 {no} 步标为 {declared.get('status')}，但 {fn} 不存在（虚报进度）")
            else:
                add(E, "G-04", f"第 {no} 步 {spec['title']} 缺 {fn}")
            continue
        secs = sections(read(path))
        for kw in spec["need"]:
            if find_sec(secs, kw) is None:
                add(E, "G-05", f"{fn} 缺小节「{kw}」（第 {no} 步 {spec['title']}）— {spec['why']}")

    # ---- G-06 非目标与量级 ----
    goals = gate.get("nonGoals") or []
    if len(goals) < 3:
        add(E, "G-06", f"nonGoals 只有 {len(goals)} 条，至少 3 条（每条要能指向一个会被砍掉的功能）")
    scale = gate.get("scale") or {}
    for k, hint in [("records", "现有记录量"), ("dailyNew", "日新增量")]:
        if not isinstance(scale.get(k), (int, float)) or scale.get(k) <= 0:
            add(E, "G-07", f"scale.{k}（{hint}）缺失或非正数：不量化就没法判断该前端数组还是服务端分页")

    # ---- A1/A2/A3 确认 ----
    confs = gate.get("confirmations") or {}
    confirmed_at = {}
    for gid, name, _keys, why in GATES:
        c = confs.get(gid) or {}
        if not c.get("confirmed"):
            add(E, "G-08", f"卡点 {gid}（{name}）未确认 — {why}")
        else:
            for f in ("by", "at"):
                if not c.get(f):
                    add(E, "G-09", f"卡点 {gid} 已确认但缺 {f}（无签署人的确认等于没确认）")
            dt = parse_time(c.get("at"))
            if c.get("at") and dt is None:
                add(E, "G-09", f"卡点 {gid} 的 at 不是合法 ISO8601：{c.get('at')}")
            elif dt:
                confirmed_at[gid] = dt

    # ---- G-10 顺序倒挂：原型早于 A3 ----
    if proto_exists and "A3" in confirmed_at:
        mt = datetime.fromtimestamp(os.path.getmtime(proto_path), tz=timezone.utc)
        if mt < confirmed_at["A3"]:
            delta = (confirmed_at["A3"] - mt).total_seconds()
            add(E, "G-10", f"{os.path.basename(proto_path)} 的写入时间早于 A3 确认 {int(delta)}s："
                           "属事后补签（原型先画完再补澄清文档）")

    # ---- G-11 异常 11 类 ----
    # 不用「全文出现关键词」判：模板末尾一句「外设、追溯断链、标准改版这三类…」
    # 就能让三类同时过关。必须落在异常清单表格的行首类别列上。
    exc_path = os.path.join(shaping_dir, "06-exceptions.md")
    if os.path.isfile(exc_path):
        sec = find_sec(sections(read(exc_path)), "异常清单") or ""
        rows = [ln for ln in sec.splitlines()
                if ln.strip().startswith("|") and not re.match(r"^\|[\s:\-|]+\|$", ln.strip())]
        body = rows[1:] if rows else []                      # 去掉表头
        covered, orphan = set(), []
        for ln in body:
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if not cells or not cells[0]:
                orphan.append("(空类别)")
                continue
            head = cells[0]
            hit = [name for name, kws in EXC_CLASSES if any(k in head for k in kws)]
            if hit:
                covered.update(hit)
            else:
                orphan.append(head)
        miss = [name for name, _ in EXC_CLASSES if name not in covered]
        if miss:
            add(E, "G-11", f"06-exceptions.md 异常清单未覆盖 {len(miss)}/{len(EXC_CLASSES)} 类：{', '.join(miss)}")
        if len(body) < 11:
            add(E, "G-11b", f"06-exceptions.md 异常清单只有 {len(body)} 行，11 类每类至少 1 行")
        for o in orphan:
            add(W, "G-11c", f"06-exceptions.md 异常行「{o}」归不进 11 类，确认是否重复归类或漏了类别")

    # ---- G-12 评审四角色 ----
    rv_path = os.path.join(shaping_dir, "07-review.md")
    if os.path.isfile(rv_path):
        secs = sections(read(rv_path))
        miss = [r for r in REVIEW_ROLES if find_sec(secs, r) is None]
        if miss:
            add(E, "G-12", f"07-review.md 缺角色小节：{', '.join(miss)}（缺现场使用者最致命）")
        else:
            for r in REVIEW_ROLES:
                blk = find_sec(secs, r) or ""
                qs = list_items(blk)
                if qs < 10:
                    add(W, "G-13", f"07-review.md「{r}」只有 {qs} 个问题，要求 ≥10（少于 10 个通常没问到底）")
            risk = find_sec(secs, "风险") or ""
            if table_rows(risk) < 5 and list_items(risk) < 5:
                add(E, "G-14", "07-review.md 风险清单不足 5 条")

    # ---- G-15 替代路径 ----
    pb_path = os.path.join(shaping_dir, "02-problem.md")
    if os.path.isfile(pb_path):
        secs = sections(read(pb_path))
        sec = find_sec(secs, "替代路径") or ""
        n = table_rows(sec) or list_items(sec)
        if n < 3:
            add(E, "G-15", f"02-problem.md 替代路径只有 {n} 条，至少 3 条")
        if not re.search(r"不改系统|改流程|改组织|不开发|调流程|培训", sec):
            add(E, "G-16", "02-problem.md 替代路径里没有「不改系统」的做法：三条都在讲怎么改产品，"
                           "说明没真考虑过更省钱的路")
        else:
            # 只看表格行，不看小节里的总结段。否则「路径 1 是唯一不开发也能省时间的做法」
            # 这类复述会让 G-16 恒绿——判据不能读叙述文字，只能读条目本身。
            rows = [ln for ln in sec.splitlines() if ln.strip().startswith("|")]
            body = [ln for ln in rows[1:] if not re.match(r"^\|[\s:\-|]+\|$", ln.strip())]
            if not any(re.search(r"不改系统|改流程|改组织|不开发|调流程|培训", ln) for ln in body):
                add(E, "G-16", "02-problem.md 替代路径的表格里没有「不改系统」那一条："
                               "只在总结段提到不算，必须是一条可选项")
        # G-17 证据等级只看「原话拆解」表，不看全文（写了「证据等级」三个字不算标了等级）
        st = find_sec(secs, "原话拆解") or ""
        if not re.search(r"stated|inferred|measured", st):
            add(E, "G-17", "02-problem.md 原话拆解表没有标注证据等级（stated/inferred/measured）："
                           "不标等级的推断最后会被当事实写进 PRD")

    # ---- G-18 角色两列 ----
    ro_path = os.path.join(shaping_dir, "03-roles.md")
    if os.path.isfile(ro_path):
        txt = read(ro_path)
        sec = find_sec(sections(txt), "角色表") or ""
        hd = header_of(sec)
        for kw, code in [("真实", "G-18"), ("同一人", "G-19")]:
            if kw not in hd:
                add(E, code, f"03-roles.md 角色表缺列「是否{'真实存在' if kw == '真实' else '与其他角色同一人'}」"
                             "（决定权限是否给了一个不存在的人 / 四眼原则能否落地）")

    # ---- G-20 失败兜底 ----
    sc_path = os.path.join(shaping_dir, "04-scenarios.md")
    if os.path.isfile(sc_path):
        sec = find_sec(sections(read(sc_path)), "场景表") or ""
        if "兜底" not in header_of(sec):
            add(E, "G-20", "04-scenarios.md 场景表缺列「失败兜底」：不写兜底，上线后现场一定用纸条绕过系统")

    # ---- G-21 状态变化必须是 from→to ----
    fl_path = os.path.join(shaping_dir, "05-user-flows.md")
    if os.path.isfile(fl_path):
        sec = find_sec(sections(read(fl_path)), "状态变化") or ""
        pairs = re.findall(r"[\u4e00-\u9fa5A-Za-z0-9_]+\s*(?:→|->)\s*[\u4e00-\u9fa5A-Za-z0-9_]+", sec)
        if len(pairs) < 2:
            add(E, "G-21", f"05-user-flows.md 状态变化小节只有 {len(pairs)} 处 from→to，至少 2 处"
                           "（写成「状态更新」这种自然语言无法推按钮可用性）")
        if re.search(r"(?<!→)状态更新(?!到)", sec) and not pairs:
            add(W, "G-22", "05-user-flows.md 出现「状态更新」这类空话，应改写成 待取样 → 已取样")
        for m in re.finditer(r"(?:→|->)\s*([\u4e00-\u9fa5A-Za-z0-9_]+)", sec):
            if m.group(1) in ("状态", "下一步", "完成", "更新"):
                add(W, "G-22", f"05-user-flows.md 状态迁移的目标端不具体：{m.group(1)}")

    # ---- G-23 契约侧的开放问题 ----
    if proto_exists:
        proto = json.loads(read(proto_path))
        for q in (proto.get("openQuestions") or []):
            if q.get("priority") == "P0" and q.get("status") not in ("resolved", "assumed"):
                add(E, "G-23", f"proto.openQuestions 的 P0「{q.get('question')}」未 resolved/assumed，"
                               "不许冻结契约")
        # 需求要点名的字段必须有登记
        if not (proto.get("fieldRegistry") or []):
            add(W, "G-24", "proto.fieldRegistry 为空：源文档点名的业务字段没有落位")

    if not issues:
        add("OK", "PASS", f"{product} 七步澄清已走完，三道卡点均已签署，可以进入契约与组件树")


def init(shaping_dir, product):
    os.makedirs(shaping_dir, exist_ok=True)
    gate = {
        "gateVersion": "1.0",
        "product": product or "(待填)",
        "protoFile": "",
        "steps": [{"no": s["no"], "key": s["key"], "file": s["file"], "status": "todo"} for s in STEPS],
        "nonGoals": [],
        "scale": {"records": 0, "dailyNew": 0, "batchSize": [1, 1]},
        "confirmations": {
            "A1": {"confirmed": False, "by": "", "at": "", "decision": ""},
            "A2": {"confirmed": False, "by": "", "at": "", "decision": ""},
            "A3": {"confirmed": False, "by": "", "at": "", "decision": ""},
        },
    }
    with open(os.path.join(shaping_dir, "_gate.json"), "w", encoding="utf-8") as f:
        json.dump(gate, f, ensure_ascii=False, indent=2)

    for s in STEPS:
        p = os.path.join(shaping_dir, s["file"])
        if os.path.exists(p):
            continue
        body = [f"# {s['no']} {s['title']}", ""]
        for kw in s["need"]:
            body += [f"## {kw}", "", "（待填）", ""]
        body += ["---", f"> 这一节为什么必须存在：{s['why']}", ""]
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(body))
    print(f"已生成骨架：{shaping_dir}（{len(STEPS)} 份文档 + _gate.json）")
    print("填完后跑：python3 scripts/check_gate.py " + shaping_dir)


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2

    if argv[0] == "--init":
        args = argv[1:]
        d = next((a for a in args if not a.startswith("--")), "shaping")
        prod = ""
        if "--product" in args:
            i = args.index("--product")
            if i + 1 < len(args):
                prod = args[i + 1]
        init(d, prod)
        return 0

    proto = None
    if "--proto" in argv:
        i = argv.index("--proto")
        if i + 1 < len(argv):
            proto = argv[i + 1]
    dirs = [a for a in argv if not a.startswith("--") and a != proto]
    if not dirs:
        print(__doc__)
        return 2
    check(dirs[0], proto)

    errors = [i for i in issues if i[0] == E]
    warns = [i for i in issues if i[0] == W]
    print(f"闸门检查：{dirs[0]}")
    print("-" * 66)
    for level, code, msg in issues:
        print(f"[{level:5}] {code:6} {msg}")
    print("-" * 66)
    print(f"结果：ERROR={len(errors)}  WARN={len(warns)}  {'放行' if not errors else '拦截'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
