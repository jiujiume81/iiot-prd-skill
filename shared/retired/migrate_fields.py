#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把旧契约草迁到「字段主档 + 渲染位」形状。

这是**草稿工具**，不是"一键过判据"：
- 只填 key / label / 一个占位 source.ds；`rules` / `display` / `target` 一律不编，留给人工；
- 不猜业务语义：标签取该渲染位自己的界面文案，不从 `columns[].title` 反推来源；
- 迁不动的（DescList 缺 key、旧登记找不到同名渲染位）逐条列出，不静默跳过；
- 默认只读；`--apply` 才落盘，且第二遍必须 0 改动（幂等）。

用法：
    python3 scripts/migrate_fields.py --proto <proto>              # dry-run，摘要到 stderr，契约到 stdout
    python3 scripts/migrate_fields.py --proto <proto> --out <p>    # dry-run + 写草稿到 p
    python3 scripts/migrate_fields.py --proto <proto> --apply --out <p>
"""
import argparse
import json
import os
import sys

import field_sites

PLACEHOLDER_DS = "TODO"


def walk(n, out):
    out.append(n)
    for c in n.get("children") or []:
        walk(c, out)
    return out


def draft(proto):
    """返回 (新契约, 报告)。不改入参。"""
    d = json.loads(json.dumps(proto))          # 深拷贝，保证 dry-run 不碰原件
    sites = field_sites.render_sites(proto)
    old_reg = d.pop("fieldRegistry", None)
    had_catalog = "fieldCatalog" in d
    cat = d.setdefault("fieldCatalog", [])
    existing = {f.get("key") for f in cat}

    report = {
        "sites": len(sites),
        "added": [],
        "skipped_existing": 0,
        "unmovable": [],          # 逐条：为什么迁不动
        "no_key": [],
        "reg_unmatched": [],
        "need_rules": [],
        "need_display": [],
        "need_target": [],
        "placeholder_source": [],
    }

    # 1. 旧登记先做匹配：只搬 label，不反推来源
    reg_by_label = {}
    for r in (old_reg or []):
        reg_by_label.setdefault(r.get("name"), []).append(r)

    def add_entry(biz, label, site=None):
        if not biz or biz in existing:
            report["skipped_existing"] += 1
            return
        item = {"key": biz, "label": label or biz, "source": {"ds": PLACEHOLDER_DS}}
        cat.append(item)
        existing.add(biz)
        report["added"].append(biz)
        report["placeholder_source"].append(biz)
        if site and site["scope"] == "in":
            report["need_target"].append(biz)
        if site and site["scope"] == "filter-field":
            pass

    for s in sites:
        if s["missing_key"]:
            report["no_key"].append("%s / %s（DescList 项「%s」没有 key）"
                                    % (s["page_id"], s["site_id"], s["label"]))
            continue
        if s["scope"] == "filter-cond":
            continue          # 条件筛选不是字段（关键词/日期区间/是否超期），不给它编主档
        add_entry(s["biz"], s["label"], s)

    # 2. 旧登记里没能对上渲染位的，逐条列出来（不硬塞进主档）
    site_labels = {s["label"] for s in sites}
    for name, items in reg_by_label.items():
        if name not in site_labels:
            report["reg_unmatched"].append("%s（%d 条，pageId=%s）"
                                           % (name, len(items), items[0].get("pageId")))

    # 3. 待人工：rules / display / target
    by_key = {f.get("key"): f for f in cat}
    for s in sites:
        if s["missing_key"]:
            continue
        if s["scope"] == "in" and not ((s["raw"].get("rules") or {}).get("text")):
            report["need_rules"].append("%s/%s" % (s["page_id"], s["key"]))
        if s["scope"] == "out" and not ((s["raw"].get("display") or {}).get("empty")):
            report["need_display"].append("%s/%s" % (s["page_id"], s["key"]))
        if s["scope"] == "in":
            f = by_key.get(s["biz"])
            if f is not None and not f.get("target"):
                report["need_target"].append(s["biz"])
    report["need_target"] = sorted(set(report["need_target"]))
    report["unmovable"] = report["no_key"] + report["reg_unmatched"]

    # 4. 只保留真正的变化：空 fieldCatalog 且无旧登记时，不加空数组
    if not cat and not had_catalog:
        d.pop("fieldCatalog", None)
    changed = (json.dumps(d, ensure_ascii=False, sort_keys=True)
               != json.dumps(proto, ensure_ascii=False, sort_keys=True))
    return d, report, changed


def summary(rep, changed, applied):
    n = len(rep["added"])
    print("-" * 66, file=sys.stderr)
    print("渲染位 %d 个；生成主档 %d 条；已存在跳过 %d 条" %
          (rep["sites"], n, rep["skipped_existing"]), file=sys.stderr)
    print("迁不动 %d 条：" % len(rep["unmovable"]), file=sys.stderr)
    for x in rep["unmovable"][:12]:
        print("  - " + x, file=sys.stderr)
    if len(rep["unmovable"]) > 12:
        print("  …（共 %d 条）" % len(rep["unmovable"]), file=sys.stderr)
    print("待人工补：rules %d 处 / display.empty %d 处 / target %d 个字段" %
          (len(rep["need_rules"]), len(rep["need_display"]), len(rep["need_target"])), file=sys.stderr)
    print("source.ds 占位（%s）%d 条：脚本不猜取数口，必须人工补" %
          (PLACEHOLDER_DS, len(rep["placeholder_source"])), file=sys.stderr)
    if changed:
        print("本次有改动%s" % ("，已落盘" if applied else "（dry-run，未落盘）"), file=sys.stderr)
    else:
        print("本次无改动（幂等：第二遍 0 变化）", file=sys.stderr)
    print("-" * 66, file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--proto", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--apply", action="store_true", help="真写；默认只读")
    ap.add_argument("--report", default=None, help="额外写一份 migrate-report.md")
    args = ap.parse_args()

    proto = json.load(open(args.proto, encoding="utf-8"))
    out, rep, changed = draft(proto)
    summary(rep, changed, args.apply and changed)

    if args.apply and changed:
        path = args.out or args.proto
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print("written: " + path, file=sys.stderr)
    elif not args.apply:
        # dry-run 不指定 --out 时，把草稿打到 stdout，便于 diff
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
                f.write("\n")
        else:
            json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")

    if args.report:
        lines = ["# 字段迁移报告", "", "契约：`%s`" % os.path.basename(args.proto), "",
                 "| 项 | 数 |", "|---|---|",
                 "| 渲染位 | %d |" % rep["sites"],
                 "| 生成主档 | %d |" % len(rep["added"]),
                 "| 已存在跳过 | %d |" % rep["skipped_existing"],
                 "| 迁不动 | %d |" % len(rep["unmovable"]),
                 "| 待补 rules | %d |" % len(rep["need_rules"]),
                 "| 待补 display.empty | %d |" % len(rep["need_display"]),
                 "| 待补 target | %d |" % len(rep["need_target"]), "",
                 "## 迁不动（必须人工处理）", ""]
        lines += ["- " + x for x in rep["unmovable"]] or ["- （无）"]
        lines += ["", "## source.ds 占位（必须人工补）", ""]
        lines += ["- " + x for x in rep["placeholder_source"]] or ["- （无）"]
        open(args.report, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        print("report: " + args.report, file=sys.stderr)

    return 0 if not rep["unmovable"] else 1


if __name__ == "__main__":
    sys.exit(main())
