# 田乘风破 封存 · 2026-10-10（283 期）· 提交 94efb56

## 1. 用户指令与依据
- User：「田乘风破 封存」→ 依据 `AGENTS.md`「封存与恢复」段与项目规则：只处理点名站点 —— 移出活跃配置、写入封存配置（原始条目深拷贝 + reason）、移除精确缓存身份、从当期失败报告只删该站记录并保留其他记录及顺序；不抓取、不写成功报告。
- 封存依据（283 期实测）：`browser_dom` 仅 **45 字符** 前端壳页（`搜 索 / 登 陆 / 注 册 / Failed to fetch / 首页 / 规则 / 充值 / 客服`），`script:18` 为后台管理脚本，页内 `田乘风破`/`283`/`九肖` 命中**全为 0**；该站配置 `fetcher=dynamic_article`、`api_url=/api/proxy/manager-articles/6a3146cf32c7c4bb3c056f95`，直连返回 **HTTP 404 `{"message":"AdminArticle 不存在","error":"Not Found","statusCode":404}`** ⇒ 站方已删除该文章（无数据），不会自愈。

## 2. 落盘结果（脚本 `audit/archive-tianchengfengpo-283/run_archive.py`）
| 对象 | 变化 |
|---|---|
| `config/sources.json` | 438 → **437**（移除该条目；其余按原序逐字段未变） |
| `config/archived_sources.json` | 72 → **73**（原始条目深拷贝 + `archived_at=2026-10-10T18:44:18+08:00` + reason） |
| `cache/recent_10_cache.json` | 438 → **437**（按身份键 `d73ec1fba151…` 移除；窗口 283..274 与 `latest_issue=283` 未动） |
| `..\七类数据统一归纳失败\283期-生肖-失败.txt` | 745 B / 3 条 → **2 条**（仅剩 否极泰来 + 依然公主九肖，原文逐字、顺序不变） |
| `..\七类数据统一归纳\283期-生肖.txt` | **未触碰**（该站为失败站，本无 283 成功行） |

改动前基线（`*.before`）：`sources.json` sha `925b62f3…`、`archived_sources.json` `1fae54ef…`、`recent_10_cache.json` `7aafdbe9…`、283 失败TXT `0c5eec51…`（745 B）。

## 3. 测试同步与验收
- `tests/test_fixed_catalog.py`：目录断言 438 → **437** 并补注释（2026-10-10 封存 田乘风破）。
- `tests/test_routine_cleanup.py`：退役登记 `expected` 增补 `"田乘风破": "https://hcsuuoy…/6a3146cf32c7c4bb3c056f95?url=cww"`。
- `audit/archive-tianchengfengpo-283/verify_archive.py`（对照 `*.before`、只读）：**PASS 33 / FAIL 0** —— 活跃 438→437 且其余逐条/顶层未变、移除条目唯一且 URL 一致、封存 72→73 且原 72 条逐字段未变、新条目深拷贝+三字段+reason+时间戳合规、封存无重名且与活跃无交集、缓存 438→437 且其余逐条未变、窗口/latest 未变、身份键唯一 437、失败TXT 恰为「原文 − 该站」且剩余两站顺序保留、单尾换行、报告未含该站且报告+失败=活跃、两处测试已更新。
- pytest：**215 passed / 7 failed**（既有 7 例基线）。
- 提交 `94efb56`「chore: archive tianchengfengpo source per user request」（4 files / 26+ / 16-），已推送 `origin/main`（126baa5..94efb56）；`cache\recent_10_cache.json` 与 `parsers\registry.py` 依 `AGENTS.md` 不提交。

## 4. 备注
- 封存后 283 失败清单剩 **否极泰来**（站方 TLS 证书过期，`SEC_E_CERT_EXPIRED`）与 **依然公主九肖**（283 尚未发布，`ISSUE_MISSING`），二者均待站方侧变化后原样复跑。
