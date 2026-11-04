# 宝刀不老 封存 · 2026-10-06（279 期）

## 1. 用户指令
User：「宝刀不老 封存」→ 依据 `AGENTS.md:71-75` 执行站点封存（只处理点名站点：移出活跃配置、写入封存配置、移除该站精确缓存身份、失败报告只删该站记录并保留其他记录及顺序；不抓取、不写成功报告）。

## 2. 封存依据（279 期实测）
- 失败清单条目：`失败 宝刀不老 https://www.jinjintianniulaihenhaokan.xyz/read.php?tid=6030 方向: bottom 期数: 279 阶段: 栏目锚点校验 原因: 未找到目录关键字`。
- 真实抓取 `audit/probe-279/宝刀不老.browser-dom.txt` 仅 **189 B**：七星高手论坛模板登录墙「提示信息 / 您没有登录或者您没有权限访问此页面…链接无效,可能链接不完整,或数据已被删除! / 您还不是论坛会员,请先登录论坛」；全页 `宝刀不老`/`279`/`278`/`九肖` 命中均为 **0**，无任何九肖/期号原文。
- 裁定：**站方侧**（帖子对游客不可见，需登录），非我方解析缺陷，符合用户点名封存条件。

## 3. 落盘结果（脚本 `audit/archive-baodaobulao-279/run_archive.py`）
| 对象 | 变化 |
|---|---|
| `config/sources.json` | 438 → **437**（移除 idx 372 条目，其余 437 条顺序与字段逐条未变） |
| `config/archived_sources.json` | 67 → **68**（追加原始条目深拷贝 + `archived_at=2026-10-06T19:11:24+08:00` + reason） |
| `cache/recent_10_cache.json` | 438 → **437**（按身份键 `abecc01f5732…` 移除该条目；`issues`、`latest_issue=279` 与其余条目未动） |
| `..\七类数据统一归纳失败\279期-生肖-失败.txt` | 371 B / 2 条 → **1 条**（仅剩 揭阳小李） |
| `..\七类数据统一归纳\279期-生肖.txt` | **未触碰**（436 行 / sha256 `71aca378…`） |

封存 reason（全文存 `removed_entries.json`）：`用户明确封存，不再抓取；279期抓取失败：站方侧拒绝访客，需登录（browser_dom 正文仅 189 字符，为七星高手论坛「您没有登录或者您没有权限访问此页面…链接无效,可能链接不完整,或数据已被删除!…您还不是论坛会员,请先登录论坛」登录墙，两次新鲜抓取页面「宝刀不老」「279」「278」「九肖」命中均为 0，无任何九肖/期号原文）`

四文件封存后 sha256：sources.json `f35aa339d10ad41d63ae2f9af8edea11451911c4e298b463190278fe467e589f`、archived_sources.json `311d038027558c44a6b1f7e5061d615abb04a5d16a2330ceea895f86a62c84af`、recent_10_cache.json `6bbb5f65d262de2e60f66140aa268f5baf0cabfaac852c88d66e8c7d8cb5b8dc`、失败TXT `759714bf0aa2a0e296739131370c505d4f46e38d8e920f317e073101b91ee601`。

改动前基线（`*.before` 同步留存于本目录）：活跃 438 / 封存 67 / 缓存 438；sources.json `d18b5782…`、archived_sources.json `ce82455f…`、recent_10_cache.json `0b5f7846…`、失败TXT `c450cfcb…`（371 B）。

## 4. 测试同步
- `tests/test_fixed_catalog.py:66-70`：目录断言 438 → **437**，注释补「2026-10-06 封存「宝刀不老」（279 期站方侧登录墙，游客不可见）」。
- `tests/test_routine_cleanup.py::test_retired_sources_are_archived_and_absent_from_cache` 的 `expected` 增补 `"宝刀不老": "https://www.jinjintianniulaihenhaokan.xyz/read.php?tid=6030"`。

## 5. 独立复验
`audit/archive-baodaobulao-279/verify_archive.py`（对照 `*.before`、只读）：**PASS 29 / FAIL 0**（备份齐全含失败TXT 备份、活跃去一且其余逐条/顶层不变、封存原 67 条逐字段未变、新条目深拷贝+三字段+reason 前缀+时间戳合规、封存无重名且与活跃无交集、缓存按身份键去一且其余逐条未变、窗口/latest 未动、失败TXT 结构与内容、成功报告 sha 未变、两处测试已更新）。
