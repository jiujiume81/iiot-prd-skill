# shared/retired — 已退役，不删

| 文件 | 原用途 | 为什么退役 | 谁接管 |
|---|---|---|---|
| `check_gate.py` | 七步澄清闸门（`G-01`~`G-24`），验 `01-positioning.md`…`07-review.md` + `_gate.json` 的 `A1/A2/A3` | 与 `check_analysis.py` 大面积重复且阈值不同（异常 11 类 vs 12 类、四角色小节名不同、"非目标 ≥3"两边各判一遍）。两套判据管同一件事，必然一边绿一边红：实测拿 mfg 样例喂它 `ERROR=11`，拿它的样例喂 `check_analysis` `ERROR=9` | `check_analysis.py`（A 系 46 条）。**唯一例外**：`G-10`（proto 写入时间早于确认时间 = 事后补签）无等价判据，已移植为 `check_analysis.py --stage 2` 的 `A-66` |
| `migrate_fields.py` | 一次性迁移工具，把旧契约的 `fieldRegistry` 改成 `fieldCatalog` | 新套件里不存在 `fieldRegistry` 写法（`check_contract` 的 `L2-97` 见到就报硬错） | 无。历史交付目录里的旧契约要用时，单独 `python3 shared/retired/migrate_fields.py --proto <旧契约>` |

保留而不是删除的理由：历史交付目录（如 `QMS-事故报告-正式交付/`）里存着旧格式契约与脚本快照，将来要对照或救数据时，这两份是唯一参照。
