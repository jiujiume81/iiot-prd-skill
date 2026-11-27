# 02 需求分析

```bash
SUITE=/Users/yuxiufu/WorkBuddy/原型PRD/iiot-prd-suite
python3 $SUITE/shared/bin/check_analysis.py analysis/<产品>/ --stage 2
python3 $SUITE/shared/bin/check_contract.py --half req analysis/<产品>/<产品>.proto.json
```

**出口**：`M4-flows.md`、`M5-exceptions.md`、`M6-review.md` + `{产品}.proto.json` 的**需求半边**（`pages` 只给骨架）+ `slices.json`。

**上游**：`iiot-business-analysis`（01）。入口条件是 `stages["1"].status = done`，不 done 不接活。
**下游**：`iiot-prototype`（03）。交接口令：`stages["2"].status = done` 且 `--half req` 绿。

出口前再跑一次 `--stage all`，跨阶段 6 条判据不漏。
