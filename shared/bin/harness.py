#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""iiot-prd-suite · harness —— 执行状态与链路管控（_run/ 那一层）

它回答「这一轮在怎么干」，不回答「产物到哪一步」：
  _state.json（check_analysis.py 管）  产物真相：六步谁签的字
  _run/（本脚本管）                    执行过程：目标、规划、每一步、判定
两层正交。harness 一个字节都不写 _state.json，只在 close 时读它对账（只 WARN，不阻断）。

一趟完整的流程（不知道这套东西的人照这五行抄就够）：

  1) 起
     python3 shared/bin/harness.py init --dir <产品目录> --product "新锂想QMS 来料检验" \\
         --goal "把来料检验这单需求分析清楚，产出可交给开发的契约与原型" --auto --stage 1
     → 建 <产品目录>/_run/：contract.json（目标 + 规划，冻结）、state.json（当前快照）、
       journal.jsonl（一步一行，只追加）、RUNLOG.md（journal 的人看渲染）
       --product 用来渲染 doneWhen 里的 {产品}（契约、PRD 的文件名），不传就取目录名

  2) 每次开工前 —— 模型必须跑，这是唯一的目标注入点
     python3 shared/bin/harness.py next --dir <产品目录>
     → 目标原句 / 进度 / 下一步 / 约束 / 上次 / 账本 / 任务列表同步
     末尾那行「同步 任务列表」是给对话里那套 Task 工具看的：_run/ 是真相，列表是投影。
     按 plan 建好列表后跑一次 mark-tasks，之后 next 不再喊先建：
     python3 shared/bin/harness.py mark-tasks --dir <产品目录> --completed-count 2

  3) 每做完一个动作
     python3 shared/bin/harness.py step --dir <产品目录> \\
         --intent "扫 D2 维度时发现没问过留样" --tool Read \\
         --args "M3-scenarios.md" --out "发现 1 条漏项" --taskId A3
     → 记一步，同时跑检测：循环 / 偏移累计 / 非法任务 / 遗漏
     任务真的要记完成时，加 --done 并把产物文件放到 --out：
     python3 shared/bin/harness.py step --dir D --taskId A1 --intent "写完 M1 立场句" \\
         --tool Write --args "M1-problem.md" --out "M1-problem.md" --done
     （--out 的文件必须真的躺在 --dir 下，且 doneWhen.contains 每个串都在；缺一样 exit 6）

  4) 每 2 步（milestoneEvery）—— 里程碑自检，只读计数，不推进任务
     python3 shared/bin/harness.py milestone --dir <产品目录> --gap "还缺 M3 确认单"
     → 清零计数、记 gap。gap 空着不算自检（exit 3）

  5) 收工
     python3 shared/bin/harness.py close --dir <产品目录> --result "契约+原型已交"
     → 复盘摘要 + 与 _state.json 对账

随时能看：
  status --dir D            终端视图（人看）
  status --dir D --md       同一份内容的 markdown（贴群里）
  log --dir D --tail 20     原始 journal 尾部
  check --dir D             只检测不记账（想知道"这一步会不会被判死循环"时用）
  amend --dir D --add "补充留样场景" --why "M3 漏项"   往 plan 里加一步，先校验对不对得上目标

参数表（值里有空格就加引号）：
  init        --dir --goal [--product] --keywords k1,k2  --auto --stage 1|2|3  |  --plan f.json  |  --force
  next        --dir
  step        --dir --intent --tool --args --out [--taskId] [--verdict ok|fail] [--done]
  check       --dir [--intent --tool --args --taskId]      不给 intent 就只报计数器
  status      --dir [--md]
  amend       --dir --add --why [--stage 1|2|3] [--done-file f]
  milestone   --dir --gap
  mark-tasks  --dir [--completed-count N]      建完对话里的任务列表后跑一次
  close       --dir [--result]
  log         --dir [--tail N]
  --force-unblock  任何子命令都能带上；也可以单独跑 --dir D --force-unblock

退出码：
  0 正常 ／ 2 循环或已 blocked ／ 3 累计偏移（连 3 次对不上目标）或 amend 不对齐
  4 遗漏（显式 --taskId 不是该做的那个）／ 5 --taskId 不在 plan 里 ／ 6 --done 但产物不成立

三条纪律（规格 §6，一条都别改）：
  1. 循环只认 (tool, argsHash)，不认「意图相似」——意图是自述，靠不住；
  2. blocked 一旦置位，除 close 外所有子命令 exit 2，脚本不自己解封；
     解封只能人看完 RUNLOG 后跑 --force-unblock；
  3. next 是唯一的目标注入点，必须打 goal 原句，不许摘要成「目标已加载」。

两条实现约定（规格没写死，这里是准）：
  - FORGET 只在显式传 --taskId 时判。默认取 state.next，等价于恒等，判不出跳步。
    跳步的真检测靠产物对账（§9 close），不靠 step 的自述。
  - 任务完成只由 step --done 推进，且必须有产物。milestone 只清零计数，不写 task.status。
"""
import hashlib
import json
import os
import re
import shutil
import sys
import unicodedata
from datetime import datetime

RUN = "_run"
CONTRACT = "contract.json"
STATE = "state.json"
JOURNAL = "journal.jsonl"
RUNLOG = "RUNLOG.md"
RUN_VERSION = "1.1"

# 规格 §2：guardrails 三个值写死，不许命令行改
GUARDRAILS = {"maxSameCall": 3, "milestoneEvery": 2, "forbidAddingBeyondPlan": True}

# --auto --stage N 的固定规划：01 = A1~A3，02 = B1~B4，03 = C1~C3
# doneWhen 是结构化的：file 是必须存在的产物，contains 是必须出现的串。
# "{产品}" 是占位符，init 时按 --product 渲染成真实文件名——常量表不许留字面占位符，
# 否则 --done 永远对不上文件。
STAGE_TASKS = {
    1: [("A1", "真问题", {"file": "M1-problem.md", "contains": ["我的立场"]}),
        ("A2", "角色", {"file": "M2-roles.md", "contains": ["角色表"]}),
        ("A3", "场景矩阵", {"file": "M3-scenarios.md", "contains": ["覆盖矩阵", "待确认清单"]})],
    2: [("B1", "业务流程", {"file": "M4-flows.md", "contains": ["主流程", "状态机"]}),
        ("B2", "异常与边界", {"file": "M5-exceptions.md", "contains": ["异常清单"]}),
        ("B3", "对抗评审", {"file": "M6-review.md", "contains": ["最大 5 个风险", "结论"]}),
        ("B4", "落契约并签收", {"file": "{产品}.proto.json", "contains": []})],
    3: [("C1", "页面骨架与组件树", {"file": "{产品}.proto.json", "contains": ["componentTree"]}),
        ("C2", "容器构建", {"file": "dist/index.html", "contains": []}),
        ("C3", "导出 PRD", {"file": "PRD-{产品}.md", "contains": []})],
}

# amend 新增步骤的编号前缀：<段字母>p<序号>，如 ap2 / bp1 / cp3
STAGE_PREFIX = {1: "a", 2: "b", 3: "c"}

# --why 能追溯到出处的词。amend 只认「有出处」或「对得上目标」，不认「我觉得」。
TRACE_WORDS = ["原话", "纪要", "确认", "用户", "客户", "业务方", "评审", "文档", "工单",
               "现场", "需求", "M1", "M2", "M3", "M4", "M5", "M6"]

# --intent 敷衍检测：短句 + 以动作词开头 = 写的是动作不是判断
ACTION_VERBS = ("读", "看", "查", "搜", "跑", "执行", "处理")
LAZY_INTENT_LIMIT = 10

# --goal 自动切词的停用词。只删「把/的/产出/交给」这类虚词与动词，
# 剩下的连续汉字块当关键词。切不出来就让调用方用 --keywords 指定，不猜。
STOPWORDS = ["把", "这单", "这个", "那个", "这些", "那些", "的", "了", "与", "和", "或",
             "及", "在", "是", "要", "请", "帮我", "产出", "交给", "可", "能", "做",
             "一个", "一下", "清楚", "分析", "需求", "整个", "全部", "还", "再", "就",
             "都", "也", "开发", "交付", "输出", "出来", "什么", "怎么", "如何"]

FLAGS = {"--force", "--auto", "--md", "--done", "--force-unblock", "--brief", "-h", "--help"}


# ------------------------------------------------------------------ 小工具
def cw(text):
    """终端显示宽度：中文占 2 列。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def pad(text, width):
    return text + " " * max(1, width - cw(text))


def clip(text, width):
    """按显示宽度截断，末尾加省略号。"""
    if cw(text) <= width:
        return text
    out, w = "", 0
    for ch in text:
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if w > width - 1:
            break
        out += ch
    return out + "…"


def now():
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def read_json(path):
    try:
        return json.loads(read(path))
    except (IOError, OSError, ValueError) as exc:
        print("读不了 %s：%s" % (path, exc))
        return None


def write_json(path, obj):
    body = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)


def args_hash(tool, args):
    """规格 §4：sha256(tool + \\x1f + 参数)。调用方传什么就 hash 什么，不解析 JSON。"""
    raw = "%s\x1f%s" % (tool or "", args or "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]


def args_brief(args, limit=60):
    """≤ 60 字，给人看。换行压成空格。"""
    text = re.sub(r"\s+", " ", (args or "").strip())
    return clip(text, limit) if text else "—"


def parse(argv):
    """手写解析：check_analysis.py 同款，不引第三方也不引 argparse 的默认值坑。"""
    if not argv or "-h" in argv or "--help" in argv:
        return None, {}
    cmd, opts, i = argv[0], {}, 1
    while i < len(argv):
        key = argv[i]
        if key in FLAGS:
            opts[key] = True
            i += 1
        elif key.startswith("--"):
            opts[key] = argv[i + 1] if i + 1 < len(argv) else ""
            i += 2
        else:
            i += 1
    return cmd, opts


# ------------------------------------------------------------------ 读写 _run/
def paths(d):
    run = os.path.join(d, RUN)
    return {"run": run, "contract": os.path.join(run, CONTRACT),
            "state": os.path.join(run, STATE),
            "journal": os.path.join(run, JOURNAL),
            "runlog": os.path.join(run, RUNLOG)}


def jread(p):
    """journal 只追加：读的时候也按文件顺序，不排序。seq 单调由 append 保证。"""
    if not os.path.isfile(p["journal"]):
        return []
    out = []
    for line in read(p["journal"]).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            print("[WARN] journal 有一行不是合法 JSON，已跳过：%s" % line[:60])
    return out


def jappend(p, contract, state, rec):
    rec = dict(rec)
    last = jread(p)
    rec["seq"] = (last[-1].get("seq") or 0) + 1 if last else 1
    rec.setdefault("ts", now())
    order = ["seq", "ts", "taskId", "intent", "tool", "argsHash", "argsBrief",
             "out", "verdict", "goalAligned", "event"]
    line = {k: rec.get(k) for k in order}
    with open(p["journal"], "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")
    render_runlog(p, contract, state)
    return line


def render_runlog(p, contract, state):
    """journal 的人看渲染。脚本生成，每次追加后重写；手改会被覆盖。"""
    rows = jread(p)
    plan = contract.get("plan") or []
    done = [t["id"] for t in plan if t.get("status") == "done"]
    warns = [r for r in rows if r.get("verdict") not in ("ok", None)]
    out = ["# RUNLOG · 执行留痕", "",
           "> 由 `harness.py` 从 `journal.jsonl` 生成，每次 step / milestone / amend / close 后重写。"
           "手改会被覆盖，要改就改 journal（只追加）。", "",
           "- 目标：%s" % contract.get("goal"),
           "- 规划：%d 个任务（%s）｜ 当前 %s ｜ 已用 %d 步 ｜ 告警 %d"
           % (len(plan), " ".join("%s%s" % (t["id"], "✓" if t["id"] in done else "")
                                  for t in plan),
              state.get("next") or "—", len(rows), len(warns)), ""]
    if not rows:
        out.append("_还没有记录任何步骤。_")
    else:
        out += ["| # | 时间 | 任务 | 意图 | 工具 | 结果 | 判定 |",
                "|---|---|---|---|---|---|---|"]
        for r in rows:
            out.append("| %d | %s | %s | %s | %s | %s | %s |" % (
                r.get("seq"), (r.get("ts") or "")[11:19], r.get("taskId") or "—",
                cell(r.get("intent")), cell(r.get("tool") or "—"),
                cell(r.get("out") or "—"), cell(verdict_label(r))))
    events = [r for r in rows if r.get("event")]
    if events:
        out += ["", "## 事件", ""]
        for r in events:
            out.append("- `%02d` %s：%s" % (r.get("seq"), r.get("event"),
                                           r.get("out") or r.get("intent") or ""))
    if state.get("blocked"):
        b = state["blocked"]
        out += ["", "## 拦截", "",
                "- %s @%s：%s" % (b.get("reason"), b.get("at"), b.get("detail")),
                "- 解封只能人看完这份 RUNLOG 后跑 `--force-unblock`，脚本不会自己解封。"]
    with open(p["runlog"], "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


def cell(text):
    return str(text if text is not None else "—").replace("|", "\\|").replace("\n", " ")


def verdict_label(rec):
    """事件行的判定列：milestone/amend/close 本身不是 ok/drift，标事件名更好读。"""
    if rec.get("event") in ("milestone", "amend", "close"):
        return "·%s" % rec["event"]
    return rec.get("verdict") or "—"


def boot(opts, allow_blocked=False):
    """所有子命令的统一入口：目录 → _run/ → contract/state → blocked 闸门。"""
    d = opts.get("--dir")
    if not d:
        print("缺 --dir <产品目录>")
        return None, 2
    d = os.path.abspath(os.path.expanduser(d))
    if not os.path.isdir(d):
        print("目录不存在：%s" % d)
        return None, 2
    p = paths(d)
    if not os.path.isdir(p["run"]):
        print("找不到 %s：这一轮还没 init（先跑 init --dir %s --goal \"...\" --auto --stage 1）"
              % (p["run"], d))
        return None, 2
    contract = read_json(p["contract"])
    state = read_json(p["state"])
    if contract is None or state is None:
        return None, 2
    if state.get("blocked") and not allow_blocked:
        print_blocked(state["blocked"])
        return None, 2
    return (d, p, contract, state), 0


def print_blocked(b):
    print("── 已拦截 ────────────────────────────────")
    print("[BLOCKED] %s @%s" % (b.get("reason"), b.get("at")))
    print("原因  %s" % b.get("detail"))
    print("快照  %s" % b.get("snapshot"))
    print("解封  只有人确认处理完之后才能跑 --force-unblock（先读 _run/RUNLOG.md 看清发生了什么）")
    print("      脚本不会自己解封，也不许换个参数绕过。")


# ------------------------------------------------------------------ 检测（规格 §6）
def dw_of(task):
    """doneWhen 归一化。

    runVersion 1.1 起是 {"file": ..., "contains": [...]}；1.0 的纯文本按 legacy 处理：
    只显示、不参与完成判定（比"静默跳过"诚实，也比"原地改写冻结的 contract"安全）。
    """
    dw = task.get("doneWhen")
    if isinstance(dw, dict):
        return {"file": dw.get("file"), "contains": [c for c in (dw.get("contains") or []) if c],
                "legacy": None}
    return {"file": None, "contains": [], "legacy": (dw or "")}


def dw_text(task):
    """人看的一行验收描述。"""
    dw = dw_of(task)
    if dw["legacy"]:
        return "%s（1.0 纯文本，不参与判定）" % dw["legacy"]
    bits = []
    if dw["file"]:
        bits.append(dw["file"])
    if dw["contains"]:
        bits.append("内含「%s」" % "、".join(dw["contains"]))
    return "｜".join(bits) or "产物文件由 --out 指定"


def first_pending(contract):
    return next((t["id"] for t in contract.get("plan") or []
                 if t.get("status") != "done"), None)


def detect(contract, state, intent, tool, ahash):
    """客观检测：只认 (tool,argsHash) 与关键词重合，不看意图写得漂不漂亮。

    返回 dict：sameCall / loop / kw / goalAligned
    """
    g = contract.get("guardrails") or GUARDRAILS
    counters = state.get("counters") or {}

    # 循环：与**前一次**比，不是"历史里出现过"。首次出现的动作算 1 次。
    same = (tool is not None and tool == state.get("lastTool")
            and ahash is not None and ahash == state.get("lastArgsHash"))
    same_call = (counters.get("sameCall") or 0) + 1 if same else 1
    loop = same_call >= g.get("maxSameCall", 3)

    # 目标对齐：intent 与本轮任务的词表比对。单次不对齐只 WARN，连续 3 次才判偏移。
    #
    # 词表三处合并，不能只从 goal 切：goal 是「整单目标」（来料检验/契约/原型），
    # 而每个子任务干的是局部的事（写完立场句、拉原话、扫 D2 维度），天然不含整单词。
    # 只比 goalKeywords 会把正常动作判成偏离，连续 3 步就误拦。
    #   goalKeywords ∪ 各任务 title ∪ 各任务 doneWhen.contains
    pool = list(contract.get("goalKeywords") or [])
    for it in (contract.get("plan") or []):
        pool.append(it.get("title") or "")
        dw = it.get("doneWhen")
        if isinstance(dw, dict):
            pool.extend(dw.get("contains") or [])
        elif isinstance(dw, str):
            pool.append(dw)

    # 双向匹配：k 是 intent 的子串，或 k 的某个二字片段出现在 intent 里。
    # 「写完 M1 的立场句」命中 A1 的 contains「我的立场」靠的是后半条（二字片段「立场」）。
    kws = [k for k in dict.fromkeys(pool)
           if k and len(k) >= 2 and _kw_hit(k, intent)]
    return {"sameCall": same_call, "loop": loop, "kw": kws, "goalAligned": bool(kws)}


def _kw_hit(k, text):
    """关键词命中：整词出现在 text 里，或它的某个二字片段出现在 text 里。

    只用整词匹配会漏：contains 写「我的立场」，intent 写「写完 M1 的立场句」，
    整词对不上而意图显然是对的。二字片段是中文无词边界下最粗也最稳的退路。
    代价是「反对立场」也会命中「我的立场」——单次只 WARN、连续 3 次才拦，
    这点误报由阈值吃掉，比误拦正常动作划算。
    """
    if k in text:
        return True
    if len(k) < 2:
        return False
    return any(k[i:i + 2] in text for i in range(len(k) - 1))


def lazy_intent(intent):
    """敷衍检测：短句 + 以动作词开头 → 写的是动作，不是判断。只看这两条客观特征。"""
    text = intent.strip()
    return len(text) < LAZY_INTENT_LIMIT and text.startswith(ACTION_VERBS)


# ------------------------------------------------------------------ init
def cmd_init(opts):
    d = opts.get("--dir")
    goal = (opts.get("--goal") or "").strip()
    if not d:
        print("缺 --dir <产品目录>")
        return 2
    d = os.path.abspath(os.path.expanduser(d))
    if not goal:
        print("缺 --goal：目标必须是一句人能看懂的话，它是一个字都不许省的（next 要原句回放）")
        return 2
    os.makedirs(d, exist_ok=True)
    p = paths(d)
    if os.path.isdir(p["run"]):
        if not opts.get("--force"):
            print("%s 已存在。重开一轮会丢历史，确认要覆盖请加 --force" % p["run"])
            return 2
        shutil.rmtree(p["run"])
    os.makedirs(p["run"])

    # goalKeywords：--keywords 覆盖，否则从 goal 自动切词；不许为空（§2）
    if opts.get("--keywords"):
        kws = [k.strip() for k in str(opts["--keywords"]).split(",") if k.strip()]
    else:
        kws = auto_keywords(goal)
    if not kws:
        print("从 --goal 切不出关键词。请用 --keywords 指定（逗号分隔），"
              "偏离检测全靠它，不许为空。")
        return 2

    product = (opts.get("--product") or "").strip() or os.path.basename(d.rstrip("/"))
    plan = build_plan(opts, product)
    if plan is None:
        return 2
    for i, t in enumerate(plan, 1):
        t["status"] = t.get("status") or "pending"

    contract = {"runVersion": RUN_VERSION, "goal": goal, "goalKeywords": kws,
                "product": product, "plan": plan, "guardrails": dict(GUARDRAILS),
                "taskListCreated": False,
                "createdAt": now(), "frozen": True}
    state = {"runVersion": RUN_VERSION,
             "current": None, "done": [], "next": plan[0]["id"] if plan else None,
             "counters": {"sameCall": 0, "stepsSinceMilestone": 0, "drifts": 0, "loops": 0},
             "blocked": None, "lastArgsHash": None, "lastTool": None, "updatedAt": now()}
    write_json(p["contract"], contract)
    write_json(p["state"], state)
    open(p["journal"], "a", encoding="utf-8").close()
    render_runlog(p, contract, state)

    print("已起 _run/：%s" % p["run"])
    print("目标  %s" % goal)
    print("产品  %s（doneWhen 里的 {产品} 已渲染成这个名字）" % product)
    print("关键词 %s" % "、".join(kws))
    print("规划  %d 步：%s" % (len(plan), " / ".join(
        "%s %s" % (t["id"], t["title"]) for t in plan)))
    files = sorted({dw_of(t)["file"] for t in plan if dw_of(t)["file"]})
    print("完成判定是产物驱动的：step --done 时 %s 必须真的存在"
          % ("、".join(files) if files else "对应产物"))
    print("下一步跑：python3 %s next --dir %s" % (os.path.abspath(__file__), d))
    return 0


def auto_keywords(goal):
    """把目标按标点切段，剔掉虚词/动词，剩下的连续汉字块当关键词。切不出来就返回空。"""
    stops = sorted(STOPWORDS, key=len, reverse=True)
    out = []
    for seg in re.split(r"[，,。、；;：:\s]+", goal):
        for s in stops:
            seg = seg.replace(s, "|")
        for chunk in seg.split("|"):
            chunk = chunk.strip()
            if len(chunk) >= 2 and chunk not in out:
                out.append(chunk)
    return out[:8]


def build_plan(opts, product):
    """--auto --stage N 生成，或 --plan file.json 指定。两者都不给就报错，不猜。

    {产品} 在这里渲染成真实文件名：常量表里不许留占位符，否则 --done 永远对不上文件。
    """
    def render(done):
        if not isinstance(done, dict):
            return done
        out = dict(done)
        if isinstance(out.get("file"), str):
            out["file"] = out["file"].replace("{产品}", product)
        return out

    if opts.get("--plan"):
        path = os.path.abspath(os.path.expanduser(str(opts["--plan"])))
        if not os.path.isfile(path):
            print("找不到 --plan 文件：%s" % path)
            return None
        data = read_json(path)
        if data is None:
            return None
        plan = data.get("plan") if isinstance(data, dict) else data
        if not isinstance(plan, list) or not plan:
            print("--plan 文件里没有 plan 数组（或为空）：%s" % path)
            return None
        bad = [t for t in plan if not (isinstance(t, dict) and t.get("id") and t.get("title"))]
        if bad:
            print("--plan 每条都要有 id / title / stage / doneWhen，缺字段：%s" % bad[:2])
            return None
        ids = [t["id"] for t in plan]
        if len(set(ids)) != len(ids):
            print("--plan 里 id 有重复：%s" % ids)
            return None
        legacy = [t["id"] for t in plan if not isinstance(t.get("doneWhen"), dict)]
        if legacy:
            print("[WARN] %s 的 doneWhen 是纯文本（1.0 格式），按兼容处理：只显示，不参与完成判定。"
                  % "、".join(legacy))
        return [{"id": t["id"], "stage": int(t.get("stage") or 1), "title": t["title"],
                 "doneWhen": render(t.get("doneWhen")) if isinstance(t.get("doneWhen"), dict)
                 else (t.get("doneWhen") or ""),
                 "status": t.get("status") or "pending"}
                for t in plan]
    if opts.get("--auto") or opts.get("--stage"):
        if not opts.get("--stage"):
            print("--auto 要配 --stage（1 / 2 / 3）")
            return None
        try:
            stage = int(opts["--stage"])
        except (TypeError, ValueError):
            print("--stage 只能是 1 / 2 / 3")
            return None
        if stage not in STAGE_TASKS:
            print("--stage 只能是 1 / 2 / 3")
            return None
        return [{"id": tid, "stage": stage, "title": title,
                 "doneWhen": render(done), "status": "pending"}
                for tid, title, done in STAGE_TASKS[stage]]
    print("要么 --auto --stage N 自动生成规划，要么 --plan <file.json> 指定；"
          "没有规划的 run 没法判遗漏。")
    return None


# ------------------------------------------------------------------ next（目标注入点）
def cmd_next(opts):
    booted, rc = boot(opts)
    if booted is None:
        return rc
    d, p, contract, state = booted
    print_injection(contract, state, jread(p), d, brief=bool(opts.get("--brief")))
    return 0


def print_injection(contract, state, rows, d=None, brief=False):
    """规格 §7。目标必须是原句，不许摘要。"""
    plan = contract.get("plan") or []
    done = [t["id"] for t in plan if t.get("status") == "done"]
    cur = state.get("next") or first_pending(contract)
    task = next((t for t in plan if t["id"] == cur), None)

    if brief:
        # 3 行紧凑块，给模型**贴进回复正文**用。
        # 对话任务列表（Task 工具）依赖宿主 UI，被 skill 调用时多半不显示；
        # 进度要让人看见，只能落在文字里。
        print("── %d/%d %s" % (len(done), len(plan), "─" * 30))
        print(progress_line(plan, done, cur, indent=""))
        if task:
            print("做 %s %s → %s ｜ 账本 %d 步"
                  % (task["id"], task["title"], dw_text(task), len(rows)))
        else:
            print("规划已走完，跑 close 收尾 ｜ 账本 %d 步" % len(rows))
        return

    print("── 本轮任务 ─────────────────────────────")
    print("目标  %s" % contract.get("goal"))
    print("进度  %s  （%d/%d）" % (progress_line(plan, done, cur), len(done), len(plan)))
    if task:
        print("下一步 %s %s：%s" % (task["id"], task["title"], dw_text(task)))
    else:
        print("下一步 规划已走完，跑一次 close 收尾")

    print("")
    print("约束  ① 只做 %s，其余任务等它 done 再说" % (cur or "当前任务"))
    print("      ② 新增动作必须能对上上面那句目标，对不上先 amend 再说")
    print("      ③ 同一动作连续 %d 次即判死循环（只认 (tool,argsHash)）"
          % (contract.get("guardrails") or GUARDRAILS).get("maxSameCall", 3))
    every = (contract.get("guardrails") or GUARDRAILS).get("milestoneEvery", 2)
    counters = state.get("counters") or {}
    if (counters.get("stepsSinceMilestone") or 0) >= every:
        print("      ④ 已经 %d 步没做里程碑自检了，先跑 milestone --gap \"还缺什么\""
              % counters["stepsSinceMilestone"])

    if rows:
        last = rows[-1]
        print("")
        print("上次  %02d %s" % (last.get("seq"), clip(last.get("intent") or "—", 40)))
        # 账本行：step 是唯一零产出的调用，模型会当开销裁掉。
        # 只有让"没记"变成它看得见的差（任务推进了而账本没动），它才会记。
        print("账本  本轮已记 %d 步，最后一步是 %s 的「%s」"
              % (len(rows), last.get("taskId") or "—",
                 clip(last.get("intent") or "—", 30)))
    else:
        print("")
        print("上次  —（还没记过步骤）")
        print("账本  本轮已记 0 步。plan 再推进，账本还是 0，就是没记。")
    print(sync_line(contract, plan, done, cur, d))


def sync_line(contract, plan, done, cur, d=None):
    """对话里的任务列表是 _run/ 的投影。

    单向：_run/ 是真相，模型照着这一行去写 Task 工具；不许反过来拿列表当进度。
    """
    if contract.get("taskListCreated") is False:
        return ("同步  任务列表：先建任务列表 —— 按 plan 建 %d 个（%s），建完跑 "
                "harness.py mark-tasks --dir %s"
                % (len(plan), "/".join(t["id"] for t in plan), d or "<产品目录>"))
    parts = []
    comp = [t["id"] for t in plan if t["id"] in done]
    if comp:
        parts.append("%s completed" % "/".join(comp))
    if cur:
        parts.append("%s 应为 in_progress" % cur)
    pend = [t["id"] for t in plan if t["id"] not in done and t["id"] != cur]
    if pend:
        parts.append("%s pending" % "/".join(pend))
    return "同步  任务列表：%s" % ("，".join(parts) or "全部 completed，可以去建 close 了")


def progress_line(plan, done, cur, indent="      "):
    tokens = []
    for t in plan:
        if t["id"] in done:
            tokens.append("%s ✓" % t["id"])
        elif t["id"] == cur:
            tokens.append("%s ← 现在" % t["id"])
        else:
            tokens.append(t["id"])
    lines, line = [], ""
    for tok in tokens:
        cand = tok if not line else line + "  " + tok
        if line and cw(cand) > 46:
            lines.append(line)
            line = tok
        else:
            line = cand
    lines.append(line)
    return ("\n" + indent).join(lines)


# ------------------------------------------------------------------ step
def cmd_step(opts):
    booted, rc = boot(opts)
    if booted is None:
        return rc
    d, p, contract, state = booted

    intent = (opts.get("--intent") or "").strip()
    tool = (opts.get("--tool") or "").strip()
    args = opts.get("--args") or ""
    out = (opts.get("--out") or "").strip()
    declared = (opts.get("--taskId") or "").strip() or None
    manual = (opts.get("--verdict") or "ok").strip() or "ok"
    want_done = bool(opts.get("--done"))
    if not intent:
        print("缺 --intent：这一步在干什么，人得看懂。空 intent 记不了账。")
        return 2
    if not tool:
        print("缺 --tool：循环只认 (tool, argsHash)，没有工具名就判不了。")
        return 2
    if manual not in ("ok", "fail"):
        print("--verdict 只能是 ok / fail（loop / drift / forget 由检测写，不许自己声明）")
        return 2

    plan = contract.get("plan") or []
    ids = [t["id"] for t in plan]
    fp = first_pending(contract)
    task_id = declared or state.get("next") or fp
    # 非法任务 id 先判：id 都不在 plan 里，后面的判定全是空转
    if declared and declared not in ids:
        print("[INVALID_TASK] --taskId %s 不在 plan 里。plan 只有：%s"
              % (declared, " / ".join(ids) or "（空）"))
        print("编一个不存在的任务 id 等于把账记到别人头上。先 amend 加任务，或改用 %s。" % (fp or "已有 id"))
        return 5

    # --done 先验产物再记账：验不过的步不属于"走过了"，不留半截账
    if want_done:
        ok, msg = check_done(d, contract, task_id, out)
        if not ok:
            print(msg)
            return 6

    ahash = args_hash(tool, args)
    hit = detect(contract, state, intent, tool, ahash)
    counters = state.setdefault("counters", {"sameCall": 0, "stepsSinceMilestone": 0,
                                             "drifts": 0, "loops": 0})
    rows = jread(p)

    counters["sameCall"] = hit["sameCall"]
    counters["stepsSinceMilestone"] = (counters.get("stepsSinceMilestone") or 0) + 1
    counters["drifts"] = 0 if hit["goalAligned"] else (counters.get("drifts") or 0) + 1
    forgotten = bool(declared) and bool(fp) and declared != fp

    event = None
    verdict = manual
    if hit["loop"]:
        verdict, event = "loop", "block"
        counters["loops"] = (counters.get("loops") or 0) + 1
        state["blocked"] = {"reason": "LOOP", "at": task_id,
                            "detail": "同一 (%s, %s) 连续 %d 次"
                                      % (tool, ahash, hit["sameCall"]),
                            "snapshot": "%s/%s" % (RUN, STATE)}
    elif counters["drifts"] >= 3:
        verdict = "drift"
    elif forgotten:
        verdict = "forget"
    elif not hit["goalAligned"]:
        verdict = "drift"

    state["lastTool"], state["lastArgsHash"] = tool, ahash
    prev = state.get("current") or {}
    state["current"] = {"taskId": task_id, "intent": intent,
                        "startedAt": prev.get("startedAt") if prev.get("taskId") == task_id
                        else now()}
    done_ok = want_done and not forgotten
    if done_ok:
        task = next(t for t in plan if t["id"] == task_id)
        task["status"] = "done"
        contract["plan"] = plan
        write_json(p["contract"], contract)
        state["done"] = [t["id"] for t in plan if t.get("status") == "done"]
        state["next"] = first_pending(contract)
    state["updatedAt"] = now()
    write_json(p["state"], state)

    rec = jappend(p, contract, state, {
        "taskId": task_id, "intent": intent, "tool": tool, "argsHash": ahash,
        "argsBrief": args_brief(args), "out": out or None, "verdict": verdict,
        "goalAligned": hit["goalAligned"], "event": event})

    print("[STEP %02d] %s · %s · %s" % (rec["seq"], task_id, tool, args_brief(args, 40)))
    print("         意图 %s" % intent)
    print("         结果 %s ｜ 判定 %s%s"
          % (out or "—", verdict, " ｜ 产物已验，任务记 done" if done_ok else ""))
    if want_done and not done_ok:
        print("         --done 未生效：%s 不是该做的任务（现在该做 %s）。跳步不算完成。"
              % (task_id, fp or "—"))

    every = (contract.get("guardrails") or GUARDRAILS).get("milestoneEvery", 2)
    if counters["stepsSinceMilestone"] >= every and verdict in ("ok", "drift", "fail"):
        print("         提醒 已连续 %d 步没做里程碑自检：milestone --dir %s --gap \"还缺什么\""
              % (counters["stepsSinceMilestone"], d))
    if lazy_intent(intent):
        print("[WARN] intent 写的是动作不是判断：「%s」。写\"从 M3 里看出什么\"，将来复盘靠它。"
              % intent)
    if verdict == "drift" and counters["drifts"] < 3:
        print("[WARN] 这句话跟目标不沾：「%s」。记进账了，放行——连续 3 次就判偏移。"
              % intent)

    if verdict == "loop":
        print("")
        print_blocked(state["blocked"])
        return 2
    if counters["drifts"] >= 3:
        print("")
        print("[DRIFT] 连续 %d 步对不上目标。最后一次：「%s」" % (counters["drifts"], intent))
        print("目标  %s" % contract.get("goal"))
        print("回 %s：%s" % (state.get("next") or "—", next_title(contract, state)))
        print("要么把动作拉回上面那句目标，要么走 amend 说明为什么要加这一步（amend 会校验对齐）。")
        return 3
    if verdict == "forget":
        print("")
        print("[FORGET] 声明的是 %s，但第一个没做完的是 %s。回正：" % (declared, fp))
        print_injection(contract, state, jread(p), d)
        return 4
    return 0


def check_done(d, contract, task_id, out):
    """--done 的产物校验：文件真的在，doneWhen.contains 每个串真的出现。

    中文没有词边界，contains 用子串匹配，只用来防呆，不当验收判据
    （验收仍是 check_analysis.py 那套）。
    """
    task = next((t for t in contract.get("plan") or [] if t["id"] == task_id), None)
    if task is None:
        return False, "[-done 拒绝] %s 不是 plan 里的任务" % task_id
    dw = dw_of(task)
    rel = out or dw["file"] or ""
    if not rel:
        return False, ("[-done 拒绝] %s 既没给 --out，doneWhen 里也没写文件名。"
                       "%s 的完成必须对应一个真的躺在 %s 下的文件。" % (task_id, task_id, d))
    if os.path.isabs(rel):
        rel = os.path.relpath(rel, d)
    if rel.startswith(".."):
        return False, "[-done 拒绝] 产物必须在 --dir 下，%s 跑到外面去了" % rel
    if dw["file"] and os.path.normpath(rel) != os.path.normpath(dw["file"]):
        return False, ("[-done 拒绝] doneWhen 要求的是 %s，你给的是 %s。"
                       "文件对不上就是没做完。" % (dw["file"], rel))
    path = os.path.join(d, rel)
    if not os.path.isfile(path):
        return False, ("[-done 拒绝] 找不到产物 %s。%s 记 done 的前提是这个文件真的存在。"
                       % (rel, task_id))
    if dw["legacy"]:
        return True, ""
    body = read(path)
    missing = [c for c in dw["contains"] if c not in body]
    if missing:
        return False, ("[-done 拒绝] %s 里少了 %s。%s 的验收是「%s」，缺一个都不算完成。"
                       % (rel, "、".join("「%s」" % m for m in missing), task_id, dw_text(task)))
    return True, ""


def next_title(contract, state):
    t = next((x for x in contract.get("plan") or []
              if x["id"] == state.get("next")), None)
    return ("%s：%s" % (t["title"], dw_text(t))) if t else "—"


# ------------------------------------------------------------------ check
def cmd_check(opts):
    booted, rc = boot(opts)
    if booted is None:
        return rc
    d, p, contract, state = booted
    rows = jread(p)
    intent = (opts.get("--intent") or "").strip()
    tool = (opts.get("--tool") or "").strip() or state.get("lastTool")
    args = opts.get("--args")
    ahash = args_hash(tool, args) if args is not None else state.get("lastArgsHash")
    declared = (opts.get("--taskId") or "").strip() or None

    if not intent:
        c = state.get("counters") or {}
        print("只读快照（没有 --intent 就不做检测，只报计数器）：")
        print("  sameCall=%s  stepsSinceMilestone=%s  drifts=%s  loops=%s"
              % (c.get("sameCall"), c.get("stepsSinceMilestone"),
                 c.get("drifts"), c.get("loops")))
        print("  上一步 %s / %s ｜ blocked %s"
              % (state.get("lastTool") or "—", state.get("lastArgsHash") or "—",
                 "有" if state.get("blocked") else "无"))
        print("要看下一步会不会被判，补 --intent \"...\" --tool X --args \"...\"")
        return 0

    ids = [t["id"] for t in contract.get("plan") or []]
    fp = first_pending(contract)
    if declared and declared not in ids:
        print("  任务  --taskId %s 不在 plan 里（%s）→ 命中，step 会 exit 5"
              % (declared, " / ".join(ids) or "空"))
        return 5

    hit = detect(contract, state, intent, tool, ahash)
    would = 0 if hit["goalAligned"] else (state.get("counters") or {}).get("drifts", 0) + 1
    forgotten = bool(declared) and bool(fp) and declared != fp
    print("检测（不记账）：%s" % intent)
    print("  循环  连续同 (tool,argsHash) %d 次 / 上限 %d → %s"
          % (hit["sameCall"], (contract.get("guardrails") or GUARDRAILS)["maxSameCall"],
             "命中" if hit["loop"] else "通过"))
    print("  对齐  命中关键词 %s ｜ 记完这一步后连续不对齐 %d 次 / 上限 3 → %s"
          % ("、".join(hit["kw"]) or "无", would, "命中" if would >= 3 else "通过"))
    print("  遗漏  第一个 pending 是 %s ｜ 声明 %s → %s"
          % (fp or "—", declared or "未声明", "命中" if forgotten else "通过"))
    if lazy_intent(intent):
        print("  提示  intent 太短且以动作词开头，step 会打 WARN")
    if hit["loop"]:
        return 2
    if would >= 3:
        print("  提示  已经连续 2 次不对齐，这一步会 exit 3")
        return 3
    if forgotten:
        print("  提示  跳过前面的任务不会 blocked，但会 exit 4 并重放注入块")
        return 4
    return 0


# ------------------------------------------------------------------ status
def cmd_status(opts):
    booted, rc = boot(opts)
    if booted is None:
        return rc
    d, p, contract, state = booted
    rows = jread(p)
    if opts.get("--md"):
        print_md(d, contract, state, rows)
    else:
        print_term(d, contract, state, rows)
    return 0


def stats(contract, state, rows):
    plan = contract.get("plan") or []
    done = [t["id"] for t in plan if t.get("status") == "done"]
    warns = [r for r in rows if r.get("verdict") not in ("ok", None)]
    return plan, done, warns


def print_term(d, contract, state, rows):
    plan, done, warns = stats(contract, state, rows)
    print("执行状态：%s" % d)
    print("目标  %s" % contract.get("goal"))
    print("进度  %d/%d ｜ 已用 %d 步 ｜ 告警 %d ｜ %s"
          % (len(done), len(plan), len(rows), len(warns),
             "已拦截 %s" % (state["blocked"] or {}).get("reason") if state.get("blocked") else "未拦截"))
    print("-" * 96)
    print(pad("任务", 6) + pad("标题", 16) + pad("状态", 10) + "验收")
    print("-" * 96)
    for t in plan:
        print(pad(t["id"], 6) + pad(t["title"], 16)
              + pad("done" if t.get("status") == "done" else t.get("status", "pending"), 10)
              + dw_text(t))
    print("-" * 96)
    if not rows:
        print("（还没有步骤）")
    else:
        print(pad("#", 4) + pad("任务", 6) + pad("意图", 34) + pad("工具", 9)
              + pad("结果", 22) + "判定")
        for r in rows[-15:]:
            print(pad(str(r.get("seq")), 4) + pad(r.get("taskId") or "—", 6)
                  + pad(clip(r.get("intent") or "—", 34), 34)
                  + pad(r.get("tool") or "—", 9)
                  + pad(clip(r.get("out") or "—", 22), 22)
                  + verdict_label(r))
        if len(rows) > 15:
            print("…只显示最近 15 步，全量看 log --tail")


def print_md(d, contract, state, rows):
    plan, done, warns = stats(contract, state, rows)
    print("## 执行记录 · %s" % os.path.basename(d.rstrip("/")))
    print("目标：%s ｜ 进度 %d/%d ｜ 已用 %d 步 ｜ 告警 %d"
          % (contract.get("goal"), len(done), len(plan), len(rows), len(warns)))
    print("")
    print("| # | 任务 | 意图 | 工具 | 结果 | 判定 |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        print("| %s | %s | %s | %s | %s | %s |"
              % (r.get("seq"), cell(r.get("taskId") or "—"), cell(r.get("intent")),
                 cell(r.get("tool") or "—"), cell(r.get("out") or "—"),
                 cell(verdict_label(r))))
    if not rows:
        print("| — | — | （还没有步骤） | — | — | — |")
    print("")
    print("任务：%s" % " ｜ ".join(
        "%s %s %s" % (t["id"], t["title"],
                      "✓" if t.get("status") == "done" else "（%s）" % t.get("status"))
        for t in plan))
    if state.get("blocked"):
        b = state["blocked"]
        print("")
        print("> **已拦截 %s @%s**：%s" % (b.get("reason"), b.get("at"), b.get("detail")))


# ------------------------------------------------------------------ amend
def cmd_amend(opts):
    booted, rc = boot(opts)
    if booted is None:
        return rc
    d, p, contract, state = booted
    add = (opts.get("--add") or "").strip()
    why = (opts.get("--why") or "").strip()
    if not add or not why:
        print("--add 与 --why 都要给：加什么、为什么加。只加不说理由，等于没把规则当回事。")
        return 2

    strong, reason, weak = aligned(contract, add, why)
    if not strong and not weak:
        print("[AMEND 拒绝] 「%s」对不上这一轮的目标，--why 里也找不到出处。" % add)
        print("目标  %s" % contract.get("goal"))
        print("理由  --why 写的是「%s」——这是「我觉得」，不是依据。" % why)
        print("要么把动作改回现有任务，要么把理由落到原话/纪要/确认单上再来一次。")
        return 3

    plan = contract.get("plan") or []
    try:
        stage = int(opts["--stage"]) if opts.get("--stage") else next(
            (t["stage"] for t in plan if t["id"] == state.get("next")),
            plan[-1]["stage"] if plan else 1)
    except (TypeError, ValueError):
        print("--stage 只能是 1 / 2 / 3")
        return 2
    if stage not in STAGE_PREFIX:
        print("--stage 只能是 1 / 2 / 3")
        return 2

    # 编号挂在段前缀下：ap2 / bp1 / cp3。前缀自己说明它挂在哪一段，也不会和 A1/B1 撞。
    prefix = STAGE_PREFIX[stage]
    nums = [int(m.group(1)) for m in
            (re.match(r"^%sp(\d+)$" % prefix, t["id"]) for t in plan) if m] or [0]
    new_id = "%sp%d" % (prefix, max(nums) + 1)
    done_file = (opts.get("--done-file") or "").strip() or None
    task = {"id": new_id, "stage": stage, "title": add,
            "doneWhen": {"file": done_file, "contains": []}, "status": "pending"}
    plan.append(task)
    contract["plan"] = plan
    write_json(p["contract"], contract)

    state["updatedAt"] = now()
    if not state.get("next"):
        state["next"] = new_id
    write_json(p["state"], state)
    jappend(p, contract, state, {
        "taskId": new_id, "intent": "新增步骤：%s" % add, "tool": "amend",
        "argsHash": args_hash("amend", add + "\x1f" + why),
        "argsBrief": args_brief("%s ｜ %s" % (add, why)), "out": why,
        "verdict": "ok" if strong else "drift", "goalAligned": strong, "event": "amend"})
    if weak:
        print("[WARN] --add 本身对不上目标，但 --why 追溯到了出处（%s），按 WARN 放行。" % weak)
    print("已加 %s（stage %d）：%s" % (new_id, stage, add))
    print("对齐依据 %s" % reason)
    print("完成判定 %s 存在才算 done（step --taskId %s --done --out <文件>）"
          % (done_file or "由 --out 指定的产物", new_id))
    print("plan 现有 %d 条：%s" % (len(plan), " / ".join(t["id"] for t in plan)))
    return 0


def aligned(contract, add, why):
    """对齐判定：只认字面重合，不做语义猜测。

    返回 (strong, reason, weak)：
      strong=True  → --add 或 --why 命中目标关键词/与规划和 goal 有 ≥2 字共同片段
      strong=False + weak→ --add 对不上，但 --why 能追溯到出处（原话/纪要/确认/M1…）
    两者都没有 → 拒绝。
    """
    for label, text in (("--add", add), ("--why", why)):
        kws = [k for k in (contract.get("goalKeywords") or []) if k and k in text]
        if kws:
            return True, "%s 命中目标关键词「%s」" % (label, kws[0]), None
    corpus = [contract.get("goal") or ""]
    for t in contract.get("plan") or []:
        corpus.append("%s %s" % (t.get("title") or "", dw_text(t)))
    for label, text in (("--add", add), ("--why", why)):
        mine = bigrams(text)
        for src in corpus:
            shared = mine & bigrams(src)
            if shared:
                word = sorted(shared, key=len, reverse=True)[0]
                return True, "%s 与规划共有「%s」" % (label, word), None
    # 字面都对不上时，只认「理由有没有出处」。这是人给理由的口子，不是模型自证的口子：
    # --why 必须点到原话/纪要/确认单/某份 M 文件，光写「觉得需要」不算。
    trace = [w for w in TRACE_WORDS if w in why]
    if trace:
        return False, "--add 对不上目标，--why 追溯到「%s」" % "、".join(trace[:2]), trace[0]
    return False, "", None


def bigrams(text):
    clean = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", text or "")
    return {clean[i:i + 2] for i in range(len(clean) - 1)}


# ------------------------------------------------------------------ milestone
def cmd_milestone(opts):
    booted, rc = boot(opts)
    if booted is None:
        return rc
    d, p, contract, state = booted
    gap = (opts.get("--gap") or "").strip()
    if not gap:
        print("[MILESTONE 拒绝] --gap 是空的。空着不算自检——「还缺什么」必须写出来。")
        print("目标  %s" % contract.get("goal"))
        return 3

    counters = state.setdefault("counters", {})
    counters["sameCall"] = 0
    counters["stepsSinceMilestone"] = 0
    counters["drifts"] = 0

    # 里程碑只读：清零计数 + 记 gap。任务完成不归它管——那由 step --done 的产物说了算。
    # 让自检顺手把任务标 done，等于给模型一份假账本（跑满 6 步就"规划已走完"，M3 一个字没写）。
    cur = state.get("next") or first_pending(contract)
    plan = contract.get("plan") or []
    task = next((t for t in plan if t["id"] == cur), None)
    state["updatedAt"] = now()
    write_json(p["state"], state)

    rec = jappend(p, contract, state, {
        "taskId": cur, "intent": "里程碑自检：%s" % gap, "tool": "milestone",
        "argsHash": args_hash("milestone", gap), "argsBrief": args_brief(gap),
        "out": gap, "verdict": "ok", "goalAligned": True, "event": "milestone"})
    print("[MILESTONE %02d] 计数已清零（任务状态没动）" % rec["seq"])
    print("还缺  %s" % gap)
    if task:
        print("当前 %s 仍是 %s：%s 才记 done"
              % (task["id"], task.get("status"), dw_text(task)))
    print("下一步 %s" % (state.get("next") or "规划已走完，跑 close 收尾"))
    return 0


# ------------------------------------------------------------------ mark-tasks
def cmd_mark_tasks(opts):
    """任务列表已按 plan 建好，D 里有这一笔之后 next 不再喊"先建"。

    只写标记 + 回报账本差。不读、不写对话里的任务列表——那份是投影，不是真相。
    """
    booted, rc = boot(opts)
    if booted is None:
        return rc
    d, p, contract, state = booted
    contract["taskListCreated"] = True
    write_json(p["contract"], contract)

    n_done = len([t for t in contract.get("plan") or [] if t.get("status") == "done"])
    print("已记：任务列表已建（taskListCreated=true），next 不再提示先建。")
    print("账本  _run/ 里已完成 %d 项" % n_done)
    raw = opts.get("--completed-count")
    if raw not in (None, ""):
        try:
            listed = int(raw)
        except (TypeError, ValueError):
            print("--completed-count 要一个整数")
            return 2
        if listed != n_done:
            print("[账本] %d 项已完，列表勾了 %d 项  ← 对不上，去补 TaskUpdate"
                  % (n_done, listed))
        else:
            print("      列表勾了 %d 项，对得上。" % listed)
    else:
        print("      没给 --completed-count，对不了账；建完/更新后带上它再跑一次。")
    # 不记 journal：建任务列表不是"走过的一步"，记进去会把账本步数吹大
    return 0


# ------------------------------------------------------------------ close
def cmd_close(opts):
    booted, rc = boot(opts, allow_blocked=True)
    if booted is None:
        return rc
    d, p, contract, state = booted
    rows = jread(p)
    result = (opts.get("--result") or "").strip()

    plan, done, warns = stats(contract, state, rows)
    print("── 复盘 ─────────────────────────────────")
    print("目标  %s" % contract.get("goal"))
    print("结果  %s" % (result or "（未填 --result）"))
    dist = {}
    for r in rows:
        dist[r.get("verdict") or "—"] = dist.get(r.get("verdict") or "—", 0) + 1
    print("步数  %d ｜ 任务 %d/%d ｜ 告警 %d ｜ 判定 %s"
          % (len(rows), len(done), len(plan), len(warns),
             " ".join("%s=%d" % (k, v) for k, v in sorted(dist.items())) or "无"))
    per = {}
    for r in rows:
        if r.get("event") in ("milestone", "amend"):
            continue
        per[r.get("taskId") or "—"] = per.get(r.get("taskId") or "—", 0) + 1
    print("轨迹  %s" % (" → ".join("%s %d 步" % (k, v) for k, v in per.items()) or "无"))
    warns_list = [r for r in warns][-5:]
    if warns_list:
        print("告警明细")
        for r in warns_list:
            print("      %02d %s 「%s」→ %s"
                  % (r.get("seq"), r.get("taskId"), clip(r.get("intent") or "", 24),
                     r.get("verdict")))
    if state.get("blocked"):
        b = state["blocked"]
        print("拦截  %s @%s：%s" % (b.get("reason"), b.get("at"), b.get("detail")))
        print("      未解封（close 不负责解封，人确认后跑 --force-unblock）")

    legacy = [t["id"] for t in plan if dw_of(t)["legacy"]]
    if legacy:
        print("兼容  %s 的 doneWhen 是 1.0 纯文本，未参与完成判定（只显示）。"
              % "、".join(legacy))
    print("")
    print("对账（产物真相以 _state.json 为准，这里只 WARN 不阻断）")
    reconcile(d, contract)

    state["updatedAt"] = now()
    write_json(p["state"], state)
    jappend(p, contract, state, {
        "taskId": state.get("next"), "intent": "收尾", "tool": "close",
        "argsHash": args_hash("close", result), "argsBrief": args_brief(result),
        "out": result or None, "verdict": "ok", "goalAligned": True, "event": "close"})
    return 0


def reconcile(d, contract):
    sp = os.path.join(d, "_state.json")
    plan = contract.get("plan") or []
    if not os.path.isfile(sp):
        print("      _state.json 不存在（这一轮还没产出真产物？）—— 跳过错账")
        return
    st = read_json(sp)
    if st is None:
        print("      _state.json 读不了 —— 跳过错账")
        return
    steps = st.get("steps") or []
    stages = sorted({t["stage"] for t in plan} | {s.get("stage") for s in steps
                                                 if s.get("stage")})
    bad = []
    for n in stages:
        pt = [t for t in plan if t["stage"] == n]
        sn = [s for s in steps if s.get("stage") == n]
        pd = len([t for t in pt if t.get("status") == "done"])
        sd = len([s for s in sn if s.get("status") == "done"])
        full_p = bool(pt) and pd == len(pt)
        full_s = bool(sn) and sd == len(sn)
        mark = "一致" if full_p == full_s else "WARN"
        print("      第 %d 段  plan %d/%d ｜ _state %d/%d ｜ %s"
              % (n, pd, len(pt), sd, len(sn), mark))
        if full_p != full_s:
            if full_p:
                bad.append("第 %d 段 plan 说完成，_state.json 还有 %d 步没 done"
                           % (n, len(sn) - sd))
            else:
                bad.append("第 %d 段 _state.json 说完成，plan 里还有 %d 条没 done"
                           % (n, len(pt) - pd))
    if bad:
        print("      [WARN] 差集：%s" % "；".join(bad))
        print("      [WARN] 不阻断。产物真相以 _state.json 为准，plan 只是过程记录。")
    else:
        print("      差集：无")


# ------------------------------------------------------------------ log / unblock
def cmd_log(opts):
    booted, rc = boot(opts)
    if booted is None:
        return rc
    d, p, contract, state = booted
    lines = [ln for ln in read(p["journal"]).splitlines() if ln.strip()]
    if opts.get("--tail"):
        try:
            n = int(opts["--tail"])
        except (TypeError, ValueError):
            print("--tail 要一个整数")
            return 2
        lines = lines[-n:] if n > 0 else []
    for ln in lines:
        print(ln)
    return 0


def unblock(opts):
    booted, rc = boot(opts, allow_blocked=True)
    if booted is None:
        return rc
    d, p, contract, state = booted
    b = state.get("blocked")
    if not b:
        print("当前没有 blocked，不用解封。")
        return 0
    state["blocked"] = None
    state.setdefault("counters", {})["sameCall"] = 0
    state["updatedAt"] = now()
    write_json(p["state"], state)
    jappend(p, contract, state, {
        "taskId": b.get("at"), "intent": "人为解封：%s" % b.get("reason"),
        "tool": "unblock", "argsHash": args_hash("unblock", json.dumps(b, ensure_ascii=False)),
        "argsBrief": args_brief(b.get("detail")), "out": "人工确认已处理",
        "verdict": "ok", "goalAligned": True, "event": None})
    print("已解封：%s @%s（%s）" % (b.get("reason"), b.get("at"), b.get("detail")))
    print("注意  解封是人做的事，不是脚本替你判断。RUNLOG 里留了这一笔。")
    return 0


# ------------------------------------------------------------------ main
DISPATCH = {"init": cmd_init, "next": cmd_next, "step": cmd_step, "check": cmd_check,
            "status": cmd_status, "amend": cmd_amend, "milestone": cmd_milestone,
            "close": cmd_close, "log": cmd_log, "mark-tasks": cmd_mark_tasks}


def main(argv):
    cmd, opts = parse(argv)
    if cmd is None:
        print(__doc__)
        return 0 if argv else 2
    if opts.get("--force-unblock"):
        rc = unblock(opts)
        if rc:
            return rc
    if cmd not in DISPATCH:
        print("不认识的子命令：%s（可用：%s）" % (cmd, " / ".join(DISPATCH)))
        print(__doc__)
        return 2
    return DISPATCH[cmd](opts)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
