# 01 业务分析（默认入口）

```bash
SUITE=/Users/yuxiufu/WorkBuddy/原型PRD/iiot-prd-suite
python3 $SUITE/shared/bin/check_analysis.py analysis/<产品>/ --stage 1
```

**出口**：`M1-problem.md`、`M2-roles.md`、`M3-scenarios.md` + `_state.json` 的 `stages["1"]`（含 `export.p0` / `export.roles`）。M3 是硬闸门，必须用户本人签署（`by` / `at` / `quote` / `contentHash` 四样齐）。

**上游**：无。用户的原话、纪要、旧系统截图。
**下游**：`iiot-req-analysis`（02 需求分析）。交接口令：`stages["1"].status = done`。

起骨架：`--init analysis/<产品>/ --product "<产品名>" --stage 1`
