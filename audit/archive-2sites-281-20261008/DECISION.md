# 封存同源镜像「风神九肖」「炉火纯青」· 2026-10-08

## 1. 用户指令与封存依据
- User：「风神九肖 炉火纯青 封存」。
- 依据：本轮缓存近 10 期（272..281）「完全一致目录组」汇报结果 —— **嫦娥奔月 <=> 风神九肖**、**朴斲之材 <=> 炉火纯青**（逐期记录全等，同源镜像）。用户点名封存每组中的第二站，保留 嫦娥奔月 / 朴斲之材。
- 依据 `AGENTS.md:71-75` 与项目 `AGENTS.md`「封存与恢复」：只处理点名站点 —— 移出活跃配置、写入封存配置（原始条目深拷贝 + reason）、移除该站精确缓存身份；不抓取、不写成功报告。

## 2. 落盘结果（脚本 `audit/archive-2sites-281-20261008/run_archive.py`）
| 对象 | 变化 |
|---|---|
| `config/sources.json` | 438 → **436**（移出 风神九肖 idx 80、炉火纯青 idx 431；其余按原序逐字段未变） |
| `config/archived_sources.json` | 69 → **71**（追加两条原始深拷贝 + `archived_at=2026-10-08T22:19:59+08:00` + reason） |
| `cache/recent_10_cache.json` | 438 → **436**（按身份键 `ec2858821c3f…` / `d4a5126d0021…` 移除；窗口 281..272 与 `latest_issue=281` 未动） |
| `七类数据统一归纳失败\281期-生肖-失败.txt` | **内容未变**（仍 1 条 炳炳凿凿；两站本不在清单） |
| `七类数据统一归纳\281期-生肖.txt` | **未触碰**（封存不写成功报告；其中仍保留这两站 281 期的历史成功行，见 §4） |
| `tests\test_fixed_catalog.py` | 目录断言 438 → **436** 并补注释 |
| `tests\test_routine_cleanup.py` | 退役登记 `expected` 增补这两站 URL |
| `tests\test_formula_article_adaptive.py` | `test_formal_config_selects_strict_ocr_alias_parser_for_target` 改为在**封存配置**上校验 `formula_article_ocr_alias` 绑定契约（并断言活跃中已无该站） |

- reason 全文存 `removed_entries.json`：`用户明确封存，不再抓取；与活跃站「嫦娥奔月」/「朴斲之材」在缓存窗口 272..281 期逐期记录完全一致（同源镜像），按用户点名保留其一并封存本站（2026-10-08 用户点名封存）`。
- 改动前基线（`*.before`）：活跃 438 / 封存 69 / 缓存 438；`sources.json` sha256 `74c520c2…`、`archived_sources.json` `088eb86a…`、`recent_10_cache.json` `13f09fc5…`。

## 3. 顺带修复的外部副作用
- 归档前发现 `281期-生肖-失败.txt` 已被工作区外部流程删除（失败目录为空）；已用审计快照 `audit\onboard-zuozeixinxu-281\281期-生肖-失败.txt.before`（175 B / sha `416b339f…`）恢复，内容仍为 1 条 炳炳凿凿。封存脚本据此以「文件存在则清理目标站记录、不存在则不新建」处理，本次未清除任何条目。

## 4. 成功报告残留（按规则未清理，需用户授权才能动）
- 281 报告当前含 457 个内容行：`活跃 436 - 失败 1 + 报告内已封存残留 2 + 外部 OCR 归纳追加 20`。
- 其中两行为本次封存站的历史成功行（`:81 鸡猴羊马蛇龙兔虎牛 风神九肖`、`:430 狗猪蛇龙鼠虎马牛羊 炉火纯青`）。按「封存不写成功报告」保持原样；若需从 281 报告中删除这两行（属覆盖输出），需用户明确授权后再做。

## 5. 验收与提交
- `audit/archive-2sites-281-20261008/verify_archive.py`（对照 `*.before`、只读）：**PASS 30 / FAIL 0**（活跃 438→436 且其余逐条/顶层不变、移除条目唯一且 URL 一致、封存 69→71 且原 69 条逐字段未变、新条目深拷贝+三字段+reason+时间戳合规、封存无重名且与活跃无交集、缓存 438→436 且其余逐条未变、窗口/latest 未动、失败清单仍仅 炳炳凿凿 且未含这两站、报告仍含这两站历史行且行数 >= 活跃-失败+2、两处计数与退役测试已更新）。
- pytest：**209 passed / 7 failed**（首跑出现 1 例新增失败 `test_formula_article_adaptive.py::test_formal_config_selects_strict_ocr_alias_parser_for_target`，因该站是 `formula_article_ocr_alias` 的唯一活跃绑定者；已按封存语义改到封存配置上校验，恢复为既有 7 例）。
- 封存后复查完全一致组：**0 组**（两对镜像已各自只留一站），齐窗口 424 / 436。
- 提交 `ed08f8e`「chore: archive mirror sources fengshenjiuxiao and luhuochunqing」（5 files / 57+ / 37-），已推送 `origin/main`（e69a12b..ed08f8e）；`cache\recent_10_cache.json` 与 `parsers\registry.py` 依 `AGENTS.md:99-100` 不提交。
